from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_api.core.config import Settings, get_settings
from forgeai_api.db.session import get_db
from forgeai_api.dependencies.auth import get_current_user
from forgeai_api.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)
from forgeai_api.modules.auth.service import AuthService
from forgeai_core.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Email/password registration only — Google/GitHub OAuth is still-pending
    Sprint 1 work, not implemented here (see the Sprint 2 status report)."""
    service = AuthService(db, settings)
    return await service.register(request)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Issues an access token only — refresh-token rotation and session
    tracking (the `sessions` table) are still-pending Sprint 1 work."""
    service = AuthService(db, settings)
    return await service.login(request)


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
