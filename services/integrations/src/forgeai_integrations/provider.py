"""The repository provider abstraction — Sprint 17's "RepositoryProvider ->
GitHubProvider / GitLabProvider / BitbucketProvider" shape. A Protocol, like
forgeai_capability_registry.sdk.Capability: structural, so a future
GitLabProvider doesn't need to inherit from anything this package defines,
and this module stays free of any GitHub-specific concept. Only
GitHubProvider (github.py) exists — GitLab/Bitbucket are deliberately not
stubbed, per this sprint's brief not to fake providers that aren't built.

Scoped to what Sprint 17's Stage 1-3 (connection + verification) needs:
reading repository metadata and the credential's granted permissions. Branch/
commit/PR operations are a later slice — adding them to this Protocol when
they exist is additive, not a redesign, since callers already depend on the
Protocol rather than a concrete provider class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RepositoryMetadata:
    owner: str
    name: str
    full_name: str
    default_branch: str
    visibility: str  # "public" | "private" | "internal" — provider-reported, not inferred
    html_url: str


class RepositoryProvider(Protocol):
    """`get_authorized_scopes` reports what the attached credential can
    actually do — used by connection verification (Stage 3) to compute
    missing permissions without guessing from a failed call."""

    async def get_repository(self, owner: str, name: str) -> RepositoryMetadata: ...

    async def get_authorized_scopes(self) -> frozenset[str]: ...
