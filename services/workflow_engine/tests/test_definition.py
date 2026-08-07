import pytest
from pydantic import ValidationError

from forgeai_workflow_engine.definition import StageDefinition, WorkflowDefinition, parse_version
from forgeai_workflow_engine.exceptions import (
    CyclicDependencyError,
    InvalidVersionError,
    UnknownStageDependencyError,
)


def _stage(id: str, depends_on: list[str] | None = None, **kwargs: object) -> StageDefinition:
    return StageDefinition(id=id, name=id, depends_on=depends_on or [], **kwargs)


class TestParseVersion:
    def test_well_formed_version(self) -> None:
        assert parse_version("1.2.3") == (1, 2, 3)

    @pytest.mark.parametrize("bad", ["1.2", "1.2.3.4", "a.b.c", "1.2.x", ""])
    def test_malformed_version_is_rejected(self, bad: str) -> None:
        with pytest.raises(InvalidVersionError):
            parse_version(bad)


class TestWorkflowDefinitionValidation:
    def test_a_reasonable_definition_is_accepted(self) -> None:
        definition = WorkflowDefinition(
            key="generic-example",
            name="Generic Example",
            version="1.0.0",
            stages=[
                _stage("plan"),
                _stage("build", depends_on=["plan"]),
                _stage("verify", depends_on=["build"]),
            ],
        )
        assert definition.stage("build").depends_on == ["plan"]

    def test_duplicate_stage_ids_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate stage id"):
            WorkflowDefinition(
                key="dup",
                name="Dup",
                version="1.0.0",
                stages=[_stage("a"), _stage("a")],
            )

    def test_dependency_on_unknown_stage_is_rejected(self) -> None:
        # ValidationError, not the raw UnknownStageDependencyError — Pydantic wraps
        # it (see exceptions.py's DefinitionValidationError docstring for why that
        # matters); the specific domain exception is still the wrapped cause.
        with pytest.raises(ValidationError) as exc_info:
            WorkflowDefinition(
                key="bad-dep",
                name="Bad Dep",
                version="1.0.0",
                stages=[_stage("a", depends_on=["does-not-exist"])],
            )
        assert isinstance(exc_info.value.errors()[0]["ctx"]["error"], UnknownStageDependencyError)

    def test_failure_handler_referencing_unknown_stage_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowDefinition(
                key="bad-handler",
                name="Bad Handler",
                version="1.0.0",
                stages=[_stage("a", failure_handler="ghost-stage")],
            )

    def test_two_stage_cycle_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            WorkflowDefinition(
                key="cycle",
                name="Cycle",
                version="1.0.0",
                stages=[_stage("a", depends_on=["b"]), _stage("b", depends_on=["a"])],
            )
        assert isinstance(exc_info.value.errors()[0]["ctx"]["error"], CyclicDependencyError)

    def test_self_dependency_is_rejected_as_a_cycle(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowDefinition(
                key="self-cycle",
                name="Self Cycle",
                version="1.0.0",
                stages=[_stage("a", depends_on=["a"])],
            )

    def test_malformed_version_is_rejected_at_definition_level_too(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowDefinition(
                key="bad-version", name="Bad Version", version="not-a-version", stages=[_stage("a")]
            )

    def test_at_least_one_stage_is_required(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowDefinition(key="empty", name="Empty", version="1.0.0", stages=[])


class TestExecutionLevels:
    def test_independent_stages_share_a_level(self) -> None:
        definition = WorkflowDefinition(
            key="fan-out",
            name="Fan Out",
            version="1.0.0",
            stages=[
                _stage("start"),
                _stage("branch-a", depends_on=["start"]),
                _stage("branch-b", depends_on=["start"]),
                _stage("join", depends_on=["branch-a", "branch-b"]),
            ],
        )

        levels = definition.execution_levels()

        assert levels[0] == ["start"]
        assert set(levels[1]) == {"branch-a", "branch-b"}
        assert levels[2] == ["join"]

    def test_a_linear_chain_produces_one_stage_per_level(self) -> None:
        definition = WorkflowDefinition(
            key="chain",
            name="Chain",
            version="1.0.0",
            stages=[_stage("a"), _stage("b", depends_on=["a"]), _stage("c", depends_on=["b"])],
        )

        assert definition.execution_levels() == [["a"], ["b"], ["c"]]


class TestStageLookup:
    def test_stage_returns_the_matching_definition(self) -> None:
        definition = WorkflowDefinition(
            key="lookup", name="Lookup", version="1.0.0", stages=[_stage("only")]
        )
        assert definition.stage("only").id == "only"

    def test_stage_raises_key_error_for_unknown_id(self) -> None:
        definition = WorkflowDefinition(
            key="lookup", name="Lookup", version="1.0.0", stages=[_stage("only")]
        )
        with pytest.raises(KeyError):
            definition.stage("missing")
