import math
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.application.embeddings import EmbeddingProvider, validate_vectors
from app.application.note_content import load_note_content
from app.application.ports import StorageRepository
from app.application.retrieval import Section, split_text
from app.core.config import get_settings
from app.core.exceptions import ConflictError, ValidationError
from app.core.logging import log_operation
from app.domain.models import Note, NoteIndexJob, NoteSection


class SemanticSectionRetriever:
    def __init__(
        self, session: AsyncSession, embeddings: EmbeddingProvider, storage: StorageRepository
    ):
        self.session, self.embeddings = session, embeddings
        self.storage = storage

    @log_operation("rag.retrieve")
    async def retrieve(self, user_id: UUID, query: str) -> list[Section]:
        # Do not silently omit unindexed notes and propose duplicate files.
        missing = ~exists(
            select(NoteSection.id).where(
                NoteSection.note_id == Note.id,
                NoteSection.embedding_model == self.embeddings.model_key,
            )
        )
        pending = exists(select(NoteIndexJob.note_id).where(NoteIndexJob.note_id == Note.id))
        incomplete = await self.session.scalar(
            select(Note.id)
            .where(
                Note.user_id == user_id,
                missing | pending,
            )
            .limit(1)
        )
        if incomplete:
            raise ConflictError(
                "Your library's search index is not ready. Finish indexing or reindex your notes before trying again."
            )
        if not await self.session.scalar(select(Note.id).where(Note.user_id == user_id).limit(1)):
            return []
        query_parts = split_text(query)
        if not query_parts or len(query_parts) > 256:
            raise ValidationError("Input is empty or too large for semantic retrieval")
        vectors = []
        for start in range(0, len(query_parts), 16):
            batch = query_parts[start : start + 16]
            vectors.extend(
                validate_vectors(await self.embeddings.embed(batch, query=True), len(batch))
            )
        # Long dumps are embedded in bounded pieces, then pooled for one query vector.
        pooled = [sum(values) / len(vectors) for values in zip(*vectors)]
        if math.sqrt(sum(value * value for value in pooled)) < 1e-12:
            raise ValidationError("Unable to form a semantic search query")
        vector = validate_vectors([pooled], 1)[0]
        settings = get_settings()
        distance = NoteSection.embedding.cosine_distance(vector)
        result = await self.session.execute(
            select(NoteSection, Note)
            .join(
                Note,
                Note.id == NoteSection.note_id,
            )
            .options(noload("*"))
            .execution_options(populate_existing=True)
            .where(
                NoteSection.user_id == user_id,
                Note.user_id == user_id,
                NoteSection.embedding_model == self.embeddings.model_key,
                distance <= 1 - settings.RAG_MIN_SIMILARITY,
            )
            .order_by(distance, NoteSection.id)
            .limit(settings.RAG_TOP_K)
        )
        sections = []
        loaded = set()
        for chunk, note in result.all():
            if note.user_id != user_id or chunk.user_id != user_id:
                continue
            if note.id not in loaded:
                await load_note_content(note, self.storage)
                loaded.add(note.id)
            if chunk.source_version != note.version:
                raise ConflictError(
                    "Search index is stale. Reindex your library before organizing notes."
                )
            if not 0 <= chunk.start_offset <= chunk.end_offset <= len(note.content):
                raise ConflictError("Search section reference is invalid; reindex the note")
            sections.append(
                Section(note, chunk.heading, note.content[chunk.start_offset : chunk.end_offset])
            )
        return sections
