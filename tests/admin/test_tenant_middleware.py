"""Tests for tenant validation middleware."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4, UUID

from fastapi import HTTPException
import pytest


class TestValidateTenantHeader:
    """Test tenant header validation."""

    @pytest.mark.asyncio
    async def test_missing_header_raises_400(self):
        """Missing X-Tenant-ID header should raise 400."""
        from services.admin.app.tenant_middleware import validate_tenant_header
        
        api_key = MagicMock()
        api_key.key_id = "test-key"
        api_key.tenant_id = str(uuid4())
        
        with pytest.raises(HTTPException) as exc_info:
            await validate_tenant_header(x_tenant_id=None, api_key=api_key)
        
        assert exc_info.value.status_code == 400
        assert "X-Tenant-ID" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_uuid_raises_400(self):
        """Invalid UUID format should raise 400."""
        from services.admin.app.tenant_middleware import validate_tenant_header
        
        api_key = MagicMock()
        api_key.key_id = "test-key"
        api_key.tenant_id = str(uuid4())
        
        with pytest.raises(HTTPException) as exc_info:
            await validate_tenant_header(x_tenant_id="not-a-uuid", api_key=api_key)
        
        assert exc_info.value.status_code == 400
        assert "valid UUID" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_api_key_without_tenant_raises_403(self):
        """API key without tenant should raise 403."""
        from services.admin.app.tenant_middleware import validate_tenant_header
        
        api_key = MagicMock()
        api_key.key_id = "test-key"
        api_key.tenant_id = None  # No tenant
        
        tenant_id = str(uuid4())
        
        with pytest.raises(HTTPException) as exc_info:
            await validate_tenant_header(x_tenant_id=tenant_id, api_key=api_key)
        
        assert exc_info.value.status_code == 403
        assert "not associated" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_mismatched_tenant_raises_403(self):
        """Mismatched tenant IDs should raise 403."""
        from services.admin.app.tenant_middleware import validate_tenant_header
        
        key_tenant = uuid4()
        header_tenant = uuid4()  # Different UUID
        
        api_key = MagicMock()
        api_key.key_id = "test-key"
        api_key.tenant_id = str(key_tenant)
        
        with pytest.raises(HTTPException) as exc_info:
            await validate_tenant_header(
                x_tenant_id=str(header_tenant),
                api_key=api_key
            )
        
        assert exc_info.value.status_code == 403
        assert "does not match" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_matching_tenant_returns_uuid(self):
        """Matching tenant IDs should return the UUID."""
        from services.admin.app.tenant_middleware import validate_tenant_header
        
        tenant_id = uuid4()
        
        api_key = MagicMock()
        api_key.key_id = "test-key"
        api_key.tenant_id = str(tenant_id)
        
        result = await validate_tenant_header(
            x_tenant_id=str(tenant_id),
            api_key=api_key
        )
        
        assert result == tenant_id
        assert isinstance(result, UUID)


class TestGetTenantFromKey:
    """Test direct tenant extraction from API key."""

    @pytest.mark.asyncio
    async def test_no_tenant_raises_403(self):
        """API key without tenant should raise 403."""
        from services.admin.app.tenant_middleware import get_tenant_from_key
        
        api_key = MagicMock()
        api_key.tenant_id = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_from_key(api_key=api_key)
        
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_tenant_uuid(self):
        """Should return tenant UUID from API key."""
        from services.admin.app.tenant_middleware import get_tenant_from_key
        
        tenant_id = uuid4()
        
        api_key = MagicMock()
        api_key.tenant_id = str(tenant_id)
        
        result = await get_tenant_from_key(api_key=api_key)
        
        assert result == tenant_id
