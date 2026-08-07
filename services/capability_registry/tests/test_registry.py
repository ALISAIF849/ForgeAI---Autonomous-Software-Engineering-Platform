from typing import Any

import pytest

from forgeai_capability_registry.definition import CapabilityDefinition
from forgeai_capability_registry.exceptions import (
    CapabilityAlreadyRegisteredError,
    CapabilityNotFoundError,
)
from forgeai_capability_registry.registry import CapabilityRegistry
from forgeai_capability_registry.sdk import CapabilityContext, CapabilityResult

_OBJECT_SCHEMA = {"type": "object", "properties": {}}


def _definition(capability_id: str, version: str) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=capability_id,
        name=capability_id,
        version=version,
        owner="platform-team",
        input_schema=_OBJECT_SCHEMA,
        output_schema=_OBJECT_SCHEMA,
    )


class _NoOpCapability:
    async def execute(
        self, context: CapabilityContext, input_data: dict[str, Any]
    ) -> CapabilityResult:
        return CapabilityResult(output={}, reasoning_summary="no-op")


class TestRegistration:
    def test_register_then_get_round_trips(self) -> None:
        registry = CapabilityRegistry()
        definition = _definition("example", "1.0.0")

        registry.register(definition, _NoOpCapability)

        assert registry.get_definition("example", "1.0.0") is definition
        assert registry.get_implementation("example", "1.0.0") is _NoOpCapability

    def test_reregistering_the_same_id_and_version_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_definition("example", "1.0.0"), _NoOpCapability)

        with pytest.raises(CapabilityAlreadyRegisteredError):
            registry.register(_definition("example", "1.0.0"), _NoOpCapability)

    def test_getting_an_unregistered_capability_raises(self) -> None:
        registry = CapabilityRegistry()
        with pytest.raises(CapabilityNotFoundError):
            registry.get_definition("nope", "1.0.0")


class TestLatestVersion:
    def test_get_latest_picks_the_highest_semver(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_definition("example", "1.9.0"), _NoOpCapability)
        registry.register(_definition("example", "1.10.0"), _NoOpCapability)
        registry.register(_definition("example", "1.2.0"), _NoOpCapability)

        assert registry.get_latest_definition("example").version == "1.10.0"

    def test_get_latest_with_nothing_registered_raises(self) -> None:
        registry = CapabilityRegistry()
        with pytest.raises(CapabilityNotFoundError):
            registry.get_latest_definition("nonexistent")


class TestListing:
    def test_list_versions_and_ids(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_definition("alpha", "1.0.0"), _NoOpCapability)
        registry.register(_definition("alpha", "2.0.0"), _NoOpCapability)
        registry.register(_definition("beta", "1.0.0"), _NoOpCapability)

        assert registry.list_versions("alpha") == ["1.0.0", "2.0.0"]
        assert registry.list_ids() == ["alpha", "beta"]

    def test_is_registered(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_definition("example", "1.0.0"), _NoOpCapability)

        assert registry.is_registered("example", "1.0.0") is True
        assert registry.is_registered("example", "2.0.0") is False


class TestCapabilityProtocolCompliance:
    async def test_registered_implementation_actually_satisfies_the_sdk_protocol(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_definition("example", "1.0.0"), _NoOpCapability)

        implementation_cls = registry.get_implementation("example", "1.0.0")
        instance = implementation_cls()
        context = CapabilityContext(
            project_id=None,
            organization_id=None,
            workflow_execution_id=None,
            invoked_by_user_id=None,
        )

        result = await instance.execute(context, {})

        assert result.output == {}
        assert result.reasoning_summary == "no-op"
