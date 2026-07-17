"""Intake acceptance tests: preservation, provenance, deterministic validation.

Covers PRD acceptance criteria 1-5 and fixtures 1-8.
"""

from __future__ import annotations

import hashlib

from .conftest import DATA_DIR, requires_db, upload_fixture

pytestmark = requires_db


def _fixture_bytes(name: str) -> bytes:
    return (DATA_DIR / name).read_bytes()


def test_valid_manifest_all_rows_pass(client):
    response = upload_fixture(client, "01_valid.csv")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_rows"] == 3
    assert body["passed"] == 3
    assert body["failed"] == 0
    assert all(not r["blocking"] for r in body["records"])
    assert body["source_sha256"] == hashlib.sha256(_fixture_bytes("01_valid.csv")).hexdigest()


def test_original_bytes_roundtrip(client):
    raw = _fixture_bytes("01_valid.csv")
    body = upload_fixture(client, "01_valid.csv").json()
    run_id = body["ingestion_run_id"]
    response = client.get(f"/api/v1/remediation/manifests/{run_id}/original")
    assert response.status_code == 200
    assert response.content == raw  # byte-for-byte preservation (AC-10)
    assert response.headers["X-Source-SHA256"] == hashlib.sha256(raw).hexdigest()


def test_auto_normalization_recorded_never_invented(client):
    body = upload_fixture(client, "02_whitespace_dates.csv").json()
    assert body["failed"] == 0, body["records"]
    run_id = body["ingestion_run_id"]
    detail = client.get(f"/api/v1/remediation/manifests/{run_id}").json()
    row1 = detail["records"][0]
    prov = row1["field_provenance"]
    # Whitespace trim, US date format, and UoM alias were all applied and recorded.
    rules_applied = {p.get("rule") for p in prov.values() if isinstance(p, dict)}
    assert "trim_whitespace" in rules_applied
    assert "date_format" in rules_applied
    assert "uom_alias" in rules_applied
    # The normalized date is deterministic ISO (07/12/2026 -> 2026-07-12).
    assert prov["kdes.receive_date"]["value"].startswith("2026-07-12")
    # Verbatim source cell is retained alongside the normalized value.
    assert prov["kdes.receive_date"]["raw_value"] == "07/12/2026"


def test_missing_tlc_blocks_row_others_pass(client):
    body = upload_fixture(client, "04_missing_tlc.csv").json()
    assert body["passed"] == 1
    assert body["failed"] == 1
    blocked = next(r for r in body["records"] if r["blocking"])
    assert blocked["row_number"] == 2
    issue_ids = {f["issue_id"] for f in blocked["failures"]}
    assert any("traceability_lot_code" in i or "TLC" in i for i in issue_ids), issue_ids
    assert blocked["remediation_case_id"] is not None


def test_missing_tlc_source_demo_fixture(client):
    body = upload_fixture(client, "05_missing_tlc_source.csv").json()
    assert body["passed"] == 2
    assert body["failed"] == 1
    blocked = next(r for r in body["records"] if r["blocking"])
    assert blocked["row_number"] == 2
    why = " ".join(f["why_failed"] for f in blocked["failures"])
    assert "tlc_source_reference" in why
    # Human explanation + rule identity are attached (FR-3).
    for failure in blocked["failures"]:
        assert failure["rule_id"]
        assert failure["severity"]
        assert failure["why_failed"]
        assert failure["remediation_owner"] == "supplier"


def test_unknown_product_alias_blocks(client):
    body = upload_fixture(client, "06_unknown_product.csv").json()
    assert body["failed"] == 1
    failures = body["records"][0]["failures"]
    assert any(f["rule_id"] == "svc.unknown_product_alias" for f in failures)


def test_approved_alias_passes_and_recorded(client, approved_alias):
    body = upload_fixture(client, "03_approved_alias.csv").json()
    assert body["failed"] == 0, body["records"]
    run_id = body["ingestion_run_id"]
    detail = client.get(f"/api/v1/remediation/manifests/{run_id}").json()
    prov = detail["records"][0]["field_provenance"]
    assert prov["kdes.product_code"]["source"] == "approved_mapping"
    assert prov["kdes.product_code"]["entity_id"] == approved_alias


