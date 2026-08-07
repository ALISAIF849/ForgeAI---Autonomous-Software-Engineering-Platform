import pytest
from pydantic import ValidationError

from forgeai_capability_registry.definition import CapabilityDefinition, parse_version
from forgeai_capability_registry.exceptions import InvalidSchemaError, InvalidVersionError
from forgeai_capability_registry.permissions import Permission

_OBJECT_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}}


def _definition(**overrides: object) -> CapabilityDefinition:
    defaults = {
        "id": "example-capability",
        "name": "Example Capability",
        "version": "1.0.0",
        "owner": "platform-team",
        "input_schema": _OBJECT_SCHEMA,
        "output_schema": _OBJECT_SCHEMA,
    }
    return CapabilityDefinition(**{**defaults, **overrides})


class TestParseVersion:
    def test_well_formed_version(self) -> None:
        assert parse_version("2.1.4") == (2, 1, 4)

    @pytest.mark.parametrize("bad", ["1", "1.2", "v1.2.3", "1.2.3-beta"])
    def test_malformed_version_is_rejected(self, bad: str) -> None:
        with pytest.raises(InvalidVersionError):
            parse_version(bad)


class TestCapabilityDefinitionValidation:
    def test_a_reasonable_definition_is_accepted(self) -> None:
        definition = _definition()
        assert definition.id == "example-capability"
        assert definition.permissions == frozenset()

    def test_permissions_parse_from_strings(self) -> None:
        definition = _definition(permissions=["read_context", "write_artifacts"])
        assert definition.permissions == {Permission.READ_CONTEXT, Permission.WRITE_ARTIFACTS}

    def test_unknown_permission_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _definition(permissions=["delete_universe"])

    def test_empty_input_schema_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _definition(input_schema={})
        assert isinstance(exc_info.value.errors()[0]["ctx"]["error"], InvalidSchemaError)

    def test_input_schema_missing_object_type_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _definition(input_schema={"properties": {"x": {"type": "string"}}})

    def test_malformed_version_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _definition(version="not-a-version")

    def test_negative_estimated_cost_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _definition(estimated_cost_usd=-1.0)

    def test_owner_is_required(self) -> None:
        with pytest.raises(ValidationError):
            _definition(owner="")


class TestGenericityAcrossDomains:
    """Confirms the schema doesn't secretly assume software engineering —
    same check as the workflow engine's loader test, applied here too."""

    def test_examples_from_unrelated_domains_all_validate(self) -> None:
        examples = [
            {"id": "requirement-analysis", "name": "Requirement Analysis"},
            {"id": "architecture-design", "name": "Architecture Design"},
            {"id": "task-planning", "name": "Task Planning"},
            {"id": "qa-review", "name": "QA Review"},
            {"id": "deployment-planning", "name": "Deployment Planning"},
        ]
        for overrides in examples:
            _definition(**overrides)  # must not raise
