"""Integration tests for the Executor (2.3) against a real Postgres schema —
exercising create_execution/submit/start/advance/pause/resume/cancel/skip_stage
together with the state manager and queue they're built on, not each in
isolation with mocks."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.workflow_approval import WorkflowApproval
from forgeai_core.models.workflow_queue_entry import QueueEntryStatus, WorkflowQueueEntry
from forgeai_core.workflow_enums import StageStatus, WorkflowStatus
from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.exceptions import StageNotSkippableError
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.registration import get_or_create_workflow, register_version
from forgeai_workflow_engine.runner import FakeStageRunner


async def _register(
    db: AsyncSession, key: str, stages: list[StageDefinition]
) -> tuple[WorkflowDefinition, uuid.UUID]:
    """Registers a fresh, unique-keyed workflow + version and returns
    (definition, workflow_version_id)."""
    unique = uuid.uuid4().hex[:8]
    full_key = f"{key}-{unique}"
    definition = WorkflowDefinition(key=full_key, name=full_key, version="1.0.0", stages=stages)
    workflow = await get_or_create_workflow(db, full_key, full_key)
    version = await register_version(db, workflow, definition)
    await db.commit()
    return definition, version.id


async def _stage_status_map(
    db: AsyncSession, executor: WorkflowExecutor, execution_id: uuid.UUID
) -> dict[str, StageStatus]:
    pairs = await executor.get_stage_executions(execution_id)
    return {key: se.status for se, key in pairs}


class TestCreateSubmitStart:
    async def test_create_execution_creates_one_pending_stage_execution_per_stage(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        definition, version_id = await _register(
            db,
            "linear",
            [
                StageDefinition(id="a", name="A"),
                StageDefinition(id="b", name="B", depends_on=["a"]),
            ],
        )
        executor = WorkflowExecutor(db, FakeStageRunner())

        from forgeai_core.models.workflow_version import WorkflowVersion

        version_row = await db.get(WorkflowVersion, version_id)
        assert version_row is not None
        execution = await executor.create_execution(
            version_row, definition, project_id=project_id, input={}
        )
        await db.commit()

        assert execution.status == WorkflowStatus.DRAFT
        statuses = await _stage_status_map(db, executor, execution.id)
        assert statuses == {"a": StageStatus.PENDING, "b": StageStatus.PENDING}

    async def test_submit_moves_to_pending_and_enqueues(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        definition, version_id = await _register(db, "submit", [StageDefinition(id="a", name="A")])
        from forgeai_core.models.workflow_version import WorkflowVersion

        version_row = await db.get(WorkflowVersion, version_id)
        assert version_row is not None
        executor = WorkflowExecutor(db, FakeStageRunner())
        execution = await executor.create_execution(
            version_row, definition, project_id=project_id, input={}
        )
        await db.commit()

        submitted = await executor.submit(execution.id, priority=5)
        await db.commit()

        assert submitted.status == WorkflowStatus.PENDING
        entries = (
            (
                await db.execute(
                    select(WorkflowQueueEntry).where(
                        WorkflowQueueEntry.workflow_execution_id == execution.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(entries) == 1
        assert entries[0].priority == 5
        assert entries[0].status == QueueEntryStatus.QUEUED

    async def test_start_moves_to_running(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        definition, version_id = await _register(db, "start", [StageDefinition(id="a", name="A")])
        from forgeai_core.models.workflow_version import WorkflowVersion

        version_row = await db.get(WorkflowVersion, version_id)
        assert version_row is not None
        executor = WorkflowExecutor(db, FakeStageRunner())
        execution = await executor.create_execution(
            version_row, definition, project_id=project_id, input={}
        )
        await executor.submit(execution.id)
        await db.commit()

        running = await executor.start(execution.id)
        await db.commit()

        assert running.status == WorkflowStatus.RUNNING


async def _create_started_execution(
    db: AsyncSession,
    executor: WorkflowExecutor,
    key: str,
    stages: list[StageDefinition],
    project_id: uuid.UUID,
) -> tuple[WorkflowDefinition, uuid.UUID]:
    definition, version_id = await _register(db, key, stages)
    from forgeai_core.models.workflow_version import WorkflowVersion

    version_row = await db.get(WorkflowVersion, version_id)
    assert version_row is not None
    execution = await executor.create_execution(
        version_row, definition, project_id=project_id, input={}
    )
    await executor.submit(execution.id)
    await executor.start(execution.id)
    await db.commit()
    return definition, execution.id


class TestAdvance:
    async def test_advance_runs_single_ready_stage_and_completes_workflow(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        _definition, execution_id = await _create_started_execution(
            db, executor, "single", [StageDefinition(id="a", name="A")], project_id
        )

        execution = await executor.advance(execution_id)
        await db.commit()

        assert execution.status == WorkflowStatus.COMPLETED
        assert runner.run_calls == ["a"]

    async def test_advance_respects_sequential_dependencies(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        _definition, execution_id = await _create_started_execution(
            db,
            executor,
            "sequential",
            [
                StageDefinition(id="a", name="A"),
                StageDefinition(id="b", name="B", depends_on=["a"]),
                StageDefinition(id="c", name="C", depends_on=["b"]),
            ],
            project_id,
        )

        execution = await executor.advance(execution_id)
        await db.commit()
        assert execution.status == WorkflowStatus.RUNNING
        assert runner.run_calls == ["a"]

        execution = await executor.advance(execution_id)
        await db.commit()
        assert runner.run_calls == ["a", "b"]

        execution = await executor.advance(execution_id)
        await db.commit()
        assert runner.run_calls == ["a", "b", "c"]
        assert execution.status == WorkflowStatus.COMPLETED

    async def test_advance_runs_fan_out_stages_in_the_same_level_together(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        _definition, execution_id = await _create_started_execution(
            db,
            executor,
            "fanout",
            [
                StageDefinition(id="root", name="Root"),
                StageDefinition(id="left", name="Left", depends_on=["root"]),
                StageDefinition(id="right", name="Right", depends_on=["root"]),
            ],
            project_id,
        )

        await executor.advance(execution_id)
        await db.commit()
        assert runner.run_calls == ["root"]

        execution = await executor.advance(execution_id)
        await db.commit()
        assert set(runner.run_calls[1:]) == {"left", "right"}
        assert execution.status == WorkflowStatus.COMPLETED

    async def test_advance_blocks_on_approval_required_stage(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        _definition, execution_id = await _create_started_execution(
            db,
            executor,
            "approval",
            [StageDefinition(id="a", name="A", requires_approval=True)],
            project_id,
        )

        execution = await executor.advance(execution_id)
        await db.commit()

        assert execution.status == WorkflowStatus.WAITING_APPROVAL
        assert runner.run_calls == []  # never actually ran — approval gate blocks before run()
        statuses = await _stage_status_map(db, executor, execution_id)
        assert statuses["a"] == StageStatus.WAITING_APPROVAL

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

        # A further advance() is a no-op while not RUNNING.
        still_waiting = await executor.advance(execution_id)
        assert still_waiting.status == WorkflowStatus.WAITING_APPROVAL
        assert runner.run_calls == []

    async def test_advance_on_paused_workflow_is_a_noop(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        _definition, execution_id = await _create_started_execution(
            db, executor, "pause", [StageDefinition(id="a", name="A")], project_id
        )

        paused = await executor.pause(execution_id)
        await db.commit()
        assert paused.status == WorkflowStatus.PAUSED

        result = await executor.advance(execution_id)
        assert result.status == WorkflowStatus.PAUSED
        assert runner.run_calls == []

        resumed = await executor.resume(execution_id)
        await db.commit()
        assert resumed.status == WorkflowStatus.RUNNING

        completed = await executor.advance(execution_id)
        await db.commit()
        assert completed.status == WorkflowStatus.COMPLETED
        assert runner.run_calls == ["a"]

    async def test_stage_failure_fails_workflow_and_rolls_back_completed_stages(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner(fail_stage_keys=frozenset({"b"}))
        executor = WorkflowExecutor(db, runner)
        _definition, execution_id = await _create_started_execution(
            db,
            executor,
            "failure",
            [
                StageDefinition(id="a", name="A"),
                StageDefinition(id="b", name="B", depends_on=["a"]),
            ],
            project_id,
        )

        await executor.advance(execution_id)  # runs "a" -> COMPLETED
        await db.commit()
        execution = await executor.advance(execution_id)  # runs "b" -> FAILED
        await db.commit()

        assert execution.status == WorkflowStatus.FAILED
        assert execution.error is not None
        assert runner.rollback_calls == ["a"]  # only the already-completed stage is rolled back

        statuses = await _stage_status_map(db, executor, execution_id)
        assert statuses["a"] == StageStatus.COMPLETED  # rollback is a hook, not an undo of status
        assert statuses["b"] == StageStatus.FAILED


class TestCancelAndSkip:
    async def test_cancel_marks_pending_and_running_stages_cancelled(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        _definition, execution_id = await _create_started_execution(
            db,
            executor,
            "cancel",
            [
                StageDefinition(id="a", name="A"),
                StageDefinition(id="b", name="B", depends_on=["a"]),
            ],
            project_id,
        )

        await executor.advance(execution_id)  # completes "a", "b" is still PENDING
        await db.commit()

        cancelled = await executor.cancel(execution_id)
        await db.commit()

        assert cancelled.status == WorkflowStatus.CANCELLED
        statuses = await _stage_status_map(db, executor, execution_id)
        assert statuses["a"] == StageStatus.COMPLETED  # already terminal — untouched
        assert statuses["b"] == StageStatus.CANCELLED

    async def test_skip_stage_raises_when_not_allowed(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        executor = WorkflowExecutor(db, FakeStageRunner())
        _definition, execution_id = await _create_started_execution(
            db,
            executor,
            "noskip",
            [StageDefinition(id="a", name="A", allow_skip=False)],
            project_id,
        )
        pairs = await executor.get_stage_executions(execution_id)
        stage_execution_id = pairs[0][0].id

        with pytest.raises(StageNotSkippableError):
            await executor.skip_stage(stage_execution_id)

    async def test_skip_stage_succeeds_and_unblocks_dependents_when_allowed(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        runner = FakeStageRunner()
        executor = WorkflowExecutor(db, runner)
        _definition, execution_id = await _create_started_execution(
            db,
            executor,
            "skip",
            [
                StageDefinition(id="a", name="A", allow_skip=True),
                StageDefinition(id="b", name="B", depends_on=["a"]),
            ],
            project_id,
        )
        pairs = await executor.get_stage_executions(execution_id)
        stage_a_id = next(se.id for se, key in pairs if key == "a")

        skipped = await executor.skip_stage(stage_a_id)
        await db.commit()
        assert skipped.status == StageStatus.SKIPPED

        execution = await executor.advance(execution_id)
        await db.commit()

        assert runner.run_calls == ["b"]  # "a" was skipped, never run — but "b" still unblocked
        assert execution.status == WorkflowStatus.COMPLETED
