import pytest

from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition
from forgeai_workflow_engine.exceptions import (
    DefinitionAlreadyRegisteredError,
    DefinitionNotFoundError,
)
from forgeai_workflow_engine.registry import WorkflowRegistry


def _definition(key: str, version: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        key=key, name=key, version=version, stages=[StageDefinition(id="only", name="Only")]
    )


class TestRegistration:
    def test_register_then_get_round_trips(self) -> None:
        registry = WorkflowRegistry()
        definition = _definition("example", "1.0.0")

        registry.register(definition)

        assert registry.get("example", "1.0.0") is definition

    def test_reregistering_the_same_key_and_version_is_rejected(self) -> None:
        registry = WorkflowRegistry()
        registry.register(_definition("example", "1.0.0"))

        with pytest.raises(DefinitionAlreadyRegisteredError):
            registry.register(_definition("example", "1.0.0"))

    def test_different_versions_of_the_same_key_coexist(self) -> None:
        registry = WorkflowRegistry()
        registry.register(_definition("example", "1.0.0"))
        registry.register(_definition("example", "2.0.0"))

        assert registry.get("example", "1.0.0").version == "1.0.0"
        assert registry.get("example", "2.0.0").version == "2.0.0"

    def test_getting_an_unregistered_definition_raises(self) -> None:
        registry = WorkflowRegistry()
        with pytest.raises(DefinitionNotFoundError):
            registry.get("nope", "1.0.0")


class TestLatestVersion:
    def test_get_latest_picks_the_highest_semver_not_the_most_recently_registered(self) -> None:
        registry = WorkflowRegistry()
        # Registered out of order on purpose — get_latest must sort numerically,
        # not just return whatever was registered last.
        registry.register(_definition("example", "1.9.0"))
        registry.register(_definition("example", "1.10.0"))
        registry.register(_definition("example", "2.0.0"))
        registry.register(_definition("example", "1.2.0"))

        assert registry.get_latest("example").version == "2.0.0"

    def test_get_latest_with_no_versions_registered_raises(self) -> None:
        registry = WorkflowRegistry()
        with pytest.raises(DefinitionNotFoundError):
            registry.get_latest("nonexistent")


class TestListing:
    def test_list_versions_is_sorted_numerically(self) -> None:
        registry = WorkflowRegistry()
        for version in ["1.10.0", "1.2.0", "1.9.0"]:
            registry.register(_definition("example", version))

        assert registry.list_versions("example") == ["1.2.0", "1.9.0", "1.10.0"]

    def test_list_keys_only_returns_distinct_keys(self) -> None:
        registry = WorkflowRegistry()
        registry.register(_definition("alpha", "1.0.0"))
        registry.register(_definition("alpha", "2.0.0"))
        registry.register(_definition("beta", "1.0.0"))

        assert registry.list_keys() == ["alpha", "beta"]

    def test_is_registered(self) -> None:
        registry = WorkflowRegistry()
        registry.register(_definition("example", "1.0.0"))

        assert registry.is_registered("example", "1.0.0") is True
        assert registry.is_registered("example", "9.9.9") is False
