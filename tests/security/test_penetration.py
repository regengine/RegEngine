
import pytest
import requests
import jwt
import time
import os
from datetime import datetime, timedelta, timezone

# Target System
BASE_URL = "http://localhost:8400"
AUTH_URL = f"{BASE_URL}/auth"
ADMIN_URL = f"{BASE_URL}/v1/admin"

# Secrets (Simulating attacker knowledge or lack thereof)
# We know the secret from .env for "White Box" testing to verify signature checks
# but we will also try "Black Box" guesses.
KNOWN_SECRET = os.getenv("AUTH_SECRET_KEY", "dev-secret-key-12345") 

@pytest.fixture(scope="module", autouse=True)
def check_service_availability():
    """Skip all tests if Admin API is not running"""
    try:
        # Try a fast health check or root endpoint
        requests.get(f"{BASE_URL}/docs", timeout=1)
    except requests.exceptions.ConnectionError:
        pytest.skip("Admin API not running - skipping penetration tests")
 

@pytest.fixture
def admin_token():
    """Get a valid admin token for baseline comparison"""
    try:
        resp = requests.post(f"{AUTH_URL}/login", json={
            "email": "admin@example.com",
            "password": "password"
        })
        if resp.status_code != 200:
             pytest.skip(f"Admin login failed: {resp.status_code}")
        return resp.json()["access_token"]
    except requests.exceptions.ConnectionError:
        pytest.skip("Admin API not running")

class TestAuthenticationAttacks:
    """
    OWASP A07:2021 - Identification and Authentication Failures
    """
    
    def test_jwt_none_algorithm(self):
        """
        Attack: Modify JWT header to use 'none' algorithm.
        Expected: 401 Unauthorized
        """
        # Create a malicious token with "none" algo
        payload = {
            "sub": "admin@example.com",
            "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
            "type": "access"
        }
        # Craft raw JWT with none alg: header.payload. (no signature)
        # Header: {"typ": "JWT", "alg": "none"} -> eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0
        encoded_header = "eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0"
        import base64
        import json
        encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        malicious_token = f"{encoded_header}.{encoded_payload}." # Trailing dot for empty sig
        
        headers = {"Authorization": f"Bearer {malicious_token}"}
        resp = requests.get(f"{ADMIN_URL}/users", headers=headers)
        
        assert resp.status_code == 401
    
    def test_jwt_invalid_signature(self):
        """
        Attack: Sign JWT with a different secret key.
        Expected: 401 Unauthorized
        """
        payload = {
            "sub": "admin@example.com",
            "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
            "type": "access",
            "sub_id": "00000000-0000-0000-0000-000000000000", # Fake ID
            "tenant_id": "00000000-0000-0000-0000-000000000000"
        }
        # Sign with wrong key
        malicious_token = jwt.encode(payload, "wrong-secret-key", algorithm="HS256")  # nosemgrep: jwt-python-hardcoded-secret
        
        headers = {"Authorization": f"Bearer {malicious_token}"}
        resp = requests.get(f"{ADMIN_URL}/users", headers=headers)
        assert resp.status_code == 401

    def test_expired_token(self):
        """
        Attack: Use an expired token.
        Expected: 401 Unauthorized
        """
        payload = {
            "sub": "admin@example.com",
            "exp": (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp(), # Expired
            "type": "access"
        }
        # Sign with CORRECT key to ensure expiration is the only failure reason
        # We need the real secret for this test to be valid verification of expiration check
        # otherwise signature check might fail first.
        # Assuming we can grab the secret from env for this specific test case.
        token = jwt.encode(payload, KNOWN_SECRET, algorithm="HS256")
        
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{ADMIN_URL}/users", headers=headers)
        assert resp.status_code == 401


class TestInjectionAttacks:
    """
    OWASP A03:2021 - Injection
    """
    
    def test_sqli_login_bypass(self):
        """
        Attack: SQL Injection in Login Email
        Payload: ' OR '1'='1' --
        Expected: 401 or 400 (Not 200)
        """
        payloads = [
            "' OR '1'='1",
            "admin@example.com' --",
            "' UNION SELECT * FROM users --"
        ]
        
        for p in payloads:
            resp = requests.post(f"{AUTH_URL}/login", json={
                "email": p,
                "password": "password"
            })
            assert resp.status_code in [401, 400, 422], f"SQLi succeeded with payload: {p}"

    def test_xss_in_invite(self, admin_token):
        """
        Attack: Stored XSS in Invite Email
        Payload: <script>alert(1)</script>
        Expected: 422 Validation Error (Email format) or Backend accepts but Frontend sanitizes.
        Backend should validate Email format, so this should fail 422.
        """
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Test 1: Invalid Email Format Injection
        xss_email = "<script>alert(1)</script>@example.com"
        resp = requests.post(f"{ADMIN_URL}/invites", headers=headers, json={
            "email": xss_email,
            "role_id": "00000000-0000-0000-0000-000000000000" # Dummy
        })
        # Pydantic EmailStr should reject this
        assert resp.status_code == 422 
        
        # Test 2: Name Injection (if we had a name field update)
        # We can try to update a user's role/status? No name field exposed in admin update yet.
        # We'll stick to email injection check for now.

class TestRateLimiting:
    """
    OWASP A04:2021 - Insecure Design (Rate Limiting)
    """
    
    def test_login_bruteforce_limiting(self):
        """
        Attack: Send 20 login requests rapidly.
        Expected: Eventually 429 Too Many Requests (if configured) or just 401s.
        NOTE: If Rate Limiting is P2 and not strictly implemented on Login yet, this might fail (allow all).
        The Walkthrough mentions F10 Rate Limiting (already in rate_limit.py), let's verify if applied to login.
        """
        # We simulate 10 requests. 
        # If no rate limit, all return 401.
        # If rate limit, some return 429.
        
        responses = []
        for _ in range(10):
            resp = requests.post(f"{AUTH_URL}/login", json={
                "email": "admin@example.com",
                "password": "wrong_password"
            })
            responses.append(resp)

        response_codes = [r.status_code for r in responses]
        assert 429 in response_codes, (
            f"Rate limiting not enforced — all responses: {response_codes}. "
            "The login endpoint must return 429 after repeated failed attempts."
        )

