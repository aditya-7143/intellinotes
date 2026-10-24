"""Durable PostgreSQL indexing queue: python -m app.infrastructure.rag.worker."""

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import noload

from app.application.embeddings import validate_vectors
from app.application.retrieval import chunk_sections, embedding_text
from app.core.config import get_settings
from app.domain.models import Note, NoteIndexJob, NoteSection
from app.infrastructure.database.session import async_session_maker, close_db, init_db
from app.infrastructure.embeddings.ollama import OllamaEmbeddingProvider
from app.infrastructure.rag.index import enqueue_note

logger = logging.getLogger("intellinotes.rag.worker")


class IndexWorker:
    def __init__(self, sessions=async_session_maker, embeddings=None):
        self.sessions = sessions
        self.embeddings = embeddings or OllamaEmbeddingProvider()

    async def run_once(self) -> bool:
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            async with session.begin():
                job = await session.scalar(
                    select(NoteIndexJob)
                    .where(
                        NoteIndexJob.status == "pending",
                        NoteIndexJob.available_at <= now,
                        (NoteIndexJob.lease_until.is_(None)) | (NoteIndexJob.lease_until <= now),
                    )
                    .order_by(NoteIndexJob.available_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if job is None:
                    return False
                # Renew ownership when a lease is reclaimed; the previous worker
                # must not publish or reschedule this claim after it has expired.
                job.generation = uuid4()
                note_id, generation = job.note_id, job.generation
                job.lease_until = now + timedelta(minutes=5)
        try:
            async with self.sessions() as session:
                note = await session.scalar(
                    select(Note).options(noload("*")).where(Note.id == note_id)
                )
                if note is None:
                    return True  # cascading deletion also removes the job
                version = note.version
                sections = chunk_sections(note)
                if not sections:
                    # Empty legacy notes still receive an index marker.
                    from app.application.retrieval import Section

                    sections = [Section(note, "Empty note", "(empty note)")]
                vectors = []
                for start in range(0, len(sections), 16):
                    batch = sections[start : start + 16]
                    vectors.extend(
                        validate_vectors(
                            await self.embeddings.embed(
                                [embedding_text(section) for section in batch]
                            ),
                            len(batch),
                        )
                    )
            async with self.sessions() as session:
                async with session.begin():
                    # Writers lock a note before its job; retain that lock ordering.
                    current = await session.scalar(
                        select(Note)
                        .options(noload("*"))
                        .where(Note.id == note_id)
                        .with_for_update()
                    )
                    job = await session.scalar(
                        select(NoteIndexJob)
                        .where(NoteIndexJob.note_id == note_id)
                        .with_for_update()
                    )
                    if current is None or job is None or job.generation != generation:
                        return True
                    if current.version != version:
                        await enqueue_note(session, current)
                        return True
                    await session.execute(delete(NoteSection).where(NoteSection.note_id == note_id))
                    for ordinal, (section, vector) in enumerate(zip(sections, vectors)):
                        session.add(
                            NoteSection(
                                note_id=note_id,
                                user_id=current.user_id,
                                ordinal=ordinal,
                                heading=section.heading,
                                content=section.content,
                                source_version=version,
                                embedding_model=self.embeddings.model_key,
                                embedding=vector,
                            )
                        )
                    await session.delete(job)
            logger.info("Indexed note_id=%s sections=%d", note_id, len(sections))
        except Exception as error:
            # Persist a bounded retry schedule; a crashed worker's lease expires.
            async with self.sessions() as session:
                async with session.begin():
                    job = await session.scalar(
                        select(NoteIndexJob)
                        .where(NoteIndexJob.note_id == note_id)
                        .with_for_update()
                    )
                    if job is not None and job.generation == generation:
                        job.attempts += 1
                        job.last_error = type(error).__name__
                        job.lease_until = None
                        job.available_at = datetime.now(timezone.utc) + timedelta(
                            seconds=min(900, 2 ** min(job.attempts, 10))
                        )
                        if job.attempts >= get_settings().RAG_INDEX_MAX_ATTEMPTS:
                            job.status = "failed"
            logger.warning(
                "Indexing failed note_id=%s error_type=%s", note_id, type(error).__name__
            )
        return True


async def backfill() -> int:
    async with async_session_maker() as session:
        async with session.begin():
            notes = (
                await session.scalars(
                    select(Note).options(noload("*")).order_by(Note.id).with_for_update()
                )
            ).all()
            for note in notes:
                await enqueue_note(session, note)
    return len(notes)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backfill", action="store_true", help="Queue all existing notes, including failed jobs"
    )
    parser.add_argument("--once", action="store_true", help="Process one available job and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    await init_db()
    try:
        if args.backfill:
            logger.info("Queued notes=%d", await backfill())
        worker = IndexWorker()
        while True:
            processed = await worker.run_once()
            if args.once:
                break
            if not processed:
                await asyncio.sleep(2)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
