from __future__ import annotations

import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeai_core.db.base import Base
from forgeai_core.models.enums import ArchitectureDecisionStatus
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ArchitectureDecision(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Structured memory, per docs/architecture/05-memory-engine.md §4: ADRs
    are first-class rows with their own columns, never entries in a vector
    store — "why did we move away from X" must be answerable by reading a
    linear log, not by hoping the right chunk surfaces from similarity search.

    `superseded_by_id` is self-referential and nullable: superseding a
    decision means creating a *new* row and pointing the old one at it, never
    editing a decision in place once it exists.

    `capability_execution_id` is a plain UUID with no FK constraint yet — the
    table it would reference (a real Capability Executor's execution log)
    doesn't exist yet; this column exists so the eventual FK is a migration
    that adds a constraint, not one that also has to backfill the column."""

    __tablename__ = "architecture_decisions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    context: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text)
    consequences: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ArchitectureDecisionStatus] = mapped_column(
        Enum(ArchitectureDecisionStatus, native_enum=False, length=16),
        default=ArchitectureDecisionStatus.PROPOSED,
        server_default=ArchitectureDecisionStatus.PROPOSED.value,
        index=True,
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("architecture_decisions.id", ondelete="SET NULL"), nullable=True
    )
    capability_execution_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    superseded_by: Mapped[ArchitectureDecision | None] = relationship(
        remote_side="ArchitectureDecision.id"
    )
