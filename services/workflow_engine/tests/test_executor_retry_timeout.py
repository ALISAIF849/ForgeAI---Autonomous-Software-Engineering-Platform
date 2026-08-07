"""Integration tests for the Executor's 2.4 retry/timeout behavior against a
real Postgres schema — a transient failure that eventually succeeds, one that
exhausts its retry budget, and a stage reaped after being found stranded in
RUNNING past its TimeoutPolicy (simulating a crashed worker, the only way a
stage can legitimately still be RUNNING when advance() is called again, since
run() always resolves synchronously within the same tick)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.workflow_approval import WorkflowApproval
from forgeai_core.models.workflow_stage_execution import WorkflowStageExecution
from forgeai_core.policies import RetryPolicy, TimeoutAction, TimeoutPolicy
from forgeai_core.workflow_enums import StageStatus, WorkflowStatus
from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.registration import get_or_create_workflow, register_version
from forgeai_workflow_engine.runner import StageRunContext, StageRunner, StageRunResult
from forgeai_workflow_engine.state_manager import WorkflowStateManager


class FlakyStageRunner(StageRunner):
    """Fails the first `fail_first_n_calls[stage.id]` calls for a given stage,
    then succeeds — deterministic, no I/O, scripted per-stage like
    FakeStageRunner but with a call count instead of an always/never switch."""

    def __init__(self, fail_first_n_calls: dict[str, int]) -> None:
        self.fail_first_n_calls = fail_first_n_calls
        self.call_counts: dict[str, int] = {}
        self.run_calls: list[str] = []

    async def run(self, stage: StageDefinition, context: StageRunContext) -> StageRunResult:
        self.run_calls.append(stage.id)
        self.call_counts[stage.id] = self.call_counts.get(stage.id, 0) + 1
        threshold = self.fail_first_n_calls.get(stage.id, 0)
        if self.call_counts[stage.id] <= threshold:
            return StageRunResult(
                success=False, error=f"attempt {self.call_counts[stage.id]} failed"
            )
        return StageRunResult(success=True, output={"stage_id": stage.id})


async def _create_started_execution(
    db: AsyncSession,
    executor: WorkflowExecutor,
    key: str,
    stages: list[StageDefinition],
    project_id: uuid.UUID,
) -> uuid.UUID:
    unique = uuid.uuid4().hex[:8]
    full_key = f"{key}-{unique}"
    definition = WorkflowDefinition(key=full_key, name=full_key, version="1.0.0", stages=stages)
    workflow = await get_or_create_workflow(db, full_key, full_key)
    version = await register_version(db, workflow, definition)
    execution = await executor.create_execution(
        version, definition, project_id=project_id, input={}
    )
    await executor.submit(execution.id)
    await executor.start(execution.id)
    await db.commit()
    return execution.id


async def _stage_execution(
    db: AsyncSession, execution_id: uuid.UUID, stage_key: str
) -> WorkflowStageExecution:
    from forgeai_core.models.workflow_stage import WorkflowStage

    result = await db.execute(
        select(WorkflowStageExecution)
        .join(WorkflowStage, WorkflowStageExecution.workflow_stage_id == WorkflowStage.id)
        .where(
            WorkflowStageExecution.workflow_execution_id == execution_id,
            WorkflowStage.stage_key == stage_key,
        )
    )
    stage_execution = result.scalar_one()
    return stage_execution


class TestRetry:
    async def test_transient_failure_retries_and_eventually_succeeds(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FlakyStageRunner(fail_first_n_calls={"a": 1})
        executor = WorkflowExecutor(db, runner)
        execution_id = await _create_started_execution(
            db,
            executor,
            "retry-success",
            [
                StageDefinition(
                    id="a", name="A", retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=5.0)
                )
            ],
            project_id,
        )

        execution = await executor.advance(execution_id)
        await db.commit()
        assert execution.status == WorkflowStatus.RUNNING
        assert runner.run_calls == ["a"]

        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.RETRYING
        assert stage_execution.retry_after is not None
        assert stage_execution.attempt_number == 1

        # Backdate retry_after instead of sleeping 5s — deterministic and fast.
        stage_execution.retry_after = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

        execution = await executor.advance(execution_id)
        await db.commit()

        assert execution.status == WorkflowStatus.COMPLETED
        assert runner.run_calls == ["a", "a"]
        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.COMPLETED
        assert stage_execution.attempt_number == 2

    async def test_retry_budget_exhausted_fails_the_workflow(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FlakyStageRunner(fail_first_n_calls={"a": 99})
        executor = WorkflowExecutor(db, runner)
        execution_id = await _create_started_execution(
            db,
            executor,
            "retry-exhausted",
            [
                StageDefinition(
                    id="a", name="A", retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=5.0)
                )
            ],
            project_id,
        )

        await executor.advance(execution_id)
        await db.commit()
        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.RETRYING

        stage_execution.retry_after = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

        execution = await executor.advance(execution_id)
        await db.commit()

        assert execution.status == WorkflowStatus.FAILED
        assert execution.error is not None
        assert runner.run_calls == ["a", "a"]
        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.FAILED
        assert stage_execution.attempt_number == 2

    async def test_retrying_stage_blocks_its_dependents(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FlakyStageRunner(fail_first_n_calls={"a": 1})
        executor = WorkflowExecutor(db, runner)
        execution_id = await _create_started_execution(
            db,
            executor,
            "retry-blocks",
            [
                StageDefinition(
                    id="a", name="A", retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=5.0)
                ),
                StageDefinition(id="b", name="B", depends_on=["a"]),
            ],
            project_id,
        )

        await executor.advance(execution_id)  # "a" fails once, goes RETRYING
        await db.commit()

        assert runner.run_calls == ["a"]  # "b" never became ready
        stage_b = await _stage_execution(db, execution_id, "b")
        assert stage_b.status == StageStatus.PENDING


class TestTimeoutReaping:
    async def _strand_stage_in_running(
        self,
        db: AsyncSession,
        execution_id: uuid.UUID,
        stage_key: str,
        *,
        seconds_ago: float,
    ) -> WorkflowStageExecution:
        """Simulates a worker crash: puts the stage directly into RUNNING (not
        via advance(), which would resolve it synchronously) with a stale
        started_at, so the next advance() finds it stranded."""
        state = WorkflowStateManager(db)
        stage_execution = await _stage_execution(db, execution_id, stage_key)
        await state.transition_stage(stage_execution.id, StageStatus.RUNNING)
        stage_execution.started_at = datetime.now(UTC) - timedelta(seconds=seconds_ago)
        await db.commit()
        return stage_execution

    async def test_cancel_action_fails_the_workflow(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        executor = WorkflowExecutor(db, FlakyStageRunner(fail_first_n_calls={}))
        execution_id = await _create_started_execution(
            db,
            executor,
            "timeout-cancel",
            [
                StageDefinition(
                    id="a",
                    name="A",
                    timeout=TimeoutPolicy(seconds=1, on_timeout=TimeoutAction.CANCEL),
                )
            ],
            project_id,
        )
        await self._strand_stage_in_running(db, execution_id, "a", seconds_ago=10)

        execution = await executor.advance(execution_id)
        await db.commit()

        assert execution.status == WorkflowStatus.FAILED
        assert execution.error is not None and "timeout" in execution.error
        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.CANCELLED

    async def test_escalate_action_waits_for_approval(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        executor = WorkflowExecutor(db, FlakyStageRunner(fail_first_n_calls={}))
        execution_id = await _create_started_execution(
            db,
            executor,
            "timeout-escalate",
            [
                StageDefinition(
                    id="a",
                    name="A",
                    timeout=TimeoutPolicy(seconds=1, on_timeout=TimeoutAction.ESCALATE),
                )
            ],
            project_id,
        )
        await self._strand_stage_in_running(db, execution_id, "a", seconds_ago=10)

        execution = await executor.advance(execution_id)
        await db.commit()

        assert execution.status == WorkflowStatus.WAITING_APPROVAL
        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.WAITING_APPROVAL

        approvals = (
            (
                await db.execute(
                    select(WorkflowApproval).where(
                        WorkflowApproval.workflow_execution_id == execution_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(approvals) == 1
        assert approvals[0].payload["reason"] == "timeout"

    async def test_retry_action_retries_when_budget_allows(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        executor = WorkflowExecutor(db, FlakyStageRunner(fail_first_n_calls={}))
        execution_id = await _create_started_execution(
            db,
            executor,
            "timeout-retry",
            [
                StageDefinition(
                    id="a",
                    name="A",
                    timeout=TimeoutPolicy(seconds=1, on_timeout=TimeoutAction.RETRY),
                    retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=5.0),
                )
            ],
            project_id,
        )
        await self._strand_stage_in_running(db, execution_id, "a", seconds_ago=10)

        execution = await executor.advance(execution_id)
        await db.commit()

        assert execution.status == WorkflowStatus.RUNNING
        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.RETRYING
        assert stage_execution.retry_after is not None

    async def test_retry_action_fails_when_budget_exhausted(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        executor = WorkflowExecutor(db, FlakyStageRunner(fail_first_n_calls={}))
        execution_id = await _create_started_execution(
            db,
            executor,
            "timeout-retry-exhausted",
            [
                StageDefinition(
                    id="a",
                    name="A",
                    timeout=TimeoutPolicy(seconds=1, on_timeout=TimeoutAction.RETRY),
                    retry_policy=RetryPolicy(max_attempts=0, backoff_seconds=5.0),
                )
            ],
            project_id,
        )
        await self._strand_stage_in_running(db, execution_id, "a", seconds_ago=10)

        execution = await executor.advance(execution_id)
        await db.commit()

        assert execution.status == WorkflowStatus.FAILED
        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.FAILED

    async def test_stage_within_its_timeout_window_is_left_alone(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        executor = WorkflowExecutor(db, FlakyStageRunner(fail_first_n_calls={}))
        execution_id = await _create_started_execution(
            db,
            executor,
            "timeout-not-yet",
            [
                StageDefinition(
                    id="a",
                    name="A",
                    timeout=TimeoutPolicy(seconds=3600, on_timeout=TimeoutAction.CANCEL),
                )
            ],
            project_id,
        )
        await self._strand_stage_in_running(db, execution_id, "a", seconds_ago=1)

        execution = await executor.advance(execution_id)
        await db.commit()

        # Still RUNNING and untouched — advance() doesn't treat a merely
        # in-flight stage as ready to re-run or reap.
        assert execution.status == WorkflowStatus.RUNNING
        stage_execution = await _stage_execution(db, execution_id, "a")
        assert stage_execution.status == StageStatus.RUNNING


class TestExhaustNotAffectingIndependentStages:
    async def test_a_stalled_stage_does_not_block_advance_from_returning(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        """Regression guard: advance() must not raise or hang just because one
        stage is RUNNING-but-not-yet-timed-out while nothing else is ready."""
        _user_id, _org_id, project_id = seeded_project
        executor = WorkflowExecutor(db, FlakyStageRunner(fail_first_n_calls={}))
        execution_id = await _create_started_execution(
            db,
            executor,
            "no-op-tick",
            [StageDefinition(id="a", name="A", timeout=TimeoutPolicy(seconds=3600))],
            project_id,
        )
        await self._strand_in_running_no_timeout(db, execution_id, "a")

        execution = await executor.advance(execution_id)
        assert execution.status == WorkflowStatus.RUNNING

    @staticmethod
    async def _strand_in_running_no_timeout(
        db: AsyncSession, execution_id: uuid.UUID, stage_key: str
    ) -> None:
        state = WorkflowStateManager(db)
        stage_execution = await _stage_execution(db, execution_id, stage_key)
        await state.transition_stage(stage_execution.id, StageStatus.RUNNING)
        await db.commit()
