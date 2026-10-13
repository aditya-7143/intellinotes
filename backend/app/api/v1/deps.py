from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_token
from app.domain.models import User
from app.infrastructure.database.session import get_db
from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.llm.factory import get_llm_provider
from app.infrastructure.repositories.folder_repo import SQLAlchemyFolderRepository
from app.infrastructure.repositories.note_repo import SQLAlchemyNoteRepository
from app.infrastructure.repositories.proposal_repo import SQLAlchemyProposalRepository
from app.infrastructure.repositories.user_repo import SQLAlchemyUserRepository
from app.infrastructure.storage.base import BaseStorage
from app.infrastructure.storage.factory import get_storage

settings = get_settings()


async def get_current_user_id(authorization: Annotated[str | None, Header()] = None) -> UUID:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = authorization.split(" ")[1]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    return UUID(user_id_str)


async def get_current_user(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user_repo = SQLAlchemyUserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_user_repo(db: Annotated[AsyncSession, Depends(get_db)]) -> SQLAlchemyUserRepository:
    return SQLAlchemyUserRepository(db)


def get_folder_repo(db: Annotated[AsyncSession, Depends(get_db)]) -> SQLAlchemyFolderRepository:
    return SQLAlchemyFolderRepository(db)


def get_note_repo(db: Annotated[AsyncSession, Depends(get_db)]) -> SQLAlchemyNoteRepository:
    return SQLAlchemyNoteRepository(db)


def get_proposal_repo(db: Annotated[AsyncSession, Depends(get_db)]) -> SQLAlchemyProposalRepository:
    return SQLAlchemyProposalRepository(db)


def get_llm() -> BaseLLMProvider:
    return get_llm_provider()


def get_storage_repo() -> BaseStorage:
    return get_storage()
