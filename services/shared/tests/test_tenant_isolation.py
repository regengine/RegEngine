"""
Test suite for tenant isolation infrastructure.

This module tests the TenantValidator and TenantContextMiddleware
to ensure proper multi-tenant data isolation.
"""

import sys
import importlib.util
from pathlib import Path

# ---- Direct-load services/shared packages to avoid repo-root 'shared/' collision ----
_shared_dir = Path(__file__).resolve().parent.parent

def _load_module(name, filepath):
    """Load a module from an absolute file path."""
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# Pre-load the validators and middleware subpackages
_validators_init = _shared_dir / "validators" / "__init__.py"
_middleware_init = _shared_dir / "middleware" / "__init__.py"

# We need to load the concrete modules first, then the __init__ packages
_tenant_validator_mod = _load_module(
    "shared.validators.tenant_validator",
    _shared_dir / "validators" / "tenant_validator.py",
)
_validators_pkg = _load_module("shared.validators", _validators_init)

_tenant_context_mod = _load_module(
    "shared.middleware.tenant_context",
    _shared_dir / "middleware" / "tenant_context.py",
)
_middleware_pkg = _load_module("shared.middleware", _middleware_init)

import pytest
import uuid
from unittest.mock import Mock, AsyncMock
from fastapi import HTTPException, Request
from types import SimpleNamespace


class TestTenantValidator:
    """Test TenantValidator utility."""
    
    @pytest.fixture
    def mock_db_connection(self):
        """Mock database connection."""
        conn = AsyncMock()
        return conn
    
    @pytest.fixture
    def validator(self, mock_db_connection):
        """Create TenantValidator instance."""
        from shared.validators import TenantValidator
        return TenantValidator(mock_db_connection)
    
    @pytest.mark.asyncio
    async def test_validate_tenant_exists_true(self, validator, mock_db_connection):
        """Test validation when tenant exists."""
        tenant_id = uuid.uuid4()
        mock_db_connection.fetchval.return_value = True
        
        result = await validator.validate_tenant_exists(tenant_id)
        
        assert result is True
        mock_db_connection.fetchval.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_tenant_exists_false(self, validator, mock_db_connection):
        """Test validation when tenant does not exist."""
        tenant_id = uuid.uuid4()
        mock_db_connection.fetchval.return_value = False
        
        result = await validator.validate_tenant_exists(tenant_id)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_user_in_tenant_true(self, validator, mock_db_connection):
        """Test user belongs to tenant."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        mock_db_connection.fetchval.return_value = True
        
        result = await validator.validate_user_in_tenant(user_id, tenant_id)
        
        assert result is True
   
    @pytest.mark.asyncio
    async def test_get_tenant_info_found(self, validator, mock_db_connection):
        """Test retrieving tenant info when tenant exists."""
        tenant_id = uuid.uuid4()
        mock_row = {
            'id': tenant_id,
            'name': 'Test Tenant',
            'created_at': '2026-01-01',
            'status': 'active'
        }
        mock_db_connection.fetchrow.return_value = mock_row
        
        result = await validator.get_tenant_info(tenant_id)
        
        assert result is not None
        assert result['id'] == tenant_id
        assert result['name'] == 'Test Tenant'
    
    @pytest.mark.asyncio
    async def test_validate_tenant_active_true(self, validator, mock_db_connection):
        """Test validation when tenant is active."""
        tenant_id = uuid.uuid4()
        mock_db_connection.fetchval.return_value = True
        
        result = await validator.validate_tenant_active(tenant_id)
        
        assert result is True


class TestTenantDependencies:
    """Test FastAPI dependency functions."""
    
    @pytest.mark.asyncio
    async def test_get_current_tenant_id_success(self):
        """Test getting tenant_id when available."""
        from shared.middleware import get_current_tenant_id
        
        tenant_id = uuid.uuid4()
        request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
        
        result = await get_current_tenant_id(request)
        
        assert result == tenant_id
    
    @pytest.mark.asyncio
    async def test_get_current_tenant_id_missing(self):
        """Test error when tenant_id is missing."""
        from shared.middleware import get_current_tenant_id
        
        request = SimpleNamespace(state=SimpleNamespace(tenant_id=None))
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_tenant_id(request)
        
        assert exc_info.value.status_code == 401
        assert "Tenant ID not found" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_optional_tenant_id_present(self):
        """Test optional tenant_id when present."""
        from shared.middleware import get_optional_tenant_id
        
        tenant_id = uuid.uuid4()
        request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
        
        result = await get_optional_tenant_id(request)
        
        assert result == tenant_id
    
    @pytest.mark.asyncio
    async def test_get_optional_tenant_id_missing(self):
        """Test optional tenant_id when missing (should return None)."""
        from shared.middleware import get_optional_tenant_id
        
        # Use SimpleNamespace without tenant_id attribute
        request = SimpleNamespace(state=SimpleNamespace())
        
        result = await get_optional_tenant_id(request)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_validate_tenant_access_success(self):
        """Test tenant access validation when IDs match."""
        from shared.middleware import validate_tenant_access
        
        tenant_id = uuid.uuid4()
        request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
        
        result = await validate_tenant_access(request, tenant_id)
        
        assert result == tenant_id
    
    @pytest.mark.asyncio
    async def test_validate_tenant_access_mismatch(self):
        """Test tenant access validation when IDs don't match."""
        from shared.middleware import validate_tenant_access
        
        user_tenant_id = uuid.uuid4()
        requested_tenant_id = uuid.uuid4()
        
        request = SimpleNamespace(state=SimpleNamespace(tenant_id=user_tenant_id))
        
        with pytest.raises(HTTPException) as exc_info:
            await validate_tenant_access(request, requested_tenant_id)
        
        assert exc_info.value.status_code == 403
        assert "Access denied" in str(exc_info.value.detail)


if __name__ == "__main__":
    print("Running tenant isolation tests...")
    pytest.main([__file__, "-v", "--tb=short"])
