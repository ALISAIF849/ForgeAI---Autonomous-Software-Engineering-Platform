from __future__ import annotations

from decimal import Decimal

import pytest

from forgeai_model_router.exceptions import ModelAlreadyRegisteredError, ModelNotFoundError
from forgeai_model_router.profile import ModelProfile, ModelTier
from forgeai_model_router.registry import ModelRegistry


def _profile(key: str, tier: ModelTier = ModelTier.FAST_CHEAP) -> ModelProfile:
    return ModelProfile(
        key=key,
        provider="mock",
        model_id=f"mock-{key}",
        tier=tier,
        context_window=8000,
        cost_per_1m_input=Decimal("1.00"),
        cost_per_1m_output=Decimal("2.00"),
    )


class TestRegisterAndGet:
    def test_register_then_get_round_trips(self) -> None:
        registry = ModelRegistry()
        profile = _profile("fast-a")
        registry.register(profile)

        assert registry.get("fast-a") == profile

    def test_registering_a_duplicate_key_raises(self) -> None:
        registry = ModelRegistry()
        registry.register(_profile("dup"))

        with pytest.raises(ModelAlreadyRegisteredError):
            registry.register(_profile("dup"))

    def test_getting_an_unregistered_key_raises(self) -> None:
        registry = ModelRegistry()
        with pytest.raises(ModelNotFoundError):
            registry.get("nope")


class TestListByTier:
    def test_list_by_tier_returns_only_matching_active_profiles(self) -> None:
        registry = ModelRegistry()
        registry.register(_profile("fast-1", ModelTier.FAST_CHEAP))
        registry.register(_profile("fast-2", ModelTier.FAST_CHEAP))
        registry.register(_profile("balanced-1", ModelTier.BALANCED))

        fast = registry.list_by_tier(ModelTier.FAST_CHEAP)

        assert {p.key for p in fast} == {"fast-1", "fast-2"}

    def test_list_by_tier_excludes_deactivated_profiles(self) -> None:
        registry = ModelRegistry()
        registry.register(_profile("fast-1", ModelTier.FAST_CHEAP))
        registry.deactivate("fast-1")

        assert registry.list_by_tier(ModelTier.FAST_CHEAP) == []


class TestDeactivate:
    def test_deactivate_flips_is_active_but_leaves_the_profile_gettable(self) -> None:
        registry = ModelRegistry()
        registry.register(_profile("fast-1"))

        registry.deactivate("fast-1")

        profile = registry.get("fast-1")
        assert profile.is_active is False
        assert profile.key == "fast-1"
