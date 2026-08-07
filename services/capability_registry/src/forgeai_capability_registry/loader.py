"""Parses a declarative capability definition (a plain dict, or JSON text of
one) into a validated CapabilityDefinition. Loading the *definition* and
registering an *implementation* are separate steps — see registry.py — since
a definition can be authored/reviewed as pure data before any code exists to
back it.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from forgeai_capability_registry.definition import CapabilityDefinition
from forgeai_capability_registry.exceptions import CapabilityValidationError


class CapabilityLoader:
    @staticmethod
    def load_from_dict(data: dict[str, Any]) -> CapabilityDefinition:
        try:
            return CapabilityDefinition.model_validate(data)
        except ValidationError as exc:
            raise CapabilityValidationError(str(exc)) from exc

    @staticmethod
    def load_from_json(raw: str) -> CapabilityDefinition:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CapabilityValidationError(f"Invalid JSON: {exc}") from exc
        return CapabilityLoader.load_from_dict(data)
