import json

import pytest

from forgeai_capability_registry.exceptions import CapabilityValidationError
from forgeai_capability_registry.loader import CapabilityLoader

_VALID_DEFINITION = {
    "id": "example",
    "name": "Example Capability",
    "version": "1.0.0",
    "owner": "platform-team",
    "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
    "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
}


class TestLoadFromDict:
    def test_valid_dict_loads_successfully(self) -> None:
        definition = CapabilityLoader.load_from_dict(_VALID_DEFINITION)
        assert definition.id == "example"

    def test_missing_required_field_raises_capability_validation_error(self) -> None:
        broken = {k: v for k, v in _VALID_DEFINITION.items() if k != "output_schema"}
        with pytest.raises(CapabilityValidationError):
            CapabilityLoader.load_from_dict(broken)

    def test_bad_schema_shape_raises_capability_validation_error_not_the_raw_domain_error(
        self,
    ) -> None:
        """Same class of regression this sprint's workflow_engine already
        covers: InvalidSchemaError must be a ValueError subclass (see
        exceptions.py) or Pydantic never wraps it and this loader's `except
        ValidationError` silently misses it."""
        broken = {**_VALID_DEFINITION, "input_schema": {}}
        with pytest.raises(CapabilityValidationError):
            CapabilityLoader.load_from_dict(broken)


class TestLoadFromJson:
    def test_valid_json_loads_successfully(self) -> None:
        definition = CapabilityLoader.load_from_json(json.dumps(_VALID_DEFINITION))
        assert definition.id == "example"

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(CapabilityValidationError, match="Invalid JSON"):
            CapabilityLoader.load_from_json("{not valid json")
