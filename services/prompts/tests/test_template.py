from __future__ import annotations

import pytest
from pydantic import ValidationError

from forgeai_prompts.exceptions import MissingVariableError
from forgeai_prompts.template import PromptTemplate


def _template(**overrides: object) -> PromptTemplate:
    defaults: dict[str, object] = {
        "key": "greet",
        "name": "Greet",
        "version": "1.0.0",
        "content": "Hello, {name}!",
        "required_variables": ["name"],
    }
    defaults.update(overrides)
    return PromptTemplate.model_validate(defaults)


class TestVersionValidation:
    @pytest.mark.parametrize("bad", ["1.2", "1.2.3.4", "a.b.c", "1.2.x", ""])
    def test_malformed_version_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            _template(version=bad)

    def test_well_formed_version_is_accepted(self) -> None:
        assert _template(version="1.2.3").version == "1.2.3"


class TestRequiredVariablesContract:
    def test_declared_variables_matching_content_is_accepted(self) -> None:
        template = _template(
            content="Hello, {name}! Age: {age}", required_variables=["name", "age"]
        )
        assert set(template.required_variables) == {"name", "age"}

    def test_a_placeholder_used_but_not_declared_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _template(content="Hello, {name}! Age: {age}", required_variables=["name"])

    def test_a_declared_variable_not_used_in_content_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _template(content="Hello, {name}!", required_variables=["name", "unused"])

    def test_a_template_with_no_placeholders_needs_no_declared_variables(self) -> None:
        template = _template(content="Hello, world!", required_variables=[])
        assert template.required_variables == []


class TestRender:
    def test_renders_with_all_variables_supplied(self) -> None:
        template = _template()
        assert template.render({"name": "Ada"}) == "Hello, Ada!"

    def test_extra_variables_beyond_what_is_required_are_ignored(self) -> None:
        template = _template()
        assert template.render({"name": "Ada", "unrelated": "context"}) == "Hello, Ada!"

    def test_a_missing_required_variable_raises(self) -> None:
        template = _template()
        with pytest.raises(MissingVariableError):
            template.render({})
