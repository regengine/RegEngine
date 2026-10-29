"""Hardening tests for ``app.settings``.

Complements ``test_settings_1342.py``. Covers the security properties added
to the settings router:

- Data-retention floors on writes (422) while legacy under-floor blobs still
  GET without a 500.
- ``api_keys`` never echoed in any response body, while the persisted blob
  keeps the full key records.
- Rate limiting on both PUT endpoints (429 past the budget).
- A ``SETTINGS_UPDATE`` audit event on each successful PUT carrying changed
  field *names* only (no PII, no secrets).
- Negative auth: unauthenticated GET/PUT is rejected; a tenant-pinned
  context cannot read or modify another tenant's data.

All data-free: ``get_jsonb`` / ``set_jsonb`` are swapped with in-process
fakes, the audit helper is monkeypatched, and auth is exercised via the
shared ``install_tenant_context_override`` helper (or its absence).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.rate_limit import limiter

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import settings as s  # noqa: E402
from app.settings import (  # noqa: E402
    MIN_AUDIT_LOG_RETENTION_DAYS,
    MIN_CTE_RETENTION_DAYS,
    MIN_EXPORT_RETENTION_DAYS,
    DataRetention,
    DataRetentionUpdate,
    SettingsResponse,
    _default_settings,
    _redact_api_keys,
    router,
)

from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override  # noqa: E402

FAKE_KEY = "sk_test_FAKE_DO_NOT_USE_1234"
FAKE_SECRET_VALUE = (
    "super-" + FAKE_KEY  # pragma: allowlist secret  # synthetic test fixture only; never a real credential
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_memory_store():
    s._settings_store.clear()
    yield
    s._settings_store.clear()


@pytest.fixture(autouse=True)
def _reset_limiter():
    try:
        limiter.reset()
    except Exception:  # pragma: no cover - defensive fallback
        pass
    yield
    try:
        limiter.reset()
    except Exception:  # pragma: no cover - defensive fallback
        pass


@pytest.fixture
def stubbed_jsonb(monkeypatch):
    state = {"db": {}, "set_fail_for": set(), "set_calls": []}

    def _fake_get(tenant_id, table, column):
        data = state["db"].get(tenant_id)
        return dict(data) if data is not None else None

    def _fake_set(tenant_id, table, column, value):
        state["set_calls"].append((tenant_id, dict(value)))
        if tenant_id in state["set_fail_for"]:
            return False
        state["db"][tenant_id] = dict(value)
        return True

    monkeypatch.setattr(s, "get_jsonb", _fake_get)
    monkeypatch.setattr(s, "set_jsonb", _fake_set)
    return state


def _make_app(*, enforce_claims: bool = False, default_tenant: str = "t1", auth: bool = True):
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)
    if auth:
        from app.webhook_compat import _verify_api_key

        app.dependency_overrides[_verify_api_key] = lambda: None
        install_tenant_context_override(app, default_tenant=default_tenant, enforce_claims=enforce_claims)
    return app


@pytest.fixture
def client(stubbed_jsonb):
    return TestClient(_make_app())


# ---------------------------------------------------------------------------
# 1. Retention floors
# ---------------------------------------------------------------------------


class TestRetentionFloors:
    def test_floor_constants(self):
        assert MIN_CTE_RETENTION_DAYS == 730
        assert MIN_AUDIT_LOG_RETENTION_DAYS == 730
        assert MIN_EXPORT_RETENTION_DAYS == 1

    def test_update_model_rejects_under_floor_cte(self):
        with pytest.raises(ValueError):
            DataRetentionUpdate(cte_retention_days=729)

    def test_put_rejects_under_floor_with_422(self, client):
        resp = client.put(
            "/api/v1/settings/t1/retention",
            json={
                "cte_retention_days": 100,  # below 730
                "audit_log_retention_days": 2555,
                "export_retention_days": 365,
                "auto_archive": True,
            },
        )
        assert resp.status_code == 422

    def test_put_accepts_at_floor(self, client, stubbed_jsonb):
        resp = client.put(
            "/api/v1/settings/t1/retention",
            json={
                "cte_retention_days": 730,
                "audit_log_retention_days": 730,
                "export_retention_days": 1,
                "auto_archive": True,
            },
        )
        assert resp.status_code == 200
        assert stubbed_jsonb["db"]["t1"]["data_retention"]["cte_retention_days"] == 730

    def test_read_model_has_no_floor(self):
        # The read model must still accept legacy under-floor values.
        legacy = DataRetention(cte_retention_days=30, audit_log_retention_days=30, export_retention_days=0)
        assert legacy.cte_retention_days == 30

    def test_legacy_under_floor_blob_still_gets_without_500(self, client, stubbed_jsonb):
        legacy = _default_settings("t1").model_dump(exclude={"tenant_id"})
        legacy["data_retention"] = {
            "cte_retention_days": 30,
            "audit_log_retention_days": 45,
            "export_retention_days": 0,
            "auto_archive": False,
        }
        stubbed_jsonb["db"]["t1"] = legacy

        resp = client.get("/api/v1/settings/t1")
        assert resp.status_code == 200
        assert resp.json()["data_retention"]["cte_retention_days"] == 30


# ---------------------------------------------------------------------------
# 2. api_keys redaction
# ---------------------------------------------------------------------------


def _blob_with_key():
    blob = _default_settings("t1").model_dump(exclude={"tenant_id"})
    blob["api_keys"] = [
        {
            "id": "key-1",
            "name": "CI token",
            "prefix": "sk_test",
            "last4": "1234",
            "key": FAKE_KEY,
            "secret": FAKE_SECRET_VALUE,
            "hash": "deadbeef",
            "status": "active",
        }
    ]
    return blob


class TestApiKeyRedaction:
    def test_redact_helper_drops_secret_fields(self):
        out = _redact_api_keys([{"id": "k", "key": FAKE_KEY, "secret": FAKE_KEY, "token": FAKE_KEY}])
        assert out == [{"id": "k"}]
        assert FAKE_KEY not in str(out)

    def test_redact_helper_masks_raw_only_entry(self):
        out = _redact_api_keys([{"api_key": FAKE_KEY}])
        assert out == [{"last4": "1234", "status": "redacted"}]
        assert FAKE_KEY not in str(out)

    def test_get_via_db_never_echoes_key(self, client, stubbed_jsonb):
        stubbed_jsonb["db"]["t1"] = _blob_with_key()
        resp = client.get("/api/v1/settings/t1")
        assert resp.status_code == 200
        assert FAKE_KEY not in resp.text
        # Safe metadata survives.
        assert resp.json()["api_keys"][0]["id"] == "key-1"

    def test_get_via_cache_never_echoes_key(self, stubbed_jsonb):
        # No DB row; prime the cache directly then GET (cache-hit path).
        app = _make_app()
        client = TestClient(app)
        cached = SettingsResponse(**{**_blob_with_key(), "tenant_id": "t1"})
        s._settings_store["t1"] = cached
        resp = client.get("/api/v1/settings/t1")
        assert resp.status_code == 200
        assert FAKE_KEY not in resp.text

    def test_put_profile_never_echoes_key_and_store_keeps_original(self, client, stubbed_jsonb):
        stubbed_jsonb["db"]["t1"] = _blob_with_key()
        resp = client.put("/api/v1/settings/t1/profile", json={"company_name": "Acme"})
        assert resp.status_code == 200
        assert FAKE_KEY not in resp.text
        # The stored blob still holds the original key material.
        assert stubbed_jsonb["db"]["t1"]["api_keys"][0]["key"] == FAKE_KEY

    def test_put_retention_never_echoes_key_and_store_keeps_original(self, client, stubbed_jsonb):
        stubbed_jsonb["db"]["t1"] = _blob_with_key()
        resp = client.put(
            "/api/v1/settings/t1/retention",
            json={
                "cte_retention_days": 730,
                "audit_log_retention_days": 730,
                "export_retention_days": 1,
                "auto_archive": True,
            },
        )
        assert resp.status_code == 200
        assert FAKE_KEY not in resp.text
        assert stubbed_jsonb["db"]["t1"]["api_keys"][0]["key"] == FAKE_KEY

    def test_cache_not_mutated_by_redaction(self, client, stubbed_jsonb):
        stubbed_jsonb["db"]["t1"] = _blob_with_key()
        client.get("/api/v1/settings/t1")
        # The in-memory cache (warmed by the GET) retains the full record.
        assert s._settings_store["t1"].api_keys[0]["key"] == FAKE_KEY


# ---------------------------------------------------------------------------
# 3. Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_put_profile_rate_limited(self, client, stubbed_jsonb):
        from shared.rate_limit import add_rate_limiting

        app = FastAPI()
        app.include_router(router)
        add_rate_limiting(app)  # attaches limiter + SlowAPIMiddleware (429 handler)
        from app.webhook_compat import _verify_api_key

        app.dependency_overrides[_verify_api_key] = lambda: None
        install_tenant_context_override(app)
        rl_client = TestClient(app)

        last = None
        for _ in range(35):
            last = rl_client.put("/api/v1/settings/t1/profile", json={"company_name": "X"})
        assert last.status_code == 429

    def test_put_retention_rate_limited(self, stubbed_jsonb):
        from shared.rate_limit import add_rate_limiting

        app = FastAPI()
        app.include_router(router)
        add_rate_limiting(app)
        from app.webhook_compat import _verify_api_key

        app.dependency_overrides[_verify_api_key] = lambda: None
        install_tenant_context_override(app)
        rl_client = TestClient(app)

        body = {
            "cte_retention_days": 730,
            "audit_log_retention_days": 730,
            "export_retention_days": 1,
            "auto_archive": True,
        }
        last = None
        for _ in range(35):
            last = rl_client.put("/api/v1/settings/t1/retention", json=body)
        assert last.status_code == 429


# ---------------------------------------------------------------------------
# 4. Audit emission
# ---------------------------------------------------------------------------


class TestAudit:
    def test_profile_put_emits_audit(self, client, stubbed_jsonb, monkeypatch):
        calls = []
        monkeypatch.setattr(
            s,
            "_audit_settings_update",
            lambda tenant_id, endpoint, changed_fields, *, ctx, db_fallback: calls.append(
                (tenant_id, endpoint, changed_fields, db_fallback)
            ),
        )

        resp = client.put("/api/v1/settings/t1/profile", json={"company_name": "SecretCorp", "fei_number": "FEI-9"})
        assert resp.status_code == 200
        assert len(calls) == 1
        tenant_id, endpoint, changed_fields, db_fallback = calls[0]
        assert tenant_id == "t1"
        assert endpoint == "update_profile"
        assert db_fallback is False
        # Field NAMES only -- no PII values leak into the audit detail.
        assert "company_name" in changed_fields
        assert "SecretCorp" not in str(changed_fields)
        assert "FEI-9" not in str(changed_fields)

    def test_retention_put_emits_audit(self, client, stubbed_jsonb, monkeypatch):
        calls = []
        monkeypatch.setattr(
            s,
            "_audit_settings_update",
            lambda tenant_id, endpoint, changed_fields, *, ctx, db_fallback: calls.append(
                (tenant_id, endpoint, changed_fields, db_fallback)
            ),
        )
        resp = client.put(
            "/api/v1/settings/t1/retention",
            json={
                "cte_retention_days": 730,
                "audit_log_retention_days": 730,
                "export_retention_days": 1,
                "auto_archive": True,
            },
        )
        assert resp.status_code == 200
        assert calls[0][1] == "update_retention"
        assert "cte_retention_days" in calls[0][2]

    def test_audit_notes_db_fallback(self, client, stubbed_jsonb, monkeypatch):
        calls = []
        monkeypatch.setattr(
            s,
            "_audit_settings_update",
            lambda tenant_id, endpoint, changed_fields, *, ctx, db_fallback: calls.append(db_fallback),
        )
        stubbed_jsonb["set_fail_for"].add("t1")
        resp = client.put("/api/v1/settings/t1/profile", json={"company_name": "X"})
        assert resp.status_code == 200
        assert calls == [True]


# ---------------------------------------------------------------------------
# 5. Negative auth
# ---------------------------------------------------------------------------


class TestNegativeAuth:
    @pytest.fixture
    def noauth_client(self, stubbed_jsonb):
        # No tenant context override, no credentials -> real auth runs.
        return TestClient(_make_app(auth=False), raise_server_exceptions=False)

    def test_unauthenticated_get_rejected(self, noauth_client):
        resp = noauth_client.get("/api/v1/settings/t1")
        assert resp.status_code in (401, 403)

    def test_unauthenticated_put_profile_rejected(self, noauth_client):
        resp = noauth_client.put("/api/v1/settings/t1/profile", json={"company_name": "X"})
        assert resp.status_code in (401, 403)

    def test_unauthenticated_put_retention_rejected(self, noauth_client):
        resp = noauth_client.put(
            "/api/v1/settings/t1/retention",
            json={
                "cte_retention_days": 730,
                "audit_log_retention_days": 730,
                "export_retention_days": 1,
                "auto_archive": True,
            },
        )
        assert resp.status_code in (401, 403)

    def _pinned_app(self):
        """App whose auth context is pinned to tenant-a regardless of path.

        Mirrors production: the router does ``tenant_id = ctx.tenant_id`` so a
        caller authenticated as tenant-a cannot pivot to tenant-b by putting
        it in the URL.
        """
        from app.webhook_compat import _verify_api_key
        from shared.tenant_context import TenantContext

        app = FastAPI()
        app.state.limiter = limiter
        app.include_router(router)
        app.dependency_overrides[_verify_api_key] = lambda: None
        app.dependency_overrides[s.require_tenant_context] = lambda: TenantContext(
            tenant_id="tenant-a", principal_kind="test", principal_id="pinned"
        )
        return app

    def test_wrong_tenant_cannot_read_other_tenant(self, stubbed_jsonb):
        # Caller is tenant-a; store has only tenant-b data. A GET for the
        # tenant-b URL must operate on tenant-a (ctx.tenant_id), never return
        # tenant-b's stored blob.
        client = TestClient(self._pinned_app(), raise_server_exceptions=False)
        tenant_b_blob = _default_settings("tenant-b").model_dump(exclude={"tenant_id"})
        tenant_b_blob["profile"]["company_name"] = "TenantBSecret"
        stubbed_jsonb["db"]["tenant-b"] = tenant_b_blob

        resp = client.get("/api/v1/settings/tenant-b")
        assert resp.status_code == 200
        body = resp.json()
        # Router used ctx.tenant_id, not the path param.
        assert body["tenant_id"] == "tenant-a"
        assert body["profile"]["company_name"] != "TenantBSecret"

    def test_wrong_tenant_cannot_modify_other_tenant(self, stubbed_jsonb):
        client = TestClient(self._pinned_app(), raise_server_exceptions=False)
        resp = client.put("/api/v1/settings/tenant-b/profile", json={"company_name": "Evil"})
        assert resp.status_code == 200
        # The write landed on tenant-a (the authenticated tenant), not tenant-b.
        assert "tenant-b" not in stubbed_jsonb["db"]
        assert stubbed_jsonb["db"]["tenant-a"]["profile"]["company_name"] == "Evil"


# ---------------------------------------------------------------------------
# 6. Audit actor is the signed-in principal (not a hardcoded service)
# ---------------------------------------------------------------------------


class _FakeAuditLogger:
    """Records the kwargs passed to ``.log`` synchronously at call time.

    ``_audit_settings_update`` calls ``audit.log(**kwargs)`` synchronously to
    build the coroutine, then schedules it fire-and-forget. Recording in the
    (non-async) ``log`` call makes the assertion deterministic without having
    to await the detached task. ``log`` still returns a real awaitable so the
    scheduled task has something to run.
    """

    def __init__(self):
        self.calls = []

    def log(self, **kwargs):
        self.calls.append(kwargs)

        async def _noop():
            return None

        return _noop()


def _app_with_ctx(ctx):
    """Build a settings app whose tenant context is pinned to ``ctx``."""
    from app.webhook_compat import _verify_api_key

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[s.require_tenant_context] = lambda: ctx
    return app


class TestAuditActorIsPrincipal:
    def _install_fake_audit(self, monkeypatch):
        from shared.audit_logging import AuditLogger

        fake = _FakeAuditLogger()
        monkeypatch.setattr(AuditLogger, "get_instance", classmethod(lambda cls: fake))
        return fake

    def test_profile_audit_actor_is_signed_in_principal(self, stubbed_jsonb, monkeypatch):
        from shared.tenant_context import TenantContext

        fake = self._install_fake_audit(monkeypatch)
        ctx = TenantContext(tenant_id="t1", principal_kind="test", principal_id="router-test")
        client = TestClient(_app_with_ctx(ctx))

        resp = client.put("/api/v1/settings/t1/profile", json={"company_name": "Acme"})
        assert resp.status_code == 200
        assert len(fake.calls) == 1
        actor = fake.calls[0]["actor"]
        assert actor.actor_id == "router-test"
        assert actor.actor_type == "test"
        assert actor.tenant_id == "t1"
        # Never the old hardcoded service identity.
        assert actor.actor_id != "settings-router"
        assert actor.actor_type != "service"

    def test_retention_audit_actor_is_signed_in_principal(self, stubbed_jsonb, monkeypatch):
        from shared.tenant_context import TenantContext

        fake = self._install_fake_audit(monkeypatch)
        ctx = TenantContext(tenant_id="t1", principal_kind="api_key", principal_id="key-42")
        client = TestClient(_app_with_ctx(ctx))

        resp = client.put(
            "/api/v1/settings/t1/retention",
            json={
                "cte_retention_days": 730,
                "audit_log_retention_days": 730,
                "export_retention_days": 1,
                "auto_archive": True,
            },
        )
        assert resp.status_code == 200
        actor = fake.calls[0]["actor"]
        assert actor.actor_id == "key-42"
        assert actor.actor_type == "api_key"
        assert actor.actor_id != "settings-router"
        assert actor.actor_type != "service"

    def test_audit_actor_carries_email_when_present(self, stubbed_jsonb, monkeypatch):
        from shared.tenant_context import TenantContext

        fake = self._install_fake_audit(monkeypatch)
        ctx = TenantContext(
            tenant_id="t1",
            principal_kind="test",
            principal_id="router-test",
            actor_email="user@example.test",
        )
        client = TestClient(_app_with_ctx(ctx))

        resp = client.put("/api/v1/settings/t1/profile", json={"company_name": "Acme"})
        assert resp.status_code == 200
        actor = fake.calls[0]["actor"]
        assert actor.email == "user@example.test"


# ---------------------------------------------------------------------------
# 7. CompanyProfile is bounded (extra=forbid + max_length)
# ---------------------------------------------------------------------------


class TestCompanyProfileBounds:
    def test_put_rejects_unknown_extra_field(self, client):
        resp = client.put(
            "/api/v1/settings/t1/profile",
            json={"company_name": "Acme", "unexpected": "nope"},
        )
        assert resp.status_code == 422

    def test_put_rejects_over_max_length(self, client):
        resp = client.put(
            "/api/v1/settings/t1/profile",
            json={"company_name": "A" * 201},
        )
        assert resp.status_code == 422

    def test_put_accepts_bounded_values(self, client, stubbed_jsonb):
        resp = client.put(
            "/api/v1/settings/t1/profile",
            json={
                "company_name": "Acme Foods",
                "company_type": "distributor",
                "primary_contact": "Jane Doe",
                "contact_email": "jane@example.test",
                "phone": "555-0100",
                "address": "1 Market St",
                "website": "https://example.test",
                "fei_number": "1234567",
            },
        )
        assert resp.status_code == 200
        assert stubbed_jsonb["db"]["t1"]["profile"]["company_name"] == "Acme Foods"

    def test_model_forbids_extra_fields(self):
        with pytest.raises(ValueError):
            s.CompanyProfile(bogus="x")

    def test_model_enforces_max_length(self):
        with pytest.raises(ValueError):
            s.CompanyProfile(fei_number="9" * 51)
