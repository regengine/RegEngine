
import pytest
import requests
import time
from datetime import datetime

BASE_URL = "http://localhost:8400/auth"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "password"

@pytest.fixture
def logged_in_session():
    """Returns access_token, refresh_token, session_id"""
    resp = requests.post(f"{BASE_URL}/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200
    data = resp.json()
    return data["access_token"], data["refresh_token"]

def test_session_lifecycle(logged_in_session):
    access_token, refresh_token = logged_in_session
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # 1. List Sessions
    resp = requests.get(f"{BASE_URL}/sessions", headers=headers)
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) >= 1
    session_id = sessions[0]["id"]
    print(f"Active Session: {session_id}")
    
    # 2. Refresh Token (Rotation)
    refresh_resp = requests.post(f"{BASE_URL}/refresh", json={
        "refresh_token": refresh_token
    })
    assert refresh_resp.status_code == 200
    new_data = refresh_resp.json()
    new_refresh_token = new_data["refresh_token"]
    
    assert new_refresh_token != refresh_token
    print("Refresh Token Rotated Successfully")
    
    # 3. Use OLD Refresh Token (Reuse Detection / Failure)
    # Our simple implementation just fails 401 (Invalid Token) because hash changed.
    fail_resp = requests.post(f"{BASE_URL}/refresh", json={
        "refresh_token": refresh_token
    })
    assert fail_resp.status_code == 401
    print("Old Refresh Token Rejected")
    
    # 4. Revoke Session
    revoke_resp = requests.post(f"{BASE_URL}/sessions/{session_id}/revoke", headers=headers)
    assert revoke_resp.status_code == 200
    
    # 5. Try to Refresh with VALID NEW token (Should fail because session is revoked)
    # We need to verify that we are using the LATEST token, which maps to the session.
    # The session entry is now marked revoked.
    final_resp = requests.post(f"{BASE_URL}/refresh", json={
        "refresh_token": new_refresh_token
    })
    # Expect 401 (Session revoked in logic)
    assert final_resp.status_code == 401
    assert "revoked" in final_resp.text.lower()
    print("Revoked Session Rejected")

    # 6. Logout All
    # Login again to get a fresh session (since we revoked the old one)
    # Actually we can just use the fixture logic or verify nothing works.
    # Let's create TWO new sessions.
    resp1 = requests.post(f"{BASE_URL}/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    access1 = resp1.json()["access_token"]
    refresh1 = resp1.json()["refresh_token"]
    
    resp2 = requests.post(f"{BASE_URL}/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    access2 = resp2.json()["access_token"]
    refresh2 = resp2.json()["refresh_token"]
    
    # Logout ALL using access1
    headers1 = {"Authorization": f"Bearer {access1}"}
    logout_resp = requests.post(f"{BASE_URL}/logout-all", headers=headers1)
    assert logout_resp.status_code == 200
    print(f"Logout All: {logout_resp.json()}")
    
    # Verify BOTH refresh tokens are now invalid
    check1 = requests.post(f"{BASE_URL}/refresh", json={"refresh_token": refresh1})
    assert check1.status_code == 401
    
    check2 = requests.post(f"{BASE_URL}/refresh", json={"refresh_token": refresh2})
    assert check2.status_code == 401
    
    print("Logout Call successfully revoked multiple sessions.")

