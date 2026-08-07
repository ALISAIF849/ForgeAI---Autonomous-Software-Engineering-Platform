"""In-process catalog of registered WorkflowDefinitions. Persistence (2.2)
mirrors this to the `workflows`/`workflow_versions` tables for discoverability
and cross-process/restart durability — this registry is the fast, in-memory
path the Executor actually reads from at run time, per
docs/architecture/03-workflow-engine.md §7.
"""

from __future__ import annotations

from forgeai_workflow_engine.definition import WorkflowDefinition, parse_version
from forgeai_workflow_engine.exceptions import (
    DefinitionAlreadyRegisteredError,
    DefinitionNotFoundError,
)


class WorkflowRegistry:
    def __init__(self) -> None:
        self._definitions: dict[tuple[str, str], WorkflowDefinition] = {}

    def register(self, definition: WorkflowDefinition) -> None:
        """Definitions are immutable once registered — this is the mechanism,
        not just a convention: re-registering the same (key, version) pair is
        a hard error rather than a silent overwrite."""
        key = (definition.key, definition.version)
        if key in self._definitions:
            raise DefinitionAlreadyRegisteredError(definition.key, definition.version)
        self._definitions[key] = definition

    def get(self, key: str, version: str) -> WorkflowDefinition:
        try:
            return self._definitions[(key, version)]
        except KeyError:
            raise DefinitionNotFoundError(key, version) from None

    def get_latest(self, key: str) -> WorkflowDefinition:
        candidates = [definition for (k, _v), definition in self._definitions.items() if k == key]
        if not candidates:
            raise DefinitionNotFoundError(key, "latest")
        return max(candidates, key=lambda d: parse_version(d.version))

    def list_versions(self, key: str) -> list[str]:
        versions = [v for (k, v) in self._definitions if k == key]
        return sorted(versions, key=parse_version)

    def list_keys(self) -> list[str]:
        return sorted({key for key, _version in self._definitions})

    def is_registered(self, key: str, version: str) -> bool:
        return (key, version) in self._definitions
