from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.enums import OAuthProvider
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from forgeai_core.models.user import User


class OAuthAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Links a User to an external identity provider. Deliberately does not store
    the provider's access/refresh tokens — this table exists only to answer
    "which ForgeAI user does this Google/GitHub identity belong to" for login.
    Storing provider tokens to call GitHub's API on a user's behalf is a
    services/integrations concern for a later, AI-sprint feature, not this."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", name="uq_oauth_provider_account"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[OAuthProvider] = mapped_column(
        Enum(OAuthProvider, native_enum=False, length=16)
    )
    provider_account_id: Mapped[str] = mapped_column(String(255))
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="oauth_accounts")
