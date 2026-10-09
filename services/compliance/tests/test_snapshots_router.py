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

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
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
from shared.auth import APIKey, APIKeyStore, require_api_key  # noqa: E402
from shared.database import get_db_session  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from services.compliance.app.snapshots import router as snapshots_router  # noqa: E402

TENANT_A = str(uuid4())
TENANT_B = str(uuid4())

# SQLite mirror of the v103 DDL (fcf558aeb1e2): TEXT ids/timestamps,
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

# #2931: the freeze path now reads the tenant's live alert posture, so the
# fixture has to mirror fsma.compliance_alerts (v078 DDL) as well. Column
# shape follows the real table: org_id NOT NULL + nullable backfilled
# tenant_id, TEXT severity, boolean-as-INTEGER resolved.
_SQLITE_ALERTS_DDL = """
CREATE TABLE fsma.compliance_alerts (
    id           TEXT PRIMARY KEY,
    org_id       TEXT NOT NULL,
    tenant_id    TEXT,
    alert_type   TEXT NOT NULL,
    severity     TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT,
    resolved     INTEGER NOT NULL DEFAULT 0,
    resolved_at  TEXT,
    created_at   TEXT NOT NULL
)
"""


def _new_engine(with_alerts: bool = True):
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS fsma")
        conn.exec_driver_sql(_SQLITE_DDL)
        if with_alerts:
            conn.exec_driver_sql(_SQLITE_ALERTS_DDL)
    return eng


@pytest.fixture()
def engine():
    eng = _new_engine()
    yield eng
    eng.dispose()


@pytest.fixture()
def engine_without_alerts():
    """No fsma.compliance_alerts at all — exercises the #2931 fail-closed path
    (posture read raises, snapshot must record NOT CAPTURED, never COMPLIANT)."""
    eng = _new_engine(with_alerts=False)
    yield eng
    eng.dispose()


