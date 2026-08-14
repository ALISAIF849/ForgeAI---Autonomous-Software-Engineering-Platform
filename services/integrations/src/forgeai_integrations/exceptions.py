"""Every domain error this package raises. Same one-file, one-base-class
convention as forgeai_workflow_engine.exceptions / forgeai_capability_registry.exceptions
— catch `IntegrationError` to handle anything from this package without
needing to know which provider or module raised it. Deliberately
provider-agnostic names (not "GitHubNotFoundError"): a future GitLabProvider
raises the same exceptions for the same situations, so callers (connection
verification, workflows) don't need provider-specific except clauses.
"""

from __future__ import annotations


class IntegrationError(Exception):
    """Base class for every error this package raises."""


class RepositoryNotFoundError(IntegrationError):
    def __init__(self, owner: str, name: str) -> None:
        self.owner = owner
        self.name = name
        super().__init__(f"Repository '{owner}/{name}' was not found or is not accessible.")


class AuthenticationFailureError(IntegrationError):
    """The credential itself is missing, malformed, expired, or revoked —
    distinct from InsufficientPermissionsError, where the credential is
    valid but doesn't carry a required scope/permission."""

    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"Authentication with {provider} failed: {reason}")


class InsufficientPermissionsError(IntegrationError):
    """`missing` is empty when the provider returned a bare "forbidden"
    without this package being able to attribute it to specific scopes (a
    single 403 doesn't say which permission was missing) — connect_repository()
    (connection.py) is where a full missing-scope set gets computed by
    comparing granted vs. required scopes."""

    def __init__(self, provider: str, missing: frozenset[str] = frozenset()) -> None:
        self.provider = provider
        self.missing = missing
        detail = ", ".join(sorted(missing)) if missing else "access to this resource"
        super().__init__(f"{provider} credential is missing required permissions: {detail}.")


class ProviderUnavailableError(IntegrationError):
    """The provider's API itself failed (5xx, network error) — not a
    permission or not-found situation, and generally worth retrying."""

    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"{provider} is unavailable: {reason}")


class RateLimitedError(IntegrationError):
    def __init__(self, provider: str, retry_after_seconds: float | None) -> None:
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds
        suffix = (
            f" Retry after {retry_after_seconds:.0f}s." if retry_after_seconds is not None else ""
        )
        super().__init__(f"{provider} rate limit exceeded.{suffix}")
