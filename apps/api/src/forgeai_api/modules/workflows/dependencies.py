from forgeai_workflow_engine.runner import StageRunner, UnconfiguredStageRunner

_default_runner = UnconfiguredStageRunner()


def get_stage_runner() -> StageRunner:
    """A single shared, stateless UnconfiguredStageRunner instance by default
    — see its docstring for why production has no real one to inject yet.
    Tests override this via `app.dependency_overrides[get_stage_runner]` to
    inject an explicitly-labeled fake runner instead."""
    return _default_runner
