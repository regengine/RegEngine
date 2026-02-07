"""
SEC-008: Role-Based Access Control (RBAC) for RegEngine.

This module provides a comprehensive RBAC system with:
- Hierarchical roles with inheritance
- Fine-grained permission scopes
- Resource-level access control
- Tenant isolation
- Policy-based authorization

Usage:
    from shared.rbac import RBACManager, Permission, Role
    
    rbac = RBACManager()
    
    # Check permissions
    if rbac.has_permission(user, Permission.REGULATION_READ):
        # Allow access
        ...
    
    # Require permissions (raises if denied)
    rbac.require_permission(user, Permission.REGULATION_WRITE)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, Set, TypeVar, Union

import structlog
from pydantic import BaseModel

logger = structlog.get_logger("rbac")


# =============================================================================
# Permission Definitions
# =============================================================================

class Permission(str, Enum):
    """Fine-grained permission scopes.
    
    Format: {resource}:{action}
    
    Resources:
    - regulation: Regulatory documents and rules
    - analysis: Compliance analysis results
    - tenant: Tenant management
    - user: User management
    - api_key: API key management
    - webhook: Webhook configuration
    - audit: Audit logs
    - admin: Administrative functions
    """
    
    # Regulation permissions
    REGULATION_READ = "regulation:read"
    REGULATION_WRITE = "regulation:write"
    REGULATION_DELETE = "regulation:delete"
    REGULATION_INGEST = "regulation:ingest"
    
    # Analysis permissions
    ANALYSIS_READ = "analysis:read"
    ANALYSIS_CREATE = "analysis:create"
    ANALYSIS_DELETE = "analysis:delete"
    ANALYSIS_EXPORT = "analysis:export"
    
    # Graph permissions
    GRAPH_READ = "graph:read"
    GRAPH_WRITE = "graph:write"
    GRAPH_QUERY = "graph:query"
    
    # Tenant permissions
    TENANT_READ = "tenant:read"
    TENANT_WRITE = "tenant:write"
    TENANT_DELETE = "tenant:delete"
    TENANT_MANAGE_USERS = "tenant:manage_users"
    
    # User permissions
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"
    USER_INVITE = "user:invite"
    
    # API key permissions
    API_KEY_READ = "api_key:read"
    API_KEY_CREATE = "api_key:create"
    API_KEY_REVOKE = "api_key:revoke"
    API_KEY_MANAGE = "api_key:manage"
    
    # Webhook permissions
    WEBHOOK_READ = "webhook:read"
    WEBHOOK_WRITE = "webhook:write"
    WEBHOOK_DELETE = "webhook:delete"
    
    # Audit permissions
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"
    
    # Admin permissions
    ADMIN_READ = "admin:read"
    ADMIN_WRITE = "admin:write"
    ADMIN_SUPER = "admin:super"  # Full system access
    
    # Billing permissions
    BILLING_READ = "billing:read"
    BILLING_WRITE = "billing:write"


# =============================================================================
# Role Definitions
# =============================================================================

class Role(str, Enum):
    """Predefined roles with hierarchical permissions.
    
    Hierarchy (from lowest to highest):
    1. VIEWER - Read-only access
    2. ANALYST - Read + create analyses
    3. EDITOR - Read + write regulations
    4. MANAGER - Full access within tenant
    5. ADMIN - Tenant administration
    6. SUPER_ADMIN - System-wide administration
    """
    
    VIEWER = "viewer"
    ANALYST = "analyst"
    EDITOR = "editor"
    MANAGER = "manager"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


# Role permission mappings
ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.VIEWER: {
        Permission.REGULATION_READ,
        Permission.ANALYSIS_READ,
        Permission.GRAPH_READ,
        Permission.GRAPH_QUERY,
    },
    
    Role.ANALYST: {
        # Inherits from VIEWER
        Permission.REGULATION_READ,
        Permission.ANALYSIS_READ,
        Permission.GRAPH_READ,
        Permission.GRAPH_QUERY,
        # Additional
        Permission.ANALYSIS_CREATE,
        Permission.ANALYSIS_EXPORT,
    },
    
    Role.EDITOR: {
        # Inherits from ANALYST
        Permission.REGULATION_READ,
        Permission.ANALYSIS_READ,
        Permission.GRAPH_READ,
        Permission.GRAPH_QUERY,
        Permission.ANALYSIS_CREATE,
        Permission.ANALYSIS_EXPORT,
        # Additional
        Permission.REGULATION_WRITE,
        Permission.REGULATION_INGEST,
        Permission.GRAPH_WRITE,
    },
    
    Role.MANAGER: {
        # Inherits from EDITOR
        Permission.REGULATION_READ,
        Permission.REGULATION_WRITE,
        Permission.REGULATION_INGEST,
        Permission.ANALYSIS_READ,
        Permission.ANALYSIS_CREATE,
        Permission.ANALYSIS_EXPORT,
        Permission.GRAPH_READ,
        Permission.GRAPH_WRITE,
        Permission.GRAPH_QUERY,
        # Additional
        Permission.REGULATION_DELETE,
        Permission.ANALYSIS_DELETE,
        Permission.USER_READ,
        Permission.USER_INVITE,
        Permission.API_KEY_READ,
        Permission.API_KEY_CREATE,
        Permission.WEBHOOK_READ,
        Permission.WEBHOOK_WRITE,
        Permission.AUDIT_READ,
    },
    
    Role.ADMIN: {
        # Full tenant access
        Permission.REGULATION_READ,
        Permission.REGULATION_WRITE,
        Permission.REGULATION_DELETE,
        Permission.REGULATION_INGEST,
        Permission.ANALYSIS_READ,
        Permission.ANALYSIS_CREATE,
        Permission.ANALYSIS_DELETE,
        Permission.ANALYSIS_EXPORT,
        Permission.GRAPH_READ,
        Permission.GRAPH_WRITE,
        Permission.GRAPH_QUERY,
        Permission.TENANT_READ,
        Permission.TENANT_WRITE,
        Permission.TENANT_MANAGE_USERS,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_DELETE,
        Permission.USER_INVITE,
        Permission.API_KEY_READ,
        Permission.API_KEY_CREATE,
        Permission.API_KEY_REVOKE,
        Permission.API_KEY_MANAGE,
        Permission.WEBHOOK_READ,
        Permission.WEBHOOK_WRITE,
        Permission.WEBHOOK_DELETE,
        Permission.AUDIT_READ,
        Permission.AUDIT_EXPORT,
        Permission.BILLING_READ,
        Permission.BILLING_WRITE,
        Permission.ADMIN_READ,
    },
    
    Role.SUPER_ADMIN: {
        # All permissions
        *Permission,
    },
}


# =============================================================================
# User Context
# =============================================================================

@dataclass
class UserContext:
    """Represents the current user's security context.
    
    This is typically populated from JWT claims or API key metadata.
    """
    
    user_id: str
    tenant_id: Optional[str] = None
    roles: Set[Role] = field(default_factory=set)
    permissions: Set[Permission] = field(default_factory=set)  # Direct permissions
    scopes: Set[str] = field(default_factory=set)  # OAuth scopes
    
    # Resource-level restrictions
    allowed_jurisdictions: Set[str] = field(default_factory=set)
    
    # Additional context
    is_service_account: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: Role) -> bool:
        """Check if user has a specific role."""
        return role in self.roles

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission (direct or via role)."""
        # Check direct permissions first
        if permission in self.permissions:
            return True
        
        # Check role-based permissions
        for role in self.roles:
            if permission in ROLE_PERMISSIONS.get(role, set()):
                return True
        
        return False

    def get_all_permissions(self) -> Set[Permission]:
        """Get all permissions (direct + role-based)."""
        all_perms = set(self.permissions)
        for role in self.roles:
            all_perms.update(ROLE_PERMISSIONS.get(role, set()))
        return all_perms


