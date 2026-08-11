"""The plug point for "how does a completion actually happen" — same
ABC-not-Protocol reasoning as forgeai_workflow_engine.runner.StageRunner: a
real, minimal contract every adapter implements.

MockProvider is a genuine first-class provider choice, not a test-only
double — docs/architecture/06-model-router.md's own Sprint 3 brief lists
"Gemini/OpenAI/Anthropic/Mock providers" side by side. It's what local
development and CI run against until a real provider (Gemini — sub-sprint
3.2) is wired in: deterministic and free, not randomized, so anything
asserting on its output stays stable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from forgeai_model_router.exceptions import ProviderError
from forgeai_model_router.profile import ModelProfile
from forgeai_model_router.types import CompletionRequest, ProviderResult


class ModelProvider(ABC):
    @abstractmethod
    async def complete(
        self, request: CompletionRequest, profile: ModelProfile
    ) -> ProviderResult: ...


def _estimate_tokens(text: str) -> int:
    """A rough, honestly-approximate chars-per-token heuristic — real token
    counts come from a real provider's own tokenizer (3.2+); this exists so
    MockProvider's usage numbers are non-trivial (proportional to input/
    output length) rather than a hardcoded constant that would make cost
    computation untestable."""
    return max(1, len(text) // 4)


class MockProvider(ModelProvider):
    def __init__(self, *, fail_first_n_calls: int = 0) -> None:
        self.fail_first_n_calls = fail_first_n_calls
        self.call_count = 0
        self.requests: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest, profile: ModelProfile) -> ProviderResult:
        self.call_count += 1
        self.requests.append(request)
        if self.call_count <= self.fail_first_n_calls:
            raise ProviderError(f"mock provider scripted failure (call {self.call_count})")

        last_message = request.messages[-1].content
        text = f"[mock:{profile.model_id}] {last_message}"
        return ProviderResult(
            text=text,
            finish_reason="stop",
            input_tokens=_estimate_tokens(last_message),
            output_tokens=_estimate_tokens(text),
        )
