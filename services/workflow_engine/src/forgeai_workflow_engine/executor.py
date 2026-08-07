"""Ties definitions (2.1), persistence (2.2), state transitions, dispatch,
and stage execution together. `advance()` does one "tick": it runs whatever
stage(s) in the next dependency level are currently ready, then returns — it
does not loop until the workflow finishes. A future worker process calls
`advance()` repeatedly (e.g. once per dequeued item); this package doesn't
own that scheduling loop, only what happens on a single tick. That's also
what makes "pause" free: pausing just means the next `advance()` call is a
no-op, not that anything needs to be torn down.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.workflow_approval import WorkflowApproval
from forgeai_core.models.workflow_execution import WorkflowExecution
from forgeai_core.models.workflow_stage import WorkflowStage
from forgeai_core.models.workflow_stage_execution import WorkflowStageExecution
from forgeai_core.models.workflow_version import WorkflowVersion
from forgeai_core.policies import TimeoutAction
from forgeai_core.workflow_enums import ApprovalDecision, StageStatus, WorkflowStatus
from forgeai_workflow_engine import approval_engine, retry_engine, timeout_engine
from forgeai_workflow_engine.approval_engine import ApprovalOutcome
from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.event_bus import EventBus
from forgeai_workflow_engine.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    StageNotSkippableError,
    WorkflowVersionNotFoundError,
)
from forgeai_workflow_engine.loader import DefinitionLoader
from forgeai_workflow_engine.queue import WorkflowQueue
from forgeai_workflow_engine.runner import StageRunContext, StageRunner
from forgeai_workflow_engine.state_manager import WorkflowStateManager

_DONE_FOR_DEPENDENCY_PURPOSES = frozenset({StageStatus.COMPLETED, StageStatus.SKIPPED})
_CANCELLABLE = frozenset(
    {StageStatus.PENDING, StageStatus.RUNNING, StageStatus.WAITING_APPROVAL, StageStatus.RETRYING}
)


class WorkflowExecutor:
    def __init__(
        self, db: AsyncSession, runner: StageRunner, event_bus: EventBus | None = None
    ) -> None:
        self._db = db
        self._runner = runner
        self.event_bus = event_bus if event_bus is not None else EventBus()
        self._state = WorkflowStateManager(db, self.event_bus)
        self._queue = WorkflowQueue(db)

    # ------------------------------------------------------------------ setup

    async def create_execution(
        self,
        workflow_version: WorkflowVersion,
        definition: WorkflowDefinition,
        *,
        project_id: uuid.UUID,
        input: dict[str, Any],
        started_by: uuid.UUID | None = None,
    ) -> WorkflowExecution:
        """DRAFT, with one PENDING WorkflowStageExecution per stage in the
        definition — the full plan is visible from the start, not built up
        lazily, so an Execution Timeline UI has something to render before
        anything has actually run."""
        execution = WorkflowExecution(
            workflow_id=workflow_version.workflow_id,
            workflow_version_id=workflow_version.id,
            project_id=project_id,
            status=WorkflowStatus.DRAFT,
            input=input,
            started_by=started_by,
        )
        self._db.add(execution)
        await self._db.flush()

        stages_result = await self._db.execute(
            select(WorkflowStage).where(WorkflowStage.workflow_version_id == workflow_version.id)
        )
        stage_row_by_key = {row.stage_key: row for row in stages_result.scalars().all()}

        for stage_def in definition.stages:
            self._db.add(
                WorkflowStageExecution(
                    workflow_execution_id=execution.id,
                    workflow_stage_id=stage_row_by_key[stage_def.id].id,
                    status=StageStatus.PENDING,
                )
            )
        await self._db.flush()
        return execution

    async def submit(
        self,
        execution_id: uuid.UUID,
        *,
        priority: int = 0,
    ) -> WorkflowExecution:
        """DRAFT -> PENDING, and enqueues for dispatch — a future worker calls
        `start()` once it claims the queue entry."""
        execution = await self._state.transition_workflow(execution_id, WorkflowStatus.PENDING)
        await self._queue.enqueue(execution_id, priority=priority)
        return execution

    async def start(self, execution_id: uuid.UUID) -> WorkflowExecution:
        return await self._state.transition_workflow(execution_id, WorkflowStatus.RUNNING)

    # ------------------------------------------------------------------ reads

    async def get_execution(self, execution_id: uuid.UUID) -> WorkflowExecution:
        return await self._state.get_execution(execution_id)

    async def get_stage_executions(
        self, execution_id: uuid.UUID
    ) -> list[tuple[WorkflowStageExecution, str]]:
        """Each stage execution paired with its stage_key (joined from
        WorkflowStage — not a column on WorkflowStageExecution itself).
        Public: callers outside this module (e.g. an API layer rendering
        execution status) need the same view this class uses internally."""
        result = await self._db.execute(
            select(WorkflowStageExecution, WorkflowStage.stage_key)
            .join(WorkflowStage, WorkflowStageExecution.workflow_stage_id == WorkflowStage.id)
            .where(WorkflowStageExecution.workflow_execution_id == execution_id)
        )
        return [(row[0], row[1]) for row in result.all()]

    # --------------------------------------------------------------- control

    async def pause(self, execution_id: uuid.UUID) -> WorkflowExecution:
        return await self._state.transition_workflow(execution_id, WorkflowStatus.PAUSED)

    async def resume(self, execution_id: uuid.UUID) -> WorkflowExecution:
        return await self._state.transition_workflow(execution_id, WorkflowStatus.RUNNING)

    async def cancel(self, execution_id: uuid.UUID) -> WorkflowExecution:
        for stage_execution, _key in await self.get_stage_executions(execution_id):
            if stage_execution.status in _CANCELLABLE:
                await self._state.transition_stage(stage_execution.id, StageStatus.CANCELLED)
        return await self._state.transition_workflow(execution_id, WorkflowStatus.CANCELLED)

    async def skip_stage(self, stage_execution_id: uuid.UUID) -> WorkflowStageExecution:
        stage_execution = await self._state.get_stage_execution(stage_execution_id)
        stage_row = await self._db.get(WorkflowStage, stage_execution.workflow_stage_id)
        if stage_row is None or not stage_row.allow_skip:
            raise StageNotSkippableError(stage_execution_id)
        return await self._state.transition_stage(stage_execution_id, StageStatus.SKIPPED)

    # -------------------------------------------------------------- approval

    async def resolve_approval(
        self,
        approval_id: uuid.UUID,
        decision: ApprovalDecision,
        *,
        decided_by: uuid.UUID | None = None,
        comment: str | None = None,
    ) -> WorkflowApproval:
        """Records a human decision on a pending WorkflowApproval and drives
        the consequence: APPROVE/REQUEST_CHANGES resume the gated stage and
        actually run it now (mirroring what a normal advance() tick would do
        for a freshly-ready stage — there's no intermediate "ready but not
        running" state to leave it in), REJECT/TIMEOUT halt the workflow the
        same way a permanent stage failure does, rollback included."""
        approval = await self._db.get(WorkflowApproval, approval_id)
        if approval is None:
            raise ApprovalNotFoundError(approval_id)
        if approval.decision is not None:
            raise ApprovalAlreadyDecidedError(approval_id)

        outcome = approval_engine.outcome_for_decision(decision)
        now = datetime.now(UTC)

        approval.decision = decision
        approval.decided_by_id = decided_by
        approval.decided_at = now
        approval.comment = comment
        await self._db.flush()

        execution = await self._state.get_execution(approval.workflow_execution_id)
        definition = await self._load_definition(execution.workflow_version_id)
        pairs = await self.get_stage_executions(approval.workflow_execution_id)
        status_by_key = {key: se.status for se, key in pairs}
        se_by_key = {key: se for se, key in pairs}

        if outcome == ApprovalOutcome.HALT:
            halt_error = f"approval {decision.value}" + (f": {comment}" if comment else "")
            if approval.stage_execution_id is not None:
                await self._state.transition_stage(
                    approval.stage_execution_id, StageStatus.FAILED, error=halt_error
                )
                stage_key = self._key_for_stage_execution_id(se_by_key, approval.stage_execution_id)
                status_by_key[stage_key] = StageStatus.FAILED
            await self._fail_workflow(
                approval.workflow_execution_id,
                definition,
                status_by_key,
                se_by_key,
                execution.project_id,
                error=halt_error,
            )
            return approval

        # RESUME
        await self._state.transition_workflow(
            approval.workflow_execution_id, WorkflowStatus.RUNNING
        )
        if approval.stage_execution_id is not None:
            stage_key = self._key_for_stage_execution_id(se_by_key, approval.stage_execution_id)
            stage_def = definition.stage(stage_key)
            stage_execution = se_by_key[stage_key]
            terminal = await self._run_and_apply_stage_result(
                execution,
                definition,
                stage_def,
                stage_execution,
                status_by_key,
                se_by_key,
                is_retry=False,
                now=now,
            )
            if terminal is None:
                await self._check_completion(approval.workflow_execution_id, status_by_key)
        return approval

    # -------------------------------------------------------------- execution

    async def advance(self, execution_id: uuid.UUID) -> WorkflowExecution:
        execution = await self._state.get_execution(execution_id)
        if execution.status != WorkflowStatus.RUNNING:
            return execution  # paused, waiting on approval, or terminal — nothing to do

        definition = await self._load_definition(execution.workflow_version_id)
        pairs = await self.get_stage_executions(execution_id)
        status_by_key = {key: se.status for se, key in pairs}
        se_by_key = {key: se for se, key in pairs}
        now = datetime.now(UTC)

        reaped = await self._reap_timed_out_stage(
            execution_id, definition, status_by_key, se_by_key, execution, now
        )
        if reaped is not None:
            return reaped

        retry_ready_keys = [
            key
            for key, status in status_by_key.items()
            if status == StageStatus.RETRYING
            and (retry_after := se_by_key[key].retry_after) is not None
            and retry_after <= now
        ]
        pending_ready_keys = [
            key
            for key, status in status_by_key.items()
            if status == StageStatus.PENDING
            and all(
                status_by_key.get(dep) in _DONE_FOR_DEPENDENCY_PURPOSES
                for dep in definition.stage(key).depends_on
            )
        ]
        ready_keys = retry_ready_keys + pending_ready_keys

        if not ready_keys:
            completed = await self._check_completion(execution_id, status_by_key)
            return completed if completed is not None else execution

        for key in ready_keys:
            stage_def = definition.stage(key)
            stage_execution = se_by_key[key]
            is_retry = status_by_key[key] == StageStatus.RETRYING

            if not is_retry and stage_def.requires_approval:
                self._db.add(
                    WorkflowApproval(
                        workflow_execution_id=execution_id,
                        stage_execution_id=stage_execution.id,
                        requested_from_role=None,
                        payload={"stage_id": stage_def.id, "stage_name": stage_def.name},
                    )
                )
                await self._state.transition_stage(stage_execution.id, StageStatus.WAITING_APPROVAL)
                return await self._state.transition_workflow(
                    execution_id, WorkflowStatus.WAITING_APPROVAL
                )

            terminal = await self._run_and_apply_stage_result(
                execution,
                definition,
                stage_def,
                stage_execution,
                status_by_key,
                se_by_key,
                is_retry=is_retry,
                now=now,
            )
            if terminal is not None:
                return terminal

        # Re-check completion after this tick's stages ran — a workflow whose
        # last remaining stage(s) just finished should complete in the same
        # tick that finished them, not sit in RUNNING for one extra no-op
        # advance() call before anyone notices.
        completed = await self._check_completion(execution_id, status_by_key)
        return completed if completed is not None else await self._state.get_execution(execution_id)

    # ------------------------------------------------------------------ internals

    async def _run_and_apply_stage_result(
        self,
        execution: WorkflowExecution,
        definition: WorkflowDefinition,
        stage_def: StageDefinition,
        stage_execution: WorkflowStageExecution,
        status_by_key: dict[str, StageStatus],
        se_by_key: dict[str, WorkflowStageExecution],
        *,
        is_retry: bool,
        now: datetime,
    ) -> WorkflowExecution | None:
        """Runs one stage via the configured StageRunner and applies the
        outcome (COMPLETED / RETRYING / FAILED+rollback+workflow FAILED).
        Shared by advance()'s per-tick loop and resolve_approval()'s "run it
        now that a human said yes" path — both need identical run/retry/
        failure handling. Returns the terminal WorkflowExecution if this
        outcome ended the workflow, else None (meaning "keep going")."""
        key = stage_def.id
        next_attempt_number = stage_execution.attempt_number + 1 if is_retry else None
        await self._state.transition_stage(
            stage_execution.id,
            StageStatus.RUNNING,
            attempt_number=next_attempt_number,
            reset_started_at=is_retry,
            retry_after=None,
        )
        context = StageRunContext(
            workflow_execution_id=execution.id,
            project_id=execution.project_id,
            stage_input=execution.input,
        )
        result = await self._runner.run(stage_def, context)

        if result.success:
            await self._state.transition_stage(
                stage_execution.id, StageStatus.COMPLETED, output=result.output
            )
            status_by_key[key] = StageStatus.COMPLETED
            return None

        attempted = next_attempt_number or stage_execution.attempt_number
        decision = retry_engine.decide(stage_def.retry_policy, attempted, now=now)
        if decision.should_retry:
            await self._state.transition_stage(
                stage_execution.id,
                StageStatus.RETRYING,
                error=result.error,
                retry_after=decision.retry_after,
            )
            status_by_key[key] = StageStatus.RETRYING
            return None

        await self._state.transition_stage(
            stage_execution.id, StageStatus.FAILED, error=result.error
        )
        status_by_key[key] = StageStatus.FAILED
        return await self._fail_workflow(
            execution.id,
            definition,
            status_by_key,
            se_by_key,
            execution.project_id,
            error=result.error or f"stage '{key}' failed",
        )

    async def _check_completion(
        self, execution_id: uuid.UUID, status_by_key: dict[str, StageStatus]
    ) -> WorkflowExecution | None:
        if all(status in _DONE_FOR_DEPENDENCY_PURPOSES for status in status_by_key.values()):
            return await self._state.transition_workflow(execution_id, WorkflowStatus.COMPLETED)
        return None

    async def _fail_workflow(
        self,
        execution_id: uuid.UUID,
        definition: WorkflowDefinition,
        status_by_key: dict[str, StageStatus],
        se_by_key: dict[str, WorkflowStageExecution],
        project_id: uuid.UUID,
        *,
        error: str,
    ) -> WorkflowExecution:
        await self._rollback_completed_stages(
            execution_id, definition, status_by_key, se_by_key, project_id
        )
        return await self._state.transition_workflow(
            execution_id, WorkflowStatus.FAILED, error=error
        )

    @staticmethod
    def _key_for_stage_execution_id(
        se_by_key: dict[str, WorkflowStageExecution], stage_execution_id: uuid.UUID
    ) -> str:
        return next(key for key, se in se_by_key.items() if se.id == stage_execution_id)

    async def _reap_timed_out_stage(
        self,
        execution_id: uuid.UUID,
        definition: WorkflowDefinition,
        status_by_key: dict[str, StageStatus],
        se_by_key: dict[str, WorkflowStageExecution],
        execution: WorkflowExecution,
        now: datetime,
    ) -> WorkflowExecution | None:
        """Finds a stage stranded in RUNNING past its TimeoutPolicy — only
        possible if a previous tick's runner.run() never returned (a worker
        crashed, or a real long-running capability is still executing
        elsewhere) — and applies its on_timeout action. Handles at most one
        per call, same "return early" shape as the approval-gate and failure
        paths; a second stranded stage (rare) is caught by the next tick.
        """
        for key, status in status_by_key.items():
            if status != StageStatus.RUNNING:
                continue
            stage_def = definition.stage(key)
            stage_execution = se_by_key[key]
            if stage_execution.started_at is None:
                continue
            if not timeout_engine.has_timed_out(
                stage_def.timeout, stage_execution.started_at, now=now
            ):
                continue

            timeout_error = f"stage '{key}' exceeded its {stage_def.timeout.seconds}s timeout"
            action = timeout_engine.action_for_timeout(stage_def.timeout)

            if action == TimeoutAction.ESCALATE:
                self._db.add(
                    WorkflowApproval(
                        workflow_execution_id=execution_id,
                        stage_execution_id=stage_execution.id,
                        requested_from_role=None,
                        payload={"stage_id": key, "reason": "timeout", "error": timeout_error},
                    )
                )
                await self._state.transition_stage(
                    stage_execution.id, StageStatus.WAITING_APPROVAL, error=timeout_error
                )
                return await self._state.transition_workflow(
                    execution_id, WorkflowStatus.WAITING_APPROVAL
                )

            if action == TimeoutAction.RETRY:
                decision = retry_engine.decide(
                    stage_def.retry_policy, stage_execution.attempt_number, now=now
                )
                if decision.should_retry:
                    await self._state.transition_stage(
                        stage_execution.id,
                        StageStatus.RETRYING,
                        error=timeout_error,
                        retry_after=decision.retry_after,
                    )
                    return await self._state.get_execution(execution_id)
                await self._state.transition_stage(
                    stage_execution.id, StageStatus.FAILED, error=timeout_error
                )
                status_by_key[key] = StageStatus.FAILED
                return await self._fail_workflow(
                    execution_id,
                    definition,
                    status_by_key,
                    se_by_key,
                    execution.project_id,
                    error=timeout_error,
                )

            # action == TimeoutAction.CANCEL
            await self._state.transition_stage(
                stage_execution.id, StageStatus.CANCELLED, error=timeout_error
            )
            status_by_key[key] = StageStatus.CANCELLED
            return await self._fail_workflow(
                execution_id,
                definition,
                status_by_key,
                se_by_key,
                execution.project_id,
                error=timeout_error,
            )

        return None

    async def _rollback_completed_stages(
        self,
        execution_id: uuid.UUID,
        definition: WorkflowDefinition,
        status_by_key: dict[str, StageStatus],
        se_by_key: dict[str, WorkflowStageExecution],
        project_id: uuid.UUID,
    ) -> None:
        """Walks already-COMPLETED stages in reverse definition order, calling
        each one's (optional, default no-op) rollback hook. A structural
        mechanism only — what "undo" actually does depends on real capability
        execution, which doesn't exist yet; this is what a real StageRunner
        plugs into once it does."""
        completed_keys_in_order = [
            stage.id
            for stage in definition.stages
            if status_by_key.get(stage.id) == StageStatus.COMPLETED
        ]
        for key in reversed(completed_keys_in_order):
            stage_execution = se_by_key[key]
            context = StageRunContext(
                workflow_execution_id=execution_id,
                project_id=project_id,
                stage_input=stage_execution.input,
            )
            await self._runner.rollback(definition.stage(key), context)

    async def _load_definition(self, workflow_version_id: uuid.UUID) -> WorkflowDefinition:
        version = await self._db.get(WorkflowVersion, workflow_version_id)
        if version is None:
            raise WorkflowVersionNotFoundError(workflow_version_id)
        return DefinitionLoader.load_from_dict(version.graph_spec)
