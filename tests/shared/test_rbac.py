"""
SEC-008: Tests for Role-Based Access Control (RBAC).
"""

from dataclasses import dataclass

import pytest


class TestPermissionEnum:
    """Test Permission enumeration."""

    def test_regulation_permissions_exist(self):
        """Regulation permissions should be defined."""
        from shared.rbac import Permission

        assert Permission.REGULATION_READ.value == "regulation:read"
        assert Permission.REGULATION_WRITE.value == "regulation:write"
        assert Permission.REGULATION_DELETE.value == "regulation:delete"
        assert Permission.REGULATION_INGEST.value == "regulation:ingest"

    def test_analysis_permissions_exist(self):
        """Analysis permissions should be defined."""
        from shared.rbac import Permission

        assert Permission.ANALYSIS_READ.value == "analysis:read"
        assert Permission.ANALYSIS_CREATE.value == "analysis:create"
        assert Permission.ANALYSIS_DELETE.value == "analysis:delete"
        assert Permission.ANALYSIS_EXPORT.value == "analysis:export"

    def test_admin_permissions_exist(self):
        """Admin permissions should be defined."""
        from shared.rbac import Permission

        assert Permission.ADMIN_READ.value == "admin:read"
        assert Permission.ADMIN_WRITE.value == "admin:write"
        assert Permission.ADMIN_SUPER.value == "admin:super"

    def test_permission_format(self):
        """Permissions should follow resource:action format."""
        from shared.rbac import Permission

        for perm in Permission:
            assert ":" in perm.value, f"Permission {perm} should have ':' separator"
            parts = perm.value.split(":")
            assert len(parts) == 2, f"Permission {perm} should have exactly 2 parts"


class TestRoleEnum:
    """Test Role enumeration."""

    def test_all_roles_exist(self):
        """All expected roles should be defined."""
        from shared.rbac import Role

        assert Role.VIEWER.value == "viewer"
        assert Role.ANALYST.value == "analyst"
        assert Role.EDITOR.value == "editor"
        assert Role.MANAGER.value == "manager"
        assert Role.ADMIN.value == "admin"
        assert Role.SUPER_ADMIN.value == "super_admin"

    def test_role_count(self):
        """Should have exactly 6 roles."""
        from shared.rbac import Role

        assert len(Role) == 6


class TestRolePermissions:
    """Test role-permission mappings."""

    def test_viewer_has_read_permissions(self):
        """Viewer should have read-only permissions."""
        from shared.rbac import Role, Permission, ROLE_PERMISSIONS

        viewer_perms = ROLE_PERMISSIONS[Role.VIEWER]
        
        assert Permission.REGULATION_READ in viewer_perms
        assert Permission.ANALYSIS_READ in viewer_perms
        assert Permission.GRAPH_READ in viewer_perms
        
        # Should NOT have write permissions
        assert Permission.REGULATION_WRITE not in viewer_perms
        assert Permission.ANALYSIS_CREATE not in viewer_perms

    def test_analyst_extends_viewer(self):
        """Analyst should have viewer permissions plus analysis creation."""
        from shared.rbac import Role, Permission, ROLE_PERMISSIONS

        analyst_perms = ROLE_PERMISSIONS[Role.ANALYST]
        viewer_perms = ROLE_PERMISSIONS[Role.VIEWER]
        
        # Should have all viewer permissions
        assert viewer_perms.issubset(analyst_perms)
        
        # Plus analysis create/export
        assert Permission.ANALYSIS_CREATE in analyst_perms
        assert Permission.ANALYSIS_EXPORT in analyst_perms

    def test_editor_extends_analyst(self):
        """Editor should have analyst permissions plus write access."""
        from shared.rbac import Role, Permission, ROLE_PERMISSIONS

        editor_perms = ROLE_PERMISSIONS[Role.EDITOR]
        
        # Should have write permissions
        assert Permission.REGULATION_WRITE in editor_perms
        assert Permission.REGULATION_INGEST in editor_perms
        assert Permission.GRAPH_WRITE in editor_perms

    def test_admin_has_full_tenant_access(self):
        """Admin should have full tenant access."""
        from shared.rbac import Role, Permission, ROLE_PERMISSIONS

        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
        
        # Should have all tenant management
        assert Permission.TENANT_READ in admin_perms
        assert Permission.TENANT_WRITE in admin_perms
        assert Permission.TENANT_MANAGE_USERS in admin_perms
        
        # Should have user management
        assert Permission.USER_READ in admin_perms
        assert Permission.USER_WRITE in admin_perms
        assert Permission.USER_DELETE in admin_perms

    def test_super_admin_has_all_permissions(self):
        """Super admin should have all permissions."""
        from shared.rbac import Role, Permission, ROLE_PERMISSIONS

        super_admin_perms = ROLE_PERMISSIONS[Role.SUPER_ADMIN]
        
        # Should have every permission
        for perm in Permission:
            assert perm in super_admin_perms, f"Super admin missing {perm}"


