"""Integration tests for the workflow efficiency calculators — driving real
WorkflowExecutor/WorkflowStateManager runs (forgeai_workflow_engine) to
terminal states, then verifying the metric calculators read genuine
WorkflowMetric/WorkflowExecution rows, not fixtures that bypass the engine."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_analytics.exceptions import MissingScopeError
from forgeai_analytics.workflow_metrics import (
    WorkflowAverageDurationMetric,
    WorkflowRetryRateMetric,
    WorkflowSuccessRateMetric,
)
from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.executor import WorkflowExecutor
from forgeai_workflow_engine.registration import get_or_create_workflow, register_version
from forgeai_workflow_engine.runner import FakeStageRunner

_WIDE_WINDOW_START = datetime(2000, 1, 1, tzinfo=UTC)
_WIDE_WINDOW_END = datetime(2100, 1, 1, tzinfo=UTC)


async def _run_to_completion(
    db: AsyncSession, project_id: uuid.UUID, *, fail_stage_keys: frozenset[str] = frozenset()
) -> None:
    unique = uuid.uuid4().hex[:8]
    key = f"metrics-{unique}"
    definition = WorkflowDefinition(
        key=key, name=key, version="1.0.0", stages=[StageDefinition(id="a", name="A")]
    )
    workflow = await get_or_create_workflow(db, key, key)
    version = await register_version(db, workflow, definition)
    await db.commit()

    executor = WorkflowExecutor(db, FakeStageRunner(fail_stage_keys=fail_stage_keys))
    execution = await executor.create_execution(
        version, definition, project_id=project_id, input={}
    )
    await db.commit()
    await executor.submit(execution.id)
    await db.commit()
    await executor.start(execution.id)
    await db.commit()
    await executor.advance(execution.id)
    await db.commit()


class TestWorkflowSuccessRateMetric:
    async def test_no_terminal_executions_is_not_available(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        metric = WorkflowSuccessRateMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.is_available is False
        assert result.reason_unavailable is not None

    async def test_all_successful_executions_yield_100_percent(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        await _run_to_completion(db, project_id)
        await _run_to_completion(db, project_id)
        metric = WorkflowSuccessRateMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.is_available is True
        assert result.value == 100.0
        assert result.evidence == {"total_executions": 2, "successful_executions": 2}

    async def test_a_mix_of_success_and_failure_yields_a_partial_rate(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        await _run_to_completion(db, project_id)
        await _run_to_completion(db, project_id, fail_stage_keys=frozenset({"a"}))
        metric = WorkflowSuccessRateMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.value == 50.0

    async def test_missing_project_scope_raises(self, db: AsyncSession) -> None:
        metric = WorkflowSuccessRateMetric()
        with pytest.raises(MissingScopeError):
            await metric.calculate(
                db,
                organization_id=None,
                project_id=None,
                window_start=_WIDE_WINDOW_START,
                window_end=_WIDE_WINDOW_END,
            )

    async def test_a_narrow_window_excludes_executions_outside_it(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        await _run_to_completion(db, project_id)
        metric = WorkflowSuccessRateMetric()
        far_future_start = datetime.now(UTC) + timedelta(days=365)
        far_future_end = far_future_start + timedelta(days=1)

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=far_future_start,
            window_end=far_future_end,
        )

        assert result.is_available is False


class TestWorkflowAverageDurationMetric:
    async def test_no_data_is_not_available(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        metric = WorkflowAverageDurationMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.is_available is False

    async def test_a_completed_execution_yields_a_non_negative_duration(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        await _run_to_completion(db, project_id)
        metric = WorkflowAverageDurationMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.is_available is True
        assert result.unit == "seconds"
        assert result.value is not None
        assert result.value >= 0
        assert result.evidence["sample_size"] == 1


class TestWorkflowRetryRateMetric:
    async def test_a_workflow_with_no_retries_yields_zero_average(
        self, db: AsyncSession, seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        await _run_to_completion(db, project_id)
        metric = WorkflowRetryRateMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.is_available is True
        assert result.value == 0.0


class TestTenantIsolation:
    async def test_a_projects_metrics_never_include_another_projects_executions(
        self,
        db: AsyncSession,
        seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
        other_seeded_project: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
    ) -> None:
        _user_id, _org_id, project_id = seeded_project
        _other_user_id, _other_org_id, other_project_id = other_seeded_project
        await _run_to_completion(db, project_id)
        await _run_to_completion(db, other_project_id)
        await _run_to_completion(db, other_project_id)
        metric = WorkflowSuccessRateMetric()

        result = await metric.calculate(
            db,
            organization_id=None,
            project_id=project_id,
            window_start=_WIDE_WINDOW_START,
            window_end=_WIDE_WINDOW_END,
        )

        assert result.evidence["total_executions"] == 1
