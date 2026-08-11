"""Every model must be imported here — Alembic's autogenerate diffs against
Base.metadata, which only knows about models that have actually been imported
somewhere. A model defined but missing from this file is invisible to migrations.
"""

from forgeai_core.models.audit_log import AuditLog
from forgeai_core.models.model_profile import ModelProfileRecord
from forgeai_core.models.notification import Notification
from forgeai_core.models.oauth_account import OAuthAccount
from forgeai_core.models.organization import Organization
from forgeai_core.models.organization_member import OrganizationMember
from forgeai_core.models.project import Project
from forgeai_core.models.project_member import ProjectMember
from forgeai_core.models.session import UserSession
from forgeai_core.models.usage_ledger_entry import UsageLedgerEntry
from forgeai_core.models.user import User
from forgeai_core.models.user_preference import UserPreference
from forgeai_core.models.workflow import Workflow
from forgeai_core.models.workflow_approval import WorkflowApproval
from forgeai_core.models.workflow_artifact import WorkflowArtifact
from forgeai_core.models.workflow_event import WorkflowEvent
from forgeai_core.models.workflow_execution import WorkflowExecution
from forgeai_core.models.workflow_log import WorkflowLog
from forgeai_core.models.workflow_metric import WorkflowMetric
from forgeai_core.models.workflow_queue_entry import WorkflowQueueEntry
from forgeai_core.models.workflow_stage import WorkflowStage
from forgeai_core.models.workflow_stage_execution import WorkflowStageExecution
from forgeai_core.models.workflow_template import WorkflowTemplate
from forgeai_core.models.workflow_version import WorkflowVersion

__all__ = [
    "AuditLog",
    "ModelProfileRecord",
    "Notification",
    "OAuthAccount",
    "Organization",
    "OrganizationMember",
    "Project",
    "ProjectMember",
    "UsageLedgerEntry",
    "User",
    "UserPreference",
    "UserSession",
    "Workflow",
    "WorkflowApproval",
    "WorkflowArtifact",
    "WorkflowEvent",
    "WorkflowExecution",
    "WorkflowLog",
    "WorkflowMetric",
    "WorkflowQueueEntry",
    "WorkflowStage",
    "WorkflowStageExecution",
    "WorkflowTemplate",
    "WorkflowVersion",
]
