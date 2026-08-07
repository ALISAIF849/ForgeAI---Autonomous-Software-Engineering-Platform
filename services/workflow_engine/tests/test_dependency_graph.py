import pytest

from forgeai_workflow_engine.dependency_graph import topological_levels
from forgeai_workflow_engine.exceptions import CyclicDependencyError


def test_no_dependencies_means_everything_is_one_level() -> None:
    levels = topological_levels(["a", "b", "c"], {})
    assert levels == [["a", "b", "c"]]


def test_linear_chain() -> None:
    levels = topological_levels(["a", "b", "c"], {"b": ["a"], "c": ["b"]})
    assert levels == [["a"], ["b"], ["c"]]


def test_diamond_shape() -> None:
    levels = topological_levels(
        ["start", "left", "right", "end"],
        {"left": ["start"], "right": ["start"], "end": ["left", "right"]},
    )
    assert levels[0] == ["start"]
    assert set(levels[1]) == {"left", "right"}
    assert levels[2] == ["end"]


def test_direct_cycle_raises() -> None:
    with pytest.raises(CyclicDependencyError) as exc_info:
        topological_levels(["a", "b"], {"a": ["b"], "b": ["a"]})
    assert set(exc_info.value.unresolved_stage_ids) == {"a", "b"}


def test_indirect_cycle_raises() -> None:
    with pytest.raises(CyclicDependencyError):
        topological_levels(["a", "b", "c"], {"a": ["c"], "b": ["a"], "c": ["b"]})


def test_a_dependency_pointing_outside_stage_ids_never_resolves() -> None:
    # dependency_graph.py doesn't validate references itself (that's
    # UnknownStageDependencyError's job, checked separately in definition.py) —
    # but it must still fail safely (as a cycle-shaped error) rather than loop
    # forever or silently drop the stage.
    with pytest.raises(CyclicDependencyError):
        topological_levels(["a"], {"a": ["nonexistent"]})
