"""Every domain error this package raises. Same one-file convention as
forgeai_workflow_engine.exceptions — catch `ModelRouterError` to handle
anything from this package without needing to know which module raised it.
"""

from __future__ import annotations


class ModelRouterError(Exception):
    """Base class for every error this package raises."""


class ModelNotFoundError(ModelRouterError):
    def __init__(self, model_key: str) -> None:
        self.model_key = model_key
        super().__init__(f"No model profile registered for key '{model_key}'.")


class ModelAlreadyRegisteredError(ModelRouterError):
    def __init__(self, model_key: str) -> None:
        self.model_key = model_key
        super().__init__(f"Model profile '{model_key}' is already registered.")


class ProviderError(ModelRouterError):
    """Raised by a ModelProvider when a single completion attempt fails —
    network error, rate limit, provider-side error, whatever the cause. The
    router treats every ProviderError identically: retryable, then
    fallback-chain-triggering, regardless of what specifically went wrong."""


class ProviderNotConfiguredError(ModelRouterError):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"No provider implementation configured for '{provider}'.")


class AllModelsExhaustedError(ModelRouterError):
    def __init__(self, model_keys: list[str]) -> None:
        self.model_keys = model_keys
        super().__init__(
            "All candidate models exhausted without a successful completion: "
            f"{', '.join(model_keys)}."
        )
