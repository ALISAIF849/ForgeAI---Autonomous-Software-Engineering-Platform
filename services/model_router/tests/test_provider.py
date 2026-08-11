from __future__ import annotations

from decimal import Decimal

import pytest

from forgeai_model_router.exceptions import ProviderError
from forgeai_model_router.profile import ModelProfile, ModelTier
from forgeai_model_router.provider import MockProvider
from forgeai_model_router.types import CompletionRequest, ModelMessage, Role

_PROFILE = ModelProfile(
    key="fast",
    provider="mock",
    model_id="mock-fast-1",
    tier=ModelTier.FAST_CHEAP,
    context_window=8000,
    cost_per_1m_input=Decimal("1.00"),
    cost_per_1m_output=Decimal("2.00"),
)


def _request(content: str = "hello") -> CompletionRequest:
    return CompletionRequest(messages=[ModelMessage(role=Role.USER, content=content)])


class TestMockProvider:
    async def test_returns_a_deterministic_response_derived_from_the_input(self) -> None:
        provider = MockProvider()

        result = await provider.complete(_request("what is 2+2"), _PROFILE)

        assert result.text == "[mock:mock-fast-1] what is 2+2"
        assert result.finish_reason == "stop"
        assert result.input_tokens > 0
        assert result.output_tokens > 0

    async def test_is_deterministic_across_repeated_calls_with_the_same_input(self) -> None:
        provider = MockProvider()

        first = await provider.complete(_request("same input"), _PROFILE)
        second = await provider.complete(_request("same input"), _PROFILE)

        assert first.text == second.text
        assert first.input_tokens == second.input_tokens

    async def test_records_every_request_it_receives(self) -> None:
        provider = MockProvider()

        await provider.complete(_request("first"), _PROFILE)
        await provider.complete(_request("second"), _PROFILE)

        assert len(provider.requests) == 2
        assert provider.requests[0].messages[0].content == "first"
        assert provider.requests[1].messages[0].content == "second"

    async def test_scripted_failures_raise_provider_error_then_recover(self) -> None:
        provider = MockProvider(fail_first_n_calls=2)

        with pytest.raises(ProviderError):
            await provider.complete(_request(), _PROFILE)
        with pytest.raises(ProviderError):
            await provider.complete(_request(), _PROFILE)

        result = await provider.complete(_request(), _PROFILE)
        assert result.text.startswith("[mock:")
