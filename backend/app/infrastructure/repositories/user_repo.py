from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports import UserRepository
from app.core.logging import log_operation
from app.domain.models import User


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @log_operation("infrastructure.repositories.user_repo.SQLAlchemyUserRepository.create")
    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    @log_operation("infrastructure.repositories.user_repo.SQLAlchemyUserRepository.get_by_id")
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @log_operation("infrastructure.repositories.user_repo.SQLAlchemyUserRepository.get_by_email")
    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @log_operation("infrastructure.repositories.user_repo.SQLAlchemyUserRepository.update")
    async def update(self, user: User) -> User:
        await self.session.flush()
        await self.session.refresh(user)
        return user

    @log_operation("infrastructure.repositories.user_repo.SQLAlchemyUserRepository.delete")
    async def delete(self, user_id: UUID) -> bool:
        user = await self.get_by_id(user_id)
        if user:
            await self.session.delete(user)
            return True
        return False
