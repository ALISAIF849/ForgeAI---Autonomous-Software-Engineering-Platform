"""API-shaped wrappers around forgeai_workflow_engine's domain exceptions —
the service layer catches the domain exception and raises one of these
instead, same pattern as modules/auth and modules/organizations: every
exception the API returns is an AppError subclass with a stable error_type,
never a raw domain exception leaking through (those don't have status codes
or RFC 7807 shape)."""

from forgeai_api.core.exceptions import ConflictError, NotFoundError, UnprocessableEntityError


class WorkflowVersionNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("Workflow version not found.", error_type="workflow_version_not_found")


class WorkflowExecutionNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("Workflow execution not found.", error_type="execution_not_found")


class StageExecutionNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("Stage execution not found.", error_type="stage_execution_not_found")


class ApprovalNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("Approval not found.", error_type="approval_not_found")


class WorkflowVersionAlreadyRegisteredError(ConflictError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, error_type="version_already_registered")


class StageNotSkippableError(ConflictError):
    def __init__(self) -> None:
        super().__init__("This stage does not allow skipping.", error_type="stage_not_skippable")


class InvalidWorkflowTransitionError(ConflictError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, error_type="invalid_transition")


class ApprovalAlreadyDecidedError(ConflictError):
    def __init__(self) -> None:
        super().__init__(
            "This approval has already been decided.", error_type="approval_already_decided"
        )


class UnsupportedApprovalDecisionError(UnprocessableEntityError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, error_type="unsupported_approval_decision")
