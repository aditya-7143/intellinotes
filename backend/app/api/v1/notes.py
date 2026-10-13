from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.deps import get_current_user_id, get_folder_repo, get_note_repo, get_storage_repo
from app.application.dtos import NoteCreate, NoteResponse, NoteUpdate
from app.application.use_cases.notes import (
    CreateNoteUseCase,
    DeleteNoteUseCase,
    GetNoteUseCase,
    ListNotesUseCase,
    SearchNotesUseCase,
    UpdateNoteUseCase,
)

router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    note_data: NoteCreate,
    user_id=Depends(get_current_user_id),
    note_repo=Depends(get_note_repo),
    folder_repo=Depends(get_folder_repo),
    storage_repo=Depends(get_storage_repo),
):
    use_case = CreateNoteUseCase(note_repo, folder_repo, storage_repo)
    note = await use_case.execute(
        user_id, note_data.title, note_data.content, note_data.folder_id, note_data.tags
    )
    return note


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    folder_id: UUID | None = None,
    user_id=Depends(get_current_user_id),
    note_repo=Depends(get_note_repo),
):
    use_case = ListNotesUseCase(note_repo)
    notes = await use_case.execute(user_id, folder_id)
    return notes


@router.get("/search", response_model=list[NoteResponse])
async def search_notes(
    q: str,
    user_id=Depends(get_current_user_id),
    note_repo=Depends(get_note_repo),
):
    use_case = SearchNotesUseCase(note_repo)
    notes = await use_case.execute(user_id, q)
    return notes


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: UUID, user_id=Depends(get_current_user_id), note_repo=Depends(get_note_repo)
):
    use_case = GetNoteUseCase(note_repo)
    note = await use_case.execute(note_id, user_id)
    return note


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: UUID,
    note_data: NoteUpdate,
    user_id=Depends(get_current_user_id),
    note_repo=Depends(get_note_repo),
    folder_repo=Depends(get_folder_repo),
    storage_repo=Depends(get_storage_repo),
):
    use_case = UpdateNoteUseCase(note_repo, folder_repo, storage_repo)
    note = await use_case.execute(
        note_id, user_id, note_data.title, note_data.content, note_data.folder_id, note_data.tags
    )
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: UUID,
    user_id=Depends(get_current_user_id),
    note_repo=Depends(get_note_repo),
    storage_repo=Depends(get_storage_repo),
):
    use_case = DeleteNoteUseCase(note_repo, storage_repo)
    await use_case.execute(note_id, user_id)
