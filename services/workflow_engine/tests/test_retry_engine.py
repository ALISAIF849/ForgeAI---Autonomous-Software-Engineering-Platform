from __future__ import annotations

from datetime import UTC, datetime

from forgeai_core.policies import RetryPolicy
from forgeai_workflow_engine import retry_engine


class TestShouldRetry:
    def test_zero_max_attempts_never_retries(self) -> None:
        policy = RetryPolicy(max_attempts=0)
        assert retry_engine.should_retry(policy, attempt_number=1) is False

    def test_retries_while_attempt_number_within_budget(self) -> None:
        policy = RetryPolicy(max_attempts=2)
        assert retry_engine.should_retry(policy, attempt_number=1) is True
        assert retry_engine.should_retry(policy, attempt_number=2) is True
        assert retry_engine.should_retry(policy, attempt_number=3) is False


class TestBackoff:
    def test_first_retry_uses_base_backoff(self) -> None:
        policy = RetryPolicy(
            max_attempts=5, backoff_seconds=2.0, backoff_multiplier=2.0, max_backoff_seconds=100.0
        )
        assert retry_engine.compute_backoff_seconds(policy, attempt_number=1) == 2.0

    def test_backoff_grows_exponentially(self) -> None:
        policy = RetryPolicy(
            max_attempts=5, backoff_seconds=2.0, backoff_multiplier=2.0, max_backoff_seconds=100.0
        )
        assert retry_engine.compute_backoff_seconds(policy, attempt_number=2) == 4.0
        assert retry_engine.compute_backoff_seconds(policy, attempt_number=3) == 8.0

    def test_backoff_is_capped(self) -> None:
        policy = RetryPolicy(
            max_attempts=10, backoff_seconds=2.0, backoff_multiplier=2.0, max_backoff_seconds=5.0
        )
        assert retry_engine.compute_backoff_seconds(policy, attempt_number=5) == 5.0


class TestDecide:
    def test_decides_not_to_retry_past_budget(self) -> None:
        policy = RetryPolicy(max_attempts=1)
        decision = retry_engine.decide(policy, attempt_number=2, now=datetime.now(UTC))
        assert decision.should_retry is False
        assert decision.retry_after is None

    def test_decides_to_retry_and_computes_retry_after(self) -> None:
        policy = RetryPolicy(max_attempts=1, backoff_seconds=10.0)
        now = datetime.now(UTC)
        decision = retry_engine.decide(policy, attempt_number=1, now=now)
        assert decision.should_retry is True
        assert decision.retry_after is not None
        assert (decision.retry_after - now).total_seconds() == 10.0
