"""Request/response schemas for the workflows API. The definition-registration
request body IS forgeai_workflow_engine's own WorkflowDefinition — it's
already a fully-validated Pydantic model (cycle detection, dependency checks,
version format all included), so redefining an equivalent shape here would be
duplication with no benefit, not a layering improvement.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from forgeai_core.workflow_enums import ApprovalDecision, StageStatus, WorkflowStatus


class WorkflowVersionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    version: str
    is_active: bool
    created_at: datetime


class WorkflowVersionDetail(WorkflowVersionPublic):
    graph_spec: dict[str, Any]


class CreateExecutionRequest(BaseModel):
    workflow_key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)


class StageExecutionPublic(BaseModel):
    id: uuid.UUID
    stage_key: str
    status: StageStatus
    attempt_number: int
    output: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None


class WorkflowExecutionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_version_id: uuid.UUID
    project_id: uuid.UUID
    status: WorkflowStatus
    input: dict[str, Any]
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class WorkflowExecutionDetail(WorkflowExecutionPublic):
    stages: list[StageExecutionPublic]


class ApprovalPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_execution_id: uuid.UUID
    stage_execution_id: uuid.UUID | None
    decision: ApprovalDecision | None
    payload: dict[str, Any]
    comment: str | None
    decided_at: datetime | None


class ResolveApprovalRequest(BaseModel):
    decision: ApprovalDecision
    comment: str | None = None
