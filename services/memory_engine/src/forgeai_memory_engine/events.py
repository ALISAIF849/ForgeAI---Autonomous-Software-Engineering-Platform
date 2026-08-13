"""Episodic memory: an append-only log of "everything that happened" for a
project (docs/architecture/05-memory-engine.md §1). Deliberately a pure
store-and-retrieve service — per §6, it doesn't call other layers or decide
when it should be written to; a workflow completing, an approval being
granted, or a human recording something are all just callers of remember().
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.memory_event import MemoryEvent


class EpisodicMemoryStore:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def remember(
        self,
        *,
        project_id: uuid.UUID,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        event = MemoryEvent(
            project_id=project_id,
            event_type=event_type,
            source=source,
            payload=payload or {},
        )
        self._db.add(event)
        await self._db.flush()
        return event

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        event_type: str | None = None,
        before: datetime | None = None,
        limit: int = 50,
    ) -> list[MemoryEvent]:
        """Most-recent-first, optionally filtered by event_type and/or
        cursor-paginated via `before` (strictly older than this timestamp) —
        the shape an Activity Feed needs."""
        query = select(MemoryEvent).where(MemoryEvent.project_id == project_id)
        if event_type is not None:
            query = query.where(MemoryEvent.event_type == event_type)
        if before is not None:
            query = query.where(MemoryEvent.created_at < before)
        query = query.order_by(MemoryEvent.created_at.desc()).limit(limit)
        result = await self._db.execute(query)
        return list(result.scalars().all())