# =============================================================================
# Authorization Errors
# =============================================================================

class AuthorizationError(Exception):
    """Base class for authorization errors."""
    pass


class PermissionDeniedError(AuthorizationError):
    """Raised when user lacks required permission."""
    
    def __init__(
        self,
        permission: Permission,
        user_id: Optional[str] = None,
        message: Optional[str] = None,
    ):
        self.permission = permission
        self.user_id = user_id
        self.message = message or f"Permission denied: {permission.value}"
        super().__init__(self.message)


class RoleDeniedError(AuthorizationError):
    """Raised when user lacks required role."""
    
    def __init__(
        self,
        role: Role,
        user_id: Optional[str] = None,
        message: Optional[str] = None,
    ):
        self.role = role
        self.user_id = user_id
        self.message = message or f"Role required: {role.value}"
        super().__init__(self.message)


class TenantAccessDeniedError(AuthorizationError):
    """Raised when user cannot access a tenant's resources."""
    
    def __init__(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        message: Optional[str] = None,
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.message = message or f"Access denied to tenant: {tenant_id}"
        super().__init__(self.message)


# =============================================================================
# Policy Engine
# =============================================================================

class Policy(ABC):
    """Abstract base class for authorization policies."""
    
    @abstractmethod
    def evaluate(
        self,
        user: UserContext,
        action: str,
        resource: Any,
    ) -> bool:
        """Evaluate if the user can perform the action on the resource.
        
        Args:
            user: The user context
            action: The action being performed
            resource: The resource being accessed
            
        Returns:
            True if allowed, False if denied
        """
        pass


class PermissionPolicy(Policy):
    """Policy that checks for specific permissions."""
    
    def __init__(self, required_permission: Permission):
        self.required_permission = required_permission

    def evaluate(
        self,
        user: UserContext,
        action: str,
        resource: Any,
    ) -> bool:
        return user.has_permission(self.required_permission)


class RolePolicy(Policy):
    """Policy that checks for specific roles."""
    
    def __init__(self, required_roles: Set[Role]):
        self.required_roles = required_roles

    def evaluate(
        self,
        user: UserContext,
        action: str,
        resource: Any,
    ) -> bool:
        return bool(user.roles & self.required_roles)


class TenantPolicy(Policy):
    """Policy that ensures tenant isolation."""
    
    def evaluate(
        self,
        user: UserContext,
        action: str,
        resource: Any,
    ) -> bool:
        # Super admins can access any tenant
        if Role.SUPER_ADMIN in user.roles:
            return True
        
        # Check if resource has tenant_id attribute
        resource_tenant = getattr(resource, "tenant_id", None)
        if resource_tenant is None:
            return True  # No tenant restriction on resource
        
        return user.tenant_id == resource_tenant


class JurisdictionPolicy(Policy):
    """Policy that checks jurisdiction access."""
    
    def evaluate(
        self,
        user: UserContext,
        action: str,
        resource: Any,
    ) -> bool:
        # If no jurisdiction restrictions, allow
        if not user.allowed_jurisdictions:
            return True
        
        # Check if resource has jurisdiction attribute
        resource_jurisdiction = getattr(resource, "jurisdiction", None)
        if resource_jurisdiction is None:
            return True  # No jurisdiction on resource
        
        return resource_jurisdiction in user.allowed_jurisdictions


class CompositePolicy(Policy):
    """Combines multiple policies with AND/OR logic."""
    
    def __init__(
        self,
        policies: list[Policy],
        require_all: bool = True,  # AND vs OR
    ):
        self.policies = policies
        self.require_all = require_all

    def evaluate(
        self,
        user: UserContext,
        action: str,
        resource: Any,
    ) -> bool:
        results = [p.evaluate(user, action, resource) for p in self.policies]
        
        if self.require_all:
            return all(results)
        return any(results)


# =============================================================================
# RBAC Manager
# =============================================================================

class RBACManager:
    """Central RBAC manager for authorization decisions.
    
    This class provides:
    - Permission checking with role inheritance
    - Policy-based authorization
    - Tenant isolation enforcement
    - Jurisdiction-based filtering
    """

    def __init__(self):
        self._policies: list[Policy] = [
            TenantPolicy(),  # Always enforce tenant isolation
        ]

    def add_policy(self, policy: Policy) -> None:
        """Add a custom policy to the authorization chain."""
        self._policies.append(policy)

    def has_permission(
        self,
        user: UserContext,
        permission: Permission,
    ) -> bool:
        """Check if user has a specific permission.
        
        Args:
            user: The user context
            permission: The permission to check
            
        Returns:
            True if user has the permission
        """
        return user.has_permission(permission)

    def has_role(
        self,
        user: UserContext,
        role: Role,
    ) -> bool:
        """Check if user has a specific role.
        
        Args:
            user: The user context
            role: The role to check
            
        Returns:
            True if user has the role
        """
        return user.has_role(role)

    def has_any_role(
        self,
        user: UserContext,
        roles: Set[Role],
    ) -> bool:
        """Check if user has any of the specified roles.
        
        Args:
            user: The user context
            roles: Set of roles to check
            
        Returns:
            True if user has at least one role
        """
        return bool(user.roles & roles)

    def require_permission(
        self,
        user: UserContext,
        permission: Permission,
    ) -> None:
        """Require user has a permission or raise PermissionDeniedError.
        
        Args:
            user: The user context
            permission: The required permission
            
        Raises:
            PermissionDeniedError: If user lacks the permission
        """
        if not self.has_permission(user, permission):
            logger.warning(
                "permission_denied",
                user_id=user.user_id,
                permission=permission.value,
            )
            raise PermissionDeniedError(permission, user.user_id)

    def require_role(
        self,
        user: UserContext,
        role: Role,
    ) -> None:
        """Require user has a role or raise RoleDeniedError.
        
        Args:
            user: The user context
            role: The required role
            
        Raises:
            RoleDeniedError: If user lacks the role
        """
        if not self.has_role(user, role):
            logger.warning(
                "role_denied",
                user_id=user.user_id,
                required_role=role.value,
            )
            raise RoleDeniedError(role, user.user_id)

    def authorize(
        self,
        user: UserContext,
        action: str,
        resource: Any,
        extra_policies: Optional[list[Policy]] = None,
    ) -> bool:
        """Evaluate all policies for an authorization decision.
        
        Args:
            user: The user context
            action: The action being performed
            resource: The resource being accessed
            extra_policies: Additional policies to evaluate
            
        Returns:
            True if all policies pass
        """
        all_policies = self._policies + (extra_policies or [])
        
        for policy in all_policies:
            if not policy.evaluate(user, action, resource):
                logger.warning(
                    "policy_denied",
                    user_id=user.user_id,
                    action=action,
                    policy=policy.__class__.__name__,
                )
                return False
        
        return True

    def require_authorization(
        self,
        user: UserContext,
        action: str,
        resource: Any,
        extra_policies: Optional[list[Policy]] = None,
    ) -> None:
        """Require authorization or raise AuthorizationError.
        
        Args:
            user: The user context
            action: The action being performed
            resource: The resource being accessed
            extra_policies: Additional policies to evaluate
            
        Raises:
            AuthorizationError: If any policy denies access
        """
        if not self.authorize(user, action, resource, extra_policies):
            raise AuthorizationError(
                f"Access denied for action '{action}' on resource"
            )

    def can_access_tenant(
        self,
        user: UserContext,
        tenant_id: str,
    ) -> bool:
        """Check if user can access a tenant.
        
        Args:
            user: The user context
            tenant_id: The tenant to check
            
        Returns:
            True if user can access the tenant
        """
        # Super admins can access any tenant
        if Role.SUPER_ADMIN in user.roles:
            return True
        
        return user.tenant_id == tenant_id

    def require_tenant_access(
        self,
        user: UserContext,
        tenant_id: str,
    ) -> None:
        """Require user can access a tenant or raise TenantAccessDeniedError.
        
        Args:
            user: The user context
            tenant_id: The tenant to check
            
        Raises:
            TenantAccessDeniedError: If user cannot access the tenant
        """
        if not self.can_access_tenant(user, tenant_id):
            logger.warning(
                "tenant_access_denied",
                user_id=user.user_id,
                tenant_id=tenant_id,
            )
            raise TenantAccessDeniedError(tenant_id, user.user_id)

    def filter_by_jurisdiction(
        self,
        user: UserContext,
        items: list[Any],
        jurisdiction_attr: str = "jurisdiction",
    ) -> list[Any]:
        """Filter items by user's allowed jurisdictions.
        
        Args:
            user: The user context
            items: Items to filter
            jurisdiction_attr: Attribute name for jurisdiction
            
        Returns:
            Filtered list of items
        """
        if not user.allowed_jurisdictions:
            return items  # No restrictions
        
        return [
            item for item in items
            if getattr(item, jurisdiction_attr, None) in user.allowed_jurisdictions
        ]


# =============================================================================
# Decorators
# =============================================================================

F = TypeVar("F", bound=Callable[..., Any])


def require_permission_decorator(permission: Permission) -> Callable[[F], F]:
    """Decorator to require a permission for a function.
    
    The function must have a 'user' parameter of type UserContext.
    
    Usage:
        @require_permission_decorator(Permission.REGULATION_READ)
        def get_regulation(user: UserContext, reg_id: str):
            ...
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Find user context in args/kwargs
            user = kwargs.get("user")
            if user is None:
                for arg in args:
                    if isinstance(arg, UserContext):
                        user = arg
                        break
            
            if user is None:
                raise ValueError("No UserContext found in function arguments")
            
            rbac = RBACManager()
            rbac.require_permission(user, permission)
            
            return func(*args, **kwargs)
        
        return wrapper  # type: ignore
    
    return decorator


def require_role_decorator(role: Role) -> Callable[[F], F]:
    """Decorator to require a role for a function.
    
    The function must have a 'user' parameter of type UserContext.
    
    Usage:
        @require_role_decorator(Role.ADMIN)
        def admin_only_action(user: UserContext):
            ...
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            user = kwargs.get("user")
            if user is None:
                for arg in args:
                    if isinstance(arg, UserContext):
                        user = arg
                        break
            
            if user is None:
                raise ValueError("No UserContext found in function arguments")
            
            rbac = RBACManager()
            rbac.require_role(user, role)
            
            return func(*args, **kwargs)
        
        return wrapper  # type: ignore
    
    return decorator


# =============================================================================
# FastAPI Dependencies
# =============================================================================

class PermissionChecker:
    """FastAPI dependency for permission checking.
    
    Usage:
        @app.get("/regulations")
        def get_regulations(
            user: UserContext = Depends(get_current_user),
            _: None = Depends(PermissionChecker(Permission.REGULATION_READ)),
        ):
            ...
    """
    
    def __init__(self, permission: Permission):
        self.permission = permission

    def __call__(self, user: UserContext) -> None:
        rbac = RBACManager()
        rbac.require_permission(user, self.permission)


class RoleChecker:
    """FastAPI dependency for role checking.
    
    Usage:
        @app.get("/admin/users")
        def get_users(
            user: UserContext = Depends(get_current_user),
            _: None = Depends(RoleChecker(Role.ADMIN)),
        ):
            ...
    """
    
    def __init__(self, role: Role):
        self.role = role

    def __call__(self, user: UserContext) -> None:
        rbac = RBACManager()
        rbac.require_role(user, self.role)


# =============================================================================
# Helper Functions
# =============================================================================

def get_permissions_for_role(role: Role) -> Set[Permission]:
    """Get all permissions granted to a role.
    
    Args:
        role: The role
        
    Returns:
        Set of permissions
    """
    return ROLE_PERMISSIONS.get(role, set())


def get_roles_with_permission(permission: Permission) -> Set[Role]:
    """Get all roles that have a specific permission.
    
    Args:
        permission: The permission
        
    Returns:
        Set of roles
    """
    return {
        role for role, perms in ROLE_PERMISSIONS.items()
        if permission in perms
    }


def create_user_context_from_jwt(payload: dict[str, Any]) -> UserContext:
    """Create UserContext from JWT payload.
    
    Args:
        payload: Decoded JWT payload
        
    Returns:
        UserContext instance
    """
    roles = {Role(r) for r in payload.get("roles", []) if r in [e.value for e in Role]}
    permissions = {
        Permission(p) for p in payload.get("permissions", [])
        if p in [e.value for e in Permission]
    }
    
    return UserContext(
        user_id=payload["sub"],
        tenant_id=payload.get("tenant_id"),
        roles=roles,
        permissions=permissions,
        scopes=set(payload.get("scopes", [])),
        allowed_jurisdictions=set(payload.get("allowed_jurisdictions", [])),
        is_service_account=payload.get("is_service_account", False),
        metadata=payload.get("extra", {}),
    )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Enums
    "Permission",
    "Role",
    "ROLE_PERMISSIONS",
    
    # User context
    "UserContext",
    
    # Errors
    "AuthorizationError",
    "PermissionDeniedError",
    "RoleDeniedError",
    "TenantAccessDeniedError",
    
    # Policies
    "Policy",
    "PermissionPolicy",
    "RolePolicy",
    "TenantPolicy",
    "JurisdictionPolicy",
    "CompositePolicy",
    
    # Manager
    "RBACManager",
    
    # Decorators
    "require_permission_decorator",
    "require_role_decorator",
    
    # FastAPI dependencies
    "PermissionChecker",
    "RoleChecker",
    
    # Helpers
    "get_permissions_for_role",
    "get_roles_with_permission",
    "create_user_context_from_jwt",
]
