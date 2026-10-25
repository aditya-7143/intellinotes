"""Explicit, transactional migration. Stop API/workers and back up the DB first."""

import asyncio

from sqlalchemy import select, text

from app.application.note_content import load_note_content
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
            legacy = await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = 'notes' "
                    "AND column_name = 'content')"
                )
            )
            if not legacy:
                return 0
            await session.execute(
                text("LOCK TABLE notes, note_sections, note_index_jobs IN ACCESS EXCLUSIVE MODE")
            )
            rows = (
                (await session.execute(text("SELECT id, user_id, storage_key, content FROM notes")))
                .mappings()
                .all()
            )
            # Never discard the database copy until every existing file is verified.
            for row in rows:
                note = Note(user_id=row["user_id"], storage_key=row["storage_key"])
                await load_note_content(note, storage)
                if note.content != row["content"]:
                    raise RuntimeError(
                        f"Note {row['id']} differs from its file. Reconcile before migration."
                    )
            await session.execute(text("DELETE FROM note_sections"))
            await session.execute(text("ALTER TABLE note_sections DROP COLUMN content"))
            await session.execute(
                text(
                    "ALTER TABLE note_sections ADD COLUMN start_offset INTEGER NOT NULL, "
                    "ADD COLUMN end_offset INTEGER NOT NULL"
                )
            )
            await session.execute(text("ALTER TABLE notes DROP COLUMN content"))
            notes = (await session.scalars(select(Note))).all()
            for note in notes:
                await enqueue_note(session, note)
            return len(notes)


async def main():
    try:
        count = await migrate()
        print(f"File storage migration complete; queued {count} notes for indexing.")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
