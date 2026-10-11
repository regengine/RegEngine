"""QA5 DB-backed regressions: BOM intake, atomic single-use exchange,
fail-closed release ids, and explicit empty allowlists.

Runs against the migrated scratch Postgres via conftest.py's fixtures.
"""

from __future__ import annotations

import hashlib
import io
import uuid

import pytest
from app.remediation import tokens as tokens_mod
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from .conftest import requires_db, upload_fixture

pytestmark = requires_db

HEADER = (
    "cte_type,tlc,product,quantity,uom,receive_date,receiving_location,previous_source,tlc_source,reference_document"
)
VALID_ROW = (
    "receiving,VF-BOM-01,Romaine Hearts 24ct,10,cases,2026-07-13,"
    "Fresh Distributors DC 4,Valley Farms LLC,Valley Farms Packinghouse,BOL-01"
)


def _inline_upload(client, payload: bytes, name: str = "inline.csv"):
    return client.post(
        "/api/v1/remediation/manifests",
        files={"file": (name, io.BytesIO(payload), "text/csv")},
        data={"supplier_org": "Valley Farms LLC"},
    )


def test_bom_manifest_ingests_cleanly_and_preserves_bytes(client):
    """Excel-saved manifests (UTF-8 BOM) validate like plain UTF-8 uploads."""
    raw = ("\ufeff" + HEADER + "\n" + VALID_ROW + "\n").encode("utf-8")
    response = _inline_upload(client, raw, name="bom_manifest.csv")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_rows"] == 1
    assert body["passed"] == 1, body["records"]
    assert body["failed"] == 0
    assert body["records"][0]["blocking"] is False
    # Integrity still covers the untouched bytes: BOM included.
    assert body["source_sha256"] == hashlib.sha256(raw).hexdigest()
    run_id = body["ingestion_run_id"]
    original = client.get(f"/api/v1/remediation/manifests/{run_id}/original")
    assert original.status_code == 200
    assert original.content == raw


def test_exchange_is_atomic_against_stale_snapshot_replay(client, app_engine):
    """Two exchanges from one token snapshot mint one session, not two.

    Simulates two concurrent exchange requests that both read
    exchange_count=0: the second UPDATE must affect zero rows and fail
    closed instead of minting a second session.
    """
    body = upload_fixture(client, "05_missing_tlc_source.csv").json()
    blocked = next(r for r in body["records"] if r["blocking"])
    link = client.post(
        f"/api/v1/remediation/cases/{blocked['remediation_case_id']}/link",
        json={"supplier_email": "logistics@valleyfarms.example"},
    ).json()

    Session = sessionmaker(bind=app_engine)
    db = Session()
    try:
        snapshot = tokens_mod.resolve_active_token(db, link["token"])
        first = tokens_mod.exchange_for_session(db, snapshot)
        assert first["session_token"]
        with pytest.raises(HTTPException) as excinfo:
            tokens_mod.exchange_for_session(db, snapshot)
        assert excinfo.value.status_code == 400
        assert excinfo.value.detail == "Remediation link is not usable"
    finally:
        db.rollback()
        db.close()


def test_release_unknown_record_ids_fail_closed(client):
    """Record ids outside the manifest 404 instead of silently no-op-ing."""
    body = upload_fixture(client, "01_valid.csv").json()
    run_id = body["ingestion_run_id"]

    bogus = str(uuid.uuid4())
    response = client.post(f"/api/v1/remediation/manifests/{run_id}/release", json={"record_ids": [bogus]})
    assert response.status_code == 404
    assert bogus[:8] in response.json()["detail"]

    # A valid subset still releases exactly the requested rows.
    wanted = [body["records"][0]["record_id"]]
    response = client.post(f"/api/v1/remediation/manifests/{run_id}/release", json={"record_ids": wanted})
    assert response.status_code == 200, response.text
    result = response.json()
    assert [r["record_id"] for r in result["released"]] == wanted
    assert result["skipped"] == []


def test_create_link_empty_authorized_fields_rejected(client):
    """An explicit empty allowlist must not fall through to the full default."""
    body = upload_fixture(client, "05_missing_tlc_source.csv").json()
    blocked = next(r for r in body["records"] if r["blocking"])
    response = client.post(
        f"/api/v1/remediation/cases/{blocked['remediation_case_id']}/link",
        json={"authorized_fields": []},
    )
    assert response.status_code == 422
