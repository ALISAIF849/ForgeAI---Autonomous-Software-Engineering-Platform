"""Workflow/stage/approval status vocabulary — shared between the Pydantic
domain layer (services/workflow_engine, which validates transitions between
these) and the ORM layer (this package's models, which persist them).
Originally defined inside services/workflow_engine (Sprint 2); moved here in
sub-sprint 2.2 because the new WorkflowExecution/WorkflowStageExecution/
WorkflowApproval ORM models need the same enums, and forgeai-core cannot
depend on forgeai-workflow-engine without inverting the existing dependency
direction (workflow_engine already depends on core, for RetryPolicy/
TimeoutPolicy — see policies.py). Same reasoning, same fix, as that move.
"""

import enum


class WorkflowStatus(enum.StrEnum):
    """See forgeai_workflow_engine.state_machine for the validated transition
    graph between these."""

    DRAFT = "draft"
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class StageStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ApprovalDecision(enum.StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    ESCALATE = "escalate"
    TIMEOUT = "timeout"
