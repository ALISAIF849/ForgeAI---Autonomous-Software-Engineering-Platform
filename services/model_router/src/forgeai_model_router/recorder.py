"""The plug point for "what happens to usage/cost after a successful
completion" — same ABC-as-injection-seam pattern as ModelProvider (provider.py)
and forgeai_workflow_engine.runner.StageRunner. ModelRouter itself stays
persistence-agnostic: it calls whatever UsageRecorder it's given (recording
is entirely opt-in — see router.py), never importing a concrete, DB-backed
implementation directly. The real implementation (UsageLedger) lives in
persistence.py, sub-sprint 3.2.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from forgeai_model_router.types import TokenUsage


class UsageRecorder(ABC):
    @abstractmethod
    async def record(
        self,
        model_key: str,
        usage: TokenUsage,
        *,
        organization_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        workflow_execution_id: uuid.UUID | None = None,
    ) -> None: ...
