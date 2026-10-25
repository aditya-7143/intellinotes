"""Detect external changes to registered files without storing their text."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import noload

from app.application.note_content import load_note_content
from app.core.exceptions import ConflictError, ValidationError
from app.domain.models import Note, NoteIndexJob, NoteSection
from app.infrastructure.rag.index import enqueue_note

logger = logging.getLogger("intellinotes.rag.reconcile")


async def reconcile_files(sessions, storage, model_key: str) -> int:
    queued = 0
    async with sessions() as session:
        async with session.begin():
            notes = (
                await session.scalars(
                    select(Note).options(noload("*")).order_by(Note.id).with_for_update()
                )
            ).all()
            for note in notes:
                if await session.scalar(
                    select(NoteIndexJob.note_id).where(NoteIndexJob.note_id == note.id)
                ):
                    continue
                indexed_version = await session.scalar(
                    select(NoteSection.source_version)
                    .where(
                        NoteSection.note_id == note.id,
                        NoteSection.embedding_model == model_key,
                    )
                    .limit(1)
                )
                try:
                    await load_note_content(note, storage)
                except (ConflictError, ValidationError):
                    # Invalidate missing/invalid files, but retain metadata for recovery.
                    logger.warning("File unavailable; reindex queued note_id=%s", note.id)
                    await enqueue_note(session, note)
                    queued += 1
                    continue
                if indexed_version != note.version:
                    await enqueue_note(session, note)
                    queued += 1
    return queued
