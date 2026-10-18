from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.application.ports import FolderRepository, NoteRepository, StorageRepository
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.models import Note


@dataclass
class CreateNoteUseCase:
    note_repo: NoteRepository
    folder_repo: FolderRepository
    storage_repo: StorageRepository

    async def execute(
        self,
        user_id: UUID,
        title: Optional[str],
        content: str,
        folder_id: Optional[UUID] = None,
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

        folder_path = "/"
        if folder_id:
            folder = await self.folder_repo.get_by_id(folder_id)
            if not folder or folder.user_id != user_id:
                raise NotFoundError("Folder not found")
            folder_path = folder.path

        storage_key = f"{user_id}{folder_path}/{title}.md".replace("//", "/")
        existing = await self.note_repo.get_by_storage_key(storage_key)
        if existing:
            raise ConflictError("Note already exists at this path")

        await self.storage_repo.save(storage_key, content.encode())

        note = Note(
            user_id=user_id,
            folder_id=folder_id,
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

    async def execute(self, note_id: UUID, user_id: UUID) -> Note:
        note = await self.note_repo.get_by_id(note_id)
        if not note or note.user_id != user_id:
            raise NotFoundError("Note not found")
        return note


@dataclass
class ListNotesUseCase:
    note_repo: NoteRepository

    async def execute(self, user_id: UUID, folder_id: Optional[UUID] = None) -> list[Note]:
        return await self.note_repo.get_by_user(user_id, folder_id)


@dataclass
class UpdateNoteUseCase:
    note_repo: NoteRepository
    folder_repo: FolderRepository
    storage_repo: StorageRepository

    async def execute(
        self,
        note_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        content: Optional[str] = None,
        folder_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
    ) -> Note:
        note = await self.note_repo.get_by_id(note_id, for_update=True)
        if not note or note.user_id != user_id:
            raise NotFoundError("Note not found")

        new_title = title if title is not None else note.title
        new_folder_path = note.folder_path

        if folder_id is not None:
            folder = await self.folder_repo.get_by_id(folder_id)
            if not folder or folder.user_id != user_id:
                raise NotFoundError("Folder not found")
            note.folder_id = folder_id
            new_folder_path = folder.path
            note.folder_path = new_folder_path

        new_storage_key = f"{user_id}{new_folder_path}/{new_title}.md".replace("//", "/")
        if note.storage_key and note.storage_key != new_storage_key:
            await self.storage_repo.delete(note.storage_key)
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

        return await self.note_repo.update(note)


@dataclass
class DeleteNoteUseCase:
    note_repo: NoteRepository
    storage_repo: StorageRepository

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

    async def execute(self, user_id: UUID, query: str) -> list[Note]:
        return await self.note_repo.search(user_id, query)
