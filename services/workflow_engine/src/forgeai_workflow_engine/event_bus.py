"""The Event Bus docs/architecture/03-workflow-engine.md describes — but per
state_manager.py's own docstring, "transitions ARE the events": every
WorkflowEvent row is already written the moment a transition happens (2.2/
2.3). What's been missing is the *consumption* side: a way for other
in-process subsystems (a future notification capability, an audit log
writer, or simply a test spy) to react without WorkflowStateManager needing
to know who's listening.

In-process, not a poll-the-table consumer: publishing happens synchronously,
right after the event is persisted, in the same call stack as the
transition that caused it — no separate worker loop to build or to lag
behind. A handler's failure must never break the transition that triggered
it (an observability hook crashing the thing it's observing would be worse
than not having it), so publish() isolates handler exceptions rather than
letting them propagate; callers that care can inspect `handler_errors`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from forgeai_core.models.workflow_event import WorkflowEvent

EventHandler = Callable[[WorkflowEvent], Awaitable[None]]


def _matches(pattern: str, event_type: str) -> bool:
    """ "*" matches anything; "workflow.*" matches any event_type starting
    with "workflow." (i.e. every workflow-level event, not stage-level);
    anything else must match exactly."""
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return event_type.startswith(pattern[:-1])
    return pattern == event_type


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[tuple[str, EventHandler]] = []
        self.handler_errors: list[tuple[WorkflowEvent, BaseException]] = []

    def subscribe(self, pattern: str, handler: EventHandler) -> None:
        self._subscribers.append((pattern, handler))

    async def publish(self, event: WorkflowEvent) -> None:
        for pattern, handler in self._subscribers:
            if not _matches(pattern, event.event_type):
                continue
            try:
                await handler(event)
            except Exception as exc:
                self.handler_errors.append((event, exc))
