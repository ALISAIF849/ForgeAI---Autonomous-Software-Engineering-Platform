from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.enums import DigestFrequency
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from forgeai_core.models.user import User


class UserPreference(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """1:1 with User, split into its own table rather than more columns on `users`
    because these are behavioral/notification settings, not identity — keeping
    them separate means the frequently-read User row stays small, and this table
    can grow new preference flags without every User query paying for it."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    email_on_org_invite: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    email_on_project_update: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    email_on_mention: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    digest_frequency: Mapped[DigestFrequency] = mapped_column(
        Enum(DigestFrequency, native_enum=False, length=16), default=DigestFrequency.WEEKLY
    )

    user: Mapped[User] = relationship(back_populates="preferences")