class TestUserContext:
    """Test UserContext dataclass."""

    def test_create_user_context(self):
        """Should create UserContext with required fields."""
        from shared.rbac import UserContext

        user = UserContext(
            user_id="user-123",
            tenant_id="tenant-456",
        )

        assert user.user_id == "user-123"
        assert user.tenant_id == "tenant-456"
        assert user.roles == set()
        assert user.permissions == set()

    def test_has_role(self):
        """has_role should check role membership."""
        from shared.rbac import UserContext, Role

        user = UserContext(
            user_id="user-123",
            roles={Role.ADMIN, Role.EDITOR},
        )

        assert user.has_role(Role.ADMIN) is True
        assert user.has_role(Role.EDITOR) is True
        assert user.has_role(Role.VIEWER) is False

    def test_has_permission_direct(self):
        """has_permission should check direct permissions."""
        from shared.rbac import UserContext, Permission

        user = UserContext(
            user_id="user-123",
            permissions={Permission.REGULATION_READ},
        )

        assert user.has_permission(Permission.REGULATION_READ) is True
        assert user.has_permission(Permission.REGULATION_WRITE) is False

    def test_has_permission_via_role(self):
        """has_permission should check role-based permissions."""
        from shared.rbac import UserContext, Role, Permission

        user = UserContext(
            user_id="user-123",
            roles={Role.VIEWER},
        )

        # Viewer has REGULATION_READ via role
        assert user.has_permission(Permission.REGULATION_READ) is True
        # But not REGULATION_WRITE
        assert user.has_permission(Permission.REGULATION_WRITE) is False

    def test_get_all_permissions(self):
        """get_all_permissions should combine direct and role-based."""
        from shared.rbac import UserContext, Role, Permission

        user = UserContext(
            user_id="user-123",
            roles={Role.VIEWER},
            permissions={Permission.ADMIN_READ},  # Direct permission
        )

        all_perms = user.get_all_permissions()
        
        # Should have viewer permissions
        assert Permission.REGULATION_READ in all_perms
        # Plus direct permission
        assert Permission.ADMIN_READ in all_perms


class TestAuthorizationErrors:
    """Test authorization error classes."""

    def test_permission_denied_error(self):
        """PermissionDeniedError should contain permission info."""
        from shared.rbac import Permission, PermissionDeniedError

        error = PermissionDeniedError(
            Permission.REGULATION_WRITE,
            user_id="user-123",
        )

        assert error.permission == Permission.REGULATION_WRITE
        assert error.user_id == "user-123"
        assert "regulation:write" in str(error)

    def test_role_denied_error(self):
        """RoleDeniedError should contain role info."""
        from shared.rbac import Role, RoleDeniedError

        error = RoleDeniedError(
            Role.ADMIN,
            user_id="user-123",
        )

        assert error.role == Role.ADMIN
        assert error.user_id == "user-123"
        assert "admin" in str(error)

    def test_tenant_access_denied_error(self):
        """TenantAccessDeniedError should contain tenant info."""
        from shared.rbac import TenantAccessDeniedError

        error = TenantAccessDeniedError(
            tenant_id="tenant-456",
            user_id="user-123",
        )

        assert error.tenant_id == "tenant-456"
        assert "tenant-456" in str(error)


