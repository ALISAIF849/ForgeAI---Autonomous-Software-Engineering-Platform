from __future__ import annotations

import uuid

from forgeai_core.models.workflow_event import WorkflowEvent
from forgeai_workflow_engine.event_bus import EventBus


def _event(event_type: str) -> WorkflowEvent:
    return WorkflowEvent(workflow_execution_id=uuid.uuid4(), event_type=event_type, payload={})


class TestPublishSubscribe:
    async def test_subscriber_with_an_exact_match_is_called(self) -> None:
        bus = EventBus()
        received: list[WorkflowEvent] = []

        async def handler(event: WorkflowEvent) -> None:
            received.append(event)

        bus.subscribe("workflow.completed", handler)
        event = _event("workflow.completed")
        await bus.publish(event)

        assert received == [event]

    async def test_subscriber_with_a_different_exact_pattern_is_not_called(self) -> None:
        bus = EventBus()
        received: list[WorkflowEvent] = []

        async def handler(event: WorkflowEvent) -> None:
            received.append(event)

        bus.subscribe("workflow.failed", handler)
        await bus.publish(_event("workflow.completed"))

        assert received == []

    async def test_prefix_wildcard_matches_any_event_in_that_namespace(self) -> None:
        bus = EventBus()
        received: list[str] = []

        async def handler(event: WorkflowEvent) -> None:
            received.append(event.event_type)

        bus.subscribe("stage.*", handler)
        await bus.publish(_event("stage.completed"))
        await bus.publish(_event("stage.failed"))
        await bus.publish(_event("workflow.completed"))  # not "stage." — must not match

        assert received == ["stage.completed", "stage.failed"]

    async def test_global_wildcard_matches_everything(self) -> None:
        bus = EventBus()
        received: list[str] = []

        async def handler(event: WorkflowEvent) -> None:
            received.append(event.event_type)

        bus.subscribe("*", handler)
        await bus.publish(_event("workflow.pending"))
        await bus.publish(_event("stage.running"))

        assert received == ["workflow.pending", "stage.running"]

    async def test_multiple_subscribers_to_the_same_event_all_run(self) -> None:
        bus = EventBus()
        calls: list[str] = []

        async def handler_a(event: WorkflowEvent) -> None:
            calls.append("a")

        async def handler_b(event: WorkflowEvent) -> None:
            calls.append("b")

        bus.subscribe("workflow.completed", handler_a)
        bus.subscribe("workflow.completed", handler_b)
        await bus.publish(_event("workflow.completed"))

        assert calls == ["a", "b"]


class TestErrorIsolation:
    async def test_a_failing_handler_does_not_stop_other_handlers(self) -> None:
        bus = EventBus()
        calls: list[str] = []

        async def failing_handler(event: WorkflowEvent) -> None:
            raise RuntimeError("boom")

        async def ok_handler(event: WorkflowEvent) -> None:
            calls.append("ok")

        bus.subscribe("*", failing_handler)
        bus.subscribe("*", ok_handler)

        await bus.publish(_event("workflow.completed"))

        assert calls == ["ok"]

    async def test_a_failing_handler_is_recorded_not_raised(self) -> None:
        bus = EventBus()

        async def failing_handler(event: WorkflowEvent) -> None:
            raise ValueError("bad handler")

        bus.subscribe("*", failing_handler)
        event = _event("workflow.completed")

        await bus.publish(event)  # must not raise

        assert len(bus.handler_errors) == 1
        recorded_event, recorded_error = bus.handler_errors[0]
        assert recorded_event is event
        assert isinstance(recorded_error, ValueError)
