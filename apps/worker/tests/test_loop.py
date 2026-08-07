"""Integration tests for run_iteration() (2.9) against a real Postgres
schema — the worker's actual claim/start/advance/reenqueue behavior, not
just that WorkflowQueue and WorkflowExecutor individually work (already
covered by services/workflow_engine's own test suite)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from forgeai_core.models.workflow_queue_entry import QueueEntryStatus, WorkflowQueueEntry
from forgeai_core.policies import RetryPolicy
from forgeai_core.workflow_enums import WorkflowStatus
from forgeai_worker.loop import run_iteration
from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.registration import get_or_create_workflow, register_version
from forgeai_workflow_engine.runner import (
    FakeStageRunner,
    StageRunContext,
    StageRunner,
    StageRunResult,
)


class FlakyStageRunner(StageRunner):
    """Fails the first `fail_first_n_calls[stage.id]` calls for a given stage,
    then succeeds — same double used in workflow_engine's own retry tests."""

    def __init__(self, fail_first_n_calls: dict[str, int]) -> None:
        self.fail_first_n_calls = fail_first_n_calls
        self.call_counts: dict[str, int] = {}
        self.run_calls: list[str] = []

    async def run(self, stage: StageDefinition, context: StageRunContext) -> StageRunResult:
        self.run_calls.append(stage.id)
        self.call_counts[stage.id] = self.call_counts.get(stage.id, 0) + 1
        threshold = self.fail_first_n_calls.get(stage.id, 0)
        if self.call_counts[stage.id] <= threshold:
            return StageRunResult(success=False, error="scripted failure")
        return StageRunResult(success=True, output={"stage_id": stage.id})


async def _submit_execution(
    db: AsyncSession,
    key: str,
    stages: list[StageDefinition],
    project_id: uuid.UUID,
    *,
    priority: int = 0,
) -> uuid.UUID:
    """Registers a definition and creates+submits (but does NOT start) an
    execution — run_iteration() itself is responsible for the PENDING ->
    RUNNING transition on first claim, so tests exercise that instead of
    doing it for it."""
    unique = uuid.uuid4().hex[:8]
    full_key = f"{key}-{unique}"
    definition = WorkflowDefinition(key=full_key, name=full_key, version="1.0.0", stages=stages)
    workflow = await get_or_create_workflow(db, full_key, full_key)
    version = await register_version(db, workflow, definition)
    executor = WorkflowExecutor(db, FakeStageRunner())
    execution = await executor.create_execution(
        version, definition, project_id=project_id, input={}
    )
    await executor.submit(execution.id, priority=priority)
    await db.commit()
    return execution.id


async def _queue_entries_for(db: AsyncSession, execution_id: uuid.UUID) -> list[WorkflowQueueEntry]:
    result = await db.execute(
        select(WorkflowQueueEntry).where(WorkflowQueueEntry.workflow_execution_id == execution_id)
    )
    return list(result.scalars().all())


class TestEmptyQueue:
    async def test_returns_false_when_queue_is_empty(self, db: AsyncSession) -> None:
        did_work = await run_iteration(db, "worker-1", FakeStageRunner())
        assert did_work is False