class TestRBACManager:
    """Test RBACManager class."""

    @pytest.fixture
    def rbac(self):
        """Create RBAC manager."""
        from shared.rbac import RBACManager

        return RBACManager()

    @pytest.fixture
    def admin_user(self):
        """Create admin user context."""
        from shared.rbac import UserContext, Role

        return UserContext(
            user_id="admin-user",
            tenant_id="tenant-123",
            roles={Role.ADMIN},
        )

    @pytest.fixture
    def viewer_user(self):
        """Create viewer user context."""
        from shared.rbac import UserContext, Role

        return UserContext(
            user_id="viewer-user",
            tenant_id="tenant-123",
            roles={Role.VIEWER},
        )

    def test_has_permission(self, rbac, admin_user):
        """has_permission should delegate to UserContext."""
        from shared.rbac import Permission

        assert rbac.has_permission(admin_user, Permission.REGULATION_READ) is True
        assert rbac.has_permission(admin_user, Permission.ADMIN_SUPER) is False

    def test_has_role(self, rbac, admin_user):
        """has_role should delegate to UserContext."""
        from shared.rbac import Role

        assert rbac.has_role(admin_user, Role.ADMIN) is True
        assert rbac.has_role(admin_user, Role.SUPER_ADMIN) is False

    def test_require_permission_passes(self, rbac, admin_user):
        """require_permission should pass when user has permission."""
        from shared.rbac import Permission

        # Should not raise
        rbac.require_permission(admin_user, Permission.REGULATION_READ)

    def test_require_permission_raises(self, rbac, viewer_user):
        """require_permission should raise when user lacks permission."""
        from shared.rbac import Permission, PermissionDeniedError

        with pytest.raises(PermissionDeniedError):
            rbac.require_permission(viewer_user, Permission.REGULATION_WRITE)

    def test_require_role_passes(self, rbac, admin_user):
        """require_role should pass when user has role."""
        from shared.rbac import Role

        # Should not raise
        rbac.require_role(admin_user, Role.ADMIN)

    def test_require_role_raises(self, rbac, viewer_user):
        """require_role should raise when user lacks role."""
        from shared.rbac import Role, RoleDeniedError

        with pytest.raises(RoleDeniedError):
            rbac.require_role(viewer_user, Role.ADMIN)

    def test_can_access_tenant_own_tenant(self, rbac, admin_user):
        """User should access their own tenant."""
        assert rbac.can_access_tenant(admin_user, "tenant-123") is True

    def test_can_access_tenant_other_tenant_denied(self, rbac, admin_user):
        """User should not access other tenant."""
        assert rbac.can_access_tenant(admin_user, "other-tenant") is False

    def test_can_access_tenant_super_admin(self, rbac):
        """Super admin should access any tenant."""
        from shared.rbac import UserContext, Role

        super_admin = UserContext(
            user_id="super-admin",
            tenant_id="tenant-123",
            roles={Role.SUPER_ADMIN},
        )

        assert rbac.can_access_tenant(super_admin, "any-tenant") is True

    def test_require_tenant_access_passes(self, rbac, admin_user):
        """require_tenant_access should pass for own tenant."""
        # Should not raise
        rbac.require_tenant_access(admin_user, "tenant-123")

    def test_require_tenant_access_raises(self, rbac, admin_user):
        """require_tenant_access should raise for other tenant."""
        from shared.rbac import TenantAccessDeniedError

        with pytest.raises(TenantAccessDeniedError):
            rbac.require_tenant_access(admin_user, "other-tenant")


