"""Proves connect_repository() and GitHubProvider are actually wired
together correctly, not just individually correct in isolation — a real
GitHubProvider (backed by a scripted httpx.MockTransport) run through
connect_repository() end to end."""

from __future__ import annotations

import httpx

from forgeai_integrations.connection import ConnectionStatus, connect_repository
from forgeai_integrations.github import GitHubProvider


def _handler_for(*, scopes: str, repo_status: int, private: bool = True) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={}, headers={"X-OAuth-Scopes": scopes})
        if request.url.path == "/repos/forgeai/forge":
            if repo_status == 404:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(
                repo_status,
                json={
                    "owner": {"login": "forgeai"},
                    "name": "forge",
                    "full_name": "forgeai/forge",
                    "default_branch": "main",
                    "private": private,
                    "visibility": "private" if private else "public",
                    "html_url": "https://github.com/forgeai/forge",
                },
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    return httpx.MockTransport(handler)


class TestEndToEnd:
    async def test_a_private_repository_with_repo_scope_connects(self) -> None:
        client = httpx.AsyncClient(
            base_url="https://api.github.com",
            transport=_handler_for(scopes="repo, read:org", repo_status=200, private=True),
        )
        async with GitHubProvider("real-shaped-token", http_client=client) as provider:
            report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.CONNECTED
        assert report.repository is not None
        assert report.repository.default_branch == "main"
        assert report.provider == "github"

    async def test_a_private_repository_without_repo_scope_is_insufficient_permissions(
        self,
    ) -> None:
        client = httpx.AsyncClient(
            base_url="https://api.github.com",
            transport=_handler_for(scopes="", repo_status=200, private=True),
        )
        async with GitHubProvider("scoped-token", http_client=client) as provider:
            report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.INSUFFICIENT_PERMISSIONS
        assert report.missing_scopes == frozenset({"repo"})

    async def test_an_unknown_repository_is_reported_not_found(self) -> None:
        client = httpx.AsyncClient(
            base_url="https://api.github.com",
            transport=_handler_for(scopes="repo", repo_status=404),
        )
        async with GitHubProvider("real-shaped-token", http_client=client) as provider:
            report = await connect_repository(provider, "forgeai", "forge")

        assert report.connection_status == ConnectionStatus.REPOSITORY_NOT_FOUND
        assert report.repository is None
