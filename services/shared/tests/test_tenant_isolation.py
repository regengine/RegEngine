"""
Test suite for tenant isolation infrastructure.

This module tests the TenantValidator and TenantContextMiddleware
to ensure proper multi-tenant data isolation.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, Request


@pytest.mark.security
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
        mock_row = {"id": tenant_id, "name": "Test Tenant", "created_at": "2026-01-01", "status": "active"}
        mock_db_connection.fetchrow.return_value = mock_row

        result = await validator.get_tenant_info(tenant_id)

        assert result is not None
        assert result["id"] == tenant_id
        assert result["name"] == "Test Tenant"

    @pytest.mark.asyncio
    async def test_validate_tenant_active_true(self, validator, mock_db_connection):
        """Test validation when tenant is active."""
        tenant_id = uuid.uuid4()
        mock_db_connection.fetchval.return_value = True

        result = await validator.validate_tenant_active(tenant_id)

        assert result is True


@pytest.mark.security
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
    async def test_db_issued_api_key_resolves_own_tenant(self):
        """#2524: a DB-issued API key (no env-key match, so middleware leaves
        request.state.tenant_id=None) must still resolve its own tenant via the
        principal that require_api_key attaches to request.state.api_key."""
        from shared.middleware import get_current_tenant_id

        tenant_id = uuid.uuid4()
        api_key = SimpleNamespace(key_id="db-key-1", tenant_id=str(tenant_id))
        request = SimpleNamespace(state=SimpleNamespace(tenant_id=None, api_key=api_key))

        result = await get_current_tenant_id(request)

        assert result == tenant_id

    @pytest.mark.asyncio
    async def test_two_db_keys_resolve_to_own_tenants(self):
        """#2524: two distinct DB-issued keys resolve to their own tenants — no
        cross-tenant bleed and no shared-env pinning."""
        from shared.middleware import get_current_tenant_id

        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()

        req_a = SimpleNamespace(
            state=SimpleNamespace(tenant_id=None, api_key=SimpleNamespace(key_id="a", tenant_id=str(tenant_a)))
        )
        req_b = SimpleNamespace(
            state=SimpleNamespace(tenant_id=None, api_key=SimpleNamespace(key_id="b", tenant_id=str(tenant_b)))
        )

        assert await get_current_tenant_id(req_a) == tenant_a
        assert await get_current_tenant_id(req_b) == tenant_b
        assert tenant_a != tenant_b

    @pytest.mark.asyncio
    async def test_middleware_tenant_must_match_principal(self):
        """When the middleware resolved a tenant (JWT/internal header) and the
        authenticated API key carries a different one, fail closed with 409
        ``E_TENANT_MISMATCH`` (the ``reconcile_tenant_scope`` contract, #2511).
        The middleware tenant never overrides the principal: #3698 made it the
        last writer of the RLS contextvar on the graph routers, so letting it
        win meant key tenant A operated on tenant B's rows."""
        from shared.middleware import get_current_tenant_id

        mw_tenant = uuid.uuid4()
        key_tenant = uuid.uuid4()
        request = SimpleNamespace(
            state=SimpleNamespace(
                tenant_id=mw_tenant,
                api_key=SimpleNamespace(key_id="k", tenant_id=str(key_tenant)),
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_tenant_id(request)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "E_TENANT_MISMATCH"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_principal", ["not-a-uuid", " {mw} "])
    async def test_unparseable_principal_tenant_with_middleware_tenant_fails_closed(self, bad_principal):
        """A principal whose tenant does not parse is a malformed credential:
        401, never a fall-through that resolves the middleware tenant — even
        when the middleware tenant is the same UUID with surrounding spaces."""
        from shared.middleware import get_current_tenant_id

        mw_tenant = uuid.uuid4()
        request = SimpleNamespace(
            state=SimpleNamespace(
                tenant_id=mw_tenant,
                api_key=SimpleNamespace(key_id="k", tenant_id=bad_principal.format(mw=mw_tenant)),
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_tenant_id(request)
        assert exc_info.value.status_code == 401
        assert "Tenant ID not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_matching_middleware_and_principal_tenant_resolves(self):
        """Agreement between the two sources resolves to that tenant and seeds
        the RLS contextvar with it — never a 409, whatever the spelling (the
        principal here is upper-case with no hyphens)."""
        from shared.middleware import get_current_tenant_id
        from shared.tenant_context import get_rls_tenant_id

        tenant = uuid.uuid4()
        request = SimpleNamespace(
            state=SimpleNamespace(
                tenant_id=tenant,
                api_key=SimpleNamespace(key_id="k", tenant_id=str(tenant).upper().replace("-", "")),
            )
        )

        assert await get_current_tenant_id(request) == tenant
        assert get_rls_tenant_id() == str(tenant)

    @pytest.mark.asyncio
    async def test_api_key_without_tenant_fails_closed(self):
        """#2524: a principal with no tenant (or an invalid UUID) must still
        fail closed with 401 — never fall through to a 'None => all tenants'
        query."""
        from shared.middleware import get_current_tenant_id

        # Principal present but tenant_id is None.
        request = SimpleNamespace(
            state=SimpleNamespace(tenant_id=None, api_key=SimpleNamespace(key_id="k", tenant_id=None))
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_current_tenant_id(request)
        assert exc_info.value.status_code == 401

        # Principal present but tenant_id is not a valid UUID.
        request_bad = SimpleNamespace(
            state=SimpleNamespace(tenant_id=None, api_key=SimpleNamespace(key_id="k", tenant_id="not-a-uuid"))
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_current_tenant_id(request_bad)
        assert exc_info.value.status_code == 401

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
