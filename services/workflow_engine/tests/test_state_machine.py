import pytest

from forgeai_core.workflow_enums import StageStatus, WorkflowStatus
from forgeai_workflow_engine.exceptions import InvalidTransitionError
from forgeai_workflow_engine.state_machine import (
    StageStateMachine,
    WorkflowStateMachine,
    is_terminal_stage_status,
    is_terminal_workflow_status,
    validate_stage_transition,
    validate_workflow_transition,
)


class TestWorkflowTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (WorkflowStatus.DRAFT, WorkflowStatus.PENDING),
            (WorkflowStatus.PENDING, WorkflowStatus.RUNNING),
            (WorkflowStatus.RUNNING, WorkflowStatus.WAITING_APPROVAL),
            (WorkflowStatus.WAITING_APPROVAL, WorkflowStatus.RUNNING),
            (WorkflowStatus.RUNNING, WorkflowStatus.COMPLETED),
            (WorkflowStatus.FAILED, WorkflowStatus.RETRYING),
            (WorkflowStatus.COMPLETED, WorkflowStatus.ARCHIVED),
        ],
    )
    def test_legal_transitions_are_accepted(
        self, current: WorkflowStatus, target: WorkflowStatus
    ) -> None:
        validate_workflow_transition(current, target)  # must not raise

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (WorkflowStatus.DRAFT, WorkflowStatus.COMPLETED),
            (WorkflowStatus.COMPLETED, WorkflowStatus.RUNNING),
            (WorkflowStatus.ARCHIVED, WorkflowStatus.PENDING),
            (WorkflowStatus.CANCELLED, WorkflowStatus.RUNNING),
            (WorkflowStatus.PENDING, WorkflowStatus.PAUSED),
        ],
    )
    def test_illegal_transitions_are_rejected(
        self, current: WorkflowStatus, target: WorkflowStatus
    ) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_workflow_transition(current, target)

    def test_archived_is_a_true_terminal_state(self) -> None:
        assert is_terminal_workflow_status(WorkflowStatus.ARCHIVED)
        for target in WorkflowStatus:
            with pytest.raises(InvalidTransitionError):
                validate_workflow_transition(WorkflowStatus.ARCHIVED, target)

    def test_running_is_not_terminal(self) -> None:
        assert not is_terminal_workflow_status(WorkflowStatus.RUNNING)


class TestStageTransitions:
    def test_legal_stage_transition(self) -> None:
        validate_stage_transition(StageStatus.PENDING, StageStatus.RUNNING)

    def test_completed_stage_cannot_retry(self) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_stage_transition(StageStatus.COMPLETED, StageStatus.RETRYING)

    def test_failed_stage_can_retry(self) -> None:
        validate_stage_transition(StageStatus.FAILED, StageStatus.RETRYING)

    def test_skipped_is_terminal(self) -> None:
        assert is_terminal_stage_status(StageStatus.SKIPPED)


class TestWorkflowStateMachine:
    def test_starts_in_draft_by_default(self) -> None:
        machine = WorkflowStateMachine()
        assert machine.status == WorkflowStatus.DRAFT
        assert not machine.is_terminal()

    def test_transition_updates_status_and_history(self) -> None:
        machine = WorkflowStateMachine()
        machine.transition_to(WorkflowStatus.PENDING)
        machine.transition_to(WorkflowStatus.RUNNING)

        assert machine.status == WorkflowStatus.RUNNING
        assert [status for status, _ts in machine.history] == [
            WorkflowStatus.DRAFT,
            WorkflowStatus.PENDING,
            WorkflowStatus.RUNNING,
        ]

    def test_invalid_transition_raises_and_leaves_status_unchanged(self) -> None:
        machine = WorkflowStateMachine()
        with pytest.raises(InvalidTransitionError):
            machine.transition_to(WorkflowStatus.COMPLETED)
        assert machine.status == WorkflowStatus.DRAFT

    def test_can_transition_to_reports_without_raising(self) -> None:
        machine = WorkflowStateMachine()
        assert machine.can_transition_to(WorkflowStatus.PENDING) is True
        assert machine.can_transition_to(WorkflowStatus.COMPLETED) is False

    def test_history_is_a_copy_not_a_live_reference(self) -> None:
        machine = WorkflowStateMachine()
        history = machine.history
        machine.transition_to(WorkflowStatus.PENDING)
        assert len(history) == 1  # the earlier snapshot didn't mutate


class TestStageStateMachine:
    def test_starts_pending_and_reaches_completed(self) -> None:
        machine = StageStateMachine()
        machine.transition_to(StageStatus.RUNNING)
        machine.transition_to(StageStatus.COMPLETED)
        assert machine.status == StageStatus.COMPLETED
        assert machine.is_terminal()