class TestSingleStageWorkflow:
    async def test_claims_starts_completes_and_marks_the_queue_entry_done(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        execution_id = await _submit_execution(
            db, "single", [StageDefinition(id="a", name="A")], project_id
        )

        did_work = await run_iteration(db, "worker-1", runner)

        assert did_work is True
        assert runner.run_calls == ["a"]
        executor = WorkflowExecutor(db, runner)
        execution = await executor.get_execution(execution_id)
        assert execution.status == WorkflowStatus.COMPLETED

        entries = await _queue_entries_for(db, execution_id)
        assert len(entries) == 1
        assert entries[0].status == QueueEntryStatus.DONE

    async def test_does_not_reenqueue_a_completed_execution(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        execution_id = await _submit_execution(
            db, "no-reenqueue", [StageDefinition(id="a", name="A")], project_id
        )

        await run_iteration(db, "worker-1", FakeStageRunner())

        entries = await _queue_entries_for(db, execution_id)
        assert len(entries) == 1  # only the original — nothing re-added


class TestMultiStageWorkflow:
    async def test_reenqueues_a_still_running_execution_and_a_second_iteration_progresses_it(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        execution_id = await _submit_execution(
            db,
            "multi",
            [
                StageDefinition(id="a", name="A"),
                StageDefinition(id="b", name="B", depends_on=["a"]),
            ],
            project_id,
        )

        first = await run_iteration(db, "worker-1", runner)
        assert first is True
        assert runner.run_calls == ["a"]  # "b" not ready yet this tick

        entries = await _queue_entries_for(db, execution_id)
        assert len(entries) == 2  # original (DONE) + reenqueued (QUEUED)
        queued = [e for e in entries if e.status == QueueEntryStatus.QUEUED]
        assert len(queued) == 1
        assert queued[0].scheduled_for is None  # immediate, no retry involved

        second = await run_iteration(db, "worker-2", runner)
        assert second is True
        assert runner.run_calls == ["a", "b"]

        executor = WorkflowExecutor(db, runner)
        execution = await executor.get_execution(execution_id)
        assert execution.status == WorkflowStatus.COMPLETED

    async def test_reenqueue_preserves_priority(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        execution_id = await _submit_execution(
            db,
            "priority",
            [
                StageDefinition(id="a", name="A"),
                StageDefinition(id="b", name="B", depends_on=["a"]),
            ],
            project_id,
            priority=7,
        )

        await run_iteration(db, "worker-1", FakeStageRunner())

        entries = await _queue_entries_for(db, execution_id)
        queued = next(e for e in entries if e.status == QueueEntryStatus.QUEUED)
        assert queued.priority == 7


class TestRetryReenqueue:
    async def test_reenqueue_is_scheduled_for_the_retrying_stages_retry_after(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FlakyStageRunner(fail_first_n_calls={"a": 1})
        execution_id = await _submit_execution(
            db,
            "retry",
            [
                StageDefinition(
                    id="a", name="A", retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=30.0)
                )
            ],
            project_id,
        )

        await run_iteration(db, "worker-1", runner)

        executor = WorkflowExecutor(db, runner)
        execution = await executor.get_execution(execution_id)
        assert execution.status == WorkflowStatus.RUNNING  # retrying, not failed

        entries = await _queue_entries_for(db, execution_id)
        queued = next(e for e in entries if e.status == QueueEntryStatus.QUEUED)
        assert queued.scheduled_for is not None
        # Roughly 30s out (backoff_seconds), not immediate.
        assert queued.scheduled_for > datetime.now(UTC) + timedelta(seconds=20)

    async def test_a_claim_before_retry_after_elapses_does_nothing_new(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FlakyStageRunner(fail_first_n_calls={"a": 1})
        await _submit_execution(
            db,
            "retry-not-yet",
            [
                StageDefinition(
                    id="a", name="A", retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=30.0)
                )
            ],
            project_id,
        )
        await run_iteration(db, "worker-1", runner)

        # claim_next() skips future-scheduled entries entirely — the queue is
        # effectively empty right now from a worker's point of view.
        did_work = await run_iteration(db, "worker-2", runner)

        assert did_work is False
        assert runner.run_calls == ["a"]  # never retried — too soon

    async def test_a_claim_after_retry_after_elapses_retries_and_completes(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FlakyStageRunner(fail_first_n_calls={"a": 1})
        execution_id = await _submit_execution(
            db,
            "retry-elapsed",
            [
                StageDefinition(
                    id="a", name="A", retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=30.0)
                )
            ],
            project_id,
        )
        await run_iteration(db, "worker-1", runner)

        # Backdate instead of sleeping 30s — deterministic. Two independent
        # fields gate this, and both must move: the queue entry's
        # scheduled_for (what claim_next() checks) and the stage execution's
        # own retry_after (what advance() checks before treating it as
        # ready) — backdating only one leaves the other still blocking.
        entries = await _queue_entries_for(db, execution_id)
        queued = next(e for e in entries if e.status == QueueEntryStatus.QUEUED)
        queued.scheduled_for = datetime.now(UTC) - timedelta(seconds=1)

        executor = WorkflowExecutor(db, runner)
        pairs = await executor.get_stage_executions(execution_id)
        stage_a = next(se for se, key in pairs if key == "a")
        stage_a.retry_after = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

        did_work = await run_iteration(db, "worker-2", runner)

        assert did_work is True
        assert runner.run_calls == ["a", "a"]
        executor = WorkflowExecutor(db, runner)
        execution = await executor.get_execution(execution_id)
        assert execution.status == WorkflowStatus.COMPLETED


class TestConcurrentWorkers:
    async def test_two_workers_racing_never_both_process_the_same_execution(
        self,
        database_url: str,
        db: AsyncSession,
        seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        execution_id = await _submit_execution(
            db, "race", [StageDefinition(id="a", name="A")], project_id
        )

        async def _claim(worker_id: str) -> bool:
            engine = create_async_engine(database_url, poolclass=NullPool)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                did_work = await run_iteration(session, worker_id, FakeStageRunner())
            await engine.dispose()
            return did_work

        results = await asyncio.gather(_claim("worker-a"), _claim("worker-b"))

        # Exactly one of the two genuinely claimed and processed it — SKIP
        # LOCKED (already proven in workflow_engine's own queue tests) means
        # the second finds nothing left to claim, not a duplicate run.
        assert sorted(results) == [False, True]

        entries = await _queue_entries_for(db, execution_id)
        assert len(entries) == 1
        assert entries[0].status == QueueEntryStatus.DONE
