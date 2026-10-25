"""Materialize legacy folders in storage, then remove the redundant DB hierarchy.

Stop API/workers and back up database and storage before running this command.
Run migrate_file_storage first if the legacy notes.content column still exists.
"""

import asyncio

from sqlalchemy import select, text

from app.application.note_content import load_note_content
from app.core.paths import validate_folder_path
from app.domain.models import Note
from app.infrastructure.database.session import async_session_maker, close_db
from app.infrastructure.rag.index import enqueue_note
from app.infrastructure.storage.factory import get_storage


async def migrate() -> int:
    storage = get_storage()
    async with async_session_maker() as session:
        async with session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('intellinotes-schema-init'))")
            )
            if not await session.scalar(text("SELECT to_regclass('folders')")):
                return 0
            if await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = 'notes' "
                    "AND column_name = 'content')"
                )
            ):
                raise RuntimeError("Run migrate_file_storage before migrate_storage_folders")
            await session.execute(
                text(
                    "LOCK TABLE folders, notes, note_sections, note_index_jobs IN ACCESS EXCLUSIVE MODE"
                )
            )
            rows = (
                (await session.execute(text("SELECT user_id, path FROM folders"))).mappings().all()
            )
            notes = (await session.scalars(select(Note))).all()
            for note in notes:
                validate_folder_path(note.folder_path)
                expected = f"{note.user_id}{note.folder_path.rstrip('/')}/{note.title}.md"
                if note.storage_key != expected:
                    raise RuntimeError(
                        f"Note {note.id} has inconsistent file metadata; reconcile first"
                    )
                await load_note_content(note, storage)
            keys = []
            for row in rows:
                path = validate_folder_path(row["path"])
                if path != "/":
                    keys.append(f"{row['user_id']}{path}")
            # Additive/idempotent: a failed migration may leave empty directories,
            # but never removes a user's file or overwrites its contents.
            for key in keys:
                await storage.create_folder(key)
            await session.execute(text("ALTER TABLE notes DROP COLUMN IF EXISTS folder_id"))
            await session.execute(text("DROP TABLE folders"))
            await session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_notes_user_path ON notes (user_id, folder_path)"
                )
            )
            # Removing folder IDs changes version fingerprints; invalidate old vectors.
            for note in notes:
                await enqueue_note(session, note)
            return len(rows)


async def main():
    try:
        count = await migrate()
        print(f"Folder migration complete; preserved {count} storage directories.")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
