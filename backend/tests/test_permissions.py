"""Tests for role-based access control.

Tests the role hierarchy and permission checks.
Note: The permissions module may not exist yet. These tests define the
expected RBAC contract for the Avni AI Platform.
"""

import pytest


# Define the expected role hierarchy and permissions
ROLE_PERMISSIONS = {
    "ngo_user": {"chat", "knowledge_search", "support_diagnose"},
    "implementor": {
        "chat", "knowledge_search", "support_diagnose",
        "bundle_generate", "bundle_validate", "rule_generate", "rule_validate",
    },
    "org_admin": {
        "chat", "knowledge_search", "support_diagnose",
        "bundle_generate", "bundle_validate", "rule_generate", "rule_validate",
        "bundle_upload", "user_manage", "org_configure",
    },
    "platform_admin": {
        "chat", "knowledge_search", "support_diagnose",
        "bundle_generate", "bundle_validate", "rule_generate", "rule_validate",
        "bundle_upload", "user_manage", "org_configure",
        "manage_system", "view_usage", "manage_knowledge",
    },
}

ALL_PERMISSIONS = set()
for perms in ROLE_PERMISSIONS.values():
    ALL_PERMISSIONS |= perms


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a given permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())


class TestNGOUser:
    def test_ngo_user_has_chat_permission(self):
        assert has_permission("ngo_user", "chat") is True

    def test_ngo_user_has_knowledge_search(self):
        assert has_permission("ngo_user", "knowledge_search") is True

    def test_ngo_user_has_support_diagnose(self):
        assert has_permission("ngo_user", "support_diagnose") is True

    def test_ngo_user_lacks_bundle_generate(self):
        assert has_permission("ngo_user", "bundle_generate") is False

    def test_ngo_user_lacks_rule_generate(self):
        assert has_permission("ngo_user", "rule_generate") is False

    def test_ngo_user_lacks_manage_system(self):
        assert has_permission("ngo_user", "manage_system") is False


class TestImplementor:
    def test_implementor_has_bundle_generate(self):
        assert has_permission("implementor", "bundle_generate") is True

    def test_implementor_has_rule_generate(self):
        assert has_permission("implementor", "rule_generate") is True

    def test_implementor_has_bundle_validate(self):
        assert has_permission("implementor", "bundle_validate") is True

    def test_implementor_lacks_bundle_upload(self):
        assert has_permission("implementor", "bundle_upload") is False

    def test_implementor_lacks_user_manage(self):
        assert has_permission("implementor", "user_manage") is False

    def test_implementor_lacks_manage_system(self):
        assert has_permission("implementor", "manage_system") is False


class TestOrgAdmin:
    def test_org_admin_has_bundle_upload(self):
        assert has_permission("org_admin", "bundle_upload") is True

    def test_org_admin_has_user_manage(self):
        assert has_permission("org_admin", "user_manage") is True

    def test_org_admin_has_org_configure(self):
        assert has_permission("org_admin", "org_configure") is True

    def test_org_admin_inherits_implementor_permissions(self):
        implementor_perms = ROLE_PERMISSIONS["implementor"]
        org_admin_perms = ROLE_PERMISSIONS["org_admin"]
        assert implementor_perms.issubset(org_admin_perms)

    def test_org_admin_lacks_manage_system(self):
        assert has_permission("org_admin", "manage_system") is False


class TestPlatformAdmin:
    def test_platform_admin_has_everything(self):
        for perm in ALL_PERMISSIONS:
            assert has_permission("platform_admin", perm) is True, f"platform_admin missing {perm}"

    def test_platform_admin_has_manage_system(self):
        assert has_permission("platform_admin", "manage_system") is True

    def test_platform_admin_has_view_usage(self):
        assert has_permission("platform_admin", "view_usage") is True

    def test_platform_admin_has_manage_knowledge(self):
        assert has_permission("platform_admin", "manage_knowledge") is True


class TestRoleHierarchy:
    def test_role_hierarchy_inherits_correctly(self):
        """Each role level includes all permissions from lower levels."""
        ngo = ROLE_PERMISSIONS["ngo_user"]
        implementor = ROLE_PERMISSIONS["implementor"]
        org_admin = ROLE_PERMISSIONS["org_admin"]
        platform_admin = ROLE_PERMISSIONS["platform_admin"]

        assert ngo.issubset(implementor)
        assert implementor.issubset(org_admin)
        assert org_admin.issubset(platform_admin)

    def test_unknown_role_has_no_permissions(self):
        assert has_permission("unknown_role", "chat") is False
        assert has_permission("", "chat") is False

    def test_permission_count_increases_with_role(self):
        ngo_count = len(ROLE_PERMISSIONS["ngo_user"])
        impl_count = len(ROLE_PERMISSIONS["implementor"])
        admin_count = len(ROLE_PERMISSIONS["org_admin"])
        platform_count = len(ROLE_PERMISSIONS["platform_admin"])

        assert ngo_count < impl_count < admin_count < platform_count
