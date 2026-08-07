"""Every domain error the engine raises. Kept in one file, imported by every
other module, so a caller can catch `WorkflowEngineError` to handle anything
the engine raises without needing to know which submodule raised it.
"""

from __future__ import annotations


class WorkflowEngineError(Exception):
    """Base class for every error this package raises."""


class InvalidTransitionError(WorkflowEngineError):
    def __init__(self, current: str, target: str, entity: str = "workflow") -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition {entity} from '{current}' to '{target}'.")


class DefinitionValidationError(WorkflowEngineError, ValueError):
    """A WorkflowDefinition failed validation — bad shape, not a registry problem.

    Also inherits ValueError: Pydantic only auto-wraps ValueError/TypeError/
    AssertionError raised inside a field_validator/model_validator into its own
    ValidationError — a plain WorkflowEngineError subclass would propagate
    unwrapped, which would in turn make DefinitionLoader's `except
    ValidationError` silently miss exactly the custom validation failures
    (cycles, unknown stage references, bad version strings) it exists to catch.
    """


class UnknownStageDependencyError(DefinitionValidationError):
    def __init__(self, stage_id: str, unknown_dependency: str) -> None:
        self.stage_id = stage_id
        self.unknown_dependency = unknown_dependency
        super().__init__(
            f"Stage '{stage_id}' depends on '{unknown_dependency}', which is not a defined stage."
        )


class CyclicDependencyError(DefinitionValidationError):
    def __init__(self, unresolved_stage_ids: list[str]) -> None:
        self.unresolved_stage_ids = unresolved_stage_ids
        super().__init__(
            "Stage dependency graph has a cycle — these stages can never become "
            f"ready: {', '.join(unresolved_stage_ids)}."
        )


class DefinitionAlreadyRegisteredError(WorkflowEngineError):
    def __init__(self, key: str, version: str) -> None:
        self.key = key
        self.version = version
        super().__init__(
            f"Workflow definition '{key}' version '{version}' is already registered "
            "— definitions are immutable once registered; register a new version instead."
        )


class DefinitionNotFoundError(WorkflowEngineError):
    def __init__(self, key: str, version: str) -> None:
        self.key = key
        self.version = version
        super().__init__(f"No workflow definition registered for '{key}' version '{version}'.")


class InvalidVersionError(DefinitionValidationError):
    def __init__(self, version: str) -> None:
        self.version = version
        super().__init__(f"'{version}' is not a valid version string — expected 'N.N.N'.")


class ExecutionNotFoundError(WorkflowEngineError):
    def __init__(self, execution_id: object) -> None:
        self.execution_id = execution_id
        super().__init__(f"No workflow execution found for id '{execution_id}'.")


class StageExecutionNotFoundError(WorkflowEngineError):
    def __init__(self, stage_execution_id: object) -> None:
        self.stage_execution_id = stage_execution_id
        super().__init__(f"No workflow stage execution found for id '{stage_execution_id}'.")


class WorkflowVersionNotFoundError(WorkflowEngineError):
    def __init__(self, workflow_version_id: object) -> None:
        self.workflow_version_id = workflow_version_id
        super().__init__(f"No workflow version found for id '{workflow_version_id}'.")


class StageNotSkippableError(WorkflowEngineError):
    def __init__(self, stage_execution_id: object) -> None:
        self.stage_execution_id = stage_execution_id
        super().__init__(
            f"Stage execution '{stage_execution_id}' does not allow skipping "
            "(its definition has allow_skip=False)."
        )


class ApprovalNotFoundError(WorkflowEngineError):
    def __init__(self, approval_id: object) -> None:
        self.approval_id = approval_id
        super().__init__(f"No workflow approval found for id '{approval_id}'.")


class ApprovalAlreadyDecidedError(WorkflowEngineError):
    def __init__(self, approval_id: object) -> None:
        self.approval_id = approval_id
        super().__init__(
            f"Approval '{approval_id}' has already been decided and cannot be resolved again."
        )


class UnsupportedApprovalDecisionError(WorkflowEngineError):
    def __init__(self, decision: object) -> None:
        self.decision = decision
        super().__init__(f"Approval decision '{decision}' is not supported by resolve_approval().")
