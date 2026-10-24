from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Note, NoteIndexJob, NoteSection


async def enqueue_note(session: AsyncSession, note: Note) -> None:
    """The job and invalidation commit atomically with the note write."""
    await session.execute(delete(NoteSection).where(NoteSection.note_id == note.id))
    values = {
        "note_id": note.id,
        "user_id": note.user_id,
        "generation": uuid4(),
        "status": "pending",
        "attempts": 0,
        "available_at": datetime.now(timezone.utc),
        "lease_until": None,
        "last_error": None,
    }
    await session.execute(
        insert(NoteIndexJob)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[NoteIndexJob.note_id],
            set_={key: value for key, value in values.items() if key != "note_id"},
        )
    )
