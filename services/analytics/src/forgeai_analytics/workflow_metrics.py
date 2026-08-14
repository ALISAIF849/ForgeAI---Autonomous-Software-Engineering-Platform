"""Workflow efficiency metrics (Sprint 18 Stage 7), computed from
WorkflowExecution + WorkflowMetric. WorkflowMetric only has rows to read
because forgeai_workflow_engine.state_manager.WorkflowStateManager now
actually writes one on every terminal transition (this sprint's fix to a
gap that existed since sub-sprint 2.2) — before that, these metrics would
have had nothing to compute from.

Every calculator here requires `project_id`: WorkflowExecution has no
organization_id column of its own (only project_id; organization scoping
would need a join through Project this slice doesn't add yet), and
computing across an unscoped set of projects would mean reading across
tenants, which this package refuses to do (see MissingScopeError).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forgeai_analytics.exceptions import MissingScopeError
from forgeai_analytics.registry import (
    MetricAvailability,
    MetricCategory,
    MetricDefinition,
    MetricResult,
    confidence_for_sample_size,
)
from forgeai_core.models.workflow_execution import WorkflowExecution
from forgeai_core.models.workflow_metric import WorkflowMetric
from forgeai_core.workflow_enums import WorkflowStatus

_TERMINAL = (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED)


def _unavailable(
    metric_id: str, window_start: datetime, window_end: datetime, reason: str
) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        availability=MetricAvailability.NOT_AVAILABLE,
        value=None,
        unit=None,
        window_start=window_start,
        window_end=window_end,
        evidence={},
        confidence=None,
        reason_unavailable=reason,
    )


class WorkflowSuccessRateMetric:
    definition = MetricDefinition(
        id="workflow_success_rate",
        name="Workflow Success Rate",
        description=(
            "Share of workflow executions that reached COMPLETED, out of all "
            "executions that reached a terminal state in the window."
        ),
        category=MetricCategory.RELIABILITY,
        formula="COMPLETED executions / (COMPLETED + FAILED + CANCELLED executions)",
        data_sources=("workflow_executions",),
        window="custom",
        aggregation="rate",
        owner="platform-team",
    )

    async def calculate(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> MetricResult:
        if project_id is None:
            raise MissingScopeError(self.definition.id)

        statuses = (
            (
                await db.execute(
                    select(WorkflowExecution.status).where(
                        WorkflowExecution.project_id == project_id,
                        WorkflowExecution.status.in_(_TERMINAL),
                        WorkflowExecution.completed_at >= window_start,
                        WorkflowExecution.completed_at <= window_end,
                    )
                )
            )
            .scalars()
            .all()
        )

        total = len(statuses)
        if total == 0:
            # A rate with a zero denominator is undefined — reporting 0%
            # here would misrepresent "nothing ran" as "everything failed".
            return _unavailable(
                self.definition.id,
                window_start,
                window_end,
                "No workflow executions reached a terminal state in this window.",
            )

        successful = sum(1 for status in statuses if status == WorkflowStatus.COMPLETED)
        return MetricResult(
            metric_id=self.definition.id,
            availability=MetricAvailability.AVAILABLE,
            value=round(successful / total * 100, 2),
            unit="percent",
            window_start=window_start,
            window_end=window_end,
            evidence={"total_executions": total, "successful_executions": successful},
            confidence=confidence_for_sample_size(total),
        )


class WorkflowAverageDurationMetric:
    definition = MetricDefinition(
        id="workflow_average_duration_seconds",
        name="Average Workflow Duration",
        description=(
            "Average wall-clock duration (start to terminal) of workflow "
            "executions that reached a terminal state in the window."
        ),
        category=MetricCategory.DELIVERY,
        formula="AVG(workflow_metrics.total_duration_seconds) over terminal executions",
        data_sources=("workflow_executions", "workflow_metrics"),
        window="custom",
        aggregation="average",
        owner="platform-team",
    )

    async def calculate(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> MetricResult:
        if project_id is None:
            raise MissingScopeError(self.definition.id)

        raw_durations = (
            (
                await db.execute(
                    select(WorkflowMetric.total_duration_seconds)
                    .join(
                        WorkflowExecution,
                        WorkflowExecution.id == WorkflowMetric.workflow_execution_id,
                    )
                    .where(
                        WorkflowExecution.project_id == project_id,
                        WorkflowExecution.completed_at >= window_start,
                        WorkflowExecution.completed_at <= window_end,
                        WorkflowMetric.total_duration_seconds.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        # The is_not(None) filter above already guarantees this at the SQL
        # level; this comprehension is only here to narrow the type for mypy.
        durations = [value for value in raw_durations if value is not None]

        if not durations:
            return _unavailable(
                self.definition.id,
                window_start,
                window_end,
                "No completed workflow executions with a recorded duration in this window.",
            )

        average = sum(durations) / len(durations)
        return MetricResult(
            metric_id=self.definition.id,
            availability=MetricAvailability.AVAILABLE,
            value=round(average, 3),
            unit="seconds",
            window_start=window_start,
            window_end=window_end,
            evidence={"sample_size": len(durations)},
            confidence=confidence_for_sample_size(len(durations)),
        )


class WorkflowRetryRateMetric:
    definition = MetricDefinition(
        id="workflow_average_retries",
        name="Average Retries per Workflow Execution",
        description=(
            "Average number of stage-level retries across workflow executions that "
            "reached a terminal state in the window — a proxy for how often stages "
            "fail transiently."
        ),
        category=MetricCategory.RELIABILITY,
        formula="AVG(workflow_metrics.retries_total) over terminal executions",
        data_sources=("workflow_executions", "workflow_metrics"),
        window="custom",
        aggregation="average",
        owner="platform-team",
    )

    async def calculate(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> MetricResult:
        if project_id is None:
            raise MissingScopeError(self.definition.id)

        retries = (
            (
                await db.execute(
                    select(WorkflowMetric.retries_total)
                    .join(
                        WorkflowExecution,
                        WorkflowExecution.id == WorkflowMetric.workflow_execution_id,
                    )
                    .where(
                        WorkflowExecution.project_id == project_id,
                        WorkflowExecution.completed_at >= window_start,
                        WorkflowExecution.completed_at <= window_end,
                    )
                )
            )
            .scalars()
            .all()
        )

        if not retries:
            return _unavailable(
                self.definition.id,
                window_start,
                window_end,
                "No workflow executions reached a terminal state in this window.",
            )

        average = sum(retries) / len(retries)
        return MetricResult(
            metric_id=self.definition.id,
            availability=MetricAvailability.AVAILABLE,
            value=round(average, 3),
            unit="retries",
            window_start=window_start,
            window_end=window_end,
            evidence={"sample_size": len(retries), "total_retries": sum(retries)},
            confidence=confidence_for_sample_size(len(retries)),
        )
