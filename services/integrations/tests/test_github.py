"""Tests GitHubProvider's real request/response handling against a scripted
httpx.MockTransport — the actual URL construction, headers, and status-code
branching in github.py all run for real; only the network socket is
replaced, the same "mock the boundary, not the logic" discipline as
forgeai_model_router.provider.MockProvider."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from forgeai_integrations.exceptions import (
    AuthenticationFailureError,
    InsufficientPermissionsError,
    ProviderUnavailableError,
    RateLimitedError,
    RepositoryNotFoundError,
)
from forgeai_integrations.github import GitHubProvider


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    )


def _repo_response(*, private: bool = False, visibility: str | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "owner": {"login": "forgeai"},
            "name": "forge",
            "full_name": "forgeai/forge",
            "default_branch": "main",
            "private": private,
            "visibility": visibility,
            "html_url": "https://github.com/forgeai/forge",
        },
    )


class TestGetRepository:
    async def test_returns_repository_metadata_on_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/repos/forgeai/forge"
            assert request.headers["Authorization"] == "Bearer test-token"
            return _repo_response(private=True, visibility="private")

        async with GitHubProvider("test-token", http_client=_client(handler)) as provider:
            metadata = await provider.get_repository("forgeai", "forge")

        assert metadata.owner == "forgeai"
        assert metadata.name == "forge"
        assert metadata.default_branch == "main"
        assert metadata.visibility == "private"

    async def test_falls_back_to_private_flag_when_visibility_field_absent(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return _repo_response(private=False, visibility=None)

        async with GitHubProvider("test-token", http_client=_client(handler)) as provider:
            metadata = await provider.get_repository("forgeai", "forge")

        assert metadata.visibility == "public"

    async def test_404_raises_repository_not_found(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "Not Found"})

        async with GitHubProvider("test-token", http_client=_client(handler)) as provider:
            with pytest.raises(RepositoryNotFoundError):
                await provider.get_repository("forgeai", "ghost")

    async def test_401_raises_authentication_failure(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "Bad credentials"})

        async with GitHubProvider("bad-token", http_client=_client(handler)) as provider:
            with pytest.raises(AuthenticationFailureError):
                await provider.get_repository("forgeai", "forge")

    async def test_403_without_rate_limit_headers_raises_insufficient_permissions(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"message": "Forbidden"})

        async with GitHubProvider("test-token", http_client=_client(handler)) as provider:
            with pytest.raises(InsufficientPermissionsError):
                await provider.get_repository("forgeai", "forge")

    async def test_403_with_exhausted_rate_limit_raises_rate_limited(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                json={"message": "API rate limit exceeded"},
                headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"},
            )

        async with GitHubProvider("test-token", http_client=_client(handler)) as provider:
            with pytest.raises(RateLimitedError) as exc_info:
                await provider.get_repository("forgeai", "forge")

        assert exc_info.value.retry_after_seconds is not None
        assert exc_info.value.retry_after_seconds > 0

    async def test_5xx_raises_provider_unavailable(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="Service Unavailable")

        async with GitHubProvider("test-token", http_client=_client(handler)) as provider:
            with pytest.raises(ProviderUnavailableError):
                await provider.get_repository("forgeai", "forge")

    async def test_network_error_raises_provider_unavailable(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        async with GitHubProvider("test-token", http_client=_client(handler)) as provider:
            with pytest.raises(ProviderUnavailableError):
                await provider.get_repository("forgeai", "forge")


class TestGetAuthorizedScopes:
    async def test_parses_the_oauth_scopes_header(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/user"
            return httpx.Response(200, json={}, headers={"X-OAuth-Scopes": "repo, read:org"})

        async with GitHubProvider("test-token", http_client=_client(handler)) as provider:
            scopes = await provider.get_authorized_scopes()

        assert scopes == frozenset({"repo", "read:org"})

    async def test_missing_scopes_header_yields_empty_set(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        async with GitHubProvider("test-token", http_client=_client(handler)) as provider:
            scopes = await provider.get_authorized_scopes()

        assert scopes == frozenset()

    async def test_401_raises_authentication_failure(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "Bad credentials"})

        async with GitHubProvider("bad-token", http_client=_client(handler)) as provider:
            with pytest.raises(AuthenticationFailureError):
                await provider.get_authorized_scopes()


class TestClientLifecycle:
    async def test_aclose_closes_a_client_it_owns(self) -> None:
        provider = GitHubProvider("test-token")
        assert provider._client.is_closed is False
        await provider.aclose()
        assert provider._client.is_closed is True

    async def test_aclose_does_not_close_a_client_it_was_given(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        client = _client(handler)
        provider = GitHubProvider("test-token", http_client=client)
        await provider.aclose()
        assert client.is_closed is False
        await client.aclose()