class TestPolicies:
    """Test policy classes."""

    def test_permission_policy(self):
        """PermissionPolicy should check for permission."""
        from shared.rbac import (
            PermissionPolicy,
            Permission,
            UserContext,
            Role,
        )

        policy = PermissionPolicy(Permission.REGULATION_READ)
        
        viewer = UserContext(user_id="u1", roles={Role.VIEWER})
        admin = UserContext(user_id="u2", roles={Role.ADMIN})

        assert policy.evaluate(viewer, "read", None) is True
        assert policy.evaluate(admin, "read", None) is True

    def test_role_policy(self):
        """RolePolicy should check for roles."""
        from shared.rbac import RolePolicy, Role, UserContext

        policy = RolePolicy({Role.ADMIN, Role.SUPER_ADMIN})
        
        viewer = UserContext(user_id="u1", roles={Role.VIEWER})
        admin = UserContext(user_id="u2", roles={Role.ADMIN})

        assert policy.evaluate(viewer, "action", None) is False
        assert policy.evaluate(admin, "action", None) is True

    def test_tenant_policy(self):
        """TenantPolicy should enforce tenant isolation."""
        from shared.rbac import TenantPolicy, UserContext

        policy = TenantPolicy()

        @dataclass
        class Resource:
            tenant_id: str

        user = UserContext(user_id="u1", tenant_id="tenant-123")
        own_resource = Resource(tenant_id="tenant-123")
        other_resource = Resource(tenant_id="other-tenant")

        assert policy.evaluate(user, "action", own_resource) is True
        assert policy.evaluate(user, "action", other_resource) is False

    def test_jurisdiction_policy(self):
        """JurisdictionPolicy should check jurisdiction access."""
        from shared.rbac import JurisdictionPolicy, UserContext

        policy = JurisdictionPolicy()

        @dataclass
        class Resource:
            jurisdiction: str

        user = UserContext(
            user_id="u1",
            allowed_jurisdictions={"US", "EU"},
        )
        us_resource = Resource(jurisdiction="US")
        jp_resource = Resource(jurisdiction="JP")

        assert policy.evaluate(user, "action", us_resource) is True
        assert policy.evaluate(user, "action", jp_resource) is False

    def test_composite_policy_and(self):
        """CompositePolicy with AND should require all policies."""
        from shared.rbac import (
            CompositePolicy,
            PermissionPolicy,
            Permission,
            UserContext,
            Role,
        )

        policy = CompositePolicy(
            policies=[
                PermissionPolicy(Permission.REGULATION_READ),
                PermissionPolicy(Permission.ANALYSIS_READ),
            ],
            require_all=True,
        )

        viewer = UserContext(user_id="u1", roles={Role.VIEWER})
        
        # Viewer has both permissions
        assert policy.evaluate(viewer, "action", None) is True

    def test_composite_policy_or(self):
        """CompositePolicy with OR should require any policy."""
        from shared.rbac import (
            CompositePolicy,
            PermissionPolicy,
            Permission,
            UserContext,
            Role,
        )

        policy = CompositePolicy(
            policies=[
                PermissionPolicy(Permission.ADMIN_SUPER),  # Viewer doesn't have
                PermissionPolicy(Permission.REGULATION_READ),  # Viewer has
            ],
            require_all=False,
        )

        viewer = UserContext(user_id="u1", roles={Role.VIEWER})
        
        # Viewer has REGULATION_READ, so OR passes
        assert policy.evaluate(viewer, "action", None) is True


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_permissions_for_role(self):
        """get_permissions_for_role should return role's permissions."""
        from shared.rbac import get_permissions_for_role, Role, Permission

        viewer_perms = get_permissions_for_role(Role.VIEWER)
        
        assert Permission.REGULATION_READ in viewer_perms
        assert Permission.REGULATION_WRITE not in viewer_perms

    def test_get_roles_with_permission(self):
        """get_roles_with_permission should return matching roles."""
        from shared.rbac import get_roles_with_permission, Role, Permission

        roles = get_roles_with_permission(Permission.REGULATION_READ)
        
        assert Role.VIEWER in roles
        assert Role.ANALYST in roles
        assert Role.ADMIN in roles

    def test_create_user_context_from_jwt(self):
        """create_user_context_from_jwt should parse JWT payload."""
        from shared.rbac import create_user_context_from_jwt, Role

        payload = {
            "sub": "user-123",
            "tenant_id": "tenant-456",
            "roles": ["admin", "editor"],
            "scopes": ["read:all"],
            "allowed_jurisdictions": ["US", "EU"],
        }

        user = create_user_context_from_jwt(payload)

        assert user.user_id == "user-123"
        assert user.tenant_id == "tenant-456"
        assert Role.ADMIN in user.roles
        assert Role.EDITOR in user.roles
        assert "read:all" in user.scopes
        assert "US" in user.allowed_jurisdictions


class TestDecorators:
    """Test decorator functions."""

    def test_require_permission_decorator_passes(self):
        """Decorator should pass when user has permission."""
        from shared.rbac import (
            require_permission_decorator,
            Permission,
            UserContext,
            Role,
        )

        @require_permission_decorator(Permission.REGULATION_READ)
        def protected_function(user: UserContext):
            return "success"

        user = UserContext(user_id="u1", roles={Role.VIEWER})
        result = protected_function(user=user)

        assert result == "success"

    def test_require_permission_decorator_raises(self):
        """Decorator should raise when user lacks permission."""
        from shared.rbac import (
            require_permission_decorator,
            Permission,
            UserContext,
            Role,
            PermissionDeniedError,
        )

        @require_permission_decorator(Permission.ADMIN_SUPER)
        def admin_function(user: UserContext):
            return "success"

        user = UserContext(user_id="u1", roles={Role.VIEWER})

        with pytest.raises(PermissionDeniedError):
            admin_function(user=user)

    def test_require_role_decorator_passes(self):
        """Decorator should pass when user has role."""
        from shared.rbac import (
            require_role_decorator,
            Role,
            UserContext,
        )

        @require_role_decorator(Role.ADMIN)
        def admin_function(user: UserContext):
            return "success"

        user = UserContext(user_id="u1", roles={Role.ADMIN})
        result = admin_function(user=user)

        assert result == "success"

    def test_require_role_decorator_raises(self):
        """Decorator should raise when user lacks role."""
        from shared.rbac import (
            require_role_decorator,
            Role,
            UserContext,
            RoleDeniedError,
        )

        @require_role_decorator(Role.ADMIN)
        def admin_function(user: UserContext):
            return "success"

        user = UserContext(user_id="u1", roles={Role.VIEWER})

        with pytest.raises(RoleDeniedError):
            admin_function(user=user)
