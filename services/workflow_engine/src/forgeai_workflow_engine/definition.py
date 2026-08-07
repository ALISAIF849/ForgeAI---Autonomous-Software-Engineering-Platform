"""The declarative workflow definition format. Deliberately domain-agnostic —
nothing here references software engineering, AI, or capabilities by name.
`capability` on a stage is an opaque string key (e.g. "send-email",
"run-tests", "generate-report") the engine never interprets; whatever plugs
into it later (AI-backed or not) is out of this package's concern entirely.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from forgeai_core.policies import RetryPolicy, TimeoutPolicy
from forgeai_workflow_engine.dependency_graph import topological_levels
from forgeai_workflow_engine.exceptions import InvalidVersionError, UnknownStageDependencyError


def parse_version(version: str) -> tuple[int, int, int]:
    """Strict 'N.N.N' parsing — not full semver (no pre-release/build metadata
    support). Workflow definition versions don't need that expressiveness, and
    a strict parse fails loudly on anything else rather than silently
    misordering versions that don't fit the expected shape."""
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise InvalidVersionError(version)
    major, minor, patch = (int(part) for part in parts)
    return (major, minor, patch)


class StageDefinition(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    estimated_seconds: int | None = Field(default=None, gt=0)
    capability: str | None = None
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    requires_approval: bool = False
    allow_skip: bool = False
    failure_handler: str | None = Field(
        default=None, description="ID of another stage to run if this one fails permanently."
    )


class WorkflowDefinition(BaseModel):
    """`key` is stable across versions (what a WorkflowExecution references
    indirectly); `version` pins a specific, immutable snapshot. Two definitions
    with the same key but different versions can coexist — an in-flight
    execution keeps running against whatever version it started on even if a
    newer one is registered, per docs/architecture/03-workflow-engine.md §7's
    already-established versioning rule, which applies unchanged here."""

    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    version: str

    stages: list[StageDefinition] = Field(min_length=1)

    entry_conditions: list[str] = Field(default_factory=list)
    exit_conditions: list[str] = Field(default_factory=list)
    rollback_rules: list[str] = Field(default_factory=list)

    timeout: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

    required_capabilities: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def _version_is_well_formed(cls, value: str) -> str:
        parse_version(value)  # raises InvalidVersionError if malformed
        return value

    @model_validator(mode="after")
    def _stage_ids_are_unique(self) -> WorkflowDefinition:
        seen: set[str] = set()
        for stage in self.stages:
            if stage.id in seen:
                raise ValueError(f"Duplicate stage id '{stage.id}' — stage IDs must be unique.")
            seen.add(stage.id)
        return self

    @model_validator(mode="after")
    def _dependencies_reference_real_stages(self) -> WorkflowDefinition:
        stage_ids = {stage.id for stage in self.stages}
        for stage in self.stages:
            for dependency in stage.depends_on:
                if dependency not in stage_ids:
                    raise UnknownStageDependencyError(stage.id, dependency)
            if stage.failure_handler is not None and stage.failure_handler not in stage_ids:
                raise UnknownStageDependencyError(stage.id, stage.failure_handler)
        return self

    @model_validator(mode="after")
    def _dependency_graph_has_no_cycles(self) -> WorkflowDefinition:
        # Raises CyclicDependencyError itself if the graph isn't a DAG — this
        # validator's only job is to trigger that check at definition-load time
        # rather than leaving it to be discovered mid-execution later.
        topological_levels(
            [stage.id for stage in self.stages],
            {stage.id: stage.depends_on for stage in self.stages},
        )
        return self

    def stage(self, stage_id: str) -> StageDefinition:
        for stage in self.stages:
            if stage.id == stage_id:
                return stage
        raise KeyError(f"No stage '{stage_id}' in workflow '{self.key}' v{self.version}.")

    def execution_levels(self) -> list[list[str]]:
        """Stage IDs grouped into parallelizable levels, in dependency order —
        the Executor (2.3) uses this to decide what can run concurrently."""
        return topological_levels(
            [stage.id for stage in self.stages],
            {stage.id: stage.depends_on for stage in self.stages},
        )
