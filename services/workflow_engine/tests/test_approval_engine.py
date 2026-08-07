from __future__ import annotations

import pytest

from forgeai_core.workflow_enums import ApprovalDecision
from forgeai_workflow_engine import approval_engine
from forgeai_workflow_engine.approval_engine import ApprovalOutcome
from forgeai_workflow_engine.exceptions import UnsupportedApprovalDecisionError


class TestOutcomeForDecision:
    @pytest.mark.parametrize(
        "decision", [ApprovalDecision.APPROVE, ApprovalDecision.REQUEST_CHANGES]
    )
    def test_approve_and_request_changes_resume(self, decision: ApprovalDecision) -> None:
        assert approval_engine.outcome_for_decision(decision) == ApprovalOutcome.RESUME

    @pytest.mark.parametrize("decision", [ApprovalDecision.REJECT, ApprovalDecision.TIMEOUT])
    def test_reject_and_timeout_halt(self, decision: ApprovalDecision) -> None:
        assert approval_engine.outcome_for_decision(decision) == ApprovalOutcome.HALT

    def test_escalate_is_not_supported(self) -> None:
        with pytest.raises(UnsupportedApprovalDecisionError):
            approval_engine.outcome_for_decision(ApprovalDecision.ESCALATE)
