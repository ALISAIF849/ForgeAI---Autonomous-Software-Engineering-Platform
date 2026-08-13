"""In-process prompt template registry — same immutable-once-registered
shape as forgeai_workflow_engine.registry.WorkflowRegistry: a (key, version)
pair is registered exactly once, `get_latest` picks the highest semver (not
the most recently registered), and an in-flight consumer can keep rendering
whatever version it started with even after a newer one is registered.
Deliberately duplicated rather than shared — see versioning.py's docstring
for why this package has no internal workspace dependencies.
"""

from __future__ import annotations

from forgeai_prompts.exceptions import TemplateAlreadyRegisteredError, TemplateNotFoundError
from forgeai_prompts.template import PromptTemplate
from forgeai_prompts.versioning import parse_version


class PromptRegistry:
    def __init__(self) -> None:
        self._templates: dict[tuple[str, str], PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> None:
        key = (template.key, template.version)
        if key in self._templates:
            raise TemplateAlreadyRegisteredError(template.key, template.version)
        self._templates[key] = template

    def get(self, key: str, version: str) -> PromptTemplate:
        try:
            return self._templates[(key, version)]
        except KeyError:
            raise TemplateNotFoundError(key, version) from None

    def get_latest(self, key: str) -> PromptTemplate:
        candidates = [t for (k, _v), t in self._templates.items() if k == key]
        if not candidates:
            raise TemplateNotFoundError(key, "latest")
        return max(candidates, key=lambda t: parse_version(t.version))

    def list_versions(self, key: str) -> list[str]:
        versions = [v for (k, v) in self._templates if k == key]
        return sorted(versions, key=parse_version)
