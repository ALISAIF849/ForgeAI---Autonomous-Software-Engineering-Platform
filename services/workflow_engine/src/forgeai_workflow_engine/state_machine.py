"""Validated state transitions for both workflow-level and stage-level status.
Nothing here touches persistence — this is pure in-memory state tracking:
executors, tests, or a persistence layer are all responsible for durability,
this module is only responsible for saying whether a transition is legal.
"""

from __future__ import annotations

from datetime import UTC, datetime

from forgeai_core.workflow_enums import StageStatus, WorkflowStatus
from forgeai_workflow_engine.exceptions import InvalidTransitionError

# Reject is modeled as WAITING_APPROVAL -> FAILED (a deliberate stop, distinct
# from CANCELLED which is reserved for explicit external cancellation regardless
# of approval outcome) — "Request Changes" is WAITING_APPROVAL -> RUNNING (the
# stage re-executes), not a self-loop, since staying in the same state can't be
# represented as a transition at all under this model.
_WORKFLOW_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.DRAFT: frozenset({WorkflowStatus.PENDING, WorkflowStatus.CANCELLED}),
    WorkflowStatus.PENDING: frozenset({WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED}),
    WorkflowStatus.RUNNING: frozenset(
        {
            WorkflowStatus.PAUSED,
            WorkflowStatus.WAITING_APPROVAL,
            WorkflowStatus.RETRYING,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.PAUSED: frozenset({WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED}),
    WorkflowStatus.WAITING_APPROVAL: frozenset(
        {WorkflowStatus.RUNNING, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}
    ),
    WorkflowStatus.RETRYING: frozenset(
        {WorkflowStatus.RUNNING, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}
    ),
    WorkflowStatus.COMPLETED: frozenset({WorkflowStatus.ARCHIVED}),
    WorkflowStatus.FAILED: frozenset({WorkflowStatus.RETRYING, WorkflowStatus.ARCHIVED}),
    WorkflowStatus.CANCELLED: frozenset({WorkflowStatus.ARCHIVED}),
    WorkflowStatus.ARCHIVED: frozenset(),
}

_STAGE_TRANSITIONS: dict[StageStatus, frozenset[StageStatus]] = {
    # PENDING -> WAITING_APPROVAL (not via RUNNING first): a `requires_approval`
    # stage is gated *before* it ever runs, per the Executor's advance() — the
    # approval decision is what allows the stage to run at all, not something
    # checked mid-execution.
    StageStatus.PENDING: frozenset(
        {
            StageStatus.RUNNING,
            StageStatus.WAITING_APPROVAL,
            StageStatus.SKIPPED,
            StageStatus.CANCELLED,
        }
    ),
    StageStatus.RUNNING: frozenset(
        {
            StageStatus.WAITING_APPROVAL,
            StageStatus.RETRYING,
            StageStatus.COMPLETED,
            StageStatus.FAILED,
            StageStatus.CANCELLED,
        }
    ),
    StageStatus.WAITING_APPROVAL: frozenset(
        {StageStatus.RUNNING, StageStatus.FAILED, StageStatus.CANCELLED}
    ),
    StageStatus.RETRYING: frozenset(
        {StageStatus.RUNNING, StageStatus.FAILED, StageStatus.CANCELLED}
    ),
    StageStatus.COMPLETED: frozenset(),
    StageStatus.FAILED: frozenset({StageStatus.RETRYING}),
    StageStatus.SKIPPED: frozenset(),
    StageStatus.CANCELLED: frozenset(),
}

_TERMINAL_WORKFLOW_STATUSES = frozenset(
    {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.ARCHIVED,
    }
)
_TERMINAL_STAGE_STATUSES = frozenset(
    {StageStatus.COMPLETED, StageStatus.SKIPPED, StageStatus.CANCELLED}
)


def is_terminal_workflow_status(status: WorkflowStatus) -> bool:
    return status in _TERMINAL_WORKFLOW_STATUSES


def is_terminal_stage_status(status: StageStatus) -> bool:
    return status in _TERMINAL_STAGE_STATUSES


def validate_workflow_transition(current: WorkflowStatus, target: WorkflowStatus) -> None:
    if target not in _WORKFLOW_TRANSITIONS[current]:
        raise InvalidTransitionError(current.value, target.value, entity="workflow")


def validate_stage_transition(current: StageStatus, target: StageStatus) -> None:
    if target not in _STAGE_TRANSITIONS[current]:
        raise InvalidTransitionError(current.value, target.value, entity="stage")


class WorkflowStateMachine:
    """Tracks one workflow execution's status plus its full transition history —
    the in-memory counterpart to the `current_state` + history that
    docs/architecture/07-database-schema.md's `workflow_executions` /
    `workflow_events` tables persist (wired up in sub-sprint 2.2)."""

    def __init__(self, initial: WorkflowStatus = WorkflowStatus.DRAFT) -> None:
        self._status = initial
        self._history: list[tuple[WorkflowStatus, datetime]] = [(initial, datetime.now(UTC))]

    @property
    def status(self) -> WorkflowStatus:
        return self._status

    @property
    def history(self) -> list[tuple[WorkflowStatus, datetime]]:
        return list(self._history)

    def can_transition_to(self, target: WorkflowStatus) -> bool:
        return target in _WORKFLOW_TRANSITIONS[self._status]

    def transition_to(self, target: WorkflowStatus) -> None:
        validate_workflow_transition(self._status, target)
        self._status = target
        self._history.append((target, datetime.now(UTC)))

    def is_terminal(self) -> bool:
        return is_terminal_workflow_status(self._status)


class StageStateMachine:
    def __init__(self, initial: StageStatus = StageStatus.PENDING) -> None:
        self._status = initial
        self._history: list[tuple[StageStatus, datetime]] = [(initial, datetime.now(UTC))]

    @property
    def status(self) -> StageStatus:
        return self._status

    @property
    def history(self) -> list[tuple[StageStatus, datetime]]:
        return list(self._history)

    def can_transition_to(self, target: StageStatus) -> bool:
        return target in _STAGE_TRANSITIONS[self._status]

    def transition_to(self, target: StageStatus) -> None:
        validate_stage_transition(self._status, target)
        self._status = target
        self._history.append((target, datetime.now(UTC)))

    def is_terminal(self) -> bool:
        return is_terminal_stage_status(self._status)
