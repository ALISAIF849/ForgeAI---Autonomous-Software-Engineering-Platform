"""In-process model profile registry — the 3.1 counterpart to
forgeai_workflow_engine.registry's in-process WorkflowRegistry (2.1), same
bootstrap sequence: an in-memory registry first, DB-backed persistence
(model_profiles / model_routing_rules / usage_ledger,
docs/architecture/06-model-router.md §4) as a later sub-sprint once this
abstraction is proven.
"""

from __future__ import annotations

from forgeai_model_router.exceptions import ModelAlreadyRegisteredError, ModelNotFoundError
from forgeai_model_router.profile import ModelProfile, ModelTier


class ModelRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, ModelProfile] = {}

    def register(self, profile: ModelProfile) -> None:
        if profile.key in self._profiles:
            raise ModelAlreadyRegisteredError(profile.key)
        self._profiles[profile.key] = profile

    def get(self, key: str) -> ModelProfile:
        try:
            return self._profiles[key]
        except KeyError:
            raise ModelNotFoundError(key) from None

    def list_by_tier(self, tier: ModelTier) -> list[ModelProfile]:
        """Active profiles only — an inactive model isn't a real candidate
        for tier-based selection. Direct get() by key still returns an
        inactive profile; the router (not the registry) decides what to do
        with that when a caller names a specific model explicitly."""
        return [p for p in self._profiles.values() if p.tier == tier and p.is_active]

    def deactivate(self, key: str) -> None:
        profile = self.get(key)
        self._profiles[key] = profile.model_copy(update={"is_active": False})