def test_invalid_quantity_blocks(client):
    body = upload_fixture(client, "07_invalid_quantity.csv").json()
    assert body["failed"] == 2
    for record in body["records"]:
        assert any(f["rule_id"] == "svc.invalid_quantity" for f in record["failures"])


def test_duplicate_rows_second_blocked(client):
    body = upload_fixture(client, "08_duplicate_rows.csv").json()
    assert body["passed"] == 1
    assert body["failed"] == 1
    blocked = next(r for r in body["records"] if r["blocking"])
    assert blocked["row_number"] == 2
    assert any(f["rule_id"] == "svc.duplicate_row" for f in blocked["failures"])


def test_validation_is_deterministic(client):
    first = upload_fixture(client, "05_missing_tlc_source.csv").json()
    second = upload_fixture(client, "05_missing_tlc_source.csv").json()
    strip = lambda recs: [{k: r[k] for k in ("row_number", "validation_status", "blocking")} for r in recs]
    assert strip(first["records"]) == strip(second["records"])
    assert first["ruleset_hash"] == second["ruleset_hash"]


def test_exception_case_created_and_visible(client):
    body = upload_fixture(client, "05_missing_tlc_source.csv").json()
    run_id = body["ingestion_run_id"]
    detail = client.get(f"/api/v1/remediation/manifests/{run_id}").json()
    blocked = next(r for r in detail["records"] if r["validation_status"] == "failed")
    assert blocked["remediation_case_id"]


def test_missing_dates_never_synthesized():
    """AC-5: absent factual data stays absent — no default timestamps."""
    from app.remediation.validation import build_event_from_row

    event, provenance, failures = build_event_from_row(
        {
            "cte_type": "receiving",
            "tlc": "VF-NO-DATE-1",
            "product": "Romaine Hearts 24ct",
            "quantity": "10",
            "uom": "cases",
        }
    )
    assert "timestamp" not in event
    assert "receive_date" not in event.get("kdes", {})
    assert not any(p.get("source") != "csv" and "date" in k for k, p in provenance.items())


def test_short_tlc_blocked_with_reason(client):
    import io as _io

    rows = (
        "cte_type,tlc,product,quantity,uom,receive_date,receiving_location,previous_source,tlc_source,reference_document\n"
        "receiving,AB,Romaine Hearts 24ct,10,cases,2026-07-13,Fresh Distributors DC 4,Valley Farms LLC,Valley Farms Packinghouse,BOL-STLC-1\n"
    ).encode()
    response = client.post(
        "/api/v1/remediation/manifests",
        files={"file": ("short_tlc.csv", _io.BytesIO(rows), "text/csv")},
        data={"supplier_org": "Valley Farms LLC"},
    )
    assert response.status_code == 200, response.text
    record = response.json()["records"][0]
    assert record["blocking"]
    assert any(f["rule_id"] == "svc.invalid_tlc" for f in record["failures"])


def test_manifest_list_and_case_enrichment(client):
    """FR-9 buyer view: list w/ data-hold indicator; per-record case status."""
    body = upload_fixture(client, "05_missing_tlc_source.csv").json()
    run_id = body["ingestion_run_id"]

    listing = client.get("/api/v1/remediation/manifests").json()["manifests"]
    entry = next(m for m in listing if m["ingestion_run_id"] == run_id)
    assert entry["blocked"] == 1
    assert entry["ready_to_release"] == 2
    assert entry["data_hold"] is True
    assert entry["original_filename"] == "05_missing_tlc_source.csv"

    detail = client.get(f"/api/v1/remediation/manifests/{run_id}").json()
    blocked = next(r for r in detail["records"] if r["validation_status"] == "failed")
    assert blocked["case"]["case_status"] == "supplier_action_required"
    assert blocked["case"]["due_at"]
    assert blocked["case"]["notified"] is False

    client.post(f"/api/v1/remediation/cases/{blocked['remediation_case_id']}/link", json={})
    detail2 = client.get(f"/api/v1/remediation/manifests/{run_id}").json()
    blocked2 = next(r for r in detail2["records"] if r["validation_status"] == "failed")
    assert blocked2["case"]["case_status"] == "awaiting_supplier"
    assert blocked2["case"]["notified"] is True
