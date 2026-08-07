"""The declarative capability definition format — the "Capability Metadata"
module. Deliberately domain-agnostic: nothing here references software
engineering by name, only by example (see the docstring at the bottom).
Mirrors forgeai_workflow_engine.definition's shape and validation approach
(Sprint 2's pattern), reused deliberately for consistency across the two
packages rather than inventing a second convention.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from forgeai_capability_registry.exceptions import InvalidSchemaError, InvalidVersionError
from forgeai_capability_registry.permissions import Permission
from forgeai_core.policies import RetryPolicy, TimeoutPolicy


def parse_version(version: str) -> tuple[int, int, int]:
    """Strict 'N.N.N' parsing — see forgeai_workflow_engine.definition.parse_version
    for the identical rationale (duplicated here deliberately, not shared via
    forgeai-core: the two packages' InvalidVersionError types carry different,
    package-specific context, and this function is small enough that sharing
    it would cost more in indirection than it saves in duplicated lines)."""
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise InvalidVersionError(version)
    major, minor, patch = (int(part) for part in parts)
    return (major, minor, patch)


def _validate_json_schema_shape(field_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Structural sanity check only — not full JSON-Schema-meta-validation
    (that's arguably part of sub-sprint 3.6's Output Validation work, applied
    to actual capability I/O at execution time, not the schema's own shape at
    definition time). This just rejects the obviously-wrong: missing/empty, or
    not declaring itself an object schema, which every capability I/O contract
    in this system is expected to be."""
    if not schema:
        raise InvalidSchemaError(field_name, "schema is empty.")
    if schema.get("type") != "object":
        raise InvalidSchemaError(field_name, 'root schema must declare "type": "object".')
    return schema


class CapabilityDefinition(BaseModel):
    """`id` is stable across versions; `version` pins an immutable snapshot —
    same versioning discipline as WorkflowDefinition (Sprint 2), and for the
    same reason: an in-flight execution must keep running against the
    capability version it started on even if a newer one is registered later.

    Examples this schema is expected to describe (illustrative, not built by
    this sprint — see the Sprint 3 status report): requirement analysis,
    architecture design, task planning, backend/frontend generation, QA
    review, documentation, deployment planning. Nothing in this class knows
    about any of those specifically.
    """

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    version: str
    owner: str = Field(
        min_length=1, description="Team or individual responsible for this capability."
    )

    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    required_context: list[str] = Field(
        default_factory=list,
        description="Context Builder keys this capability needs (e.g. 'project_summary').",
    )
    supported_models: list[str] = Field(
        default_factory=list,
        description="Model identifiers or tiers this capability can run on — interpreted by "
        "the Model Router (sub-sprint 3.3), never by this package.",
    )
    estimated_cost_usd: float | None = Field(default=None, ge=0)

    timeout: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

    permissions: frozenset[Permission] = Field(default_factory=frozenset)
    artifacts_produced: list[str] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def _version_is_well_formed(cls, value: str) -> str:
        parse_version(value)  # raises InvalidVersionError if malformed
        return value

    @field_validator("input_schema")
    @classmethod
    def _input_schema_is_a_valid_shape(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_schema_shape("input_schema", value)

    @field_validator("output_schema")
    @classmethod
    def _output_schema_is_a_valid_shape(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_schema_shape("output_schema", value)
