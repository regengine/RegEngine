"""F-1 / F-4 (re-audit): cross-tenant IDOR + read rate-limit on
``/api/v1/webhooks/recent`` and ``/api/v1/webhooks/chain/verify``.

Before this PR these two routes only required ``Depends(_verify_api_key)``
— a header-presence gate that does NOT validate the key. Any caller with
ANY non-empty API key value could pass ``?tenant_id=<victim>`` and read
recent CTE rows + chain integrity status for any tenant.

Fix mirrors PR #2249 (stripe-portal IDOR): bind the URL ``tenant_id`` to
the authenticated principal's tenant, return **404** on mismatch (avoid
tenant-existence oracle), and apply a tighter read-side rate limit.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_router_v2 as wr  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.subscription_gate import require_active_subscription  # noqa: E402
from shared.database import get_db_session  # noqa: E402


TENANT_A = "00000000-0000-0000-0000-0000000000aa"
TENANT_B = "00000000-0000-0000-0000-0000000000bb"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.closed = False

    def execute(self, _stmt, _params=None):
        return _FakeExecuteResult(self._rows)

    def close(self):
        self.closed = True


class _FakeChainResult:
    def __init__(self):
        self.valid = True
        self.chain_length = 1
        self.errors: list[str] = []
        self.checked_at = "2026-05-09T00:00:00+00:00"


class _FakePersistence:
    def __init__(self, _session):
        pass

    def verify_chain(self, _tenant_id):
        return _FakeChainResult()


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


def _install_db_stubs(monkeypatch):
    session = _FakeSession(
        rows=[
            (
                "evt-1",
                "shipping",
                "TLC-1",
                "Romaine",
                10.0,
                "cases",
                "Valley Fresh",
                "test",
                datetime(2026, 5, 9, 0, 0, 0, tzinfo=timezone.utc),
            )
        ]
    )
    fake_db = types.ModuleType("shared.database")
    fake_db.SessionLocal = lambda: _FakeSession(rows=session._rows)
    fake_db.get_db_session = lambda: iter([session])
    monkeypatch.setitem(sys.modules, "shared.database", fake_db)

    fake_cte = types.ModuleType("shared.cte_persistence")
    fake_cte.CTEPersistence = _FakePersistence
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", fake_cte)
    return session


def _build_app(*, principal: Optional[IngestionPrincipal]) -> FastAPI:
    app = FastAPI()
    app.include_router(wr.router)
    if principal is not None:
        app.dependency_overrides[get_ingestion_principal] = lambda: principal
    # Header-presence gate is covered separately; bypass it here so we
    # exercise the principal binding logic.
    app.dependency_overrides[wr._verify_api_key_present] = lambda: None
    app.dependency_overrides[wr._verify_api_key] = lambda: None
    app.dependency_overrides[require_active_subscription] = lambda: None
    return app


def _client(monkeypatch, *, principal, allow_rate_limit: bool = True):
    _install_db_stubs(monkeypatch)
    if allow_rate_limit:
        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
    return TestClient(_build_app(principal=principal))


def _scoped_principal(tenant_id: str) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="key-scoped",
        scopes=["webhooks.read"],
        tenant_id=tenant_id,
        auth_mode="test",
    )


# ---------------------------------------------------------------------------
# F-1: tenant binding
# ---------------------------------------------------------------------------


class TestRecentTenantBinding:
    def test_recent_rejects_cross_tenant_read(self, monkeypatch):
        client = _client(monkeypatch, principal=_scoped_principal(TENANT_A))
        resp = client.get(
            "/api/v1/webhooks/recent",
            params={"tenant_id": TENANT_B},
            headers={"X-RegEngine-API-Key": "any"},
        )
        assert resp.status_code == 404, resp.text
        # Must NOT leak victim tenant data.
        assert "events" not in resp.json() or resp.json().get("events") in (None, [])

    def test_recent_succeeds_for_own_tenant(self, monkeypatch):
        client = _client(monkeypatch, principal=_scoped_principal(TENANT_A))
        resp = client.get(
            "/api/v1/webhooks/recent",
            params={"tenant_id": TENANT_A, "limit": 5},
            headers={"X-RegEngine-API-Key": "any"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["tenant_id"] == TENANT_A
        assert isinstance(body["events"], list)


class TestChainVerifyTenantBinding:
    def test_chain_verify_rejects_cross_tenant(self, monkeypatch):
        client = _client(monkeypatch, principal=_scoped_principal(TENANT_A))
        resp = client.get(
            "/api/v1/webhooks/chain/verify",
            params={"tenant_id": TENANT_B},
            headers={"X-RegEngine-API-Key": "any"},
        )
        assert resp.status_code == 404, resp.text

    def test_chain_verify_succeeds_for_own_tenant(self, monkeypatch):
        client = _client(monkeypatch, principal=_scoped_principal(TENANT_A))
        resp = client.get(
            "/api/v1/webhooks/chain/verify",
            params={"tenant_id": TENANT_A},
            headers={"X-RegEngine-API-Key": "any"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["tenant_id"] == TENANT_A
        assert body["chain_valid"] is True


class TestPermissionEnforced:
    def test_recent_rejects_principal_without_permission(self, monkeypatch):
        principal = IngestionPrincipal(
            key_id="key-noperms",
            scopes=["webhooks.ingest"],  # ingest only — no read
            tenant_id=TENANT_A,
            auth_mode="test",
        )
        client = _client(monkeypatch, principal=principal)
        resp = client.get(
            "/api/v1/webhooks/recent",
            params={"tenant_id": TENANT_A},
            headers={"X-RegEngine-API-Key": "any"},
        )
        assert resp.status_code == 403, resp.text

    def test_chain_verify_rejects_principal_without_permission(self, monkeypatch):
        principal = IngestionPrincipal(
            key_id="key-noperms",
            scopes=["webhooks.ingest"],
            tenant_id=TENANT_A,
            auth_mode="test",
        )
        client = _client(monkeypatch, principal=principal)
        resp = client.get(
            "/api/v1/webhooks/chain/verify",
            params={"tenant_id": TENANT_A},
            headers={"X-RegEngine-API-Key": "any"},
        )
        assert resp.status_code == 403


class TestWildcardPrincipalBypass:
    """Master/admin keys (scopes=["*"]) keep cross-tenant access."""

    def test_wildcard_can_query_any_tenant(self, monkeypatch):
        principal = IngestionPrincipal(
            key_id="master",
            scopes=["*"],
            tenant_id=None,
            auth_mode="test",
        )
        client = _client(monkeypatch, principal=principal)
        resp = client.get(
            "/api/v1/webhooks/recent",
            params={"tenant_id": TENANT_B},
            headers={"X-RegEngine-API-Key": "any"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# F-4: read-side rate limit
# ---------------------------------------------------------------------------


class TestReadRateLimit:
    def test_recent_rate_limited(self, monkeypatch):
        _install_db_stubs(monkeypatch)
        # Force the bucket to deny.
        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (False, 0))
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
        client = TestClient(_build_app(principal=_scoped_principal(TENANT_A)))
        resp = client.get(
            "/api/v1/webhooks/recent",
            params={"tenant_id": TENANT_A},
            headers={"X-RegEngine-API-Key": "any"},
        )
        assert resp.status_code == 429
        assert resp.headers.get("X-RateLimit-Scope", "").startswith("webhooks.read.")

    def test_chain_verify_rate_limited(self, monkeypatch):
        _install_db_stubs(monkeypatch)
        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (False, 0))
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
        client = TestClient(_build_app(principal=_scoped_principal(TENANT_A)))
        resp = client.get(
            "/api/v1/webhooks/chain/verify",
            params={"tenant_id": TENANT_A},
            headers={"X-RegEngine-API-Key": "any"},
        )
        assert resp.status_code == 429
        assert "webhooks.read." in resp.headers.get("X-RateLimit-Scope", "")


# ---------------------------------------------------------------------------
# Header-presence gate still enforced
# ---------------------------------------------------------------------------


class TestUnauthenticated:
    def test_unauthenticated_request_rejected(self, monkeypatch):
        # Build app without overriding the presence gate so we exercise it.
        _install_db_stubs(monkeypatch)
        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)

        app = FastAPI()
        app.include_router(wr.router)
        # Override the principal so we don't hit the real auth resolver, but
        # leave _verify_api_key_present intact so missing header → 401.
        app.dependency_overrides[get_ingestion_principal] = lambda: _scoped_principal(TENANT_A)
        app.dependency_overrides[require_active_subscription] = lambda: None
        client = TestClient(app)

        resp = client.get(
            "/api/v1/webhooks/recent",
            params={"tenant_id": TENANT_A},
        )
        assert resp.status_code == 401

        resp2 = client.get(
            "/api/v1/webhooks/chain/verify",
            params={"tenant_id": TENANT_A},
        )
        assert resp2.status_code == 401
