"""Correction loop, append-only patches, release, evidence determinism.

Covers PRD fixtures 10-12 and acceptance criteria 9-12, 14-15.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from sqlalchemy import text

from .conftest import requires_db, upload_fixture

pytestmark = requires_db

ATTESTATION = {"text": "I attest this correction is accurate to the best of my knowledge.", "accepted": True}


def _correction_session(client, fixture: str = "05_missing_tlc_source.csv"):
    body = upload_fixture(client, fixture).json()
    blocked = next(r for r in body["records"] if r["blocking"])
    case_id = blocked["remediation_case_id"]
    link = client.post(
        f"/api/v1/remediation/cases/{case_id}/link",
        json={"supplier_email": "logistics@valleyfarms.example"},
    ).json()
    session = client.post("/api/v1/remediation/supplier/exchange", json={"token": link["token"]}).json()
    headers = {"Authorization": f"Bearer {session['session_token']}"}
    return body, blocked, case_id, headers


def _submit(client, headers, changes, reason="Correcting per packinghouse records"):
    return client.post(
        "/api/v1/remediation/supplier/session/corrections",
        headers=headers,
        json={
            "changes": changes,
            "actor_name": "Jordan Lee",
            "actor_role": "Logistics Coordinator",
            "reason": reason,
            "attestation": ATTESTATION,
        },
    )


def test_successful_correction_releases_record(client, admin_engine):
    """Fixture 10: correction -> revalidation -> release -> exception resolved."""
    body, blocked, case_id, headers = _correction_session(client)
    response = _submit(client, headers, {"kdes.tlc_source_reference": "Valley Farms Packinghouse"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "released"
    assert result["released_event_id"]

    with admin_engine.connect() as conn:
        case_status = conn.execute(
            text("SELECT status FROM fsma.remediation_cases WHERE id = CAST(:c AS uuid)"),
            {"c": case_id},
        ).scalar()
        assert case_status == "released"
        canonical = conn.execute(
            text(
                "SELECT event_id FROM fsma.traceability_events "
                "WHERE event_id = CAST(:e AS uuid) AND tenant_id = CAST(:t AS uuid)"
            ),
            {"e": result["released_event_id"], "t": client.tenant_a},
        ).fetchone()
        assert canonical, "released record must exist in the canonical store"
        exception_status = conn.execute(
            text(
                """
                SELECT e.status FROM fsma.exception_cases e
                JOIN fsma.remediation_cases r ON r.exception_case_id = e.case_id
                WHERE r.id = CAST(:c AS uuid)
                """
            ),
            {"c": case_id},
        ).scalar()
        assert exception_status == "resolved"

    # Buyer notification preview exists; nothing was sent.
    outbox = client.get("/api/v1/remediation/outbox").json()["notifications"]
    assert any("released" in n["subject"] for n in outbox)


def test_original_record_logically_unchanged_after_patch(client, admin_engine):
    """AC-10: the verbatim raw row survives corrections untouched."""
    body, blocked, case_id, headers = _correction_session(client)
    run_id = body["ingestion_run_id"]
    before = client.get(f"/api/v1/remediation/manifests/{run_id}").json()
    raw_before = next(r for r in before["records"] if r["record_id"] == _record_id(client, case_id))

    _submit(client, headers, {"kdes.tlc_source_reference": "Valley Farms Packinghouse"})

    with admin_engine.connect() as conn:
        raw_row = conn.execute(
            text("SELECT raw_row FROM fsma.manifest_records WHERE id = CAST(:r AS uuid)"),
            {"r": raw_before["record_id"]},
        ).scalar()
    assert raw_row["tlc_source"] == ""  # still empty in the preserved source


def _record_id(client, case_id: str) -> str:
    # Helper: the case knows its record.
    from sqlalchemy import create_engine

    from .conftest import SUPERUSER_DSN

    eng = create_engine(SUPERUSER_DSN)
    with eng.connect() as conn:
        rid = conn.execute(
            text("SELECT manifest_record_id FROM fsma.remediation_cases WHERE id = CAST(:c AS uuid)"),
            {"c": case_id},
        ).scalar()
    eng.dispose()
    return str(rid)


def test_failed_correction_stays_blocked_with_reason(client, admin_engine):
    """Fixture 11: a correction that still fails keeps the case blocked."""
    body, blocked, case_id, headers = _correction_session(client)
    response = _submit(client, headers, {"kdes.tlc_source_reference": "   "})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "still_blocked"
    assert result["failures"], "intelligible failure reasons must be returned"
    assert any("tlc_source_reference" in (f.get("why_failed") or "") for f in result["failures"])

    with admin_engine.connect() as conn:
        case_status = conn.execute(
            text("SELECT status FROM fsma.remediation_cases WHERE id = CAST(:c AS uuid)"),
            {"c": case_id},
        ).scalar()
        patch_count = conn.execute(
            text("SELECT COUNT(*) FROM fsma.correction_patches WHERE case_id = CAST(:c AS uuid)"),
            {"c": case_id},
        ).scalar()
    assert case_status == "buyer_review"
    assert patch_count == 1  # the failed attempt is still permanent history


def test_patches_append_only_and_hash_chained(client, admin_engine, app_engine):
    body, blocked, case_id, headers = _correction_session(client)
    _submit(client, headers, {"kdes.tlc_source_reference": "   "})  # failed attempt -> buyer_review

    # Buyer re-opens by issuing a fresh link; supplier corrects properly.
    link2 = client.post(f"/api/v1/remediation/cases/{case_id}/link", json={}).json()
    session2 = client.post("/api/v1/remediation/supplier/exchange", json={"token": link2["token"]}).json()
    headers2 = {"Authorization": f"Bearer {session2['session_token']}"}
    response = _submit(client, headers2, {"kdes.tlc_source_reference": "Valley Farms Packinghouse"})
    assert response.json()["status"] == "released"

    from app.remediation.corrections import load_patches, verify_patch_chain
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=admin_engine)
    db = Session()
    try:
        patches = load_patches(db, tenant_id=client.tenant_a, manifest_record_id=_record_id(client, case_id))
    finally:
        db.close()
    assert len(patches) == 2  # both attempts preserved, ordered
    assert patches[0]["patch_seq"] == 1 and patches[1]["patch_seq"] == 2
    assert patches[1]["prev_patch_hash"] == patches[0]["patch_hash"]
    assert verify_patch_chain(patches)

    # Append-only trigger blocks UPDATE/DELETE for the non-superuser app role.
    with app_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": client.tenant_a})
        with pytest.raises(Exception) as excinfo:
            conn.execute(
                text("UPDATE fsma.correction_patches SET correction_reason = 'tampered' WHERE id = CAST(:p AS uuid)"),
                {"p": patches[0]["id"]},
            )
        assert "append-only" in str(excinfo.value)


def test_granular_release_valid_rows_only(client, admin_engine):
    """Blocked row never reaches the canonical store; valid siblings do."""
    body = upload_fixture(client, "05_missing_tlc_source.csv").json()
    run_id = body["ingestion_run_id"]
    response = client.post(f"/api/v1/remediation/manifests/{run_id}/release", json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["released"]) == 2
    assert len(result["skipped"]) == 1

    with admin_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM fsma.traceability_events "
                "WHERE tenant_id = CAST(:t AS uuid) AND ingestion_run_id = CAST(:r AS uuid)"
            ),
            {"t": client.tenant_a, "r": run_id},
        ).scalar()
    assert count == 2


def test_evidence_bundle_generates_and_is_deterministic(client):
    """Fixture 12 + AC-14/15: repeat export -> identical record hashes."""
    body = upload_fixture(client, "01_valid.csv").json()
    run_id = body["ingestion_run_id"]
    client.post(f"/api/v1/remediation/manifests/{run_id}/release", json={})

    def _manifest():
        response = client.get(f"/api/v1/remediation/manifests/{run_id}/evidence")
        assert response.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(response.content))
        assert set(zf.namelist()) == {
            "original_manifest.csv",
            "accepted_records.csv",
            "manifest.json",
            "summary.txt",
            "README.txt",
        }
        return json.loads(zf.read("manifest.json")), response.content

    first, first_bytes = _manifest()
    second, second_bytes = _manifest()

    assert [r["record_hash"] for r in first["records"]] == [r["record_hash"] for r in second["records"]]
    assert first["bundle_content_hash"] == second["bundle_content_hash"]
    assert first["file_hashes"] == second["file_hashes"]
    # generated_at is intentionally outside the hashed content.
    assert first["generated_at"] != "" and "generated_at" not in json.dumps(first["file_hashes"])
    # The disclaimer must never overclaim.
    assert "post-ingest integrity" in first["integrity_note"]


def test_csv_formula_injection_neutralized_in_evidence(client):
    """A hostile cell value must be prefixed on export (CSV injection)."""
    import csv as csv_mod

    hostile = '=HYPERLINK("http://evil.example","x")'
    rows = [
        "cte_type,tlc,product,quantity,uom,receive_date,receiving_location,previous_source,tlc_source,reference_document",
        f'receiving,VF-INJ-01,Romaine Hearts 24ct,10,cases,2026-07-13,Fresh Distributors DC 4,Valley Farms LLC,"{hostile}",BOL-INJ-01',
    ]
    payload = ("\n".join(rows) + "\n").encode()
    response = client.post(
        "/api/v1/remediation/manifests",
        files={"file": ("inject.csv", io.BytesIO(payload), "text/csv")},
        data={"supplier_org": "Valley Farms LLC"},
    )
    run_id = response.json()["ingestion_run_id"]
    client.post(f"/api/v1/remediation/manifests/{run_id}/release", json={})
    bundle = client.get(f"/api/v1/remediation/manifests/{run_id}/evidence")
    zf = zipfile.ZipFile(io.BytesIO(bundle.content))
    accepted = zf.read("accepted_records.csv").decode()
    reader = csv_mod.reader(io.StringIO(accepted))
    header = next(reader)
    row = next(reader)
    cell = row[header.index("tlc_source_reference")]
    assert cell.startswith("'="), cell  # neutralized, original preserved after the quote


def test_metrics_track_supplier_resolution(client):
    body, blocked, case_id, headers = _correction_session(client)
    _submit(client, headers, {"kdes.tlc_source_reference": "Valley Farms Packinghouse"})
    metrics = client.get("/api/v1/remediation/metrics").json()
    assert metrics["supplier_corrections_submitted"] >= 1
    assert metrics["resolved_without_buyer_intervention"] >= 1
    assert metrics["resolved_without_buyer_intervention_rate"] > 0
