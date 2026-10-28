"""/ingest/csv retains the upload as an ingestion run (receipt).

Before this change the route created no fsma.ingestion_runs row and kept
neither the file nor its hash, so nothing tied an accepted event back to
the upload it came from.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# /ingest/csv retains the upload as an ingestion run
# ---------------------------------------------------------------------------


def test_csv_route_hands_ingest_events_a_receipt_for_the_whole_file(monkeypatch):
    import hashlib
    from typing import Optional

    from app import csv_templates as ct
    from app.authz import IngestionPrincipal, get_ingestion_principal
    from app.csv_templates import router
    from app.webhook_compat import _verify_api_key
    from app.webhook_models import EventResult, IngestResponse
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    captured: dict = {}

    async def _fake(payload, **kwargs):
        captured["kwargs"] = kwargs
        return IngestResponse(
            accepted=len(payload.events),
            rejected=0,
            total=len(payload.events),
            events=[
                EventResult(traceability_lot_code=e.traceability_lot_code, cte_type=e.cte_type.value, status="accepted")
                for e in payload.events
            ],
            ingestion_run_id="run-abc",
        )

    monkeypatch.setattr(ct, "ingest_events", _fake)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="key-42", scopes=["*"], tenant_id="t1"
    )
    csv_bytes = (
        "traceability_lot_code,product_description,quantity,unit_of_measure,harvest_date,location_name,reference_document\n"
        "TLC1,Kale,10,lbs,2026-04-17,Farm A,REF\n"
        ",Kale,10,lbs,2026-04-17,Farm A,REF\n"  # no lot code: parser rejects this row
    ).encode()
    resp = TestClient(app).post(
        "/api/v1/ingest/csv",
        files={"file": ("harvest.csv", csv_bytes, "text/csv")},
        data={"cte_type": "harvesting"},
    )
    assert resp.status_code == 200, resp.text
    receipt = captured["kwargs"]["source_file"]
    assert receipt.filename == "harvest.csv"
    assert receipt.raw_bytes == csv_bytes
    assert receipt.sha256 == hashlib.sha256(csv_bytes).hexdigest()
    assert receipt.content_type == "text/csv"
    assert receipt.initiated_by == "key-42"
    # Every data row is accounted for: one event plus one parse rejection.
    assert receipt.record_count == 2 and len(receipt.parse_errors) == 1
    body = resp.json()
    assert body["ingestion_run_id"] == "run-abc"
    assert body["rejected"] == 1 and body["accepted"] == 1


# These tests cover parsing and pipeline flow; location validity is covered by
# test_location_description_complete.py and test_webhook_models.py.
pytestmark = pytest.mark.usefixtures("location_complete_for_pipeline")
