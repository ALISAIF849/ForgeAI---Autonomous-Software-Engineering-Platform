"""Ties the registry (3.1), providers (3.1), and forgeai-core's generic
RetryPolicy/TimeoutPolicy together: given an ordered list of candidate model
keys (a caller-supplied fallback chain — full tier-based auto-fallback per
docs/architecture/06-model-router.md §3 is DB-backed routing-rule territory,
sub-sprint 3.2+, not this one), try each in order, retrying each with
exponential backoff before falling through to the next.

Deliberately its own local retry loop, not forgeai_workflow_engine.retry_engine:
that module's `decide()` is shaped around a persisted WorkflowStageExecution's
attempt_number — there's no equivalent persisted state for a single
synchronous completion call. Both consume the same RetryPolicy contract from
forgeai-core (that's the reuse that actually matters), just with their own
call site's control flow around it.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from forgeai_core.policies import RetryPolicy, TimeoutPolicy
from forgeai_model_router.exceptions import AllModelsExhaustedError, ProviderNotConfiguredError
from forgeai_model_router.profile import ModelProfile
from forgeai_model_router.provider import ModelProvider
from forgeai_model_router.recorder import UsageRecorder
from forgeai_model_router.registry import ModelRegistry
from forgeai_model_router.types import (
    CompletionRequest,
    CompletionResponse,
    ProviderResult,
    TokenUsage,
)


def _compute_cost(profile: ModelProfile, input_tokens: int, output_tokens: int) -> Decimal:
    input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * profile.cost_per_1m_input
    output_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * profile.cost_per_1m_output
    return input_cost + output_cost


class ModelRouter:
    def __init__(self, registry: ModelRegistry, providers: dict[str, ModelProvider]) -> None:
        self._registry = registry
        self._providers = providers

    async def complete(
        self,
        model_keys: list[str],
        request: CompletionRequest,
        *,
        retry_policy: RetryPolicy | None = None,
        timeout_policy: TimeoutPolicy | None = None,
        usage_recorder: UsageRecorder | None = None,
        organization_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        workflow_execution_id: uuid.UUID | None = None,
    ) -> CompletionResponse:
        if not model_keys:
            raise AllModelsExhaustedError(model_keys)

        retry_policy = retry_policy or RetryPolicy()
        total_attempts = 0
        last_error: Exception | None = None

        for model_key in model_keys:
            profile = self._registry.get(model_key)
            if not profile.is_active:
                continue
            provider = self._providers.get(profile.provider)
            if provider is None:
                last_error = ProviderNotConfiguredError(profile.provider)
                continue

            attempt = 0
            delay = retry_policy.backoff_seconds
            while True:
                attempt += 1
                total_attempts += 1
                try:
                    result = await self._call_with_timeout(
                        provider, request, profile, timeout_policy
                    )
                except Exception as exc:  # any failure here is retryable/fallback-worthy
                    last_error = exc
                    if attempt > retry_policy.max_attempts:
                        break  # exhausted retries for this model — try the next candidate
                    await asyncio.sleep(min(delay, retry_policy.max_backoff_seconds))
                    delay *= retry_policy.backoff_multiplier
                    continue

                usage = TokenUsage(
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_usd=_compute_cost(profile, result.input_tokens, result.output_tokens),
                )
                if usage_recorder is not None:
                    # Recording happens after a successful call, inside the
                    # same attempt — a failed/retried attempt was never
                    # billed by the provider, so it has nothing to record.
                    await usage_recorder.record(
                        model_key,
                        usage,
                        organization_id=organization_id,
                        project_id=project_id,
                        workflow_execution_id=workflow_execution_id,
                    )
                return CompletionResponse(
                    text=result.text,
                    finish_reason=result.finish_reason,
                    model_key=model_key,
                    usage=usage,
                    attempts=total_attempts,
                )

        raise AllModelsExhaustedError(model_keys) from last_error

    @staticmethod
    async def _call_with_timeout(
        provider: ModelProvider,
        request: CompletionRequest,
        profile: ModelProfile,
        timeout_policy: TimeoutPolicy | None,
    ) -> ProviderResult:
        if timeout_policy is not None and timeout_policy.seconds is not None:
            return await asyncio.wait_for(
                provider.complete(request, profile), timeout=timeout_policy.seconds
            )
        return await provider.complete(request, profile)
