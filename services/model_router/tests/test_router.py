from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from forgeai_core.policies import RetryPolicy, TimeoutPolicy
from forgeai_model_router.exceptions import AllModelsExhaustedError
from forgeai_model_router.profile import ModelProfile, ModelTier
from forgeai_model_router.provider import MockProvider, ModelProvider
from forgeai_model_router.registry import ModelRegistry
from forgeai_model_router.router import ModelRouter
from forgeai_model_router.types import CompletionRequest, ModelMessage, ProviderResult, Role


def _profile(key: str, *, provider: str = "mock", is_active: bool = True) -> ModelProfile:
    return ModelProfile(
        key=key,
        provider=provider,
        model_id=f"{provider}-{key}",
        tier=ModelTier.FAST_CHEAP,
        context_window=8000,
        cost_per_1m_input=Decimal("1.00"),
        cost_per_1m_output=Decimal("2.00"),
        is_active=is_active,
    )


def _request(content: str = "hello world") -> CompletionRequest:
    return CompletionRequest(messages=[ModelMessage(role=Role.USER, content=content)])


class SlowProvider(ModelProvider):
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self.call_count = 0

    async def complete(self, request: CompletionRequest, profile: ModelProfile) -> ProviderResult:
        self.call_count += 1
        await asyncio.sleep(self.delay_seconds)
        return ProviderResult(
            text="too slow", finish_reason="stop", input_tokens=1, output_tokens=1
        )


class TestSuccessfulCompletion:
    async def test_completes_on_the_first_try_and_computes_cost(self) -> None:
        registry = ModelRegistry()
        registry.register(_profile("fast"))
        router = ModelRouter(registry, {"mock": MockProvider()})

        response = await router.complete(["fast"], _request("hi"))

        assert response.model_key == "fast"
        assert response.attempts == 1
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0
        expected_cost = (
            Decimal(response.usage.input_tokens) / Decimal(1_000_000) * Decimal("1.00")
        ) + (Decimal(response.usage.output_tokens) / Decimal(1_000_000) * Decimal("2.00"))
        assert response.usage.cost_usd == expected_cost


class TestRetry:
    async def test_retries_within_the_same_model_before_succeeding(self) -> None:
        registry = ModelRegistry()
        registry.register(_profile("fast"))
        provider = MockProvider(fail_first_n_calls=2)
        router = ModelRouter(registry, {"mock": provider})

        response = await router.complete(
            ["fast"], _request(), retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.01)
        )

        assert response.attempts == 3
        assert provider.call_count == 3

    async def test_exhausting_retries_on_one_model_falls_through_to_the_next(self) -> None:
        # Two different provider *instances* need two different provider
        # names in the registry — "primary" is served by a provider that
        # always fails, "secondary" by one registered under a different
        # provider key that always succeeds.
        registry = ModelRegistry()
        registry.register(_profile("primary", provider="mock-broken"))
        registry.register(_profile("secondary", provider="mock-working"))
        always_fails = MockProvider(fail_first_n_calls=999)
        works = MockProvider()
        router = ModelRouter(registry, {"mock-broken": always_fails, "mock-working": works})

        response = await router.complete(
            ["primary", "secondary"],
            _request(),
            retry_policy=RetryPolicy(max_attempts=0),
        )

        assert response.model_key == "secondary"
        assert (
            always_fails.call_count == 1
        )  # no retries (max_attempts=0), one try then fall through
        assert works.call_count == 1

    async def test_all_models_exhausted_raises(self) -> None:
        registry = ModelRegistry()
        registry.register(_profile("only"))
        router = ModelRouter(registry, {"mock": MockProvider(fail_first_n_calls=999)})

        with pytest.raises(AllModelsExhaustedError):
            await router.complete(["only"], _request(), retry_policy=RetryPolicy(max_attempts=0))

    async def test_empty_model_key_list_raises_immediately(self) -> None:
        registry = ModelRegistry()
        router = ModelRouter(registry, {})

        with pytest.raises(AllModelsExhaustedError):
            await router.complete([], _request())


class TestTimeout:
    async def test_a_call_exceeding_its_timeout_is_treated_as_a_failure(self) -> None:
        # TimeoutPolicy.seconds is an int (gt=0), so the shortest expressible
        # timeout is 1s — the provider just needs to run longer than that;
        # asyncio.wait_for cancels at the 1s mark, not after the full delay.
        registry = ModelRegistry()
        registry.register(_profile("slow"))
        provider = SlowProvider(delay_seconds=2.0)
        router = ModelRouter(registry, {"mock": provider})

        with pytest.raises(AllModelsExhaustedError):
            await router.complete(
                ["slow"],
                _request(),
                retry_policy=RetryPolicy(max_attempts=0),
                timeout_policy=TimeoutPolicy(seconds=1),
            )

        assert provider.call_count == 1

    async def test_a_call_within_its_timeout_succeeds(self) -> None:
        registry = ModelRegistry()
        registry.register(_profile("fast"))
        router = ModelRouter(registry, {"mock": MockProvider()})

        response = await router.complete(
            ["fast"], _request(), timeout_policy=TimeoutPolicy(seconds=5)
        )

        assert response.model_key == "fast"


class TestInactiveAndUnconfiguredModels:
    async def test_an_inactive_model_in_the_fallback_chain_is_skipped(self) -> None:
        registry = ModelRegistry()
        registry.register(_profile("inactive", is_active=False))
        registry.register(_profile("active"))
        provider = MockProvider()
        router = ModelRouter(registry, {"mock": provider})

        response = await router.complete(["inactive", "active"], _request())

        assert response.model_key == "active"
        assert provider.call_count == 1  # never actually called for "inactive"

    async def test_a_provider_with_no_registered_implementation_falls_through(self) -> None:
        registry = ModelRegistry()
        registry.register(_profile("unwired", provider="nonexistent"))
        registry.register(_profile("wired"))
        provider = MockProvider()
        router = ModelRouter(registry, {"mock": provider})

        response = await router.complete(["unwired", "wired"], _request())

        assert response.model_key == "wired"
