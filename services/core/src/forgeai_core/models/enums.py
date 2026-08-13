import enum


class OrgRole(enum.StrEnum):
    """Ordered from most to least privileged — RBAC checks compare positions in
    this list rather than hardcoding role names, so adding a role later means
    inserting it in the right place, not touching every permission check."""

    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class ProjectStatus(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ProjectVisibility(enum.StrEnum):
    PRIVATE = "private"
    INTERNAL = "internal"
    PUBLIC = "public"


class Theme(enum.StrEnum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class OAuthProvider(enum.StrEnum):
    GOOGLE = "google"
    GITHUB = "github"


class NotificationType(enum.StrEnum):
    ORG_INVITE = "org_invite"
    ORG_ROLE_CHANGED = "org_role_changed"
    PROJECT_UPDATE = "project_update"
    MENTION = "mention"
    SYSTEM = "system"


class DigestFrequency(enum.StrEnum):
    NEVER = "never"
    DAILY = "daily"
    WEEKLY = "weekly"


class ArchitectureDecisionStatus(enum.StrEnum):
    """Mirrors the standard ADR lifecycle (docs/architecture/05-memory-engine.md
    §4) — superseding is an explicit new record pointing back at the old one
    via `superseded_by_id`, never an in-place overwrite, so "why did we move
    away from X" stays answerable from the data alone."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
