import json

import pytest

from forgeai_workflow_engine.exceptions import DefinitionValidationError
from forgeai_workflow_engine.loader import DefinitionLoader

_VALID_DEFINITION = {
    "key": "example",
    "name": "Example Workflow",
    "version": "1.0.0",
    "stages": [
        {"id": "start", "name": "Start"},
        {"id": "finish", "name": "Finish", "depends_on": ["start"]},
    ],
}


class TestLoadFromDict:
    def test_valid_dict_loads_successfully(self) -> None:
        definition = DefinitionLoader.load_from_dict(_VALID_DEFINITION)
        assert definition.key == "example"
        assert len(definition.stages) == 2

    def test_missing_required_field_raises_definition_validation_error(self) -> None:
        broken = {k: v for k, v in _VALID_DEFINITION.items() if k != "version"}
        with pytest.raises(DefinitionValidationError):
            DefinitionLoader.load_from_dict(broken)

    def test_cyclic_dependency_raises_definition_validation_error_not_the_raw_domain_error(
        self,
    ) -> None:
        """Regression test: CyclicDependencyError is raised from inside a pydantic
        model_validator, which only auto-wraps ValueError/TypeError/AssertionError
        into pydantic.ValidationError — without CyclicDependencyError also being a
        ValueError (see exceptions.py), it would propagate unwrapped and this
        loader's `except ValidationError` would never catch it at all."""
        cyclic = {
            "key": "cyclic",
            "name": "Cyclic",
            "version": "1.0.0",
            "stages": [
                {"id": "a", "name": "A", "depends_on": ["b"]},
                {"id": "b", "name": "B", "depends_on": ["a"]},
            ],
        }
        with pytest.raises(DefinitionValidationError):
            DefinitionLoader.load_from_dict(cyclic)

    def test_unknown_dependency_raises_definition_validation_error(self) -> None:
        broken = {
            "key": "bad-dep",
            "name": "Bad Dep",
            "version": "1.0.0",
            "stages": [{"id": "a", "name": "A", "depends_on": ["ghost"]}],
        }
        with pytest.raises(DefinitionValidationError):
            DefinitionLoader.load_from_dict(broken)

    def test_malformed_version_raises_definition_validation_error(self) -> None:
        broken = {**_VALID_DEFINITION, "version": "not-a-version"}
        with pytest.raises(DefinitionValidationError):
            DefinitionLoader.load_from_dict(broken)

    def test_generic_domain_examples_all_load(self) -> None:
        """Confirms the format genuinely isn't software-engineering-specific —
        the same schema accepts workflows from unrelated domains."""
        release_workflow = {
            "key": "release",
            "name": "Release",
            "version": "1.0.0",
            "stages": [{"id": "publish", "name": "Publish"}],
        }
        security_audit = {
            "key": "security-audit",
            "name": "Security Audit",
            "version": "1.0.0",
            "stages": [
                {"id": "scan", "name": "Scan"},
                {"id": "report", "name": "Report", "depends_on": ["scan"]},
            ],
        }
        db_migration = {
            "key": "database-migration",
            "name": "Database Migration",
            "version": "1.0.0",
            "stages": [
                {"id": "backup", "name": "Backup"},
                {"id": "migrate", "name": "Migrate", "depends_on": ["backup"]},
            ],
        }

        for raw in (release_workflow, security_audit, db_migration):
            DefinitionLoader.load_from_dict(raw)  # must not raise


class TestLoadFromJson:
    def test_valid_json_loads_successfully(self) -> None:
        definition = DefinitionLoader.load_from_json(json.dumps(_VALID_DEFINITION))
        assert definition.key == "example"

    def test_malformed_json_raises_definition_validation_error(self) -> None:
        with pytest.raises(DefinitionValidationError, match="Invalid JSON"):
            DefinitionLoader.load_from_json("{not valid json")

    def test_valid_json_but_invalid_schema_still_raises(self) -> None:
        with pytest.raises(DefinitionValidationError):
            DefinitionLoader.load_from_json(json.dumps({"key": "incomplete"}))
