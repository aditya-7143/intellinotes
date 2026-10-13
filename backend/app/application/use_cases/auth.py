from dataclasses import dataclass
from uuid import UUID

from app.application.ports import UserRepository
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.security import create_token_pair, get_password_hash, verify_password
from app.domain.models import User


@dataclass
class RegisterUserUseCase:
    user_repo: UserRepository

    async def execute(self, email: str, password: str, full_name: str) -> tuple[UUID, str, str]:
        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise ConflictError("Email already registered")

        from app.domain.models import User

        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
        )
        created = await self.user_repo.create(user)
        access_token, refresh_token = create_token_pair(str(created.id), created.email)
        return created.id, access_token, refresh_token


@dataclass
class LoginUserUseCase:
    user_repo: UserRepository

    async def execute(self, email: str, password: str) -> tuple[UUID, str, str]:
        user = await self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid credentials")

        access_token, refresh_token = create_token_pair(str(user.id), user.email)
        return user.id, access_token, refresh_token


@dataclass
class RefreshTokenUseCase:
    user_repo: UserRepository

    async def execute(self, user_id: UUID) -> tuple[str, str]:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        access_token, refresh_token = create_token_pair(str(user.id), user.email)
        return access_token, refresh_token


@dataclass
class GetUserUseCase:
    user_repo: UserRepository

    async def execute(self, user_id: UUID) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")
        return user


@dataclass
class UpdateUserUseCase:
    user_repo: UserRepository

    async def execute(
        self, user_id: UUID, full_name: str | None = None, settings: dict | None = None
    ) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        if full_name is not None:
            user.full_name = full_name
        if settings is not None:
            user.settings = {**user.settings, **settings}

        return await self.user_repo.update(user)
