import pytest

from forgeai_capability_registry.exceptions import PermissionDeniedError
from forgeai_capability_registry.permissions import Permission, check_permissions


def test_sufficient_permissions_pass_silently() -> None:
    check_permissions(
        "example",
        required=frozenset({Permission.READ_CONTEXT}),
        granted=frozenset({Permission.READ_CONTEXT, Permission.WRITE_ARTIFACTS}),
    )  # must not raise


def test_missing_permission_raises_with_the_specific_gap() -> None:
    with pytest.raises(PermissionDeniedError) as exc_info:
        check_permissions(
            "example",
            required=frozenset({Permission.READ_CONTEXT, Permission.ACCESS_SECRETS}),
            granted=frozenset({Permission.READ_CONTEXT}),
        )
    assert exc_info.value.missing == {"access_secrets"}


def test_no_required_permissions_always_passes() -> None:
    check_permissions("example", required=frozenset(), granted=frozenset())
