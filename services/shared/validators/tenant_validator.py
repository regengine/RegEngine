"""
Tenant Validator - Cross-Database Tenant Validation

This module provides validation utilities for ensuring tenant_id references
are valid across database boundaries. Since vertical databases cannot enforce
foreign key constraints to the Admin DB, we validate at the application layer.

Usage:
    from shared.validators.tenant_validator import TenantValidator
    
    validator = TenantValidator(admin_db_connection)
    if not await validator.validate_tenant_exists(tenant_id):
        raise HTTPException(404, "Tenant not found")
"""

from typing import Optional
import uuid
from datetime import datetime


class TenantValidator:
    """Validates tenant_id references against the Admin database."""
    
    def __init__(self, admin_db_connection):
        """
        Initialize validator with Admin DB connection.
        
        Args:
            admin_db_connection: AsyncPG connection or SQLAlchemy session to Admin DB
        """
        self.admin_conn = admin_db_connection
    
    async def validate_tenant_exists(self, tenant_id: uuid.UUID) -> bool:
        """
        Verify that a tenant exists in the Admin database.
        
        Args:
            tenant_id: UUID of the tenant to validate
            
        Returns:
            True if tenant exists, False otherwise
            
        Example:
            >>> validator = TenantValidator(admin_db)
            >>> exists = await validator.validate_tenant_exists(tenant_id)
            >>> if not exists:
            ...     raise HTTPException(404, "Tenant not found")
        """
        query = "SELECT EXISTS(SELECT 1 FROM tenants WHERE id = $1)"
        result = await self.admin_conn.fetchval(query, tenant_id)
        return bool(result)
    
    async def validate_user_in_tenant(
        self, 
        user_id: uuid.UUID, 
        tenant_id: uuid.UUID
    ) -> bool:
        """
        Verify that a user belongs to a specific tenant.
        
        This prevents users from accessing data in tenants they don't belong to.
        
        Args:
            user_id: UUID of the user
            tenant_id: UUID of the tenant
            
        Returns:
            True if user belongs to tenant, False otherwise
            
        Example:
            >>> validator = TenantValidator(admin_db)
            >>> allowed = await validator.validate_user_in_tenant(user_id, tenant_id)
            >>> if not allowed:
            ...     raise HTTPException(403, "Access denied")
        """
        query = """
            SELECT EXISTS(
                SELECT 1 FROM users 
                WHERE id = $1 AND tenant_id = $2
            )
        """
        result = await self.admin_conn.fetchval(query, user_id, tenant_id)
        return bool(result)
    
    async def get_tenant_info(self, tenant_id: uuid.UUID) -> Optional[dict]:
        """
        Retrieve tenant information from Admin database.
        
        Args:
            tenant_id: UUID of the tenant
            
        Returns:
            Dictionary with tenant info or None if not found
            
        Example:
            >>> info = await validator.get_tenant_info(tenant_id)
            >>> if info:
            ...     print(f"Tenant: {info['name']}")
        """
        query = """
            SELECT id, name, created_at, status
            FROM tenants
            WHERE id = $1
        """
        row = await self.admin_conn.fetchrow(query, tenant_id)
        
        if not row:
            return None
        
        return {
            'id': row['id'],
            'name': row['name'],
            'created_at': row['created_at'],
            'status': row['status']
        }
    
    async def validate_tenant_active(self, tenant_id: uuid.UUID) -> bool:
        """
        Verify that a tenant exists and is active (not suspended/archived).
        
        Args:
            tenant_id: UUID of the tenant
            
        Returns:
            True if tenant is active, False otherwise
        """
        query = """
            SELECT EXISTS(
                SELECT 1 FROM tenants 
                WHERE id = $1 AND status = 'active'
            )
        """
        result = await self.admin_conn.fetchval(query, tenant_id)
        return bool(result)


# SQLAlchemy version for services using ORM
class TenantValidatorORM:
    """SQLAlchemy ORM version of TenantValidator."""
    
    def __init__(self, db_session):
        """
        Initialize with SQLAlchemy session.
        
        Args:
            db_session: SQLAlchemy AsyncSession
        """
        self.db = db_session
    
    async def validate_tenant_exists(self, tenant_id: uuid.UUID) -> bool:
        """Check if tenant exists using SQLAlchemy."""
        from sqlalchemy import select, exists
        from admin.app.models import Tenant  # Adjust import as needed
        
        query = select(exists().where(Tenant.id == tenant_id))
        result = await self.db.scalar(query)
        return bool(result)
    
    async def validate_user_in_tenant(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID
    ) -> bool:
        """Check if user belongs to tenant using SQLAlchemy."""
        from sqlalchemy import select, exists, and_
        from admin.app.models import User  # Adjust import as needed
        
        query = select(exists().where(
            and_(
                User.id == user_id,
                User.tenant_id == tenant_id
            )
        ))
        result = await self.db.scalar(query)
        return bool(result)
