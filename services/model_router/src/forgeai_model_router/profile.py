"""A ModelProfile describes one routable model — provider, tier, cost rates —
looked up by `key` at call time rather than a model ID ever being hardcoded
in capability/workflow code (docs/architecture/06-model-router.md §2). `key`
is a plain string, not a UUID, for this sub-sprint: this is an in-process
registry only (no DB yet — see registry.py's own docstring), so a surrogate
UUID primary key would be premature; persistence (sub-sprint 3.2) is where
that identity question actually needs answering.
"""

from __future__ import annotations

import enum
from decimal import Decimal

from pydantic import BaseModel, Field


class ModelTier(enum.StrEnum):
    FAST_CHEAP = "fast_cheap"
    BALANCED = "balanced"
    HIGH_CAPABILITY = "high_capability"


class ModelProfile(BaseModel):
    key: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    tier: ModelTier
    context_window: int = Field(gt=0)
    supports_tools: bool = False
    supports_structured_output: bool = False
    cost_per_1m_input: Decimal = Field(ge=0)
    cost_per_1m_output: Decimal = Field(ge=0)
    is_active: bool = True
