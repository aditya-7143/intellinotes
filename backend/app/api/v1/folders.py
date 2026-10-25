from fastapi import APIRouter, Depends, status

from app.api.v1.deps import get_current_user_id, get_folder_repo, get_note_repo, get_storage_repo
from app.application.dtos import FolderCreate, FolderResponse, FolderUpdate
from app.application.use_cases.folders import (
    CreateFolderUseCase,
    DeleteFolderUseCase,
    GetFolderUseCase,
    ListFoldersUseCase,
    UpdateFolderUseCase,
)
from app.infrastructure.database.acceptance import SQLAlchemyAcceptanceTransaction
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/folders", tags=["folders"])


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    folder_data: FolderCreate,
    user_id=Depends(get_current_user_id),
    folder_repo=Depends(get_folder_repo),
):
    return await CreateFolderUseCase(folder_repo).execute(
        user_id, folder_data.name, folder_data.parent_path
    )


@router.get("", response_model=list[FolderResponse])
async def list_folders(user_id=Depends(get_current_user_id), folder_repo=Depends(get_folder_repo)):
    return await ListFoldersUseCase(folder_repo).execute(user_id)


@router.get("/item", response_model=FolderResponse)
async def get_folder(
    path: str, user_id=Depends(get_current_user_id), folder_repo=Depends(get_folder_repo)
):
    return await GetFolderUseCase(folder_repo).execute(path, user_id)


@router.patch("/item", response_model=FolderResponse)
async def update_folder(
    path: str,
    folder_data: FolderUpdate,
    user_id=Depends(get_current_user_id),
    folder_repo=Depends(get_folder_repo),
    note_repo=Depends(get_note_repo),
    storage=Depends(get_storage_repo),
    db=Depends(get_db),
):
    return await UpdateFolderUseCase(
        folder_repo, note_repo, SQLAlchemyAcceptanceTransaction(db, storage)
    ).execute(path, user_id, folder_data.name, folder_data.parent_path)


@router.delete("/item", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    path: str, user_id=Depends(get_current_user_id), folder_repo=Depends(get_folder_repo)
):
    await DeleteFolderUseCase(folder_repo).execute(path, user_id)
