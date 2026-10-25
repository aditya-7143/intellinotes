"""Directory adapter: paths are always discovered from storage."""

from uuid import UUID

from app.application.ports import StorageRepository
from app.core.exceptions import ValidationError
from app.core.logging import log_operation
from app.core.paths import validate_folder_path
from app.domain.models import Folder


class StorageFolderRepository:
    def __init__(self, storage: StorageRepository):
        self.storage = storage

    @staticmethod
    def key(user_id: UUID, path: str) -> str:
        validate_folder_path(path)
        if path == "/":
            raise ValidationError("The library root cannot be changed")
        return f"{user_id}{path}"

    @log_operation("infrastructure.repositories.folder_repo.StorageFolderRepository.get_paths")
    async def get_paths(self, user_id: UUID) -> list[str]:
        prefix = f"{user_id}/"
        return sorted(
            {
                validate_folder_path("/" + key[len(prefix) :])
                for key in await self.storage.list_folders(str(user_id))
                if key.startswith(prefix)
            }
        )

    @log_operation("infrastructure.repositories.folder_repo.StorageFolderRepository.get_by_user")
    async def get_by_user(self, user_id: UUID) -> list[Folder]:
        return [
            Folder(user_id, path.rsplit("/", 1)[-1], path) for path in await self.get_paths(user_id)
        ]

    @log_operation("infrastructure.repositories.folder_repo.StorageFolderRepository.get_by_path")
    async def get_by_path(self, user_id: UUID, path: str) -> Folder | None:
        validate_folder_path(path)
        if path in await self.get_paths(user_id):
            return Folder(user_id, path.rsplit("/", 1)[-1], path)
        return None

    @log_operation("infrastructure.repositories.folder_repo.StorageFolderRepository.create")
    async def create(self, folder: Folder) -> Folder:
        await self.storage.create_folder(self.key(folder.user_id, folder.path))
        return folder

    @log_operation("infrastructure.repositories.folder_repo.StorageFolderRepository.move")
    async def move(self, user_id: UUID, path: str, destination: str) -> Folder:
        if destination == path or destination.startswith(path + "/"):
            raise ValidationError("Cannot move a folder inside itself")
        await self.storage.move_folder(self.key(user_id, path), self.key(user_id, destination))
        return Folder(user_id, destination.rsplit("/", 1)[-1], destination)

    @log_operation("infrastructure.repositories.folder_repo.StorageFolderRepository.delete")
    async def delete(self, user_id: UUID, path: str) -> bool:
        return await self.storage.delete_folder(self.key(user_id, path))
