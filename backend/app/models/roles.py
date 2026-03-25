"""Role-Based Access Control for Avni AI Platform.

4 roles with hierarchical permissions:
- ngo_user: Field staff. Chat + knowledge search + support only
- implementor: + bundle generation, SRS wizard, rule generation
- org_admin: + bundle upload to Avni, org management, agent
- platform_admin: Everything including usage stats, all orgs
"""
from enum import Enum


class UserRole(str, Enum):
    NGO_USER = "ngo_user"
    IMPLEMENTOR = "implementor"
    ORG_ADMIN = "org_admin"
    PLATFORM_ADMIN = "platform_admin"


class Permission(str, Enum):
    # Chat & Knowledge (ngo_user)
    CHAT = "chat"
    KNOWLEDGE_SEARCH = "knowledge_search"
    SUPPORT = "support"
    VIEW_GUIDES = "view_guides"
    FEEDBACK = "feedback"
    VIEW_SESSIONS = "view_sessions"
    VIEW_PROFILE = "view_profile"
    EDIT_PROFILE = "edit_profile"

    # Implementation (implementor)
    BUNDLE_GENERATE = "bundle_generate"
    BUNDLE_VALIDATE = "bundle_validate"
    BUNDLE_REVIEW = "bundle_review"
    SRS_WIZARD = "srs_wizard"
    RULE_GENERATE = "rule_generate"
    RULE_VALIDATE = "rule_validate"
    VOICE_MAP = "voice_map"
    IMAGE_EXTRACT = "image_extract"

    # Organisation Admin (org_admin)
    BUNDLE_UPLOAD = "bundle_upload"
    ORG_CONNECT = "org_connect"
    ORG_MANAGE_USERS = "org_manage_users"
    AGENT_RUN = "agent_run"
    MCP_CALL = "mcp_call"
    VIEW_ORG_USAGE = "view_org_usage"

    # Platform Admin
    VIEW_ALL_USAGE = "view_all_usage"
    MANAGE_KNOWLEDGE = "manage_knowledge"
    MANAGE_SYSTEM = "manage_system"
    VIEW_ALL_ORGS = "view_all_orgs"


# Role -> set of permissions (hierarchical: each role includes all permissions of roles below it)
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.NGO_USER: {
        Permission.CHAT, Permission.KNOWLEDGE_SEARCH, Permission.SUPPORT,
        Permission.VIEW_GUIDES, Permission.FEEDBACK, Permission.VIEW_SESSIONS,
        Permission.VIEW_PROFILE, Permission.EDIT_PROFILE,
    },
    UserRole.IMPLEMENTOR: set(),  # filled below
    UserRole.ORG_ADMIN: set(),
    UserRole.PLATFORM_ADMIN: set(),
}

# Build hierarchy
ROLE_PERMISSIONS[UserRole.IMPLEMENTOR] = ROLE_PERMISSIONS[UserRole.NGO_USER] | {
    Permission.BUNDLE_GENERATE, Permission.BUNDLE_VALIDATE, Permission.BUNDLE_REVIEW,
    Permission.SRS_WIZARD, Permission.RULE_GENERATE, Permission.RULE_VALIDATE,
    Permission.VOICE_MAP, Permission.IMAGE_EXTRACT,
}
ROLE_PERMISSIONS[UserRole.ORG_ADMIN] = ROLE_PERMISSIONS[UserRole.IMPLEMENTOR] | {
    Permission.BUNDLE_UPLOAD, Permission.ORG_CONNECT, Permission.ORG_MANAGE_USERS,
    Permission.AGENT_RUN, Permission.MCP_CALL, Permission.VIEW_ORG_USAGE,
}
ROLE_PERMISSIONS[UserRole.PLATFORM_ADMIN] = ROLE_PERMISSIONS[UserRole.ORG_ADMIN] | {
    Permission.VIEW_ALL_USAGE, Permission.MANAGE_KNOWLEDGE, Permission.MANAGE_SYSTEM,
    Permission.VIEW_ALL_ORGS,
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


def get_permissions(role: UserRole) -> set[Permission]:
    """Get all permissions for a role."""
    return ROLE_PERMISSIONS.get(role, set())


# Map route prefixes to required permissions for middleware auto-check
ROUTE_PERMISSIONS: dict[str, Permission] = {
    "/api/chat": Permission.CHAT,
    "/api/knowledge": Permission.KNOWLEDGE_SEARCH,
    "/api/support": Permission.SUPPORT,
    "/api/bundle/generate": Permission.BUNDLE_GENERATE,
    "/api/bundle/validate": Permission.BUNDLE_VALIDATE,
    "/api/bundle/review": Permission.BUNDLE_REVIEW,
    "/api/srs": Permission.SRS_WIZARD,
    "/api/rules": Permission.RULE_GENERATE,
    "/api/voice": Permission.VOICE_MAP,
    "/api/image": Permission.IMAGE_EXTRACT,
    "/api/avni/bundle/upload": Permission.BUNDLE_UPLOAD,
    "/api/avni/org": Permission.ORG_CONNECT,
    "/api/agent": Permission.AGENT_RUN,
    "/api/mcp": Permission.MCP_CALL,
    "/api/usage": Permission.VIEW_ORG_USAGE,
    "/api/documents": Permission.MANAGE_KNOWLEDGE,
    "/api/admin": Permission.MANAGE_SYSTEM,
}
