"""Confirms the Executor's real transitions actually reach a subscribed
EventBus — not just that WorkflowStateManager can be unit-tested with one in
isolation, but that WorkflowExecutor wires it through end to end against a
real Postgres schema."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.workflow_event import WorkflowEvent
from forgeai_core.workflow_enums import WorkflowStatus
from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.event_bus import EventBus
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.registration import get_or_create_workflow, register_version
from forgeai_workflow_engine.runner import FakeStageRunner


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


class TestExecutorPublishesRealTransitions:
    async def test_a_full_run_publishes_workflow_and_stage_events_in_order(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        bus = EventBus()
        observed: list[str] = []

        async def record(event: WorkflowEvent) -> None:
            observed.append(event.event_type)

        bus.subscribe("*", record)
        executor = WorkflowExecutor(db, FakeStageRunner(), event_bus=bus)

        # submit()/start() happen inside the helper, both via `executor`, so
        # their events land on the same bus too.
        execution_id = await _create_started_execution(
            db, executor, "events", [StageDefinition(id="a", name="A")], project_id
        )
        await executor.advance(execution_id)
        await db.commit()

        assert observed == [
            "workflow.pending",
            "workflow.running",
            "stage.running",
            "stage.completed",
            "workflow.completed",
        ]

    async def test_a_scoped_subscriber_only_sees_its_namespace(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        bus = EventBus()
        stage_events: list[str] = []

        async def record_stage(event: WorkflowEvent) -> None:
            stage_events.append(event.event_type)

        bus.subscribe("stage.*", record_stage)
        executor = WorkflowExecutor(db, FakeStageRunner(), event_bus=bus)
        execution_id = await _create_started_execution(
            db, executor, "scoped", [StageDefinition(id="a", name="A")], project_id
        )
        await executor.advance(execution_id)
        await db.commit()

        assert stage_events == ["stage.running", "stage.completed"]

    async def test_default_constructed_executor_still_works_without_a_bus(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        """Regression guard: existing call sites that construct
        WorkflowExecutor(db, runner) without an event_bus argument must keep
        working unchanged."""
        _user_id, _org_id, project_id = seeded_project
        executor = WorkflowExecutor(db, FakeStageRunner())
        execution_id = await _create_started_execution(
            db, executor, "no-bus", [StageDefinition(id="a", name="A")], project_id
        )
        execution = await executor.advance(execution_id)
        await db.commit()

        assert execution.status == WorkflowStatus.COMPLETED
