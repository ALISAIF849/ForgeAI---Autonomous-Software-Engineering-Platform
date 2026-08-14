"""Sprint 17 Stage 3 — Connection Verification. `connect_repository()`
exercises a RepositoryProvider for real (an actual API call, never a
simulated one) and turns whatever happens — success, not-found,
authentication failure, missing permissions, provider outage — into a
structured RepositoryConnectionReport instead of raising, so a caller (a
future connect-repository API endpoint) always gets one report shape back
rather than needing to catch every exception this package defines.

Persisting the report / associating it with an org+project (Stage 4) and
building a repository snapshot from it (Stage 5) are later slices — this
module's job stops at "is this credential+repository combination actually
usable right now".
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime

from forgeai_integrations.exceptions import (
    AuthenticationFailureError,
    InsufficientPermissionsError,
    ProviderUnavailableError,
    RateLimitedError,
    RepositoryNotFoundError,
)
from forgeai_integrations.provider import RepositoryMetadata, RepositoryProvider

# GitHub classic-PAT scope required to read a *private* repository's contents.
# Public repositories need no scope at all, so this is only checked once a
# repository's actual visibility is known — never assumed up front.
GITHUB_PRIVATE_REPO_SCOPE = "repo"


class ConnectionStatus(enum.StrEnum):
    CONNECTED = "connected"
    REPOSITORY_NOT_FOUND = "repository_not_found"
    AUTHENTICATION_FAILED = "authentication_failed"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True, slots=True)
class RepositoryConnectionReport:
    provider: str
    connection_status: ConnectionStatus
    repository: RepositoryMetadata | None
    granted_scopes: frozenset[str]
    missing_scopes: frozenset[str]
    detail: str | None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_connected(self) -> bool:
        return self.connection_status == ConnectionStatus.CONNECTED


def _report(
    status: ConnectionStatus,
    *,
    provider_name: str,
    repository: RepositoryMetadata | None = None,
    granted_scopes: frozenset[str] = frozenset(),
    missing_scopes: frozenset[str] = frozenset(),
    detail: str | None = None,
) -> RepositoryConnectionReport:
    return RepositoryConnectionReport(
        provider=provider_name,
        connection_status=status,
        repository=repository,
        granted_scopes=granted_scopes,
        missing_scopes=missing_scopes,
        detail=detail,
    )


async def connect_repository(
    provider: RepositoryProvider,
    owner: str,
    name: str,
    *,
    provider_name: str = "github",
) -> RepositoryConnectionReport:
    try:
        granted_scopes = await provider.get_authorized_scopes()
    except AuthenticationFailureError as exc:
        return _report(
            ConnectionStatus.AUTHENTICATION_FAILED, provider_name=provider_name, detail=str(exc)
        )
    except RateLimitedError as exc:
        return _report(ConnectionStatus.RATE_LIMITED, provider_name=provider_name, detail=str(exc))
    except ProviderUnavailableError as exc:
        return _report(
            ConnectionStatus.PROVIDER_UNAVAILABLE, provider_name=provider_name, detail=str(exc)
        )

    try:
        repository = await provider.get_repository(owner, name)
    except RepositoryNotFoundError as exc:
        return _report(
            ConnectionStatus.REPOSITORY_NOT_FOUND, provider_name=provider_name, detail=str(exc)
        )
    except AuthenticationFailureError as exc:
        return _report(
            ConnectionStatus.AUTHENTICATION_FAILED, provider_name=provider_name, detail=str(exc)
        )
    except InsufficientPermissionsError as exc:
        return _report(
            ConnectionStatus.INSUFFICIENT_PERMISSIONS,
            provider_name=provider_name,
            granted_scopes=granted_scopes,
            missing_scopes=exc.missing,
            detail=str(exc),
        )
    except RateLimitedError as exc:
        return _report(ConnectionStatus.RATE_LIMITED, provider_name=provider_name, detail=str(exc))
    except ProviderUnavailableError as exc:
        return _report(
            ConnectionStatus.PROVIDER_UNAVAILABLE, provider_name=provider_name, detail=str(exc)
        )

    required_scopes = (
        frozenset({GITHUB_PRIVATE_REPO_SCOPE}) if repository.visibility != "public" else frozenset()
    )
    missing_scopes = required_scopes - granted_scopes
    if missing_scopes:
        return _report(
            ConnectionStatus.INSUFFICIENT_PERMISSIONS,
            provider_name=provider_name,
            repository=repository,
            granted_scopes=granted_scopes,
            missing_scopes=missing_scopes,
            detail=f"Repository is {repository.visibility}; missing required scope(s).",
        )

    return _report(
        ConnectionStatus.CONNECTED,
        provider_name=provider_name,
        repository=repository,
        granted_scopes=granted_scopes,
    )