def _seed_alerts(engine, tenant_id: str, severities: list[str], resolved: bool = False) -> None:
    with engine.begin() as conn:
        for index, severity in enumerate(severities):
            conn.exec_driver_sql(
                "INSERT INTO fsma.compliance_alerts "
                "(id, org_id, tenant_id, alert_type, severity, title, resolved, created_at) "
                "VALUES (?, ?, ?, 'missing_kde', ?, 'Alert', ?, ?)",
                (
                    str(uuid4()),
                    tenant_id,
                    tenant_id,
                    severity,
                    1 if resolved else 0,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


def _legacy_v1_hash(
    tenant_id: str,
    snapshot_name: str,
    snapshot_reason,
    created_by: str,
    captured_at_iso: str,
) -> str:
    """Byte-for-byte reconstruction of the pre-#2966 five-field digest.

    Written out longhand rather than imported so the test pins the historical
    wire format independently of whatever the module does today.
    """
    payload = {"tenant_id": tenant_id, "snapshot_name": snapshot_name}
    if snapshot_reason is not None:
        payload["snapshot_reason"] = snapshot_reason
    payload["created_by"] = created_by
    payload["captured_at"] = captured_at_iso
    canonical = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _insert_legacy_v1_snapshot(engine, tenant_id: str, name: str = "Legacy Freeze") -> tuple[str, str, str]:
    """Insert a row exactly as pre-#2966 ``create_snapshot`` would have: seven
    columns written, evidentiary columns left to their DDL defaults, v1 hash."""
    sid = str(uuid4())
    captured = datetime.now(timezone.utc).isoformat()
    reason = "FDA audit prep"
    digest = _legacy_v1_hash(tenant_id, name, reason, "chris@regengine.co", captured)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO fsma.compliance_evidence_snapshots "
            "(id, tenant_id, snapshot_name, snapshot_reason, created_by, content_hash, captured_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, tenant_id, name, reason, "chris@regengine.co", digest, captured),
        )
    return sid, digest, captured


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
    # #2966: the attestation is inside the seal, so recording it re-seals the
    # row. (Before #2966 this assertion read ``==``: the attestation was
    # written with no hash recomputation, which is exactly what made a
    # directly-written attestation indistinguishable from a real one.)
    assert body["content_hash"] != snapshot["content_hash"]
    assert body["integrity_verified"] is True
    assert body["hash_version"] == 2

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
    # #2964: refreeze appends a NEW evidence row rather than rewriting the
    # attested one, and the new row carries no inherited attestation.
    assert body["id"] != sid
    assert body["supersedes_snapshot_id"] == sid
    assert body["is_attested"] is False
    assert body["attested_by"] is None
    assert body["attested_at"] is None
    assert body["attestation_title"] is None

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


@pytest.fixture()
def authenticated_client(engine, monkeypatch):
    """Exercise real authentication and tenant resolution with local test keys.

    Only the key storage adapter is local/in-memory; neither FastAPI security
    dependency is overridden. PostgreSQL key storage and RLS have separate gates.
    """
    import shared.auth as auth

    store = APIKeyStore()
    monkeypatch.setattr(auth, "get_key_store", lambda: store)
    monkeypatch.delenv("AUTH_TEST_BYPASS_TOKEN", raising=False)
    client = _make_client(engine, TENANT_A)
    del client.app.dependency_overrides[require_api_key]
    with client:
        yield client, store


@pytest.mark.parametrize("credential_state", ["invalid", "expired", "revoked"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_real_auth_rejects_unusable_keys(authenticated_client, credential_state, method):
    client, store = authenticated_client
    key, metadata = store.create_key(
        "Boundary test",
        tenant_id=TENANT_A,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1) if credential_state == "expired" else None,
    )
    if credential_state == "invalid":
        key = "invalid-caller-key"
    elif credential_state == "revoked":
        store.revoke_key(metadata.key_id)

    response = client.request(
        method,
        f"/v1/compliance/snapshots/{TENANT_A}",
        headers={"X-RegEngine-API-Key": key, "X-Tenant-ID": TENANT_A},
        json={"snapshot_name": "Unauthorized freeze", "created_by": "boundary-test"} if method == "POST" else None,
    )
    assert response.status_code == 401


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_real_auth_rejects_key_path_tenant_mismatch(authenticated_client, method):
    client, store = authenticated_client
    key, _ = store.create_key("Tenant A", tenant_id=TENANT_A)
    response = client.request(
        method,
        f"/v1/compliance/snapshots/{TENANT_B}",
        headers={"X-RegEngine-API-Key": key, "X-Tenant-ID": TENANT_B},
        json={"snapshot_name": "Wrong tenant freeze", "created_by": "boundary-test"} if method == "POST" else None,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "E_TENANT_MISMATCH"


def test_real_auth_preserves_two_tenant_snapshot_isolation(authenticated_client):
    client, store = authenticated_client
    key_a, _ = store.create_key("Tenant A", tenant_id=TENANT_A)
    key_b, _ = store.create_key("Tenant B", tenant_id=TENANT_B)
    created = client.post(
        f"/v1/compliance/snapshots/{TENANT_A}",
        headers={"X-RegEngine-API-Key": key_a},
        json={"snapshot_name": "Tenant A freeze", "created_by": "boundary-test"},
    )
    assert created.status_code == 201
    own = client.get(f"/v1/compliance/snapshots/{TENANT_A}", headers={"X-RegEngine-API-Key": key_a})
    assert own.status_code == 200
    assert [item["id"] for item in own.json()["items"]] == [created.json()["id"]]
    other = client.get(f"/v1/compliance/snapshots/{TENANT_B}", headers={"X-RegEngine-API-Key": key_b})
    assert other.status_code == 200
    assert other.json()["items"] == []


# ---------------------------------------------------------------------------
# #2931 — the freeze must record the tenant's real posture, never a DDL default
# ---------------------------------------------------------------------------


def test_freeze_captures_live_alert_posture(engine) -> None:
    """A tenant sitting on open critical alerts must not freeze as COMPLIANT/0."""
    _seed_alerts(engine, TENANT_A, ["critical", "critical", "warning"])
    # Resolved alerts are history, not posture — they must not be counted.
    _seed_alerts(engine, TENANT_A, ["critical"], resolved=True)
    # Another tenant's alerts must never leak into this tenant's freeze.
    _seed_alerts(engine, TENANT_B, ["critical", "critical", "critical"])

    client = _make_client(engine, TENANT_A)
    created = _create(client, TENANT_A)

    assert created["active_alert_count"] == 3
    assert created["critical_alert_count"] == 2
    assert created["compliance_status"] == "NON_COMPLIANT"
    assert created["compliance_status_emoji"] == "🚨"
    assert created["posture_captured"] is True
    assert created["integrity_verified"] is True


def test_freeze_ignores_tenantless_alerts(engine) -> None:
    """Tenantless rows (tenant_id NULL) must not inflate any tenant's freeze.

    Regression test for the null-tenant fallback in _capture_posture: rows
    whose tenant_id was never backfilled but whose org_id matches the tenant
    used to be counted into every tenant under that org.
    """
    with engine.begin() as conn:
        for severity in ("critical", "critical", "warning"):
            conn.exec_driver_sql(
                "INSERT INTO fsma.compliance_alerts "
                "(id, org_id, tenant_id, alert_type, severity, title, resolved, created_at) "
                "VALUES (?, ?, NULL, 'missing_kde', ?, 'Alert', 0, ?)",
                (
                    str(uuid4()),
                    TENANT_A,
                    severity,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    _seed_alerts(engine, TENANT_A, ["warning"])

    client = _make_client(engine, TENANT_A)
    created = _create(client, TENANT_A)

    assert created["active_alert_count"] == 1
    assert created["critical_alert_count"] == 0
    assert created["compliance_status"] == "AT_RISK"


def test_freeze_with_only_warnings_is_at_risk(engine) -> None:
    _seed_alerts(engine, TENANT_A, ["warning", "warning"])
    client = _make_client(engine, TENANT_A)
    created = _create(client, TENANT_A)
    assert created["active_alert_count"] == 2
    assert created["critical_alert_count"] == 0
    assert created["compliance_status"] == "AT_RISK"


def test_clean_tenant_freezes_as_measured_compliant(engine) -> None:
    """COMPLIANT is still reachable — but only when it was actually measured."""
    client = _make_client(engine, TENANT_A)
    created = _create(client, TENANT_A)
    assert created["compliance_status"] == "COMPLIANT"
    assert created["active_alert_count"] == 0
    assert created["critical_alert_count"] == 0
    assert created["posture_captured"] is True


def test_audit_pack_and_fda_response_report_captured_posture(engine) -> None:
    _seed_alerts(engine, TENANT_A, ["critical", "warning", "warning"])
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]

    pack = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/audit-pack").text
    assert "Active Alerts: 3" in pack
    assert "Critical Alerts: 1" in pack
    assert "NON_COMPLIANT" in pack
    assert "Compliance Status: ✅ COMPLIANT" not in pack

    fda = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/fda-response").json()["text"]
    assert "Alerts recorded at capture: 3 active, 1 critical." in fda
    assert "Compliance Status: ✅ COMPLIANT" not in fda

    export = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/export").json()
    assert export["compliance_status"] == "NON_COMPLIANT"
    assert export["active_alert_count"] == 3
    assert export["critical_alert_count"] == 1
    assert export["posture_captured"] is True


def test_posture_read_failure_fails_closed(engine_without_alerts) -> None:
    """#2931 fail-closed: an unreadable posture source must render NOT CAPTURED,
    never the DDL default clean bill of health."""
    client = _make_client(engine_without_alerts, TENANT_A)
    created = _create(client, TENANT_A)

    assert created["posture_captured"] is False
    assert created["compliance_status"] == "NOT_CAPTURED"
    assert created["active_alert_count"] is None
    assert created["critical_alert_count"] is None
    assert created["degradation_reason"]
    # The freeze itself is still a valid, sealed record.
    assert created["integrity_verified"] is True

    sid = created["id"]
    pack = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/audit-pack").text
    assert "Compliance Status: NOT CAPTURED" in pack
    assert "Active Alerts: NOT CAPTURED" in pack
    assert "Critical Alerts: NOT CAPTURED" in pack
    assert "COMPLIANT" not in pack

    fda = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/fda-response").json()["text"]
    assert "Compliance Status: NOT CAPTURED" in fda
    assert "Alerts recorded at capture: NOT CAPTURED." in fda


# ---------------------------------------------------------------------------
# #2966 — the seal must cover what the audit pack prints next to it
# ---------------------------------------------------------------------------


def test_tampering_with_compliance_status_breaks_the_seal(engine) -> None:
    _seed_alerts(engine, TENANT_A, ["critical"])
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]

    with engine.begin() as conn:
        conn.exec_driver_sql(
            f"UPDATE fsma.compliance_evidence_snapshots SET compliance_status = 'COMPLIANT' WHERE id = '{sid}'"
        )

    verdict = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/verify").json()
    assert verdict["hash_match"] is False
    assert verdict["is_valid"] is False
    assert verdict["hash_version"] is None

    pack = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/audit-pack").text
    assert "Integrity Verified: No" in pack
    # A broken seal means the posture is untrustworthy: it must not be printed
    # as a captured fact.
    assert "Compliance Status: NOT CAPTURED" in pack


def test_tampering_with_alert_counts_breaks_the_seal(engine) -> None:
    _seed_alerts(engine, TENANT_A, ["critical", "critical"])
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]

    with engine.begin() as conn:
        conn.exec_driver_sql(
            f"UPDATE fsma.compliance_evidence_snapshots SET critical_alert_count = 0 WHERE id = '{sid}'"
        )

    verdict = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/verify").json()
    assert verdict["hash_match"] is False
    assert client.get(f"/v1/compliance/snapshots/{TENANT_A}").json()["items"][0]["integrity_verified"] is False


def test_tampering_with_attestation_breaks_the_seal(engine) -> None:
    """A directly-written attestation must be distinguishable from a real one."""
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]
    attested = client.post(
        f"/v1/compliance/snapshots/{TENANT_A}/{sid}/attest",
        json={"attested_by": "Chris Sellers", "attestation_title": "Compliance Owner"},
    )
    assert attested.status_code == 200
    assert attested.json()["integrity_verified"] is True

    with engine.begin() as conn:
        conn.exec_driver_sql(
            f"UPDATE fsma.compliance_evidence_snapshots SET attested_by = 'Mallory' WHERE id = '{sid}'"
        )

    verdict = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/verify").json()
    assert verdict["hash_match"] is False
    assert verdict["hash_version"] is None


def test_forged_attestation_flag_breaks_the_seal(engine) -> None:
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]

    with engine.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE fsma.compliance_evidence_snapshots "
            "SET is_attested = 1, attested_by = 'Mallory', attestation_title = 'CCO', "
            f"attested_at = '{datetime.now(timezone.utc).isoformat()}' WHERE id = '{sid}'"
        )

    verdict = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/verify").json()
    assert verdict["hash_match"] is False

    fda = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/fda-response").json()["text"]
    assert "Integrity Verified: No" in fda


