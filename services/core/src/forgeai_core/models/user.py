from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.enums import Theme
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    # Only for static analysis — SQLAlchemy resolves these forward references via
    # its own mapper registry at configuration time (see models/__init__.py), not
    # via a real import, so this block never runs and can't create a real circular
    # import between these model modules.
    from forgeai_core.models.oauth_account import OAuthAccount
    from forgeai_core.models.session import UserSession
    from forgeai_core.models.user_preference import UserPreference


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(39), unique=True, index=True)
    # Nullable: a user who signed up via OAuth only may never set a password.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    theme: Mapped[Theme] = mapped_column(
        Enum(Theme, native_enum=False, length=16),
        default=Theme.SYSTEM,
        server_default=Theme.SYSTEM.value,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Single-use, short-lived token hashes for the email-verification and password-reset
    # flows — kept as columns rather than separate tables since a user has at most one
    # outstanding token of each kind at a time (see docs/architecture Sprint 1 notes).
    email_verification_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_reset_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_reset_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    preferences: Mapped[UserPreference] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
