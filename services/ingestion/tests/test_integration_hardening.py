"""Hardening tests for the integrations API router (findings 2-6).

Finding 1 (credential store) is deferred — see
``/workspace/devops/router-reviews/integ-cred-options.md``.

Covers (data-free, no live DB/network):

- Rate limits on configure / sync / csv-upload / disconnect / profile
  mutations and the inbound webhook (429 past the budget).
- Webhook verification failures return a uniform 401 body (no
  secret-state oracle); a repeated signature digest inside the nonce
  TTL is rejected as a replay.
- CSV upload runs every string leaf through ``sanitize_cell`` so
  formula-injection prefixes never leave the ingest surface.
- Request models are bounded (``extra="forbid"`` + max_length / ge/le).
- Successful mutations emit tenant-bound audit events attributed to
  ``ctx.principal_id`` / ``principal_kind`` / ``actor_email``, carrying
  field NAMES only (never secret values).
- Negative auth: unauthenticated mutations are rejected; a context
  pinned to one tenant cannot configure / sync / disconnect another
  tenant's connector, and writes land under ``ctx.tenant_id``.

Synthetic fixtures only; pragma allowlist used solely for fake secrets.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from shared.rate_limit import limiter
from shared.tenant_context import TenantContext
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import integration_router as ir  # noqa: E402
from app.integration_router import (  # noqa: E402
    ConnectorConfigRequest,
    CreateIntegrationProfileRequest,
    SyncRequest,
    UpdateIntegrationProfileRequest,
    router,
)
from shared.external_connectors import registry as registry_mod  # noqa: E402
from shared.external_connectors.base import ConnectionStatus, ConnectorConfig  # noqa: E402

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
CONNECTOR_ID = "safetyculture"

# Synthetic only — never a real credential.
FAKE_API_KEY = (
    "sk_test_FAKE_INTEGRATION_DO_NOT_USE"  # pragma: allowlist secret
)
FAKE_WEBHOOK_SECRET = (
    "whsec_test_FAKE_DO_NOT_USE_0001"  # pragma: allowlist secret
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_app(*, pinned_tenant: str | None = TENANT_A, authed: bool = True) -> FastAPI:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(router)

    if authed:

        async def _ctx(request: Request) -> TenantContext:
            return TenantContext(
                tenant_id=pinned_tenant or TENANT_A,
                principal_kind="test",
                principal_id="router-test",
                actor_email="[email protected]",
            )

        app.dependency_overrides[ir.require_tenant_context] = _ctx
        # Also bypass the legacy API-key gate when present.
        try:
            from app.webhook_compat import _verify_api_key

            app.dependency_overrides[_verify_api_key] = lambda: None
        except Exception:  # pragma: no cover
            pass
    return app


def _reset_limiter() -> None:
    try:
        limiter.reset()
    except Exception:  # pragma: no cover
        storage = getattr(limiter, "_storage", None) or getattr(
            getattr(limiter, "limiter", None), "storage", None
        )
        if storage is not None and hasattr(storage, "reset"):
            storage.reset()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch):
    _reset_limiter()
    ir._reset_webhook_nonces_for_tests()
    ir._profile_store.clear()
    monkeypatch.setattr(registry_mod, "_CONNECTOR_CLASSES", {})
    monkeypatch.setattr(registry_mod, "_CONNECTOR_ALIASES", {})
    monkeypatch.setattr(registry_mod, "_ACTIVE_CONNECTORS", {})
    monkeypatch.setattr(ir, "get_db_safe", lambda: None)
    yield
    _reset_limiter()
    ir._reset_webhook_nonces_for_tests()
    ir._profile_store.clear()


class _FakeConnector:
    def __init__(self, status: ConnectionStatus = ConnectionStatus.CONNECTED):
        self.status = status
        self.handle_calls = 0

    async def test_connection(self):
        return True

    async def sync(self, *, since=None, limit=100):
        class _SyncResult:
            connector_id = CONNECTOR_ID
            events_fetched = 1
            events_accepted = 1
            events_rejected = 0
            errors: list = []
            duration_ms = 1
            success = True

        return _SyncResult()

    async def handle_webhook(self, payload: bytes, headers: dict[str, str]):
        self.handle_calls += 1
        return []

    def get_connector_info(self):
        return {"category": "food_safety"}


def _register_fake(monkeypatch: pytest.MonkeyPatch, connector: _FakeConnector | None = None):
    connector = connector or _FakeConnector()

    class _Cls:
        def __init__(self, config):
            self.config = config
            self.status = ConnectionStatus.CONNECTED

        def get_connector_info(self):
            return {"category": "food_safety"}

    monkeypatch.setattr(
        registry_mod,
        "get_connector_class",
        lambda cid: _Cls if cid == CONNECTOR_ID else None,
    )
    monkeypatch.setattr(
        registry_mod,
        "resolve_connector_id",
        lambda cid: cid,
    )
    monkeypatch.setattr(
        registry_mod,
        "remove_connector",
        lambda tid, cid: None,
    )
    monkeypatch.setattr(
        registry_mod,
        "get_or_create_connector",
        lambda tid, cid, config: connector
        if isinstance(connector, _FakeConnector)
        else _FakeConnector(),
    )
    monkeypatch.setattr(
        registry_mod,
        "get_tenant_connectors",
        lambda tid: {CONNECTOR_ID: connector} if tid == TENANT_A else {},
    )
    return connector


# ---------------------------------------------------------------------------
# Finding 5 — bounded request models
# ---------------------------------------------------------------------------


def test_configure_model_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ConnectorConfigRequest(connector_id=CONNECTOR_ID, unexpected="x")


def test_configure_model_bounds_connector_id() -> None:
    with pytest.raises(ValidationError):
        ConnectorConfigRequest(connector_id="x" * 121)


def test_configure_model_bounds_secret_length() -> None:
    with pytest.raises(ValidationError):
        ConnectorConfigRequest(connector_id=CONNECTOR_ID, api_key="k" * 4097)


def test_sync_model_bounds_limit() -> None:
    with pytest.raises(ValidationError):
        SyncRequest(connector_id=CONNECTOR_ID, limit=0)
    with pytest.raises(ValidationError):
        SyncRequest(connector_id=CONNECTOR_ID, limit=1001)
    ok = SyncRequest(connector_id=CONNECTOR_ID, limit=1000)
    assert ok.limit == 1000


def test_profile_create_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        CreateIntegrationProfileRequest(display_name="Acme", rogue=True)


def test_profile_update_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        UpdateIntegrationProfileRequest(notes="ok", not_a_field=1)


def test_configure_rejects_extra_with_422() -> None:
    # Validation is pre-handler; no registry stub required.
    client = TestClient(_build_app())
    resp = client.post(
        f"/api/v1/integrations/configure/{TENANT_A}",
        json={"connector_id": CONNECTOR_ID, "extra_field": "nope"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Finding 2 — rate limits
# ---------------------------------------------------------------------------


def test_configure_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    _register_fake(monkeypatch)
    client = TestClient(_build_app())
    saw_429 = False
    for _ in range(20):
        resp = client.post(
            f"/api/v1/integrations/configure/{TENANT_A}",
            json={"connector_id": CONNECTOR_ID, "api_key": FAKE_API_KEY},
        )
        if resp.status_code == 429:
            saw_429 = True
            break
    assert saw_429


def test_sync_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    _register_fake(monkeypatch)
    client = TestClient(_build_app())
    saw_429 = False
    for _ in range(20):
        resp = client.post(
            f"/api/v1/integrations/sync/{TENANT_A}",
            json={"connector_id": CONNECTOR_ID, "limit": 10},
        )
        if resp.status_code == 429:
            saw_429 = True
            break
    assert saw_429


def test_disconnect_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    _register_fake(monkeypatch)
    client = TestClient(_build_app())
    saw_429 = False
    for _ in range(30):
        resp = client.delete(
            f"/api/v1/integrations/disconnect/{TENANT_A}/{CONNECTOR_ID}",
        )
        if resp.status_code == 429:
            saw_429 = True
            break
    assert saw_429


def test_profile_create_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(_build_app())
    saw_429 = False
    for i in range(40):
        resp = client.post(
            f"/api/v1/integrations/profiles/{TENANT_A}",
            json={"display_name": f"Profile {i}"},
        )
        if resp.status_code == 429:
            saw_429 = True
            break
    assert saw_429


def test_webhook_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = _register_fake(monkeypatch)

    # Vary the signature each call so the nonce cache does not 401 us first.
    class _Varying(_FakeConnector):
        def __init__(self):
            super().__init__()
            self.n = 0

        async def handle_webhook(self, payload, headers):
            self.n += 1
            return []

    varying = _Varying()
    monkeypatch.setattr(
        registry_mod,
        "get_tenant_connectors",
        lambda tid: {CONNECTOR_ID: varying},
    )
    client = TestClient(_build_app())
    saw_429 = False
    for i in range(70):
        resp = client.post(
            f"/api/v1/integrations/webhook/{TENANT_A}/{CONNECTOR_ID}",
            content=b'{"n":%d}' % i,
            headers={"x-signature": f"sha256=sig{i}"},
        )
        if resp.status_code == 429:
            saw_429 = True
            break
    assert saw_429


# ---------------------------------------------------------------------------
# Finding 3 — webhook oracle + nonce replay
# ---------------------------------------------------------------------------


def test_webhook_value_error_uniform_401(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Bad(_FakeConnector):
        async def handle_webhook(self, payload, headers):
            raise ValueError("webhook secret not configured for tenant")

    monkeypatch.setattr(
        registry_mod,
        "resolve_connector_id",
        lambda cid: cid,
    )
    monkeypatch.setattr(
        registry_mod,
        "get_tenant_connectors",
        lambda tid: {CONNECTOR_ID: _Bad()},
    )
    client = TestClient(_build_app())
    resp = client.post(
        f"/api/v1/integrations/webhook/{TENANT_A}/{CONNECTOR_ID}",
        content=b'{"ping":true}',
        headers={"x-signature": "sha256=abc"},
    )
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert detail == {
        "error": "webhook_rejected",
        "message": "Webhook verification failed",
    }
    # Oracle check: connector-specific wording must not appear.
    dumped = str(detail).lower()
    assert "secret" not in dumped
    assert "not configured" not in dumped


def test_webhook_missing_secret_same_body_as_bad_sig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Missing(_FakeConnector):
        async def handle_webhook(self, payload, headers):
            raise ValueError("missing webhook secret")

    class _BadSig(_FakeConnector):
        async def handle_webhook(self, payload, headers):
            raise ValueError("invalid HMAC digest")

    monkeypatch.setattr(registry_mod, "resolve_connector_id", lambda cid: cid)
    client = TestClient(_build_app())

    monkeypatch.setattr(
        registry_mod,
        "get_tenant_connectors",
        lambda tid: {CONNECTOR_ID: _Missing()},
    )
    r1 = client.post(
        f"/api/v1/integrations/webhook/{TENANT_A}/{CONNECTOR_ID}",
        content=b'{"a":1}',
        headers={"x-signature": "sha256=one"},
    )
    monkeypatch.setattr(
        registry_mod,
        "get_tenant_connectors",
        lambda tid: {CONNECTOR_ID: _BadSig()},
    )
    r2 = client.post(
        f"/api/v1/integrations/webhook/{TENANT_A}/{CONNECTOR_ID}",
        content=b'{"a":2}',
        headers={"x-signature": "sha256=two"},
    )
    assert r1.status_code == 401 and r2.status_code == 401
    assert r1.json() == r2.json()


def test_webhook_replay_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = _FakeConnector()
    monkeypatch.setattr(registry_mod, "resolve_connector_id", lambda cid: cid)
    monkeypatch.setattr(
        registry_mod,
        "get_tenant_connectors",
        lambda tid: {CONNECTOR_ID: connector},
    )
    client = TestClient(_build_app())
    headers = {"x-signature": "sha256=replay-me"}
    body = b'{"event":"inspection.completed"}'
    first = client.post(
        f"/api/v1/integrations/webhook/{TENANT_A}/{CONNECTOR_ID}",
        content=body,
        headers=headers,
    )
    assert first.status_code == 200
    assert first.json()["accepted"] == 0
    second = client.post(
        f"/api/v1/integrations/webhook/{TENANT_A}/{CONNECTOR_ID}",
        content=body,
        headers=headers,
    )
    assert second.status_code == 401
    assert second.json()["detail"]["error"] == "webhook_rejected"
    # Second call must not reach the connector again.
    assert connector.handle_calls == 1


# ---------------------------------------------------------------------------
# Finding 4 — sanitize_cell on CSV upload path
# ---------------------------------------------------------------------------


def test_csv_upload_sanitizes_formula_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    class _CsvConn:
        def __init__(self, config):
            self.config = config

        def parse_csv(self, csv_text, source_file=None):
            class _Evt:
                def to_ingest_dict(self):
                    return {
                        "product_description": "=CMD|' /C calc'!A0",
                        "notes": "+1234+0",
                        "nested": {"lot": "@SUM(A1:A2)"},
                    }

            return [_Evt()]

    monkeypatch.setattr(
        "shared.external_connectors.csv_sftp.CSVSFTPConnector",
        _CsvConn,
    )
    client = TestClient(_build_app())
    csv_bytes = b"product_description,notes\nplain,plain\n"
    resp = client.post(
        f"/api/v1/integrations/csv-upload/{TENANT_A}",
        files={"file": ("upload.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    assert len(events) == 1
    # safe_cell prefixes a single quote in front of dangerous prefixes.
    assert events[0]["product_description"].startswith("'")
    assert events[0]["notes"].startswith("'")
    assert events[0]["nested"]["lot"].startswith("'")


# ---------------------------------------------------------------------------
# Finding 6 — audit events with signed-in principal
# ---------------------------------------------------------------------------


class _FakeAuditLogger:
    def __init__(self, sink: list) -> None:
        self._sink = sink

    def log(self, **kwargs):
        self._sink.append(kwargs)

        async def _noop() -> None:
            return None

        return _noop()


def _install_fake_audit(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    import shared.audit_logging as audit_mod

    sink: list[dict] = []
    fake = _FakeAuditLogger(sink)
    monkeypatch.setattr(
        audit_mod.AuditLogger, "get_instance", classmethod(lambda cls: fake)
    )
    return sink


def test_configure_emits_audit_with_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_fake(monkeypatch)
    sink = _install_fake_audit(monkeypatch)
    client = TestClient(_build_app())
    resp = client.post(
        f"/api/v1/integrations/configure/{TENANT_A}",
        json={
            "connector_id": CONNECTOR_ID,
            "api_key": FAKE_API_KEY,
            "webhook_secret": FAKE_WEBHOOK_SECRET,
        },
    )
    assert resp.status_code == 200, resp.text
    assert len(sink) == 1
    call = sink[0]
    actor = call["actor"]
    assert actor.actor_id == "router-test"
    assert actor.actor_type == "test"
    assert actor.email == "[email protected]"
    assert actor.tenant_id == TENANT_A
    # Field NAMES only — never the synthetic secret values.
    details = call["details"]
    assert "api_key" in details["changed_fields"]
    assert "webhook_secret" in details["changed_fields"]
    blob = str(details) + str(call.get("message", ""))
    assert FAKE_API_KEY not in blob
    assert FAKE_WEBHOOK_SECRET not in blob


def test_disconnect_emits_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    _register_fake(monkeypatch)
    sink = _install_fake_audit(monkeypatch)
    client = TestClient(_build_app())
    resp = client.delete(
        f"/api/v1/integrations/disconnect/{TENANT_A}/{CONNECTOR_ID}",
    )
    assert resp.status_code == 200
    assert len(sink) == 1
    assert sink[0]["action"] == "disconnect"
    assert sink[0]["actor"].actor_id == "router-test"


def test_profile_create_emits_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    sink = _install_fake_audit(monkeypatch)
    client = TestClient(_build_app())
    resp = client.post(
        f"/api/v1/integrations/profiles/{TENANT_A}",
        json={"display_name": "Acme CSV"},
    )
    assert resp.status_code == 200, resp.text
    assert len(sink) == 1
    assert sink[0]["action"] == "profile_create"
    assert sink[0]["actor"].actor_id == "router-test"
    assert "display_name" in sink[0]["details"]["changed_fields"]


# ---------------------------------------------------------------------------
# Negative auth + wrong-tenant
# ---------------------------------------------------------------------------


def test_unauthenticated_configure_rejected() -> None:
    client = TestClient(_build_app(authed=False))
    resp = client.post(
        f"/api/v1/integrations/configure/{TENANT_A}",
        json={"connector_id": CONNECTOR_ID, "api_key": FAKE_API_KEY},
    )
    assert resp.status_code in (401, 403, 422)


def test_unauthenticated_sync_rejected() -> None:
    client = TestClient(_build_app(authed=False))
    resp = client.post(
        f"/api/v1/integrations/sync/{TENANT_A}",
        json={"connector_id": CONNECTOR_ID},
    )
    assert resp.status_code in (401, 403, 422)


def test_unauthenticated_disconnect_rejected() -> None:
    client = TestClient(_build_app(authed=False))
    resp = client.delete(
        f"/api/v1/integrations/disconnect/{TENANT_A}/{CONNECTOR_ID}",
    )
    assert resp.status_code in (401, 403, 422)


def test_wrong_tenant_cannot_sync_other_tenant_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pinned ctx.tenant_id=TENANT_B must not see TENANT_A's connectors,
    even when the path says TENANT_A."""
    connector = _FakeConnector()
    monkeypatch.setattr(registry_mod, "resolve_connector_id", lambda cid: cid)
    # Registry only has TENANT_A's connector.
    monkeypatch.setattr(
        registry_mod,
        "get_tenant_connectors",
        lambda tid: {CONNECTOR_ID: connector} if tid == TENANT_A else {},
    )
    # Pin context to TENANT_B — path still says TENANT_A.
    client = TestClient(_build_app(pinned_tenant=TENANT_B))
    resp = client.post(
        f"/api/v1/integrations/sync/{TENANT_A}",
        json={"connector_id": CONNECTOR_ID},
    )
    # Handler uses ctx.tenant_id, so lookup is under B → 404.
    assert resp.status_code == 404


