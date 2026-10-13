from typing import Optional
from uuid import UUID

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports import NoteRepository
from app.domain.models import Note


class SQLAlchemyNoteRepository(NoteRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, note: Note) -> Note:
        self.session.add(note)
        await self.session.flush()
        await self.session.refresh(note)
        return note

    async def get_by_id(self, note_id: UUID) -> Optional[Note]:
        result = await self.session.execute(select(Note).where(Note.id == note_id))
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: UUID, folder_id: Optional[UUID] = None) -> list[Note]:
        query = select(Note).where(Note.user_id == user_id)
        if folder_id:
            query = query.where(Note.folder_id == folder_id)
        query = query.order_by(Note.updated_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_storage_key(self, storage_key: str) -> Optional[Note]:
        result = await self.session.execute(select(Note).where(Note.storage_key == storage_key))
        return result.scalar_one_or_none()

    async def update(self, note: Note) -> Note:
        await self.session.flush()
        await self.session.refresh(note)
        return note

    async def delete(self, note_id: UUID) -> bool:
        note = await self.get_by_id(note_id)
        if note:
            await self.session.delete(note)
            return True
        return False

    async def search(self, user_id: UUID, query: str) -> list[Note]:
        search_term = f"%{query}%"
        result = await self.session.execute(
            select(Note)
            .where(
                Note.user_id == user_id,
                or_(
                    Note.title.ilike(search_term),
                    Note.content.ilike(search_term),
                    cast(Note.tags, String).ilike(search_term),
                ),
            )
            .order_by(Note.updated_at.desc())
        )
        return list(result.scalars().all())