def test_audit_pack_scopes_the_integrity_claim(engine) -> None:
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]
    pack = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/audit-pack").text
    line = next(ln for ln in pack.splitlines() if ln.startswith("Integrity Verified:"))
    # The flag must say what it covers, not sit unqualified above the posture.
    assert "seal v2" in line
    assert "posture" in line.lower()
    assert "attestation" in line.lower()


# ---------------------------------------------------------------------------
# #2966 — historical rows sealed under the v1 format must keep verifying
# ---------------------------------------------------------------------------


def test_legacy_v1_row_still_verifies_under_v1(engine) -> None:
    sid, digest, captured = _insert_legacy_v1_snapshot(engine, TENANT_A)
    client = _make_client(engine, TENANT_A)

    verdict = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/verify").json()
    assert verdict["hash_match"] is True
    assert verdict["is_valid"] is True
    assert verdict["stored_hash"] == digest
    assert verdict["hash_version"] == 1

    item = client.get(f"/v1/compliance/snapshots/{TENANT_A}").json()["items"][0]
    assert item["integrity_verified"] is True
    assert item["hash_version"] == 1
    # v1 sealed identity only, so the posture columns on this row are DDL
    # defaults that were never measured — they must not read as captured facts.
    assert item["posture_captured"] is False
    assert item["compliance_status"] == "NOT_CAPTURED"
    assert item["active_alert_count"] is None


