"""Auth and tenant-scoping tests for the buyer remediation router.

``app/remediation/router.py`` had no dedicated route tests: every endpoint
takes its tenant only from the authenticated principal via
``resolve_tenant`` (never from body/header for scoped keys), enforces
``remediation.read`` / ``remediation.write`` / ``remediation.export``
scopes through ``require_permission``, and fails closed (503 without a
database, 404 for unknown cases, 409/422 for unissuable links).

These tests mount the real router with a stubbed principal and database so
each security invariant is exercised through HTTP. All database and token
collaborators are fakes; no Postgres, Redis, or network is touched.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.authz as authz
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.remediation import router as remediation_router
from shared.database import get_db_session

TENANT = str(uuid.uuid4())
OTHER_TENANT = str(uuid.uuid4())

READ_WRITE = ["remediation.read", "remediation.write"]


def _make_principal(
    tenant_id: str | None = TENANT,
    scopes: list[str] | None = None,
) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        tenant_id=tenant_id,
        scopes=scopes if scopes is not None else list(READ_WRITE),
        auth_mode="test",
    )


def _build_client(
    principal: IngestionPrincipal | Exception,
    fake_db: MagicMock | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(remediation_router.router)

    if isinstance(principal, Exception):
        def _raise() -> IngestionPrincipal:
            raise principal
        app.dependency_overrides[get_ingestion_principal] = _raise
    else:
        app.dependency_overrides[get_ingestion_principal] = lambda: principal

    db = fake_db if fake_db is not None else MagicMock()
    app.dependency_overrides[get_db_session] = lambda: db
    client = TestClient(app, raise_server_exceptions=False)
    client._fake_db = db  # type: ignore[attr-defined]
    return client


@pytest.fixture(autouse=True)
def _patch_rate_limit(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))


@pytest.fixture()
def fake_db():
    return MagicMock()


@pytest.fixture()
def client(fake_db):
    return _build_client(_make_principal(), fake_db)


def _fake_service(monkeypatch, **overrides):
    """Replace remediation service entry points used by the router."""
    svc = remediation_router.service
    for name, func in overrides.items():
        monkeypatch.setattr(svc, name, func)
    return svc


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_unauthenticated_request_returns_401(monkeypatch):
    """No API key means the real missing-key branch rejects the call.

    The principal dependency is left intact so deleting the missing-key
    branch in ``get_ingestion_principal`` turns this test red.
    """
    monkeypatch.setenv("REGENGINE_ENV", "production")
    app = FastAPI()
    app.include_router(remediation_router.router)
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/remediation/manifests")
    assert resp.status_code == 401


def test_principal_without_read_scope_cannot_list_manifests(client, monkeypatch):
    called = []
    _fake_service(monkeypatch, list_runs=lambda db, **kw: called.append(kw) or [])
    scoped_client = _build_client(_make_principal(scopes=["remediation.write"]))
    resp = scoped_client.get("/api/v1/remediation/manifests")
    assert resp.status_code == 403
    assert "remediation.read" in resp.json()["detail"]
    assert called == []


def test_write_scope_cannot_export_evidence_bundle(client, monkeypatch):
    scoped_client = _build_client(_make_principal(scopes=["remediation.write"]))
    resp = scoped_client.get(f"/api/v1/remediation/manifests/{uuid.uuid4()}/evidence")
    assert resp.status_code == 403
    assert "remediation.export" in resp.json()["detail"]


def test_write_scope_can_upload_manifest(monkeypatch):
    """Scope check is per action: remediation.write alone authorizes upload."""
    from app.remediation.schemas import ManifestUploadResponse

    receipt = ManifestUploadResponse(
        ingestion_run_id=str(uuid.uuid4()),
        source_sha256="abc",
        original_filename="manifest.csv",
        ruleset_hash="rules",
        total_rows=1,
        passed=1,
        failed=0,
        records=[],
    )
    _fake_service(monkeypatch, ingest_manifest=lambda db, **kw: receipt)
    scoped_client = _build_client(_make_principal(scopes=["remediation.write"]))
    resp = scoped_client.post(
        "/api/v1/remediation/manifests",
        files={"file": ("manifest.csv", b"lot,sku\n1,A\n", "text/csv")},
        data={"supplier_org": "Acme Farms"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ingestion_run_id"] == receipt.ingestion_run_id


# ---------------------------------------------------------------------------
# Tenant scoping
# ---------------------------------------------------------------------------


def test_cross_tenant_query_param_rejected(client, monkeypatch):
    called = []
    _fake_service(monkeypatch, list_runs=lambda db, **kw: called.append(kw) or [])
    resp = client.get("/api/v1/remediation/manifests", params={"tenant_id": OTHER_TENANT})
    assert resp.status_code == 403
    assert called == [], "service must not run for a cross-tenant request"


def test_matching_tenant_param_allowed_and_bound_to_principal(client, monkeypatch):
    seen = {}

    def _list_runs(db, **kw):
        seen.update(kw)
        return []

    _fake_service(monkeypatch, list_runs=_list_runs)
    resp = client.get("/api/v1/remediation/manifests", params={"tenant_id": TENANT})
    assert resp.status_code == 200
    assert seen["tenant_id"] == TENANT


def test_omitted_tenant_param_uses_principal_tenant(client, monkeypatch):
    seen = {}

    def _list_runs(db, **kw):
        seen.update(kw)
        return []

    _fake_service(monkeypatch, list_runs=_list_runs)
    resp = client.get("/api/v1/remediation/manifests")
    assert resp.status_code == 200
    assert seen["tenant_id"] == TENANT


def test_missing_tenant_context_returns_400(monkeypatch):
    open_client = _build_client(_make_principal(tenant_id=None, scopes=["remediation.read"]))
    resp = open_client.get("/api/v1/remediation/manifests")
    assert resp.status_code == 400


def test_dev_open_principal_may_target_explicit_uuid_tenant(monkeypatch):
    """The tenant-less local principal is the only caller allowed an
    explicit tenant; production keys are always tenant-bound."""
    seen = {}

    def _list_runs(db, **kw):
        seen.update(kw)
        return []

    _fake_service(monkeypatch, list_runs=_list_runs)
    open_client = _build_client(_make_principal(tenant_id=None, scopes=["remediation.read"]))
    resp = open_client.get("/api/v1/remediation/manifests", params={"tenant_id": OTHER_TENANT})
    assert resp.status_code == 200
    assert seen["tenant_id"] == OTHER_TENANT


def test_non_uuid_tenant_rejected_for_rls_backed_tables(client):
    """Remediation tables are RLS-backed UUID tables, so a slug tenant
    that passes the generic format check still fails closed here."""
    slug_client = _build_client(_make_principal(tenant_id="acme"))
    resp = slug_client.get("/api/v1/remediation/manifests")
    assert resp.status_code == 400


def test_cross_tenant_form_field_rejected_on_upload(client):
    resp = client.post(
        "/api/v1/remediation/manifests",
        files={"file": ("manifest.csv", b"lot,sku\n1,A\n", "text/csv")},
        data={"supplier_org": "Acme Farms", "tenant_id": OTHER_TENANT},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Fail-closed handler behavior
# ---------------------------------------------------------------------------


def test_database_unavailable_returns_503(monkeypatch):
    _fake_service(monkeypatch, list_runs=lambda db, **kw: [])
    client = _build_client(_make_principal(), fake_db=None)
    client.app.dependency_overrides[get_db_session] = lambda: None
    resp = client.get("/api/v1/remediation/manifests")
    assert resp.status_code == 503


def test_unknown_manifest_run_returns_404(monkeypatch, fake_db):
    """A missing manifest row raises 404 inside the real ``get_run_meta``.

    The service function is left intact and the fake database returns no
    row, so removing the ``if not row`` guard in the service turns this
    test red instead of staying green behind an injected raise.
    """
    fake_db.execute.return_value.fetchone.return_value = None
    client = _build_client(_make_principal(), fake_db)
    resp = client.get(f"/api/v1/remediation/manifests/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_original_download_returns_bytes_with_sha_header(client, monkeypatch):
    raw = b"lot,sku\n1,A\n"
    _fake_service(
        monkeypatch,
        get_run_meta=lambda db, **kw: {
            "sha256": "deadbeef",
            "filename": "manifest.csv",
            "raw_bytes": raw,
        },
    )
    resp = client.get(f"/api/v1/remediation/manifests/{uuid.uuid4()}/original")
    assert resp.status_code == 200
    assert resp.content == raw
    assert resp.headers["X-Source-SHA256"] == "deadbeef"


def test_release_skips_unqualified_records(client, monkeypatch):
    records = [
        {"id": "good", "validation_status": "passed", "release_status": "staged"},
        {"id": "bad-row", "validation_status": "failed", "release_status": "staged"},
        {"id": "already-out", "validation_status": "passed", "release_status": "released"},
    ]
    released = []
    _fake_service(
        monkeypatch,
        get_run_meta=lambda db, **kw: {},
        list_run_records=lambda db, **kw: records,
        release_record=lambda db, **kw: released.append(kw["record"]["id"]) or "evt-1",
    )
    resp = client.post(f"/api/v1/remediation/manifests/{uuid.uuid4()}/release", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert [r["record_id"] for r in body["released"]] == ["good"]
    assert {s["record_id"] for s in body["skipped"]} == {"bad-row", "already-out"}
    assert released == ["good"]


# ---------------------------------------------------------------------------
# Correction-link issuance
# ---------------------------------------------------------------------------

CASE_ID = str(uuid.uuid4())


def _case(**overrides):
    case = {
        "id": CASE_ID,
        "manifest_record_id": str(uuid.uuid4()),
        "exception_case_id": None,
        "supplier_org": "Acme Farms",
        "manifest_ref": "manifest.csv",
        "line_ref": "row 2",
        "validation_issue_ids": ["missing-lot"],
        "allowed_fields": [{"field_path": "traceability_lot_code"}],
        "due_at": None,
        "status": "awaiting_supplier",
    }
    case.update(overrides)
    return case


def _patch_link_collaborators(monkeypatch, calls, case):
    monkeypatch.setattr(remediation_router, "_load_case", lambda db, tid, cid: case)
    monkeypatch.setattr(
        remediation_router.tokens,
        "revoke_tokens_for_case",
        lambda db, **kw: calls.append(("revoke", kw)) or [],
    )

    def _issue(db, **kw):
        calls.append(("issue", kw))
        return {
            "token": "raw-token-value",
            "token_id": "tok-1",
            "expires_at": datetime(2026, 5, 2, tzinfo=timezone.utc),
        }

    monkeypatch.setattr(remediation_router.tokens, "issue_token", _issue)
    monkeypatch.setattr(
        remediation_router.delivery, "correction_url", lambda raw: f"https://x/{raw}"
    )
    monkeypatch.setattr(
        remediation_router.outbox, "enqueue_preview", lambda db, **kw: calls.append(("outbox", kw))
    )
    monkeypatch.setattr(remediation_router, "transition", lambda db, **kw: None)


def test_create_link_without_correctable_fields_returns_409(client, monkeypatch):
    calls = []
    _patch_link_collaborators(monkeypatch, calls, _case(allowed_fields=[]))
    resp = client.post(
        f"/api/v1/remediation/cases/{CASE_ID}/link",
        params={"tenant_id": TENANT},
        json={"supplier_email": "ops@acme.example"},
    )
    assert resp.status_code == 409
    assert [kind for kind, _kw in calls] == [], "no token may be issued for buyer-work cases"


def test_create_link_with_disallowed_status_returns_409_without_minting(client, monkeypatch):
    """A case whose status forbids links fails before any token work.

    The status gate runs above revoke and mint, so a disallowed status
    must leave zero token calls behind. Reverting the gate below the
    mint turns this test red.
    """
    calls = []
    _patch_link_collaborators(monkeypatch, calls, _case(status="closed"))
    resp = client.post(
        f"/api/v1/remediation/cases/{CASE_ID}/link",
        params={"tenant_id": TENANT},
        json={"supplier_email": "ops@acme.example"},
    )
    assert resp.status_code == 409
    assert calls == [], "no token may be revoked or minted for a closed case"


def test_create_link_with_unmatched_fields_returns_422(client, monkeypatch):
    calls = []
    _patch_link_collaborators(monkeypatch, calls, _case())
    resp = client.post(
        f"/api/v1/remediation/cases/{CASE_ID}/link",
        params={"tenant_id": TENANT},
        json={"authorized_fields": ["no.such.field"]},
    )
    assert resp.status_code == 422
    assert [kind for kind, _kw in calls] == []


def test_create_link_revokes_before_mint_and_scopes_tenant(client, monkeypatch):
    calls = []
    _patch_link_collaborators(monkeypatch, calls, _case())
    resp = client.post(
        f"/api/v1/remediation/cases/{CASE_ID}/link",
        params={"tenant_id": TENANT},
        json={"supplier_email": "ops@acme.example"},
    )
    assert resp.status_code == 200, resp.text
    kinds = [kind for kind, _kw in calls]
    assert kinds[0] == "revoke", "reissue must revoke live tokens before minting"
    assert "issue" in kinds and "outbox" in kinds
    for _kind, kw in calls:
        assert kw["tenant_id"] == TENANT
    body = resp.json()
    assert body["token"] == "raw-token-value"
    assert body["case_id"] == CASE_ID


def test_revoke_link_for_unknown_case_returns_404_without_revoking(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        remediation_router,
        "_load_case",
        lambda db, tid, cid: (_ for _ in ()).throw(
            HTTPException(status_code=404, detail="Case not found")
        ),
    )
    monkeypatch.setattr(
        remediation_router.tokens,
        "revoke_tokens_for_case",
        lambda db, **kw: calls.append(kw) or [],
    )
    resp = client.post(f"/api/v1/remediation/cases/{CASE_ID}/link/revoke")
    assert resp.status_code == 404
    assert calls == [], "fail closed before touching any token"
