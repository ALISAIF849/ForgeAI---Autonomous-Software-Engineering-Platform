"""Every domain error this package raises. Same one-file, catch-the-base-class
convention as forgeai_workflow_engine.exceptions / forgeai_model_router.exceptions.
"""

from __future__ import annotations


class PromptError(Exception):
    """Base class for every error this package raises."""


class TemplateValidationError(PromptError, ValueError):
    """A PromptTemplate failed validation — bad shape, not a registry problem.

    Also inherits ValueError: Pydantic only auto-wraps ValueError/TypeError/
    AssertionError raised inside a model_validator into its own
    ValidationError — a plain PromptError subclass would propagate unwrapped
    instead, exactly the reasoning forgeai_workflow_engine.exceptions'
    DefinitionValidationError already documents for the identical situation.
    """


class InvalidVersionError(TemplateValidationError):
    def __init__(self, version: str) -> None:
        self.version = version
        super().__init__(f"'{version}' is not a valid version string — expected 'N.N.N'.")


class DeclaredVariablesMismatchError(TemplateValidationError):
    def __init__(self, key: str, declared: set[str], found_in_content: set[str]) -> None:
        self.key = key
        self.declared = declared
        self.found_in_content = found_in_content
        missing = sorted(found_in_content - declared)
        unused = sorted(declared - found_in_content)
        detail_parts = []
        if missing:
            detail_parts.append(f"used in content but not declared: {missing}")
        if unused:
            detail_parts.append(f"declared but not used in content: {unused}")
        super().__init__(
            f"Template '{key}' has a required_variables mismatch — {'; '.join(detail_parts)}."
        )


class MissingVariableError(PromptError):
    def __init__(self, key: str, missing: list[str]) -> None:
        self.key = key
        self.missing = missing
        super().__init__(
            f"Cannot render template '{key}' — missing required variable(s): {missing}."
        )


class TemplateAlreadyRegisteredError(PromptError):
    def __init__(self, key: str, version: str) -> None:
        self.key = key
        self.version = version
        super().__init__(
            f"Prompt template '{key}' version '{version}' is already registered — "
            "templates are immutable once registered; register a new version instead."
        )


class TemplateNotFoundError(PromptError):
    def __init__(self, key: str, version: str) -> None:
        self.key = key
        self.version = version
        super().__init__(f"No prompt template registered for '{key}' version '{version}'.")
