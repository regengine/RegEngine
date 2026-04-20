"""
Tests for GDPR data-rights endpoints (issues #1094, #1095).

  #1094 — GET  /gdpr/export       Art. 15/20 data portability
  #1095 — POST /gdpr/request-erasure + POST /gdpr/confirm-erasure  Art. 17
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time

import pytest


# ---------------------------------------------------------------------------
# Token helpers (mirroring gdpr_routes internals so we can test round-trips)
# ---------------------------------------------------------------------------

def _make_token(email: str, secret: str, offset: int = 0) -> str:
    """Re-implement token generation for test assertions."""
    import secrets as _secrets
    nonce = "testnonce"
    ts = str(int(time.time()) + offset)
    message = f"{email}:{ts}:{nonce}"
    sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"{message}:{sig}"


# ---------------------------------------------------------------------------
# Unit tests — token helpers
# ---------------------------------------------------------------------------

class TestErasureTokenHelpers:
    """Direct unit tests for the token generate/verify helpers."""

    def test_valid_token_verifies(self, monkeypatch):
        monkeypatch.setenv("GDPR_ERASURE_SECRET", "test-secret-key")
        from app.gdpr_routes import _make_erasure_token, _verify_erasure_token

        email = "alice@example.com"
        token = _make_erasure_token(email)
        assert _verify_erasure_token(email, token) is True

    def test_wrong_email_fails(self, monkeypatch):
        monkeypatch.setenv("GDPR_ERASURE_SECRET", "test-secret-key")
        from app.gdpr_routes import _make_erasure_token, _verify_erasure_token

        token = _make_erasure_token("alice@example.com")
        assert _verify_erasure_token("eve@example.com", token) is False

    def test_tampered_sig_fails(self, monkeypatch):
        monkeypatch.setenv("GDPR_ERASURE_SECRET", "test-secret-key")
        from app.gdpr_routes import _make_erasure_token, _verify_erasure_token

        token = _make_erasure_token("alice@example.com")
        tampered = token[:-4] + "xxxx"
        assert _verify_erasure_token("alice@example.com", tampered) is False

    def test_expired_token_fails(self, monkeypatch):
        monkeypatch.setenv("GDPR_ERASURE_SECRET", "test-secret-key")
        from app.gdpr_routes import _verify_erasure_token, _ERASURE_TOKEN_TTL

        # Build a token with a timestamp far in the past
        secret = "test-secret-key"
        ts = str(int(time.time()) - _ERASURE_TOKEN_TTL - 10)
        message = f"alice@example.com:{ts}:nonce"
        sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        old_token = f"{message}:{sig}"

        assert _verify_erasure_token("alice@example.com", old_token) is False

    def test_malformed_token_returns_false(self, monkeypatch):
        monkeypatch.setenv("GDPR_ERASURE_SECRET", "test-secret-key")
        from app.gdpr_routes import _verify_erasure_token

        assert _verify_erasure_token("alice@example.com", "garbage") is False
        assert _verify_erasure_token("alice@example.com", "") is False


# ---------------------------------------------------------------------------
# HTTP integration tests via TestClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def gdpr_client(monkeypatch):
    """Return a TestClient wired to the gdpr_routes router only."""
    monkeypatch.setenv("GDPR_ERASURE_SECRET", "integration-test-secret")
    monkeypatch.setenv("ENV", "test")  # expose token in response

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.gdpr_routes import router

    mini_app = FastAPI()
    mini_app.include_router(router)
    return TestClient(mini_app)


class TestRequestErasure:
    def test_returns_pending(self, gdpr_client):
        resp = gdpr_client.post("/gdpr/request-erasure", json={"email": "bob@example.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        # Token is exposed in non-production environments
        assert "token" in data

    def test_missing_email_is_422(self, gdpr_client):
        resp = gdpr_client.post("/gdpr/request-erasure", json={})
        assert resp.status_code == 422


class TestConfirmErasure:
    def test_invalid_token_returns_400(self, gdpr_client):
        resp = gdpr_client.post(
            "/gdpr/confirm-erasure",
            json={"email": "bob@example.com", "token": "bad-token"},
        )
        assert resp.status_code == 400

    def test_valid_token_hits_db_delete(self, monkeypatch):
        """With a valid token the handler should attempt to delete from tool_leads.

        We patch the DB session so no real DB is required.
        """
        monkeypatch.setenv("GDPR_ERASURE_SECRET", "integration-test-secret")
        monkeypatch.setenv("ENV", "test")

        from app.gdpr_routes import _make_erasure_token
        email = "charlie@example.com"
        token = _make_erasure_token(email)

        # Build a fake DB session that captures the DELETE
        deleted_emails: list[str] = []

        class FakeResult:
            rowcount = 1

        class FakeSession:
            def execute(self, stmt, params=None):
                if params and "email" in params:
                    deleted_emails.append(params["email"])
                return FakeResult()

            def commit(self):
                pass

            def rollback(self):
                pass

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.gdpr_routes import router
        from app.database import get_session

        mini_app = FastAPI()
        mini_app.include_router(router)
        mini_app.dependency_overrides[get_session] = lambda: FakeSession()

        client = TestClient(mini_app)
        resp = client.post(
            "/gdpr/confirm-erasure",
            json={"email": email, "token": token},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "erased"
        assert email in deleted_emails


class TestGdprExportRequiresAuth:
    def test_export_without_auth_returns_401_or_422(self, gdpr_client):
        """GET /gdpr/export with no Bearer token should be rejected."""
        resp = gdpr_client.get("/gdpr/export")
        assert resp.status_code in (401, 422)
