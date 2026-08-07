"""Password hashing (argon2id, per docs/architecture/12-security-architecture.md
§1) and JWT access-token issuance/verification. Refresh-token rotation and
session tracking (the `sessions` table already exists) are NOT implemented
here yet — this is the minimal real auth needed to make Sprint 2's RBAC
requirement genuine, not the full Sprint 1.2 auth vertical.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from forgeai_api.core.config import Settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return _hasher.verify(hashed_password, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


class InvalidTokenError(Exception):
    pass


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    """Returns the user ID encoded in the token's `sub` claim, or raises
    InvalidTokenError for anything wrong with it (expired, bad signature,
    wrong type, malformed) — callers don't need to know which."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != "access":
        raise InvalidTokenError("Not an access token.")

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("Malformed subject claim.") from exc
