from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.note_content import load_note_content
from app.application.ports import NoteRepository, StorageRepository
from app.core.logging import log_operation
from app.domain.models import Note, NoteIndexJob, NoteSection
from app.infrastructure.rag.index import enqueue_note


class SQLAlchemyNoteRepository(NoteRepository):
    def __init__(self, session: AsyncSession, storage: StorageRepository):
        self.session = session
        self.storage = storage

    @log_operation("infrastructure.repositories.note_repo.SQLAlchemyNoteRepository.create")
    async def create(self, note: Note) -> Note:
        self.session.add(note)
        await self.session.flush()
        await self.session.refresh(note)
        await enqueue_note(self.session, note)
        return note

    @log_operation("infrastructure.repositories.note_repo.SQLAlchemyNoteRepository.get_by_id")
    async def get_by_id(self, note_id: UUID, for_update: bool = False) -> Optional[Note]:
        query = select(Note).where(Note.id == note_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await self.session.execute(query)
        note = result.scalar_one_or_none()
        return await load_note_content(note, self.storage) if note else None

    @log_operation("infrastructure.repositories.note_repo.SQLAlchemyNoteRepository.get_by_user")
    async def get_by_user(self, user_id: UUID, folder_path: Optional[str] = None) -> list[Note]:
        query = select(Note).where(Note.user_id == user_id)
        if folder_path is not None:
            query = query.where(Note.folder_path == folder_path)
        query = query.order_by(Note.updated_at.desc())
        result = await self.session.execute(query)
        return [await load_note_content(note, self.storage) for note in result.scalars().all()]

    @log_operation(
        "infrastructure.repositories.note_repo.SQLAlchemyNoteRepository.get_by_storage_key"
    )
    async def get_by_storage_key(self, storage_key: str) -> Optional[Note]:
        result = await self.session.execute(select(Note).where(Note.storage_key == storage_key))
        return result.scalar_one_or_none()

    @log_operation("infrastructure.repositories.note_repo.SQLAlchemyNoteRepository.update")
    async def update(self, note: Note) -> Note:
        # A body-only edit no longer dirties an ORM column automatically.
        note.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(note)
        await enqueue_note(self.session, note)
        return note

    @log_operation("infrastructure.repositories.note_repo.SQLAlchemyNoteRepository.delete")
    async def delete(self, note_id: UUID) -> bool:
        note = await self.session.get(Note, note_id)
        if note:
            await self.session.execute(delete(NoteSection).where(NoteSection.note_id == note_id))
            await self.session.execute(delete(NoteIndexJob).where(NoteIndexJob.note_id == note_id))
            await self.session.delete(note)
            return True
        return False

    @log_operation("infrastructure.repositories.note_repo.SQLAlchemyNoteRepository.search")
    async def search(self, user_id: UUID, query: str) -> list[Note]:
        # Literal text search reads files; PostgreSQL holds no searchable body copy.
        term = query.casefold()
        return [
            note
            for note in await self.get_by_user(user_id)
            if term in note.title.casefold()
            or term in note.content.casefold()
            or any(term in tag.casefold() for tag in note.tags)
        ]
