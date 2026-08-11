"""Request/response contract for a completion call — provider-agnostic, per
docs/architecture/06-model-router.md §2: nothing here names Gemini, OpenAI,
or Anthropic specifically. `ProviderResult` is a plain dataclass, not a
Pydantic model, deliberately: it's what a ModelProvider hands back before
pricing is applied, an internal seam, not something ever serialized at an API
boundary the way CompletionResponse is.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, Field


class Role(enum.StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ModelMessage(BaseModel):
    role: Role
    content: str = Field(min_length=1)


class CompletionRequest(BaseModel):
    messages: list[ModelMessage] = Field(min_length=1)
    max_tokens: int | None = Field(default=None, gt=0)
    temperature: float = Field(default=0.7, ge=0, le=2)


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """What a ModelProvider returns — raw token counts, no cost. Pricing is a
    ModelProfile/router concern (see router.py's _compute_cost), not
    something every provider adapter needs to know how to do."""

    text: str
    finish_reason: str
    input_tokens: int
    output_tokens: int


class TokenUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=0)


class CompletionResponse(BaseModel):
    text: str
    finish_reason: str
    model_key: str
    usage: TokenUsage
    attempts: int = Field(ge=1)
