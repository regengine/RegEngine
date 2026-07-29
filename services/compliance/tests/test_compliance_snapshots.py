"""Compliance Snapshots router tests (services/compliance/app/snapshots.py).

Runs against an in-memory SQLite with an attached ``fsma`` schema so the
raw-SQL persistence layer is exercised end-to-end without Postgres. RLS
itself is covered by the live-DB migration gate
(tests/migrations/test_rls_coverage.py auto-discovers
fsma.compliance_evidence_snapshots); here the app-layer guarantees are
tested: authenticated-tenant scoping, path-tenant mismatch rejection, and
hash integrity round-trips.

Auth: ``require_api_key`` is overridden with a stub that populates
``request.state.api_key`` — the REAL ``resolve_tenant_context`` dependency
still runs, so the E_TENANT_MISMATCH and tenant-binding behavior under
test is the production code path, not a mock.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[1]
_SERVICES_DIR = _SERVICE_DIR.parent
_REPO_ROOT = _SERVICES_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR, _REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from shared.auth import APIKey, require_api_key  # noqa: E402
from shared.database import get_db_session  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from services.compliance.app.snapshots import router as snapshots_router  # noqa: E402

TENANT_A = str(uuid4())
TENANT_B = str(uuid4())

# SQLite mirror of the v101 DDL (fcf558aeb1e2): TEXT ids/timestamps,
# INTEGER booleans — the router binds ISO strings and coerces on read.
_SQLITE_DDL = """
CREATE TABLE fsma.compliance_evidence_snapshots (
    id                   TEXT PRIMARY KEY,
    tenant_id            TEXT NOT NULL,
    snapshot_name        TEXT NOT NULL,
    snapshot_reason      TEXT,
    created_by           TEXT NOT NULL,
    trigger_alert_id     TEXT,
    is_auto_created      INTEGER NOT NULL DEFAULT 0,
    deadline             TEXT,
    regulatory_citation  TEXT,
    is_attested          INTEGER NOT NULL DEFAULT 0,
    attested_by          TEXT,
    attested_at          TEXT,
    attestation_title    TEXT,
    compliance_status    TEXT NOT NULL DEFAULT 'COMPLIANT',
    active_alert_count   INTEGER NOT NULL DEFAULT 0,
    critical_alert_count INTEGER NOT NULL DEFAULT 0,
    content_hash         TEXT NOT NULL,
    snapshot_state       TEXT NOT NULL DEFAULT 'VALID',
    degradation_reason   TEXT,
    captured_at          TEXT NOT NULL
)
"""


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS fsma")
        conn.exec_driver_sql(_SQLITE_DDL)
    yield eng
    eng.dispose()


def _make_client(engine, tenant_id: str) -> TestClient:
    app = FastAPI()
    app.include_router(snapshots_router)
    session_factory = sessionmaker(bind=engine)

    def _db():
        db = session_factory()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    async def _auth(request: Request) -> APIKey:
        key = APIKey(
            key_id="test",
            key_hash="",
            name="Test Key",
            tenant_id=tenant_id,
            created_at=datetime.now(timezone.utc),
        )
        request.state.api_key = key
        return key

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[require_api_key] = _auth
    return TestClient(app)


def _create(client: TestClient, tenant_id: str, name: str = "Q3 Freeze", **overrides) -> dict:
    body = {
        "snapshot_name": name,
        "snapshot_reason": "FDA audit prep",
        "created_by": "chris@regengine.co",
        **overrides,
    }
    response = client.post(f"/v1/compliance/snapshots/{tenant_id}", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_create_and_list_roundtrip(engine) -> None:
    client = _make_client(engine, TENANT_A)

    created = _create(client, TENANT_A)
    assert created["tenant_id"] == TENANT_A
    assert created["snapshot_name"] == "Q3 Freeze"
    assert created["created_by"] == "chris@regengine.co"
    assert len(created["content_hash"]) == 64
    assert created["integrity_verified"] is True
    assert created["is_attested"] is False
    assert created["is_auto_created"] is False
    assert created["snapshot_state"] == "VALID"
    assert created["state_emoji"] == "🟢"
    assert created["compliance_status"] == "COMPLIANT"
    assert created["compliance_status_emoji"] == "✅"
    assert created["age_hours"] == 0.0

    _create(client, TENANT_A, name="Second Freeze")
    listed = client.get(f"/v1/compliance/snapshots/{TENANT_A}")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 2
    assert {item["snapshot_name"] for item in items} == {"Q3 Freeze", "Second Freeze"}


def test_create_requires_snapshot_name(engine) -> None:
    client = _make_client(engine, TENANT_A)
    response = client.post(
        f"/v1/compliance/snapshots/{TENANT_A}",
        json={"created_by": "chris@regengine.co"},
    )
    assert response.status_code == 422


def test_verify_attest_refreeze_flow(engine) -> None:
    client = _make_client(engine, TENANT_A)
    snapshot = _create(client, TENANT_A)
    sid = snapshot["id"]

    verified = client.get(
        f"/v1/compliance/snapshots/{TENANT_A}/{sid}/verify",
        params={"verified_by": "auditor@regengine.co"},
    )
    assert verified.status_code == 200
    verdict = verified.json()
    assert verdict["is_valid"] is True
    assert verdict["hash_match"] is True
    assert verdict["stored_hash"] == verdict["computed_hash"] == snapshot["content_hash"]
    assert verdict["verified_by"] == "auditor@regengine.co"

    attested = client.post(
        f"/v1/compliance/snapshots/{TENANT_A}/{sid}/attest",
        json={"attested_by": "Chris Sellers", "attestation_title": "Compliance Owner"},
    )
    assert attested.status_code == 200
    body = attested.json()
    assert body["is_attested"] is True
    assert body["attested_by"] == "Chris Sellers"
    assert body["attestation_title"] == "Compliance Owner"
    assert body["attested_at"] is not None
    # Attestation does not touch the frozen identity fields.
    assert body["content_hash"] == snapshot["content_hash"]
    assert body["integrity_verified"] is True

    refrozen = client.post(
        f"/v1/compliance/snapshots/{TENANT_A}/{sid}/refreeze",
        json={"created_by": "ops@regengine.co"},
    )
    assert refrozen.status_code == 200
    body = refrozen.json()
    assert body["created_by"] == "ops@regengine.co"
    assert body["content_hash"] != snapshot["content_hash"]
    assert body["captured_at"] != snapshot["captured_at"]
    assert body["snapshot_state"] == "VALID"
    assert body["integrity_verified"] is True

    reverified = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/verify")
    assert reverified.json()["hash_match"] is True


def test_verify_detects_tampering(engine) -> None:
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]

    with engine.begin() as conn:
        conn.exec_driver_sql(
            f"UPDATE fsma.compliance_evidence_snapshots SET snapshot_name = 'tampered' WHERE id = '{sid}'"
        )

    verdict = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/verify").json()
    assert verdict["hash_match"] is False
    assert verdict["is_valid"] is False
    assert verdict["stored_hash"] != verdict["computed_hash"]

    listed = client.get(f"/v1/compliance/snapshots/{TENANT_A}").json()["items"]
    assert listed[0]["integrity_verified"] is False


# ---------------------------------------------------------------------------
# Export / audit-pack / FDA response / diff
# ---------------------------------------------------------------------------


def test_export_audit_pack_and_fda_response(engine) -> None:
    client = _make_client(engine, TENANT_A)
    snapshot = _create(client, TENANT_A)
    sid = snapshot["id"]

    export = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/export")
    assert export.status_code == 200
    payload = export.json()
    assert payload["snapshot_id"] == sid
    assert payload["tenant_id"] == TENANT_A
    assert payload["content_hash"] == snapshot["content_hash"]
    assert payload["integrity_verified"] is True
    assert payload["export_date"]

    pack = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/audit-pack")
    assert pack.status_code == 200
    assert pack.headers["content-type"].startswith("text/plain")
    assert f"ZeroTrust-AuditPack-{sid}.txt" in pack.headers["content-disposition"]
    assert "Q3 Freeze" in pack.text
    assert snapshot["content_hash"] in pack.text

    fda = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/fda-response")
    assert fda.status_code == 200
    text_body = fda.json()["text"]
    assert "FDA Response Template" in text_body
    assert "Q3 Freeze" in text_body


def test_diff(engine) -> None:
    client = _make_client(engine, TENANT_A)
    first = _create(client, TENANT_A, name="Before")
    second = _create(client, TENANT_A, name="After", snapshot_reason="post-remediation")

    diff = client.get(
        f"/v1/compliance/snapshots/{TENANT_A}/diff",
        params={"snapshot_a": first["id"], "snapshot_b": second["id"]},
    )
    assert diff.status_code == 200
    body = diff.json()
    assert body["snapshot_a"] == {"name": "Before"}
    assert body["snapshot_b"] == {"name": "After"}
    labels = {change["label"] for change in body["changes"]}
    assert {"Snapshot Name", "Snapshot Reason", "Content Hash"} <= labels

    missing = client.get(
        f"/v1/compliance/snapshots/{TENANT_A}/diff",
        params={"snapshot_a": first["id"], "snapshot_b": str(uuid4())},
    )
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Tenant binding
# ---------------------------------------------------------------------------


def test_tenant_isolation(engine) -> None:
    client_a = _make_client(engine, TENANT_A)
    client_b = _make_client(engine, TENANT_B)

    snapshot = _create(client_a, TENANT_A)

    listed_b = client_b.get(f"/v1/compliance/snapshots/{TENANT_B}")
    assert listed_b.status_code == 200
    assert listed_b.json()["items"] == []

    # Tenant B cannot see or mutate tenant A's snapshot through its own scope.
    cross = client_b.post(
        f"/v1/compliance/snapshots/{TENANT_B}/{snapshot['id']}/attest",
        json={"attested_by": "Mallory", "attestation_title": "Nope"},
    )
    assert cross.status_code == 404


def test_path_tenant_mismatch_is_rejected(engine) -> None:
    client_a = _make_client(engine, TENANT_A)
    # Authenticated as tenant A, requesting tenant B's path segment →
    # resolve_tenant_context must 409 (E_TENANT_MISMATCH), never serve B.
    response = client_a.get(f"/v1/compliance/snapshots/{TENANT_B}")
    assert response.status_code == 409


def test_missing_api_key_is_401(engine) -> None:
    app = FastAPI()
    app.include_router(snapshots_router)
    client = TestClient(app)
    response = client.get(f"/v1/compliance/snapshots/{TENANT_A}")
    assert response.status_code == 401
