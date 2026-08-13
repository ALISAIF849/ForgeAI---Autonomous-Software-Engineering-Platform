"""Every domain error this package raises. Same one-file, catch-the-base-class
convention as forgeai_workflow_engine.exceptions / forgeai_model_router.exceptions.
"""

from __future__ import annotations


class MemoryEngineError(Exception):
    """Base class for every error this package raises."""


class ArchitectureDecisionNotFoundError(MemoryEngineError):
    def __init__(self, decision_id: object) -> None:
        self.decision_id = decision_id
        super().__init__(f"No architecture decision found for id '{decision_id}'.")


class DecisionNotSupersedableError(MemoryEngineError):
    def __init__(self, decision_id: object, status: str) -> None:
        self.decision_id = decision_id
        self.status = status
        super().__init__(
            f"Architecture decision '{decision_id}' cannot be superseded from status "
            f"'{status}' — only an ACCEPTED decision can be superseded."
        )


class DecisionNotDecidableError(MemoryEngineError):
    def __init__(self, decision_id: object, status: str, attempted: str) -> None:
        self.decision_id = decision_id
        self.status = status
        self.attempted = attempted
        super().__init__(
            f"Cannot {attempted} architecture decision '{decision_id}' — it is in status "
            f"'{status}', not PROPOSED."
        )
