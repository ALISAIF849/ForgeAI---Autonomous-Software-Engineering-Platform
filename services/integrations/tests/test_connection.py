"""Unit tests for connect_repository()'s status-mapping logic, using a
small in-process fake RepositoryProvider (scripted to raise/return exactly
what's under test) — connect_repository() itself is provider-agnostic, so
this doesn't need real HTTP; the HTTP layer's own behavior is github.py's
job, covered in test_github.py. test_github_connection_integration.py covers
the two wired together end-to-end."""

from __future__ import annotations

from forgeai_integrations.connection import ConnectionStatus, connect_repository
from forgeai_integrations.exceptions import (
    AuthenticationFailureError,
    InsufficientPermissionsError,
    ProviderUnavailableError,
    RateLimitedError,
    RepositoryNotFoundError,
)
from forgeai_integrations.provider import RepositoryMetadata


class _FakeProvider:
    def __init__(
        self,
        *,
        scopes: frozenset[str] = frozenset(),
        repository: RepositoryMetadata | None = None,
        scopes_error: Exception | None = None,
        repository_error: Exception | None = None,
    ) -> None:
        self._scopes = scopes
        self._repository = repository
        self._scopes_error = scopes_error
        self._repository_error = repository_error

    async def get_authorized_scopes(self) -> frozenset[str]:
        if self._scopes_error is not None:
            raise self._scopes_error
        return self._scopes

    async def get_repository(self, owner: str, name: str) -> RepositoryMetadata:
        if self._repository_error is not None:
            raise self._repository_error
        assert self._repository is not None
        return self._repository


def _metadata(visibility: str = "public") -> RepositoryMetadata:
    return RepositoryMetadata(
        owner="forgeai",
        name="forge",
        full_name="forgeai/forge",
        default_branch="main",
        visibility=visibility,
        html_url="https://github.com/forgeai/forge",
    )


class TestConnectRepository:
    async def test_a_public_repository_connects_with_no_scopes_required(self) -> None:
        provider = _FakeProvider(scopes=frozenset(), repository=_metadata("public"))

        report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.CONNECTED
        assert report.is_connected is True
        assert report.repository is not None
        assert report.missing_scopes == frozenset()

    async def test_a_private_repository_with_repo_scope_connects(self) -> None:
        provider = _FakeProvider(scopes=frozenset({"repo"}), repository=_metadata("private"))

        report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.CONNECTED

    async def test_a_private_repository_without_repo_scope_is_insufficient_permissions(
        self,
    ) -> None:
        provider = _FakeProvider(scopes=frozenset(), repository=_metadata("private"))

        report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.INSUFFICIENT_PERMISSIONS
        assert report.missing_scopes == frozenset({"repo"})
        assert report.is_connected is False

    async def test_repository_not_found_is_reported_not_raised(self) -> None:
        provider = _FakeProvider(
            scopes=frozenset(), repository_error=RepositoryNotFoundError("forgeai", "ghost")
        )

        report = await connect_repository(provider, "forgeai", "ghost")

        assert report.connection_status == ConnectionStatus.REPOSITORY_NOT_FOUND
        assert report.repository is None

    async def test_authentication_failure_fetching_scopes_is_reported_not_raised(self) -> None:
        provider = _FakeProvider(scopes_error=AuthenticationFailureError("github", "bad token"))

        report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.AUTHENTICATION_FAILED

    async def test_authentication_failure_fetching_repository_is_reported_not_raised(
        self,
    ) -> None:
        provider = _FakeProvider(
            scopes=frozenset(),
            repository_error=AuthenticationFailureError("github", "revoked mid-request"),
        )

        report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.AUTHENTICATION_FAILED

    async def test_provider_outage_is_reported_not_raised(self) -> None:
        provider = _FakeProvider(scopes_error=ProviderUnavailableError("github", "HTTP 503"))

        report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.PROVIDER_UNAVAILABLE

    async def test_rate_limit_is_reported_not_raised(self) -> None:
        provider = _FakeProvider(scopes_error=RateLimitedError("github", 42.0))

        report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.RATE_LIMITED

    async def test_bare_forbidden_fetching_repository_reports_its_own_missing_scopes(
        self,
    ) -> None:
        provider = _FakeProvider(
            scopes=frozenset({"repo"}),
            repository_error=InsufficientPermissionsError("github", frozenset({"read:org"})),
        )

        report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.INSUFFICIENT_PERMISSIONS
        assert report.missing_scopes == frozenset({"read:org"})
