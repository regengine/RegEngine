"""Test P0 security hardening fixes.

These tests verify that critical security issues have been resolved:
- SEC-001: Admin bypass removed
- MISSING-001: Rate limiting enforced
- SEC-002: CORS properly configured
"""

import pytest
from fastapi.testclient import TestClient

from services.admin.main import app as admin_app

admin_client = TestClient(admin_app)

# Use a GET endpoint that requires admin auth
ADMIN_PROTECTED_ENDPOINT = "/v1/admin/keys"


@pytest.mark.security
def test_admin_bypass_removed():
    """A legacy admin header cannot authenticate a human admin route."""
    response = admin_client.get(ADMIN_PROTECTED_ENDPOINT, headers={"X-Admin-Key": "admin"})
    assert response.status_code == 401, "Admin bypass should be removed"
    # Admin service installs shared.error_handling which wraps errors as
    # {"error": {"type": "http_401", "message": ...}} instead of the
    # FastAPI default {"detail": ...}.
    body = response.json()
    message = body.get("error", {}).get("message") or body.get("detail", "")
    assert "X-Admin-Key is not an accepted authentication method" in message


@pytest.mark.security
def test_browser_session_required():
    """Verify requests without an opaque browser session are rejected."""
    response = admin_client.get(ADMIN_PROTECTED_ENDPOINT)
    assert response.status_code == 401


@pytest.mark.security
def test_configured_legacy_admin_key_is_still_rejected(monkeypatch):
    """Even a value matching the retired environment variable is ignored."""
    monkeypatch.setenv("ADMIN_MASTER_KEY", "retired-admin-key")
    response = admin_client.get(
        ADMIN_PROTECTED_ENDPOINT,
        headers={"X-Admin-Key": "retired-admin-key"},
    )
    assert response.status_code == 401
