"""Declared, checkable permission scopes for capabilities — the mechanism
behind docs/architecture/12-security-architecture.md §4's least-privilege
requirement ("tool credentials handed to a capability are scoped to the
specific project, never broader"). Deliberately generic: nothing here is
software-engineering-specific, matching this sprint's domain-agnostic brief.

Enforcement (actually denying an execution that requests ungranted
permissions) is the Capability Executor's job (sub-sprint 3.6) — this module
only defines the vocabulary and the pure check function both the executor and
tests can share.
"""

from __future__ import annotations

import enum

from forgeai_capability_registry.exceptions import PermissionDeniedError


class Permission(enum.StrEnum):
    READ_CONTEXT = "read_context"
    WRITE_ARTIFACTS = "write_artifacts"
    READ_MEMORY = "read_memory"
    WRITE_MEMORY = "write_memory"
    CALL_EXTERNAL_API = "call_external_api"
    EXECUTE_CODE = "execute_code"
    ACCESS_SECRETS = "access_secrets"


def check_permissions(
    capability_id: str, required: frozenset[Permission], granted: frozenset[Permission]
) -> None:
    """Raises PermissionDeniedError listing exactly what's missing, rather than
    a bare "access denied" — the caller (a human debugging a failed execution,
    or an admin deciding whether to grant more scope) needs to know which
    specific permissions to add, not just that something was rejected."""
    missing = {permission.value for permission in required - granted}
    if missing:
        raise PermissionDeniedError(capability_id, missing)
