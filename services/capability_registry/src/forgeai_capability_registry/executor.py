"""Ties the registry (definition + implementation), permission enforcement,
and I/O schema validation together — the missing "Executor" from Sprint 3's
original module list (permissions.py's own docstring already flagged this as
"the Capability Executor's job"). Mirrors forgeai_workflow_engine.executor's
role one layer down: that Executor runs a *stage*, which may or may not be
capability-backed; this Executor runs one *capability* invocation, the unit
a future CapabilityStageRunner (bridging the two packages) will call once it
exists.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import jsonschema

from forgeai_capability_registry.exceptions import CapabilityIOValidationError
from forgeai_capability_registry.permissions import Permission, check_permissions
from forgeai_capability_registry.registry import CapabilityRegistry
from forgeai_capability_registry.sdk import CapabilityContext, CapabilityResult


class CapabilityExecutor:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        capability_id: str,
        version: str,
        context: CapabilityContext,
        input_data: dict[str, Any],
        *,
        granted_permissions: frozenset[Permission] = frozenset(),
    ) -> CapabilityResult:
        definition = self._registry.get_definition(capability_id, version)
        check_permissions(capability_id, definition.permissions, granted_permissions)
        self._validate(capability_id, "input", definition.input_schema, input_data)

        implementation_cls = self._registry.get_implementation(capability_id, version)
        implementation = implementation_cls()
        # capability_definition is populated here, not by whoever built the
        # original context — this is the one place that actually knows which
        # definition is about to run, so an implementation can read its own
        # supported_models/permissions/etc. without hardcoding them.
        execution_context = dataclasses.replace(context, capability_definition=definition)

        result = await implementation.execute(execution_context, input_data)

        self._validate(capability_id, "output", definition.output_schema, result.output)
        return result

    @staticmethod
    def _validate(
        capability_id: str, kind: str, schema: dict[str, Any], data: dict[str, Any]
    ) -> None:
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as exc:
            raise CapabilityIOValidationError(capability_id, kind, exc.message) from exc
