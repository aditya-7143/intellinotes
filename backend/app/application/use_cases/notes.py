from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.application.ports import FolderRepository, NoteRepository, StorageRepository
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import log_operation
from app.core.paths import validate_folder_path, validate_note_title
from app.domain.models import Note


@dataclass
class CreateNoteUseCase:
    note_repo: NoteRepository
    folder_repo: FolderRepository
    storage_repo: StorageRepository

    @log_operation("application.use_cases.notes.CreateNoteUseCase.execute")
    async def execute(
        self,
        user_id: UUID,
        title: Optional[str],
        content: str,
        folder_path: str = "/",
        tags: Optional[list[str]] = None,
    ) -> Note:
        if not content.strip():
            raise ValidationError("Note content cannot be empty")
        title = (title or "").strip()
        if not title:
            first_line = next(line.strip() for line in content.splitlines() if line.strip())
            # Generated titles also become filenames; keep separators out of them.
            title = first_line.replace("/", " ").replace("\\", " ")
            title = " ".join(title.split())[:80].strip().strip(".") or "Untitled note"

        validate_note_title(title)
        validate_folder_path(folder_path)
        if folder_path != "/":
            folder = await self.folder_repo.get_by_path(user_id, folder_path)
            if not folder:
                raise NotFoundError("Folder not found")

        storage_key = f"{user_id}{folder_path}/{title}.md".replace("//", "/")
        existing = await self.note_repo.get_by_storage_key(storage_key)
        if existing or await self.storage_repo.exists(storage_key):
            raise ConflictError("Note already exists at this path")

        await self.storage_repo.save(storage_key, content.encode())

        note = Note(
            user_id=user_id,
            title=title,
            content=content,
            folder_path=folder_path,
            tags=tags or [],
            storage_key=storage_key,
        )
        return await self.note_repo.create(note)


@dataclass
class GetNoteUseCase:
    note_repo: NoteRepository

    @log_operation("application.use_cases.notes.GetNoteUseCase.execute")
    async def execute(self, note_id: UUID, user_id: UUID) -> Note:
        note = await self.note_repo.get_by_id(note_id)
        if not note or note.user_id != user_id:
            raise NotFoundError("Note not found")
        return note


@dataclass
class ListNotesUseCase:
    note_repo: NoteRepository

    @log_operation("application.use_cases.notes.ListNotesUseCase.execute")
    async def execute(self, user_id: UUID, folder_path: Optional[str] = None) -> list[Note]:
        if folder_path is not None:
            validate_folder_path(folder_path)
        return await self.note_repo.get_by_user(user_id, folder_path)


@dataclass
class UpdateNoteUseCase:
    note_repo: NoteRepository
    folder_repo: FolderRepository
    storage_repo: StorageRepository

    @log_operation("application.use_cases.notes.UpdateNoteUseCase.execute")
    async def execute(
        self,
        note_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        content: Optional[str] = None,
        folder_path: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> Note:
        note = await self.note_repo.get_by_id(note_id, for_update=True)
        if not note or note.user_id != user_id:
            raise NotFoundError("Note not found")

        new_title = title if title is not None else note.title
        new_folder_path = note.folder_path

        validate_note_title(new_title)
        if folder_path is not None:
            validate_folder_path(folder_path)
            if folder_path != "/" and not await self.folder_repo.get_by_path(user_id, folder_path):
                raise NotFoundError("Folder not found")
            new_folder_path = folder_path
            note.folder_path = new_folder_path

        new_storage_key = f"{user_id}{new_folder_path}/{new_title}.md".replace("//", "/")
        old_storage_key = note.storage_key
        if old_storage_key != new_storage_key:
            if await self.note_repo.get_by_storage_key(
                new_storage_key
            ) or await self.storage_repo.exists(new_storage_key):
                raise ConflictError("Note already exists at this path")
        if note.storage_key and note.storage_key != new_storage_key:
            note.storage_key = new_storage_key
        elif not note.storage_key:
            note.storage_key = new_storage_key

        if title is not None:
            note.title = title
        if content is not None:
            note.content = content
        if tags is not None:
            note.tags = tags

        if note.storage_key:
            effective_content = content if content is not None else note.content
            await self.storage_repo.save(note.storage_key, effective_content.encode())

        # Keep the original until the replacement has been written successfully.
        if old_storage_key and old_storage_key != new_storage_key:
            await self.storage_repo.delete(old_storage_key)

        return await self.note_repo.update(note)


@dataclass
class DeleteNoteUseCase:
    note_repo: NoteRepository
    storage_repo: StorageRepository

    @log_operation("application.use_cases.notes.DeleteNoteUseCase.execute")
    async def execute(self, note_id: UUID, user_id: UUID) -> bool:
        note = await self.note_repo.get_by_id(note_id, for_update=True)
        if not note or note.user_id != user_id:
            raise NotFoundError("Note not found")

        if note.storage_key:
            await self.storage_repo.delete(note.storage_key)

        return await self.note_repo.delete(note_id)


@dataclass
class SearchNotesUseCase:
    note_repo: NoteRepository

    @log_operation("application.use_cases.notes.SearchNotesUseCase.execute")
    async def execute(self, user_id: UUID, query: str) -> list[Note]:
        return await self.note_repo.search(user_id, query)
