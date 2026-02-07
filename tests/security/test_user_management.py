
import pytest
import httpx
from uuid import uuid4
import time

ADMIN_URL = "http://localhost:8400"

@pytest.fixture(scope="module")
def admin_client():
    return httpx.Client(base_url=ADMIN_URL, timeout=30)

@pytest.fixture(scope="module")
def sysadmin_auth(admin_client):
    """Register and login a sysadmin."""
    email = f"admin-{uuid4()}@example.com"
    password = "password123"
    tenant_name = f"Tenant {uuid4()}"
    
    try:
        # 1. Register (assuming check disabled)
        resp = admin_client.post("/auth/register", json={
            "email": email,
            "password": password,
            "tenant_name": tenant_name
        })
        if resp.status_code == 403:
            pytest.skip("Registration disabled - cannot run test without bootstrap")
        
        # If connect error happens here, it raises httpx.ConnectError
        
        # 2. Login
        resp_login = admin_client.post("/auth/login", json={
            "email": email,
            "password": password
        })
        assert resp_login.status_code == 200
        token_data = resp_login.json()
        return {
            "token": token_data["access_token"],
            "tenant_id": token_data["tenant_id"],
            "user_id": token_data["user"]["id"]
        }
    except httpx.ConnectError:
        pytest.skip("Admin API unavailable - skipping user management tests")

class TestUserManagement:
    
    def test_invite_lifecycle(self, admin_client, sysadmin_auth):
        token = sysadmin_auth["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 1. List Roles to get a valid Role ID
        resp = admin_client.get("/v1/admin/roles", headers=headers)
        assert resp.status_code == 200
        roles = resp.json()
        assert len(roles) > 0
        role_id = roles[0]["id"]
        
        # 2. Create Invite
        invite_email = f"invited-{uuid4()}@example.com"
        resp = admin_client.post("/v1/admin/invites", headers=headers, json={
            "email": invite_email,
            "role_id": role_id
        })
        assert resp.status_code == 200
        invite_data = resp.json()
        invite_id = invite_data["id"]
        invite_link = invite_data["invite_link"]
        assert invite_data["status"] == "pending"
        
        # 3. List Invites
        resp = admin_client.get("/v1/admin/invites", headers=headers)
        assert resp.status_code == 200
        invites = resp.json()
        assert any(i["id"] == invite_id for i in invites)
        
        # 4. Accept Invite (Public)
        # Extract token from link
        invite_token = invite_link.split("token=")[1]
        
        accept_resp = admin_client.post("/v1/auth/accept-invite", json={
            "token": invite_token,
            "password": "NewUserPassword123!",
            "name": "New User"
        })
        assert accept_resp.status_code == 200
        new_user_id = accept_resp.json()["user_id"]
        
        # 5. Verify User is now active (List Users)
        resp = admin_client.get("/v1/admin/users", headers=headers)
        assert resp.status_code == 200
        users = resp.json()
        assert any(u["email"] == invite_email for u in users)
        
        # 6. Revoke (Try to revoke accepted - should fail?)
        # Logic says: if accepted, 400.
        resp = admin_client.post(f"/v1/admin/invites/{invite_id}/revoke", headers=headers)
        assert resp.status_code == 400 # Already processed

    def test_revoke_invite(self, admin_client, sysadmin_auth):
        token = sysadmin_auth["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get Role
        resp = admin_client.get("/v1/admin/roles", headers=headers)
        role_id = resp.json()[0]["id"]
        
        # Create Invite
        invite_email = f"torevoke-{uuid4()}@example.com"
        resp = admin_client.post("/v1/admin/invites", headers=headers, json={
            "email": invite_email,
            "role_id": role_id
        })
        invite_id = resp.json()["id"]
        
        # Revoke
        resp = admin_client.post(f"/v1/admin/invites/{invite_id}/revoke", headers=headers)
        assert resp.status_code == 200
        
        # Verify in list
        resp = admin_client.get("/v1/admin/invites", headers=headers)
        # List endpoint filters for PENDING only in my impl?
        # invite_routes.py: where ... accepted_at is None, revoked_at is None.
        # So it should NOT be in the list anymore.
        invites = resp.json()
        assert not any(i["id"] == invite_id for i in invites)

