"""Rebuild the derived index with the configured vector size; never alter files.

Stop API/workers before running. Existing vectors are discarded transactionally
and all notes are queued for regeneration. Same-size reruns are a no-op.
"""

import asyncio

from sqlalchemy import select, text
from sqlalchemy.orm import noload

from app.core.config import get_settings
from app.domain.models import Note
from app.infrastructure.database.session import async_session_maker, close_db
from app.infrastructure.database.vector_schema import embedding_column_type
from app.infrastructure.rag.index import enqueue_note


async def migrate() -> int:
    dimensions = get_settings().embedding_dimensions
    async with async_session_maker() as session:
        async with session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('intellinotes-schema-init'))")
            )
            current = await embedding_column_type(session)
            if current is None or current == f"vector({dimensions})":
                return 0
            await session.execute(
                text("LOCK TABLE notes, note_sections, note_index_jobs IN ACCESS EXCLUSIVE MODE")
            )
            # No casts/truncation: embeddings from different models are incompatible.
            await session.execute(text("DELETE FROM note_sections"))
            await session.execute(
                text(f"ALTER TABLE note_sections ALTER COLUMN embedding TYPE vector({dimensions})")
            )
            notes = (await session.scalars(select(Note).options(noload("*")))).all()
            for note in notes:
                await enqueue_note(session, note)
            return len(notes)


async def main():
    try:
        count = await migrate()
        print(
            f"Vector schema ready ({get_settings().embedding_dimensions} dimensions); queued {count} notes."
        )
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
