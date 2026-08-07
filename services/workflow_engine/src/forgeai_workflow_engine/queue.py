"""Priority + FIFO + delayed-execution dispatch queue, backed by the
`workflow_queue` table (sub-sprint 2.2). "Concurrent execution limits" and
"queue monitoring" (Sprint 2's brief) are a caller's job on top of
`claim_next` (e.g. a worker loop that stops calling it once N executions are
already in flight) — this class only answers "what's next", not "how many
should run at once", which is a worker-process concern this package
deliberately doesn't own (see docs/architecture/02-service-architecture.md).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.workflow_queue_entry import QueueEntryStatus, WorkflowQueueEntry


class WorkflowQueue:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def enqueue(
        self,
        execution_id: uuid.UUID,
        *,
        priority: int = 0,
        scheduled_for: datetime | None = None,
    ) -> WorkflowQueueEntry:
        entry = WorkflowQueueEntry(
            workflow_execution_id=execution_id, priority=priority, scheduled_for=scheduled_for
        )
        self._db.add(entry)
        await self._db.flush()
        return entry

    async def claim_next(self, worker_id: str) -> WorkflowQueueEntry | None:
        """Highest priority first, then oldest first (FIFO within a priority
        tier); skips anything scheduled for the future. `SELECT ... FOR
        UPDATE SKIP LOCKED` is what makes this safe for multiple concurrent
        callers to claim from at once without two of them claiming the same
        entry — verified under actual concurrent claims, not assumed safe
        from the SQL alone (see tests)."""
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(WorkflowQueueEntry)
            .where(
                WorkflowQueueEntry.status == QueueEntryStatus.QUEUED,
                or_(
                    WorkflowQueueEntry.scheduled_for.is_(None),
                    WorkflowQueueEntry.scheduled_for <= now,
                ),
            )
            .order_by(WorkflowQueueEntry.priority.desc(), WorkflowQueueEntry.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return None

        entry.status = QueueEntryStatus.CLAIMED
        entry.claimed_at = now
        entry.claimed_by = worker_id
        await self._db.flush()
        return entry

    async def mark_done(self, entry_id: uuid.UUID) -> None:
        entry = await self._db.get(WorkflowQueueEntry, entry_id)
        if entry is not None:
            entry.status = QueueEntryStatus.DONE
            await self._db.flush()

    async def queue_depth(self) -> int:
        result = await self._db.execute(
            select(func.count())
            .select_from(WorkflowQueueEntry)
            .where(WorkflowQueueEntry.status == QueueEntryStatus.QUEUED)
        )
        return result.scalar_one()
