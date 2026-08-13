from __future__ import annotations

import pytest

from forgeai_prompts.exceptions import TemplateAlreadyRegisteredError, TemplateNotFoundError
from forgeai_prompts.registry import PromptRegistry
from forgeai_prompts.template import PromptTemplate


def _template(key: str = "greet", version: str = "1.0.0") -> PromptTemplate:
    return PromptTemplate(
        key=key,
        name=key,
        version=version,
        content="Hello, {name}!",
        required_variables=["name"],
    )


class TestRegistration:
    def test_register_then_get_round_trips(self) -> None:
        registry = PromptRegistry()
        template = _template()
        registry.register(template)

        assert registry.get("greet", "1.0.0") == template

    def test_reregistering_the_same_key_and_version_is_rejected(self) -> None:
        registry = PromptRegistry()
        registry.register(_template())

        with pytest.raises(TemplateAlreadyRegisteredError):
            registry.register(_template())

    def test_different_versions_of_the_same_key_coexist(self) -> None:
        registry = PromptRegistry()
        registry.register(_template(version="1.0.0"))
        registry.register(_template(version="1.1.0"))

        assert registry.get("greet", "1.0.0").version == "1.0.0"
        assert registry.get("greet", "1.1.0").version == "1.1.0"

    def test_getting_an_unregistered_template_raises(self) -> None:
        registry = PromptRegistry()
        with pytest.raises(TemplateNotFoundError):
            registry.get("nope", "1.0.0")


class TestLatestVersion:
    def test_get_latest_picks_the_highest_semver_not_the_most_recently_registered(self) -> None:
        registry = PromptRegistry()
        registry.register(_template(version="2.0.0"))
        registry.register(_template(version="1.9.9"))

        assert registry.get_latest("greet").version == "2.0.0"

    def test_get_latest_with_no_versions_registered_raises(self) -> None:
        registry = PromptRegistry()
        with pytest.raises(TemplateNotFoundError):
            registry.get_latest("nope")


class TestListVersions:
    def test_list_versions_is_sorted_numerically(self) -> None:
        registry = PromptRegistry()
        registry.register(_template(version="1.10.0"))
        registry.register(_template(version="1.2.0"))
        registry.register(_template(version="1.9.0"))

        assert registry.list_versions("greet") == ["1.2.0", "1.9.0", "1.10.0"]

    def test_list_versions_only_returns_matching_keys(self) -> None:
        registry = PromptRegistry()
        registry.register(_template(key="greet", version="1.0.0"))
        registry.register(_template(key="farewell", version="1.0.0"))

        assert registry.list_versions("greet") == ["1.0.0"]
