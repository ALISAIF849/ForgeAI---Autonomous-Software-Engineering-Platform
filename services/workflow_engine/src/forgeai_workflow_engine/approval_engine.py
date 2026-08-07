"""Pure decision logic for what a resolved approval means for execution — same
separation as retry_engine.py/timeout_engine.py: this only answers "does this
decision resume or halt the gated stage", the Executor (resolve_approval())
persists the consequence and actually re-runs the stage.
"""

from __future__ import annotations

import enum

from forgeai_core.workflow_enums import ApprovalDecision
from forgeai_workflow_engine.exceptions import UnsupportedApprovalDecisionError


class ApprovalOutcome(enum.StrEnum):
    RESUME = "resume"
    HALT = "halt"


_OUTCOME_BY_DECISION: dict[ApprovalDecision, ApprovalOutcome] = {
    ApprovalDecision.APPROVE: ApprovalOutcome.RESUME,
    # Per state_machine.py's own design: WAITING_APPROVAL has no self-loop, so
    # "send it back for changes" is modeled the same as approval — the stage
    # re-executes. Whatever changed is expected to already be reflected in
    # its input by the time this is called.
    ApprovalDecision.REQUEST_CHANGES: ApprovalOutcome.RESUME,
    ApprovalDecision.REJECT: ApprovalOutcome.HALT,
    # The approval itself expired without a human deciding — same terminal
    # effect as an explicit reject.
    ApprovalDecision.TIMEOUT: ApprovalOutcome.HALT,
}


def outcome_for_decision(decision: ApprovalDecision) -> ApprovalOutcome:
    try:
        return _OUTCOME_BY_DECISION[decision]
    except KeyError:
        raise UnsupportedApprovalDecisionError(decision) from None
