"""Pure decision logic for stage retries — no I/O, no persistence, matching
state_machine.py's separation: this module only answers "should this retry,
and when", the Executor (2.3/2.4) is the one that actually persists the
decision.

`max_attempts` counts *retries*, not total attempts (see RetryPolicy's own
docstring: "0 = no automatic retry"). An attempt_number of N means N attempts
have already been made; a retry is allowed while N <= max_attempts, so
max_attempts=2 permits 1 initial attempt + 2 retries = 3 attempts total.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from forgeai_core.policies import RetryPolicy


def should_retry(policy: RetryPolicy, attempt_number: int) -> bool:
    return attempt_number <= policy.max_attempts


def compute_backoff_seconds(policy: RetryPolicy, attempt_number: int) -> float:
    """Exponential backoff: backoff_seconds * multiplier^(attempt_number - 1),
    capped at max_backoff_seconds. attempt_number is the attempt that just
    failed (1-indexed), so the first retry (after attempt 1) uses the base
    backoff_seconds unmultiplied."""
    raw = policy.backoff_seconds * (policy.backoff_multiplier ** (attempt_number - 1))
    return min(raw, policy.max_backoff_seconds)


@dataclass(frozen=True, slots=True)
class RetryDecision:
    should_retry: bool
    retry_after: datetime | None = None


def decide(policy: RetryPolicy, attempt_number: int, *, now: datetime) -> RetryDecision:
    if not should_retry(policy, attempt_number):
        return RetryDecision(should_retry=False)
    delay = compute_backoff_seconds(policy, attempt_number)
    return RetryDecision(should_retry=True, retry_after=now + timedelta(seconds=delay))
