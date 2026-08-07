from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from forgeai_core.db.base import Base
from forgeai_core.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class WorkflowTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A curated, user-facing starting point for launching a workflow — not a
    duplicate of Workflow/WorkflowVersion (the registered graph itself), but
    a named preset of default input values for one, so a user picking
    "Fix a production bug" doesn't start from a blank input form."""

    __tablename__ = "workflow_templates"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
