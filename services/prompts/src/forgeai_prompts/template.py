"""A PromptTemplate is a versioned, independently-reviewable artifact —
externalizing prompt wording from capability code so a wording change shows
up as its own focused diff, distinct from a logic change, and so prompts can
eventually be A/B tested without touching capability code at all
(docs/engineering/01-repository-scaffolding.md §3).

`required_variables` is a hard, checked contract, not documentation: a
template's own validator confirms it lists exactly the placeholders that
actually appear in `content` — no more, no less — so a typo'd or forgotten
variable is caught at registration time, not discovered mid-render (or
worse, silently rendering with a variable nobody meant to leave unfilled).
"""

from __future__ import annotations

import string

from pydantic import BaseModel, Field, model_validator

from forgeai_prompts.exceptions import DeclaredVariablesMismatchError, MissingVariableError
from forgeai_prompts.versioning import parse_version


def _placeholders_in(content: str) -> set[str]:
    formatter = string.Formatter()
    return {field_name for _, field_name, _, _ in formatter.parse(content) if field_name}


class PromptTemplate(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str
    content: str = Field(min_length=1)
    description: str = ""
    required_variables: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _version_is_well_formed(self) -> PromptTemplate:
        parse_version(self.version)  # raises InvalidVersionError if malformed
        return self

    @model_validator(mode="after")
    def _required_variables_match_content(self) -> PromptTemplate:
        found = _placeholders_in(self.content)
        declared = set(self.required_variables)
        if found != declared:
            raise DeclaredVariablesMismatchError(self.key, declared, found)
        return self

    def render(self, variables: dict[str, str]) -> str:
        missing = [name for name in self.required_variables if name not in variables]
        if missing:
            raise MissingVariableError(self.key, missing)
        return self.content.format(**variables)
