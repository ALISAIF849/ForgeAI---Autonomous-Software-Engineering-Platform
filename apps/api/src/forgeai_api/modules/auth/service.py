from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_api.core.config import Settings
from forgeai_api.core.security import create_access_token, hash_password, verify_password
from forgeai_api.modules.auth.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    UsernameAlreadyTakenError,
)
from forgeai_api.modules.auth.repository import UserRepository
from forgeai_api.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from forgeai_core.models.user import User


class AuthService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings
        self._users = UserRepository(db)

    async def register(self, request: RegisterRequest) -> User:
        if await self._users.get_by_email(request.email) is not None:
            raise EmailAlreadyRegisteredError
        if await self._users.get_by_username(request.username) is not None:
            raise UsernameAlreadyTakenError

        user = await self._users.create(
            email=request.email,
            username=request.username,
            hashed_password=hash_password(request.password),
            full_name=request.full_name,
        )
        await self._db.commit()
        return user

    async def login(self, request: LoginRequest) -> TokenResponse:
        user = await self._users.get_by_email(request.email)
        # A None hashed_password means an OAuth-only account — reject the same way
        # as a wrong password, not a different error, for the same enumeration
        # reason as InvalidCredentialsError's docstring.
        if user is None or user.hashed_password is None:
            raise InvalidCredentialsError
        if not verify_password(request.password, user.hashed_password):
            raise InvalidCredentialsError

        await self._users.touch_last_login(user)
        await self._db.commit()

        token = create_access_token(user.id, self._settings)
        return TokenResponse(
            access_token=token,
            expires_in_minutes=self._settings.jwt_access_token_expire_minutes,
        )
