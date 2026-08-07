"""Every domain error this package raises — mirrors
forgeai_workflow_engine.exceptions' shape (Sprint 2's pattern), including the
same ValueError double-inheritance on CapabilityValidationError, for the same
reason: Pydantic only auto-wraps ValueError/TypeError/AssertionError raised
inside a validator into pydantic.ValidationError.
"""

from __future__ import annotations


class CapabilityRegistryError(Exception):
    """Base class for every error this package raises."""


class CapabilityValidationError(CapabilityRegistryError, ValueError):
    """A CapabilityDefinition failed validation — bad shape, not a registry problem."""


class InvalidVersionError(CapabilityValidationError):
    def __init__(self, version: str) -> None:
        self.version = version
        super().__init__(f"'{version}' is not a valid version string — expected 'N.N.N'.")


class InvalidSchemaError(CapabilityValidationError):
    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"'{field}' is not a valid JSON Schema object: {reason}")


class CapabilityAlreadyRegisteredError(CapabilityRegistryError):
    def __init__(self, capability_id: str, version: str) -> None:
        self.capability_id = capability_id
        self.version = version
        super().__init__(
            f"Capability '{capability_id}' version '{version}' is already registered "
            "— capabilities are immutable once registered; register a new version instead."
        )


class CapabilityNotFoundError(CapabilityRegistryError):
    def __init__(self, capability_id: str, version: str) -> None:
        self.capability_id = capability_id
        self.version = version
        super().__init__(f"No capability registered for '{capability_id}' version '{version}'.")


class PermissionDeniedError(CapabilityRegistryError):
    def __init__(self, capability_id: str, missing: set[str]) -> None:
        self.capability_id = capability_id
        self.missing = missing
        super().__init__(
            f"Capability '{capability_id}' requires permissions not granted to this "
            f"execution context: {', '.join(sorted(missing))}."
        )
