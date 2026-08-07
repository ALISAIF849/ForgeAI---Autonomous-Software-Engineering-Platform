"""Shared, genuinely generic execution-policy primitives — retry/timeout
behavior isn't specific to workflows, stages, or capabilities, so it lives
here once rather than being redefined per package. Originally defined inside
services/workflow_engine (Sprint 2); moved here in Sprint 3 when
services/capability_registry needed the identical shape, per this sprint's
own "everything must be modular" instruction — duplicating it a second time
would have violated that directly.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class TimeoutAction(enum.StrEnum):
    RETRY = "retry"
    ESCALATE = "escalate"
    CANCEL = "cancel"


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=0, ge=0, description="0 = no automatic retry.")
    backoff_seconds: float = Field(default=1.0, gt=0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    max_backoff_seconds: float = Field(default=300.0, gt=0)


class TimeoutPolicy(BaseModel):
    seconds: int | None = Field(default=None, gt=0, description="None = no timeout.")
    on_timeout: TimeoutAction = TimeoutAction.CANCEL