def test_legacy_v1_row_tampering_is_still_detected(engine) -> None:
    sid, _digest, _captured = _insert_legacy_v1_snapshot(engine, TENANT_A)
    client = _make_client(engine, TENANT_A)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            f"UPDATE fsma.compliance_evidence_snapshots SET snapshot_name = 'tampered' WHERE id = '{sid}'"
        )
    verdict = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/verify").json()
    assert verdict["hash_match"] is False
    assert verdict["hash_version"] is None


def test_legacy_v1_audit_pack_does_not_claim_posture_coverage(engine) -> None:
    sid, _digest, _captured = _insert_legacy_v1_snapshot(engine, TENANT_A)
    client = _make_client(engine, TENANT_A)
    pack = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/audit-pack").text
    line = next(ln for ln in pack.splitlines() if ln.startswith("Integrity Verified:"))
    assert "seal v1" in line
    assert "Compliance Status: NOT CAPTURED" in pack
    assert "Active Alerts: NOT CAPTURED" in pack


def test_attesting_a_legacy_row_does_not_seal_an_unmeasured_posture(engine) -> None:
    """Re-sealing a v1 row must not promote its DDL-default posture into a
    hash-covered 'captured' fact."""
    sid, _digest, _captured = _insert_legacy_v1_snapshot(engine, TENANT_A)
    client = _make_client(engine, TENANT_A)

    attested = client.post(
        f"/v1/compliance/snapshots/{TENANT_A}/{sid}/attest",
        json={"attested_by": "Chris Sellers", "attestation_title": "Compliance Owner"},
    ).json()

    assert attested["is_attested"] is True
    assert attested["hash_version"] == 2
    assert attested["integrity_verified"] is True
    assert attested["posture_captured"] is False
    assert attested["compliance_status"] == "NOT_CAPTURED"


