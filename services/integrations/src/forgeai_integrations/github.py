"""A real GitHub REST API (v3) client — the one concrete RepositoryProvider
this sprint implements. Authenticated with a bearer token handed to it by the
caller; this class deliberately doesn't know or care whether that token is a
classic PAT, a fine-grained PAT, or a GitHub App installation token — the
HTTP shape is identical (`Authorization: Bearer <token>`). *Acquiring* that
token via an OAuth/App authorization flow (Sprint 17 Stage 2) rather than a
user pasting a PAT into a form is a separate, still-pending concern; nothing
here should be read as "the PAT-paste flow", since this class never asks
where its token came from.

`get_authorized_scopes()` reads GitHub's `X-OAuth-Scopes` response header,
which classic PATs and OAuth tokens populate. Fine-grained PATs and GitHub
App installation tokens report permissions through a different mechanism
(the installation/permissions object, not a scopes header) — supporting
those is future work; this method is honest about that in its docstring
rather than silently returning an empty set that would misreport as
"insufficient permissions".
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from forgeai_integrations.exceptions import (
    AuthenticationFailureError,
    InsufficientPermissionsError,
    ProviderUnavailableError,
    RateLimitedError,
    RepositoryNotFoundError,
)
from forgeai_integrations.provider import RepositoryMetadata

_PROVIDER_NAME = "GitHub"
_BASE_URL = "https://api.github.com"


class GitHubProvider:
    def __init__(self, token: str, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(base_url=_BASE_URL)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> GitHubProvider:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def get_repository(self, owner: str, name: str) -> RepositoryMetadata:
        response = await self._get(f"/repos/{owner}/{name}")
        if response.status_code == 404:
            raise RepositoryNotFoundError(owner, name)
        self._raise_for_common_errors(response)
        body: dict[str, Any] = response.json()
        return RepositoryMetadata(
            owner=body["owner"]["login"],
            name=body["name"],
            full_name=body["full_name"],
            default_branch=body["default_branch"],
            visibility=body.get("visibility") or ("private" if body["private"] else "public"),
            html_url=body["html_url"],
        )

    async def get_authorized_scopes(self) -> frozenset[str]:
        response = await self._get("/user")
        self._raise_for_common_errors(response)
        scopes_header = response.headers.get("X-OAuth-Scopes", "")
        return frozenset(scope.strip() for scope in scopes_header.split(",") if scope.strip())

    async def _get(self, path: str) -> httpx.Response:
        try:
            return await self._client.get(
                path,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(_PROVIDER_NAME, str(exc)) from exc

    @staticmethod
    def _raise_for_common_errors(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise AuthenticationFailureError(_PROVIDER_NAME, "credential is invalid or expired")
        if response.status_code == 403:
            if response.headers.get("X-RateLimit-Remaining") == "0":
                reset_at = response.headers.get("X-RateLimit-Reset")
                retry_after = None
                if reset_at is not None:
                    retry_after = max(0.0, float(reset_at) - time.time())
                raise RateLimitedError(_PROVIDER_NAME, retry_after)
            raise InsufficientPermissionsError(_PROVIDER_NAME)
        if response.status_code >= 500:
            raise ProviderUnavailableError(_PROVIDER_NAME, f"HTTP {response.status_code}")
        response.raise_for_status()
