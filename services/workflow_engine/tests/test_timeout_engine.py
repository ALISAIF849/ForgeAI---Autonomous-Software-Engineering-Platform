from __future__ import annotations

from datetime import UTC, datetime, timedelta

from forgeai_core.policies import TimeoutAction, TimeoutPolicy
from forgeai_workflow_engine import timeout_engine


class TestHasTimedOut:
    def test_no_timeout_configured_never_times_out(self) -> None:
        policy = TimeoutPolicy(seconds=None)
        started = datetime.now(UTC) - timedelta(days=365)
        assert timeout_engine.has_timed_out(policy, started, now=datetime.now(UTC)) is False

    def test_within_the_window_has_not_timed_out(self) -> None:
        policy = TimeoutPolicy(seconds=60)
        now = datetime.now(UTC)
        started = now - timedelta(seconds=30)
        assert timeout_engine.has_timed_out(policy, started, now=now) is False

    def test_past_the_window_has_timed_out(self) -> None:
        policy = TimeoutPolicy(seconds=60)
        now = datetime.now(UTC)
        started = now - timedelta(seconds=61)
        assert timeout_engine.has_timed_out(policy, started, now=now) is True


class TestActionForTimeout:
    def test_returns_the_policys_configured_action(self) -> None:
        assert (
            timeout_engine.action_for_timeout(TimeoutPolicy(on_timeout=TimeoutAction.RETRY))
            == TimeoutAction.RETRY
        )
        assert (
            timeout_engine.action_for_timeout(TimeoutPolicy(on_timeout=TimeoutAction.ESCALATE))
            == TimeoutAction.ESCALATE
        )
        assert (
            timeout_engine.action_for_timeout(TimeoutPolicy(on_timeout=TimeoutAction.CANCEL))
            == TimeoutAction.CANCEL
        )
