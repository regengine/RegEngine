
import pytest
import os
from httpx import AsyncClient
from sqlalchemy import select, and_
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import hashlib

from app.sqlalchemy_models import UserModel, MembershipModel, RoleModel, InviteModel, TenantModel, AuditLogModel
from app.auth_utils import create_access_token, get_password_hash

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# --- Fixtures ---
# Connect to Dockerized DB exposed on localhost:5432 (local) or postgres (container)
DB_URL = os.getenv("TEST_DB_URL", "postgresql://regengine:regengine@localhost:5433/regengine_admin")

@pytest.fixture(scope="session")
def db_engine():
    try:
        engine = create_engine(DB_URL)
        # Test connection
        with engine.connect() as conn:
            pass
        yield engine
        engine.dispose()
    except Exception as e:
        pytest.skip(f"Database unavailable: {e}")

@pytest.fixture(scope="function")
def db(db_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    from sqlalchemy import text
    session.execute(text("SELECT set_admin_context(true)"))
    yield session
    session.close()

@pytest.fixture
async def async_client():
    try:
        async with AsyncClient(base_url="http://localhost:8400", timeout=30.0) as client:
             # Simple check
            try:
                await client.get("/docs")
            except Exception:
                pytest.skip("Admin API unavailable")
            yield client
    except Exception:
        pytest.skip("Admin API unavailable")

@pytest.fixture
def admin_user(db: Session):
    role = db.execute(select(RoleModel).where(
        RoleModel.name == "Owner",
        RoleModel.tenant_id.is_(None)
    )).scalars().first()
    
    if not role:
        role = RoleModel(name="Owner", permissions=["*"], tenant_id=None)
        db.add(role)
        db.commit()

    tenant = TenantModel(name="Admin Tenant", slug=f"admin-{uuid4().hex[:8]}")
    db.add(tenant)
    db.commit()

    user = UserModel(
        email=f"admin-{uuid4()}@example.com",
        password_hash=get_password_hash("password"),
        is_sysadmin=True,
        status="active"
    )
    db.add(user)
    db.commit()
    
    membership = MembershipModel(
        user_id=user.id,
        tenant_id=tenant.id,
        role_id=role.id,
        is_active=True
    )
    db.add(membership)
    db.commit()
    
    token = create_access_token({"sub": str(user.id), "tid": str(tenant.id)})
    return {"user": user, "tenant": tenant, "token": token, "role": role}

@pytest.fixture
def other_tenant_user(db: Session):
    role = db.execute(select(RoleModel).where(
        RoleModel.name == "Owner",
        RoleModel.tenant_id.is_(None)
    )).scalars().first()
    
    # If not found (unlikely if admin_user ran first, but possible), create it
    if not role:
        role = RoleModel(name="Owner", permissions=["*"], tenant_id=None)
        db.add(role)
        db.commit()
    
    tenant = TenantModel(name="Other Tenant", slug=f"other-{uuid4().hex[:8]}")
    db.add(tenant)
    db.commit()

    user = UserModel(
        email=f"other-{uuid4()}@example.com",
        password_hash=get_password_hash("password"),
        status="active"
    )
    db.add(user)
    db.commit()
    
    membership = MembershipModel(
        user_id=user.id,
        tenant_id=tenant.id,
        role_id=role.id,
        is_active=True
    )
    db.add(membership)
    db.commit()
    
    token = create_access_token({"sub": str(user.id), "tid": str(tenant.id)})
    return {"user": user, "tenant": tenant, "token": token}


# --- Test Classes ---

class TestAdminEndpointsRequireJWT:
    """1. Auth & Permissions: Endpoints require JWT, reject API Key."""
    
    @pytest.mark.asyncio
    async def test_endpoints_reject_no_auth(self, async_client: AsyncClient):
        endpoints = [
            ("GET", "/v1/admin/invites"),
            ("POST", "/v1/admin/invites"),
            ("GET", "/v1/admin/users"),
            ("GET", "/v1/admin/roles"),
        ]
        for method, url in endpoints:
            resp = await async_client.request(method, url)
            assert resp.status_code == 401, f"{method} {url} should require auth"

    @pytest.mark.asyncio
    async def test_endpoints_reject_api_key(self, async_client: AsyncClient):
        # Even with a valid API key header, it should fail if Bearer is missing 
        # (Assuming get_current_user only looks at Bearer)
        headers = {"X-Admin-Key": "some-key", "X-RegEngine-API-Key": "some-key"}
        resp = await async_client.get("/v1/admin/users", headers=headers)
        assert resp.status_code == 401

class TestInviteTenantIsolation:
    """2. Security / Tenant Isolation: Invites are isolated."""

    @pytest.mark.asyncio
    async def test_tenant_cannot_list_others_invites(self, async_client: AsyncClient, admin_user, other_tenant_user):
        # Admin creates invite in Tenant A
        headers_a = {"Authorization": f"Bearer {admin_user['token']}"}
        await async_client.post("/v1/admin/invites", json={
            "email": "invitee-a@example.com", 
            "role_id": str(admin_user['role'].id)
        }, headers=headers_a)
        
        # Other User (Tenant B) lists invites
        headers_b = {"Authorization": f"Bearer {other_tenant_user['token']}"}
        resp = await async_client.get("/v1/admin/invites", headers=headers_b)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 0 # Should look empty, not show Tenant A's invite

    @pytest.mark.asyncio
    async def test_tenant_cannot_revoke_others_invite(self, async_client: AsyncClient, admin_user, other_tenant_user, db: Session):
        # Admin creates invite
        headers_a = {"Authorization": f"Bearer {admin_user['token']}"}
        create_resp = await async_client.post("/v1/admin/invites", json={
            "email": "invitee-revoke-test@example.com", 
            "role_id": str(admin_user['role'].id)
        }, headers=headers_a)
        invite_id = create_resp.json()['id']
        
        # Other User tries to revoke
        headers_b = {"Authorization": f"Bearer {other_tenant_user['token']}"}
        resp = await async_client.post(f"/v1/admin/invites/{invite_id}/revoke", headers=headers_b)
        assert resp.status_code == 404 # Not found in Tenant B context

class TestUserManagementTenantIsolation:
    """2b. Security / User Mgmt Isolation."""

    @pytest.mark.asyncio
    async def test_cannot_change_role_across_tenants(self, async_client: AsyncClient, admin_user, other_tenant_user):
        # Admin tries to change role of Other Tenant User
        # We need the ID of the other user
        target_id = other_tenant_user['user'].id
        
        headers_a = {"Authorization": f"Bearer {admin_user['token']}"}
        resp = await async_client.patch(f"/v1/admin/users/{target_id}/role", json={
            "role_id": str(admin_user['role'].id)
        }, headers=headers_a)
        
        # User exists globally, but membership in Tenant A does not exist for them
        assert resp.status_code == 404 

class TestLastOwnerProtection:
    """4. Invariants: Last Owner Protection."""
    
    @pytest.mark.asyncio
    async def test_cannot_deactivate_last_owner(self, async_client: AsyncClient, admin_user):
        # Admin is the only owner in fixture
        headers = {"Authorization": f"Bearer {admin_user['token']}"}
        resp = await async_client.post(f"/v1/admin/users/{admin_user['user'].id}/deactivate", headers=headers)
        assert resp.status_code == 400
        assert "last Owner" in resp.json()['detail']

    @pytest.mark.asyncio
    async def test_cannot_demote_last_owner(self, async_client: AsyncClient, admin_user, db: Session):
        # Create another role
        viewer_role = RoleModel(name="Viewer", tenant_id=admin_user['tenant'].id, permissions=[])
        db.add(viewer_role)
        db.commit()
        
        headers = {"Authorization": f"Bearer {admin_user['token']}"}
        resp = await async_client.patch(f"/v1/admin/users/{admin_user['user'].id}/role", json={
            "role_id": str(viewer_role.id)
        }, headers=headers)
        assert resp.status_code == 400
        assert "last Owner" in resp.json()['detail']

class TestDeactivateReactivate:
    """5. Frontend Flows compatibility: Deactivate/Reactivate."""
    
    @pytest.mark.asyncio
    async def test_deactivate_reactivate_flow(self, async_client: AsyncClient, admin_user, db: Session):
        # Add a secondary user to deactivate
        user2_email = f"user2-{uuid4()}@example.com"
        user2 = UserModel(email=user2_email, password_hash="hash", status="active")
        db.add(user2)
        db.commit()
        
        # Make them an owner so we can verify we can deactivate (since admin_user is also owner, count > 1)
        mem = MembershipModel(user_id=user2.id, tenant_id=admin_user['tenant'].id, role_id=admin_user['role'].id)
        db.add(mem)
        db.commit()
        
        headers = {"Authorization": f"Bearer {admin_user['token']}"}
        
        # Deactivate
        resp = await async_client.post(f"/v1/admin/users/{user2.id}/deactivate", headers=headers)
        assert resp.status_code == 200
        assert resp.json()['status'] == "deactivated"
        
        # Verify inactive via List
        resp = await async_client.get("/v1/admin/users", headers=headers)
        users = resp.json()
        target = next(u for u in users if u['id'] == str(user2.id))
        assert target['status'] == "inactive"
        
        # Reactivate
        resp = await async_client.post(f"/v1/admin/users/{user2.id}/reactivate", headers=headers)
        assert resp.status_code == 200
        
        # Verify active
        resp = await async_client.get("/v1/admin/users", headers=headers)
        users = resp.json()
        target = next(u for u in users if u['id'] == str(user2.id))
        assert target['status'] == "active"


class TestInviteLifecycle:
    """3. Invite Security & Lifecycle."""
    
    @pytest.mark.asyncio
    async def test_invite_lifecycle_full(self, async_client: AsyncClient, admin_user, db: Session):
        headers = {"Authorization": f"Bearer {admin_user['token']}"}
        
        # 1. Create Invite
        email = f"life-{uuid4()}@example.com"
        resp = await async_client.post("/v1/admin/invites", json={
            "email": email, "role_id": str(admin_user['role'].id)
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        link = data['invite_link']
        token = link.split("token=")[1]
        
        # 1a. Duplicate Fail
        resp_dup = await async_client.post("/v1/admin/invites", json={
            "email": email, "role_id": str(admin_user['role'].id)
        }, headers=headers)
        assert resp_dup.status_code == 409
        
        # 2. Accept
        resp_accept = await async_client.post("/v1/auth/accept-invite", json={
            "token": token, "password": "Pass123!", "name": "New Guy"
        })
        assert resp_accept.status_code == 200
        
        # 3. Accept again (Fail)
        resp_again = await async_client.post("/v1/auth/accept-invite", json={
            "token": token, "password": "Pass123!", "name": "New Guy"
        })
        assert resp_again.status_code == 400

    @pytest.mark.asyncio
    async def test_revoke_flow(self, async_client: AsyncClient, admin_user, db: Session):
        headers = {"Authorization": f"Bearer {admin_user['token']}"}
        email = f"revoke-{uuid4()}@example.com"
        create_resp = await async_client.post("/v1/admin/invites", json={
            "email": email, "role_id": str(admin_user['role'].id)
        }, headers=headers)
        invite_id = create_resp.json()['id']
        token = create_resp.json()['invite_link'].split("token=")[1]
        
        # Revoke
        await async_client.post(f"/v1/admin/invites/{invite_id}/revoke", headers=headers)
        
        # Accept Revoked (Fail)
        resp = await async_client.post("/v1/auth/accept-invite", json={
            "token": token, "password": "Pass", "name": "Revoked Guy"
        })
        # Could be 400 or 404 depending on implementation (checked: 400 "Invite invalid")
        assert resp.status_code == 400

class TestAuditLogs:
    """5. Audit Log Completeness."""
    
    @pytest.mark.asyncio
    async def test_audit_log_entries(self, async_client: AsyncClient, admin_user, db: Session):
        # Trigger an event: Create Invite
        headers = {"Authorization": f"Bearer {admin_user['token']}"}
        email = f"audit-{uuid4()}@example.com"
        resp = await async_client.post("/v1/admin/invites", json={
            "email": email, "role_id": str(admin_user['role'].id)
        }, headers=headers)
        invite_id = resp.json()['id']
        
        # Refresh session visibility
        db.commit()
        
        log = db.execute(select(AuditLogModel).where(
            AuditLogModel.action == "invite.create",
            AuditLogModel.resource_id == str(invite_id)
        )).scalar_one_or_none()
        
        if not log:
            all_logs = db.execute(select(AuditLogModel)).scalars().all()
            print(f"\nDEBUG: Found {len(all_logs)} logs:")
            for l in all_logs:
                print(f" - {l.action} on {l.resource_id} (Tenant: {l.tenant_id})")
        
        assert log is not None
        assert log.tenant_id == admin_user['tenant'].id
        assert log.actor_id == admin_user['user'].id
        assert log.resource_type == "invite"
        assert log.changes['email'] == email