# ---------------------------------------------------------------------------
# #2964 — refreeze is append-only; attestation never survives onto new content
# ---------------------------------------------------------------------------


def test_refreeze_appends_and_preserves_the_original_freeze(engine) -> None:
    client = _make_client(engine, TENANT_A)
    original = _create(client, TENANT_A)
    sid = original["id"]
    client.post(
        f"/v1/compliance/snapshots/{TENANT_A}/{sid}/attest",
        json={"attested_by": "Chris Sellers", "attestation_title": "Compliance Owner"},
    )
    attested = client.get(f"/v1/compliance/snapshots/{TENANT_A}").json()["items"][0]
    attested_hash = attested["content_hash"]

    _seed_alerts(engine, TENANT_A, ["critical"])
    refrozen = client.post(
        f"/v1/compliance/snapshots/{TENANT_A}/{sid}/refreeze",
        json={"created_by": "ops@regengine.co"},
    ).json()

    # A new evidence row, unattested, carrying the freshly measured posture.
    assert refrozen["id"] != sid
    assert refrozen["is_attested"] is False
    assert refrozen["attested_at"] is None
    assert refrozen["critical_alert_count"] == 1
    assert refrozen["compliance_status"] == "NON_COMPLIANT"
    assert refrozen["snapshot_state"] == "VALID"

    # The original freeze survives intact: same hash, same capture time, its
    # attestation still attached to the content that was actually attested.
    items = {item["id"]: item for item in client.get(f"/v1/compliance/snapshots/{TENANT_A}").json()["items"]}
    assert len(items) == 2
    prior = items[sid]
    assert prior["content_hash"] == attested_hash
    assert prior["captured_at"] == attested["captured_at"]
    assert prior["is_attested"] is True
    assert prior["attested_by"] == "Chris Sellers"
    assert prior["integrity_verified"] is True
    assert prior["snapshot_state"] == "SUPERSEDED"
    assert refrozen["id"] in (prior["degradation_reason"] or "")


def test_no_response_backdates_an_attestation(engine) -> None:
    """#2964 acceptance: nothing may surface attested_at earlier than captured_at."""
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]
    client.post(
        f"/v1/compliance/snapshots/{TENANT_A}/{sid}/attest",
        json={"attested_by": "Chris Sellers", "attestation_title": "Compliance Owner"},
    )
    client.post(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/refreeze", json={})

    for item in client.get(f"/v1/compliance/snapshots/{TENANT_A}").json()["items"]:
        assert item["attestation_precedes_capture"] is False
        if item["attested_at"] is not None:
            assert item["attested_at"] >= item["captured_at"]
        export = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{item['id']}/export").json()
        assert export["attestation_precedes_capture"] is False


def test_serializer_flags_a_backdated_attestation(engine) -> None:
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]
    backdated = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE fsma.compliance_evidence_snapshots "
            f"SET is_attested = 1, attested_by = 'Mallory', attested_at = '{backdated}' WHERE id = '{sid}'"
        )
    item = client.get(f"/v1/compliance/snapshots/{TENANT_A}").json()["items"][0]
    assert item["attestation_precedes_capture"] is True
    fda = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/fda-response").json()["text"]
    assert "Attested: Yes" not in fda


def test_refreeze_of_a_superseded_snapshot_is_rejected(engine) -> None:
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]
    first = client.post(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/refreeze", json={})
    assert first.status_code == 200
    again = client.post(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/refreeze", json={})
    assert again.status_code == 409


def test_attesting_a_tampered_snapshot_is_rejected(engine) -> None:
    """Attest re-seals the row, so signing a broken record would launder the
    tampered values into a valid seal."""
    client = _make_client(engine, TENANT_A)
    sid = _create(client, TENANT_A)["id"]
    with engine.begin() as conn:
        conn.exec_driver_sql(
            f"UPDATE fsma.compliance_evidence_snapshots SET snapshot_name = 'tampered' WHERE id = '{sid}'"
        )

    response = client.post(
        f"/v1/compliance/snapshots/{TENANT_A}/{sid}/attest",
        json={"attested_by": "Mallory", "attestation_title": "CCO"},
    )
    assert response.status_code == 409

    # The tamper is still visible — the seal was not rewritten.
    verdict = client.get(f"/v1/compliance/snapshots/{TENANT_A}/{sid}/verify").json()
    assert verdict["hash_match"] is False
    assert client.get(f"/v1/compliance/snapshots/{TENANT_A}").json()["items"][0]["is_attested"] is False
