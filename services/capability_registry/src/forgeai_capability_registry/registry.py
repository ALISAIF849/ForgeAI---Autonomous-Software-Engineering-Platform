"""In-process catalog pairing each registered CapabilityDefinition with its
implementation. Unlike WorkflowRegistry (Sprint 2), which only stores
declarative data, capabilities need actual executable code attached — this is
the concrete expression of "capabilities behave like plugins": registering
one means handing the registry both the contract and the code that fulfills
it, and everything downstream (the future Executor) only ever calls through
the contract.
"""

from __future__ import annotations

from forgeai_capability_registry.definition import CapabilityDefinition, parse_version
from forgeai_capability_registry.exceptions import (
    CapabilityAlreadyRegisteredError,
    CapabilityNotFoundError,
)
from forgeai_capability_registry.sdk import Capability


class CapabilityRegistry:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], tuple[CapabilityDefinition, type[Capability]]] = {}

    def register(self, definition: CapabilityDefinition, implementation: type[Capability]) -> None:
        """Immutable once registered — re-registering the same (id, version)
        pair is a hard error rather than a silent overwrite, same discipline
        as WorkflowRegistry.register()."""
        key = (definition.id, definition.version)
        if key in self._entries:
            raise CapabilityAlreadyRegisteredError(definition.id, definition.version)
        self._entries[key] = (definition, implementation)

    def get_definition(self, capability_id: str, version: str) -> CapabilityDefinition:
        return self._get(capability_id, version)[0]

    def get_implementation(self, capability_id: str, version: str) -> type[Capability]:
        return self._get(capability_id, version)[1]

    def get_latest_definition(self, capability_id: str) -> CapabilityDefinition:
        candidates = [
            definition
            for (cap_id, _v), (definition, _impl) in self._entries.items()
            if cap_id == capability_id
        ]
        if not candidates:
            raise CapabilityNotFoundError(capability_id, "latest")
        return max(candidates, key=lambda d: parse_version(d.version))

    def list_versions(self, capability_id: str) -> list[str]:
        versions = [v for (cap_id, v) in self._entries if cap_id == capability_id]
        return sorted(versions, key=parse_version)

    def list_ids(self) -> list[str]:
        return sorted({cap_id for cap_id, _version in self._entries})

    def is_registered(self, capability_id: str, version: str) -> bool:
        return (capability_id, version) in self._entries

    def _get(
        self, capability_id: str, version: str
    ) -> tuple[CapabilityDefinition, type[Capability]]:
        try:
            return self._entries[(capability_id, version)]
        except KeyError:
            raise CapabilityNotFoundError(capability_id, version) from None
