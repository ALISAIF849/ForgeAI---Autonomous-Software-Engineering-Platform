"""Parses a declarative workflow definition (a plain dict, or JSON text of one)
into a validated WorkflowDefinition. Deliberately dict/JSON, not YAML — YAML
is a thin, easy addition once real definitions are actually authored as files
(no reason to add the dependency speculatively before that's true).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from forgeai_workflow_engine.definition import WorkflowDefinition
from forgeai_workflow_engine.exceptions import DefinitionValidationError


class DefinitionLoader:
    @staticmethod
    def load_from_dict(data: dict[str, Any]) -> WorkflowDefinition:
        try:
            return WorkflowDefinition.model_validate(data)
        except ValidationError as exc:
            raise DefinitionValidationError(str(exc)) from exc

    @staticmethod
    def load_from_json(raw: str) -> WorkflowDefinition:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DefinitionValidationError(f"Invalid JSON: {exc}") from exc
        return DefinitionLoader.load_from_dict(data)
