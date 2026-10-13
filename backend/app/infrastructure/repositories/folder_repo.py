from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports import FolderRepository
from app.domain.models import Folder


class SQLAlchemyFolderRepository(FolderRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, folder: Folder) -> Folder:
        self.session.add(folder)
        await self.session.flush()
        await self.session.refresh(folder)
        return folder

    async def get_by_id(self, folder_id: UUID) -> Optional[Folder]:
        result = await self.session.execute(select(Folder).where(Folder.id == folder_id))
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: UUID) -> list[Folder]:
        result = await self.session.execute(
            select(Folder).where(Folder.user_id == user_id).order_by(Folder.path)
        )
        return list(result.scalars().all())

    async def get_by_path(self, user_id: UUID, path: str) -> Optional[Folder]:
        result = await self.session.execute(
            select(Folder).where(Folder.user_id == user_id, Folder.path == path)
        )
        return result.scalar_one_or_none()

    async def get_children(self, parent_id: UUID) -> list[Folder]:
        result = await self.session.execute(
            select(Folder).where(Folder.parent_id == parent_id).order_by(Folder.name)
        )
        return list(result.scalars().all())

    async def update(self, folder: Folder) -> Folder:
        await self.session.flush()
        await self.session.refresh(folder)
        return folder

    async def delete(self, folder_id: UUID) -> bool:
        folder = await self.get_by_id(folder_id)
        if folder:
            await self.session.delete(folder)
            return True
        return False
