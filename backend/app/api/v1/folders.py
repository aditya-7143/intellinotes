from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.deps import get_current_user_id, get_folder_repo
from app.application.dtos import FolderCreate, FolderResponse, FolderUpdate
from app.application.use_cases.folders import (
    CreateFolderUseCase,
    DeleteFolderUseCase,
    GetFolderUseCase,
    ListFoldersUseCase,
    UpdateFolderUseCase,
)

router = APIRouter(prefix="/folders", tags=["folders"])


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    folder_data: FolderCreate,
    user_id=Depends(get_current_user_id),
    folder_repo=Depends(get_folder_repo),
):
    use_case = CreateFolderUseCase(folder_repo)
    folder = await use_case.execute(user_id, folder_data.name, folder_data.parent_id)
    return folder


@router.get("", response_model=list[FolderResponse])
async def list_folders(user_id=Depends(get_current_user_id), folder_repo=Depends(get_folder_repo)):
    use_case = ListFoldersUseCase(folder_repo)
    folders = await use_case.execute(user_id)
    return folders


@router.get("/{folder_id}", response_model=FolderResponse)
async def get_folder(
    folder_id: UUID, user_id=Depends(get_current_user_id), folder_repo=Depends(get_folder_repo)
):
    use_case = GetFolderUseCase(folder_repo)
    folder = await use_case.execute(folder_id, user_id)
    return folder


@router.patch("/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: UUID,
    folder_data: FolderUpdate,
    user_id=Depends(get_current_user_id),
    folder_repo=Depends(get_folder_repo),
):
    use_case = UpdateFolderUseCase(folder_repo)
    folder = await use_case.execute(folder_id, user_id, folder_data.name, folder_data.parent_id)
    return folder


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID, user_id=Depends(get_current_user_id), folder_repo=Depends(get_folder_repo)
):
    use_case = DeleteFolderUseCase(folder_repo)
    await use_case.execute(folder_id, user_id)
