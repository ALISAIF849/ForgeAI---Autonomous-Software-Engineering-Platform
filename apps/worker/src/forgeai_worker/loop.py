"""The actual "drive executions forward" logic — deliberately factored out of
main.py's infinite `while True` loop so it's a single, directly-testable
async function: given a DB session, claim at most one queued execution and
act on it. main.py's job is just to call this repeatedly forever and sleep
when it returns False; this function has no opinion about scheduling itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.workflow_enums import StageStatus, WorkflowStatus
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.queue import WorkflowQueue
from forgeai_workflow_engine.runner import StageRunner


async def run_iteration(db: AsyncSession, worker_id: str, runner: StageRunner) -> bool:
    """Claims the next queued execution (if any), starts it if this is its
    first claim, and advances it one tick. If it's still RUNNING afterward,
    re-enqueues it — scheduled for its earliest pending stage's retry_after
    if one is RETRYING, or immediately otherwise, since a fan-out level can
    leave other stages readier sooner than any backoff. Returns whether it
    found (and acted on) anything at all, so main.py knows whether to sleep.
    """
    queue = WorkflowQueue(db)
    entry = await queue.claim_next(worker_id)
    if entry is None:
        return False

    executor = WorkflowExecutor(db, runner)
    execution_id = entry.workflow_execution_id

    execution = await executor.get_execution(execution_id)
    if execution.status == WorkflowStatus.PENDING:
        execution = await executor.start(execution_id)

    execution = await executor.advance(execution_id)

    if execution.status == WorkflowStatus.RUNNING:
        retry_after = await _earliest_pending_retry_after(executor, execution_id)
        await queue.enqueue(execution_id, priority=entry.priority, scheduled_for=retry_after)

    await queue.mark_done(entry.id)
    await db.commit()
    return True


async def _earliest_pending_retry_after(
    executor: WorkflowExecutor, execution_id: uuid.UUID
) -> datetime | None:
    pairs = await executor.get_stage_executions(execution_id)
    pending_retries = [
        stage_execution.retry_after
        for stage_execution, _key in pairs
        if stage_execution.status == StageStatus.RETRYING
        and stage_execution.retry_after is not None
    ]
    return min(pending_retries) if pending_retries else None
