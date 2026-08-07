"""Pure decision logic for stage timeouts — same separation as retry_engine.py:
this only answers "has this stage been RUNNING too long, and what should
happen", the Executor persists the consequence. Real trigger case: a worker
process crashed (or a real, long-running capability is still executing)
between ticks, leaving a stage stranded in RUNNING with a stale started_at —
the Executor reaps these at the top of advance(), a scan a purely synchronous,
completes-within-one-tick FakeStageRunner can never itself produce.
"""

from __future__ import annotations

from datetime import datetime

from forgeai_core.policies import TimeoutAction, TimeoutPolicy


def has_timed_out(policy: TimeoutPolicy, started_at: datetime, *, now: datetime) -> bool:
    if policy.seconds is None:
        return False
    return (now - started_at).total_seconds() > policy.seconds


def action_for_timeout(policy: TimeoutPolicy) -> TimeoutAction:
    return policy.on_timeout
