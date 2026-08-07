"""Proves WorkflowStateManager transitions actually persist a WorkflowEvent
row — the Event Bus is "transitions are the events", not a separate thing
that could silently be forgotten (see state_manager.py's module docstring)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_core.models.workflow_event import WorkflowEvent
from forgeai_core.models.workflow_execution import WorkflowExecution
from forgeai_core.workflow_enums import StageStatus, WorkflowStatus
from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.exceptions import InvalidTransitionError
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.registration import get_or_create_workflow, register_version
from forgeai_workflow_engine.runner import FakeStageRunner
from forgeai_workflow_engine.state_manager import WorkflowStateManager


async def _new_execution(db: AsyncSession, project_id: uuid.UUID) -> WorkflowExecution:
    unique = uuid.uuid4().hex[:8]
    key = f"state-{unique}"
    definition = WorkflowDefinition(
        key=key, name=key, version="1.0.0", stages=[StageDefinition(id="a", name="A")]
    )
    workflow = await get_or_create_workflow(db, key, key)
    version = await register_version(db, workflow, definition)
    executor = WorkflowExecutor(db, FakeStageRunner())
    execution = await executor.create_execution(
        version, definition, project_id=project_id, input={}
    )
    await db.commit()
    return execution


class TestWorkflowTransitionEvents:
    async def test_transition_workflow_persists_a_workflow_event(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        execution = await _new_execution(db, project_id)
        state = WorkflowStateManager(db)

        await state.transition_workflow(execution.id, WorkflowStatus.PENDING)
        await db.commit()

        events = (
            (
                await db.execute(
                    select(WorkflowEvent).where(WorkflowEvent.workflow_execution_id == execution.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].event_type == "workflow.pending"
        assert events[0].payload == {"previous_status": "draft", "new_status": "pending"}

    async def test_transition_workflow_sets_started_at_and_completed_at(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        execution = await _new_execution(db, project_id)
        state = WorkflowStateManager(db)

        await state.transition_workflow(execution.id, WorkflowStatus.PENDING)
        running = await state.transition_workflow(execution.id, WorkflowStatus.RUNNING)
        assert running.started_at is not None
        assert running.completed_at is None

        completed = await state.transition_workflow(execution.id, WorkflowStatus.COMPLETED)
        await db.commit()
        assert completed.completed_at is not None

    async def test_invalid_transition_is_rejected_and_writes_no_event(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        execution = await _new_execution(db, project_id)
        state = WorkflowStateManager(db)

        with pytest.raises(InvalidTransitionError):
            # DRAFT -> RUNNING is not a legal direct transition.
            await state.transition_workflow(execution.id, WorkflowStatus.RUNNING)
        await db.commit()

        events = (
            (
                await db.execute(
                    select(WorkflowEvent).where(WorkflowEvent.workflow_execution_id == execution.id)
                )
            )
            .scalars()
            .all()
        )
        assert events == []

    async def test_transition_stage_persists_output_and_event(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        execution = await _new_execution(db, project_id)
        state = WorkflowStateManager(db)
        executor = WorkflowExecutor(db, FakeStageRunner())
        pairs = await executor.get_stage_executions(execution.id)
        stage_execution_id = pairs[0][0].id

        await state.transition_stage(stage_execution_id, StageStatus.RUNNING)
        completed = await state.transition_stage(
            stage_execution_id, StageStatus.COMPLETED, output={"result": "ok"}
        )
        await db.commit()

        assert completed.output == {"result": "ok"}
        assert completed.completed_at is not None

        events = (
            (
                await db.execute(
                    select(WorkflowEvent).where(
                        WorkflowEvent.workflow_execution_id == execution.id,
                        WorkflowEvent.event_type == "stage.completed",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].payload["new_status"] == "completed"
