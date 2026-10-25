from dataclasses import dataclass
from uuid import UUID

from app.application.ports import AcceptanceTransaction, FolderRepository, NoteRepository
from app.core.exceptions import ConflictError, NotFoundError
from app.core.paths import validate_folder_path, validate_note_title
from app.domain.models import Folder


@dataclass
class CreateFolderUseCase:
    folder_repo: FolderRepository

    async def execute(self, user_id: UUID, name: str, parent_path: str = "/") -> Folder:
        validate_note_title(name)
        validate_folder_path(parent_path)
        if parent_path != "/" and not await self.folder_repo.get_by_path(user_id, parent_path):
            raise NotFoundError("Parent folder not found")
        path = validate_folder_path(parent_path.rstrip("/") + "/" + name)
        if await self.folder_repo.get_by_path(user_id, path):
            raise ConflictError("Folder already exists at this path")
        return await self.folder_repo.create(Folder(user_id, name, path))


@dataclass
class GetFolderUseCase:
    folder_repo: FolderRepository

    async def execute(self, path: str, user_id: UUID) -> Folder:
        folder = await self.folder_repo.get_by_path(user_id, path)
        if not folder:
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
    note_repo: NoteRepository
    transaction: AcceptanceTransaction

    async def execute(
        self, path: str, user_id: UUID, name: str | None = None, parent_path: str | None = None
    ) -> Folder:
        moved = False
        destination = path
        try:
            await self.transaction.lock_user(user_id)
            folder = await GetFolderUseCase(self.folder_repo).execute(path, user_id)
            parent = parent_path if parent_path is not None else folder.parent_path
            validate_folder_path(parent)
            new_name = name if name is not None else folder.name
            validate_note_title(new_name)
            destination = validate_folder_path(parent.rstrip("/") + "/" + new_name)
            if destination == path:
                return folder
            if destination.startswith(path + "/"):
                raise ConflictError("Cannot move a folder inside itself")
            if parent != "/" and not await self.folder_repo.get_by_path(user_id, parent):
                raise NotFoundError("Parent folder not found")
            if await self.folder_repo.get_by_path(user_id, destination):
                raise ConflictError("Destination folder already exists")
            notes = [
                note
                for note in await self.note_repo.get_by_user(user_id)
                if note.folder_path == path or note.folder_path.startswith(path + "/")
            ]
            prefix = f"{user_id}{path}/"
            for note in notes:
                if not note.storage_key or not note.storage_key.startswith(prefix):
                    raise ConflictError(
                        "Note file reference disagrees with its folder; reconcile first"
                    )
            result = await self.folder_repo.move(user_id, path, destination)
            moved = True
            for note in notes:
                note.folder_path = destination + note.folder_path[len(path) :]
                note.storage_key = f"{user_id}{destination}/" + note.storage_key[len(prefix) :]
                await self.note_repo.update(note)
            await self.transaction.commit()
            return result
        except BaseException:
            await self.transaction.rollback()
            if moved:
                await self.folder_repo.move(user_id, destination, path)
            raise


@dataclass
class DeleteFolderUseCase:
    folder_repo: FolderRepository

    async def execute(self, path: str, user_id: UUID) -> bool:
        await GetFolderUseCase(self.folder_repo).execute(path, user_id)
        # Storage refuses any directory containing files or subdirectories.
        return await self.folder_repo.delete(user_id, path)
