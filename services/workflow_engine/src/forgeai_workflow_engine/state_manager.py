"""Persistence-aware wrapper around the pure, in-memory validation logic in
state_machine.py — every transition here goes through
validate_workflow_transition/validate_stage_transition first (never a second,
looser copy of the rules), and every successful transition also writes a
WorkflowEvent row and publishes it to the EventBus (2.6): transitions ARE the
events, not a separate thing to remember to emit. A workflow reaching a
terminal status is also where a WorkflowMetric row gets written (same
principle applied to forgeai_core.models.workflow_metric.WorkflowMetric,
which existed since sub-sprint 2.2 with a docstring promising "written once
the execution reaches a terminal state" but nothing ever actually wrote one
until now) — this is the one place every terminal transition already flows
through, so it's the right choke point rather than a second thing callers
must remember to do.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.workflow_event import WorkflowEvent
from forgeai_core.models.workflow_execution import WorkflowExecution
from forgeai_core.models.workflow_metric import WorkflowMetric
from forgeai_core.models.workflow_queue_entry import WorkflowQueueEntry
from forgeai_core.models.workflow_stage_execution import WorkflowStageExecution
from forgeai_core.workflow_enums import StageStatus, WorkflowStatus
from forgeai_workflow_engine.event_bus import EventBus
from forgeai_workflow_engine.exceptions import ExecutionNotFoundError, StageExecutionNotFoundError
from forgeai_workflow_engine.state_machine import (
    validate_stage_transition,
    validate_workflow_transition,
)

_TERMINAL_WORKFLOW = frozenset(
    {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}
)
_TERMINAL_STAGE = frozenset(
    {StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.SKIPPED, StageStatus.CANCELLED}
)


class WorkflowStateManager:
    def __init__(self, db: AsyncSession, event_bus: EventBus | None = None) -> None:
        self._db = db
        self._event_bus = event_bus if event_bus is not None else EventBus()

    async def get_execution(self, execution_id: uuid.UUID) -> WorkflowExecution:
        execution = await self._db.get(WorkflowExecution, execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        return execution

    async def get_stage_execution(self, stage_execution_id: uuid.UUID) -> WorkflowStageExecution:
        stage_execution = await self._db.get(WorkflowStageExecution, stage_execution_id)
        if stage_execution is None:
            raise StageExecutionNotFoundError(stage_execution_id)
        return stage_execution

    async def transition_workflow(
        self, execution_id: uuid.UUID, target: WorkflowStatus, *, error: str | None = None
    ) -> WorkflowExecution:
        execution = await self.get_execution(execution_id)
        previous = WorkflowStatus(execution.status)
        validate_workflow_transition(previous, target)

        execution.status = target
        now = datetime.now(UTC)
        if target == WorkflowStatus.RUNNING and execution.started_at is None:
            execution.started_at = now
        if target in _TERMINAL_WORKFLOW:
            execution.completed_at = now
        if error is not None:
            execution.error = error

        event = WorkflowEvent(
            workflow_execution_id=execution_id,
            event_type=f"workflow.{target.value}",
            payload={"previous_status": previous.value, "new_status": target.value},
        )
        self._db.add(event)
        await self._db.flush()
        if target in _TERMINAL_WORKFLOW:
            await self._record_metric(execution)
        await self._event_bus.publish(event)
        return execution

    async def _record_metric(self, execution: WorkflowExecution) -> None:
        stage_rows = (
            await self._db.execute(
                select(WorkflowStageExecution.status, WorkflowStageExecution.attempt_number).where(
                    WorkflowStageExecution.workflow_execution_id == execution.id
                )
            )
        ).all()
        stages_completed = sum(1 for status, _ in stage_rows if status == StageStatus.COMPLETED)
        stages_failed = sum(1 for status, _ in stage_rows if status == StageStatus.FAILED)
        retries_total = sum(max(0, attempt - 1) for _, attempt in stage_rows)

        first_queued_at = (
            await self._db.execute(
                select(func.min(WorkflowQueueEntry.created_at)).where(
                    WorkflowQueueEntry.workflow_execution_id == execution.id
                )
            )
        ).scalar_one_or_none()

        total_duration_seconds = None
        if execution.started_at is not None and execution.completed_at is not None:
            total_duration_seconds = (execution.completed_at - execution.started_at).total_seconds()

        queue_wait_seconds = None
        if first_queued_at is not None and execution.started_at is not None:
            queue_wait_seconds = (execution.started_at - first_queued_at).total_seconds()

        self._db.add(
            WorkflowMetric(
                workflow_execution_id=execution.id,
                total_duration_seconds=total_duration_seconds,
                queue_wait_seconds=queue_wait_seconds,
                stages_completed=stages_completed,
                stages_failed=stages_failed,
                retries_total=retries_total,
            )
        )
        await self._db.flush()

    async def transition_stage(
        self,
        stage_execution_id: uuid.UUID,
        target: StageStatus,
        *,
        error: str | None = None,
        output: dict[str, object] | None = None,
        retry_after: datetime | None = None,
        attempt_number: int | None = None,
        reset_started_at: bool = False,
    ) -> WorkflowStageExecution:
        stage_execution = await self.get_stage_execution(stage_execution_id)
        previous = StageStatus(stage_execution.status)
        validate_stage_transition(previous, target)

        stage_execution.status = target
        now = datetime.now(UTC)
        if reset_started_at:
            # A stage re-entering RUNNING after a retry is a new attempt, not
            # a continuation — `started_at` (and therefore timeout detection)
            # should measure from this attempt, not the original one.
            stage_execution.started_at = now
        elif target == StageStatus.RUNNING and stage_execution.started_at is None:
            stage_execution.started_at = now
        if target in _TERMINAL_STAGE:
            stage_execution.completed_at = now
        if error is not None:
            stage_execution.error = error
        if output is not None:
            stage_execution.output = output
        if attempt_number is not None:
            stage_execution.attempt_number = attempt_number
        # retry_after is set on entering RETRYING and explicitly cleared once
        # the stage leaves RETRYING again — never left stale from a prior cycle.
        stage_execution.retry_after = retry_after

        event = WorkflowEvent(
            workflow_execution_id=stage_execution.workflow_execution_id,
            event_type=f"stage.{target.value}",
            payload={
                "stage_execution_id": str(stage_execution_id),
                "previous_status": previous.value,
                "new_status": target.value,
            },
        )
        self._db.add(event)
        await self._db.flush()
        await self._event_bus.publish(event)
        return stage_execution
