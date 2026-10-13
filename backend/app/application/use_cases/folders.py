from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.application.ports import FolderRepository
from app.core.exceptions import ConflictError, NotFoundError
from app.domain.models import Folder


@dataclass
class CreateFolderUseCase:
    folder_repo: FolderRepository

    async def execute(self, user_id: UUID, name: str, parent_id: Optional[UUID] = None) -> Folder:
        if parent_id:
            parent = await self.folder_repo.get_by_id(parent_id)
            if not parent or parent.user_id != user_id:
                raise NotFoundError("Parent folder not found")
            path = f"{parent.path}/{name}"
        else:
            path = f"/{name}"

        existing = await self.folder_repo.get_by_path(user_id, path)
        if existing:
            raise ConflictError("Folder already exists at this path")

        folder = Folder(user_id=user_id, name=name, parent_id=parent_id, path=path)
        return await self.folder_repo.create(folder)


@dataclass
class GetFolderUseCase:
    folder_repo: FolderRepository

    async def execute(self, folder_id: UUID, user_id: UUID) -> Folder:
        folder = await self.folder_repo.get_by_id(folder_id)
        if not folder or folder.user_id != user_id:
            raise NotFoundError("Folder not found")
        return folder


@dataclass
class ListFoldersUseCase:
    folder_repo: FolderRepository

    async def execute(self, user_id: UUID) -> list[Folder]:
        return await self.folder_repo.get_by_user(user_id)


@dataclass
class UpdateFolderUseCase:
    folder_repo: FolderRepository

    async def execute(
        self,
        folder_id: UUID,
        user_id: UUID,
        name: Optional[str] = None,
        parent_id: Optional[UUID] = None,
    ) -> Folder:
        folder = await self.folder_repo.get_by_id(folder_id)
        if not folder or folder.user_id != user_id:
            raise NotFoundError("Folder not found")

        if name is not None:
            old_path = folder.path
            parent_path = "/".join(old_path.split("/")[:-1])
            new_path = f"{parent_path}/{name}" if parent_path else f"/{name}"

            existing = await self.folder_repo.get_by_path(user_id, new_path)
            if existing and existing.id != folder_id:
                raise ConflictError("Folder already exists at this path")

            folder.name = name
            folder.path = new_path

        if parent_id is not None:
            if parent_id == folder_id:
                raise ConflictError("Cannot set folder as its own parent")
            parent = await self.folder_repo.get_by_id(parent_id)
            if not parent or parent.user_id != user_id:
                raise NotFoundError("Parent folder not found")
            folder.parent_id = parent_id
            folder.path = f"{parent.path}/{folder.name}"

        return await self.folder_repo.update(folder)


@dataclass
class DeleteFolderUseCase:
    folder_repo: FolderRepository

    async def execute(self, folder_id: UUID, user_id: UUID) -> bool:
        folder = await self.folder_repo.get_by_id(folder_id)
        if not folder or folder.user_id != user_id:
            raise NotFoundError("Folder not found")

        children = await self.folder_repo.get_children(folder_id)
        if children:
            raise ConflictError("Cannot delete folder with children. Delete children first.")

        return await self.folder_repo.delete(folder_id)
