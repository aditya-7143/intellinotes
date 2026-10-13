from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.deps import get_current_user, get_user_repo
from app.application.dtos import (
    TokenPair,
    TokenRefresh,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from app.application.ports import UserRepository
from app.application.use_cases.auth import (
    LoginUserUseCase,
    RefreshTokenUseCase,
    RegisterUserUseCase,
    UpdateUserUseCase,
)
from app.core.security import decode_token
from app.domain.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    user_repo: UserRepository = Depends(get_user_repo),
) -> TokenPair:
    use_case = RegisterUserUseCase(user_repo)
    user_id, access_token, refresh_token = await use_case.execute(
        user_data.email, user_data.password, user_data.full_name
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenPair)
async def login(
    user_data: UserLogin,
    user_repo: UserRepository = Depends(get_user_repo),
) -> TokenPair:
    use_case = LoginUserUseCase(user_repo)
    user_id, access_token, refresh_token = await use_case.execute(
        user_data.email, user_data.password
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    token_data: TokenRefresh,
    user_repo: UserRepository = Depends(get_user_repo),
) -> TokenPair:
    payload = decode_token(token_data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject"
        )

    try:
        user_uuid = UUID(str(sub))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user ID format in token"
        )

    use_case = RefreshTokenUseCase(user_repo)
    access_token, refresh_token = await use_case.execute(user_uuid)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
) -> User:
    use_case = UpdateUserUseCase(user_repo)
    updated = await use_case.execute(current_user.id, user_data.full_name, user_data.settings)
    return updated