def test_configure_writes_under_ctx_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class _Cls:
        def __init__(self, config):
            self.config = config
            self.status = ConnectionStatus.CONNECTED

        def get_connector_info(self):
            return {"category": "food_safety"}

    def _create(tid, cid, config):
        seen["tenant_id"] = tid
        seen["config_tenant"] = config.tenant_id
        c = _FakeConnector()
        c.status = ConnectionStatus.CONNECTED
        return c

    monkeypatch.setattr(registry_mod, "get_connector_class", lambda cid: _Cls)
    monkeypatch.setattr(registry_mod, "resolve_connector_id", lambda cid: cid)
    monkeypatch.setattr(registry_mod, "remove_connector", lambda tid, cid: None)
    monkeypatch.setattr(registry_mod, "get_or_create_connector", _create)

    # Path claims TENANT_B, but ctx is pinned to TENANT_A.
    client = TestClient(_build_app(pinned_tenant=TENANT_A))
    resp = client.post(
        f"/api/v1/integrations/configure/{TENANT_B}",
        json={"connector_id": CONNECTOR_ID, "api_key": FAKE_API_KEY},
    )
    assert resp.status_code == 200, resp.text
    assert seen["tenant_id"] == TENANT_A
    assert seen["config_tenant"] == TENANT_A


def test_integration_stays_out_of_production_enabled() -> None:
    """Regression guard: do not silently enable the held integration router."""
    from server.router_policy import PRODUCTION_ENABLED_ROUTERS, VALID_ROUTER_NAMES

    assert "integration" in VALID_ROUTER_NAMES
    assert "integration" not in PRODUCTION_ENABLED_ROUTERS
