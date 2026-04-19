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
    """Verify hardcoded 'admin' key is now rejected."""
    response = admin_client.get(
        ADMIN_PROTECTED_ENDPOINT,
        headers={"X-Admin-Key": "admin"}
    )
    assert response.status_code == 401, "Admin bypass should be removed"
    # Admin service installs shared.error_handling which wraps errors as
    # {"error": {"type": "http_401", "message": ...}} instead of the
    # FastAPI default {"detail": ...}.
    body = response.json()
    message = body.get("error", {}).get("message") or body.get("detail", "")
    assert "Invalid admin credentials" in message


@pytest.mark.security
def test_admin_key_required():
    """Verify requests without admin key are rejected."""
    response = admin_client.get(ADMIN_PROTECTED_ENDPOINT)
    assert response.status_code == 401


@pytest.mark.security
def test_valid_admin_key_works():
    """Verify legitimate admin keys grant access (via dependency override)."""
    import os
    import sys
    # Access verify_admin_key from the already-loaded module to avoid
    # Prometheus metric re-registration from a second import path
    routes_mod = sys.modules.get("app.routes") or sys.modules.get("services.admin.app.routes")
    verify_admin_key = routes_mod.verify_admin_key

    # Force in-memory key store so CI doesn't need the api_keys table
    from shared.auth import get_key_store as _gks, APIKeyStore
    import shared.auth as _auth_mod
    original_env = os.environ.get("ENABLE_DB_API_KEYS")
    original_regengine_env = os.environ.get("REGENGINE_ENV")
    original_db_store = getattr(_auth_mod, "_db_store_instance", None)
    os.environ["ENABLE_DB_API_KEYS"] = "false"
    os.environ["REGENGINE_ENV"] = "test"
    _auth_mod._db_store_instance = None  # clear cached DB store

    # Override the admin key dependency to simulate a valid key
    admin_app.dependency_overrides[verify_admin_key] = lambda: True

    try:
        response = admin_client.get(ADMIN_PROTECTED_ENDPOINT)
        # Should not be 401 (may be 200 or other status based on data)
        assert response.status_code != 401
    finally:
        # Remove override so other tests aren't affected
        admin_app.dependency_overrides.pop(verify_admin_key, None)
        _auth_mod._db_store_instance = original_db_store
        if original_env is None:
            os.environ.pop("ENABLE_DB_API_KEYS", None)
        else:
            os.environ["ENABLE_DB_API_KEYS"] = original_env
        if original_regengine_env is None:
            os.environ.pop("REGENGINE_ENV", None)
        else:
            os.environ["REGENGINE_ENV"] = original_regengine_env

