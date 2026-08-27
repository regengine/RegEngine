"""Regression tests for #2892 — POST /api/v1/ingest/csv must not bypass response_model.

The handler declares ``response_model=IngestResponse`` but returns a raw
``JSONResponse``, so FastAPI's serialization is skipped entirely. Two
fields go out on the wire that the published OpenAPI schema never
mentions: ``kde_warnings`` and ``kde_warning_count`` — the only signal
telling an integrator which uploaded rows are missing required FSMA key
data elements. Generated SDKs drop them silently.

These tests pin (a) the schema advertising both fields, (b) the wire
shape staying additive, and (c) the declared model actually being
enforced instead of merely decorative.
"""

from __future__ import annotations

import csv as _csvmod
import io
from typing import Optional

import pytest
from app import csv_templates as ct
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.csv_templates import router
from app.webhook_compat import _verify_api_key
from app.webhook_models import EventResult, IngestResponse
from fastapi import FastAPI
from fastapi.testclient import TestClient

_HEADER = [
    "traceability_lot_code",
    "product_description",
    "quantity",
    "unit_of_measure",
    "harvest_date",
    "location_name",
    "reference_document",
]


def _build_app(principal_tenant: Optional[str] = "t1") -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        tenant_id=principal_tenant,
    )
    return app


def _csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    w = _csvmod.writer(buf)
    w.writerow(_HEADER)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


@pytest.fixture(autouse=True)
def _stub_ingest(monkeypatch):
    async def _fake(payload, **kwargs):
        return IngestResponse(
            accepted=len(payload.events),
            rejected=0,
            total=len(payload.events),
            events=[
                EventResult(
                    traceability_lot_code=e.traceability_lot_code,
                    cte_type=e.cte_type.value,
                    status="accepted",
                    event_id=f"evt-{i}",
                )
                for i, e in enumerate(payload.events)
            ],
        )

    monkeypatch.setattr(ct, "ingest_events", _fake)


def _post(client: TestClient, body: bytes):
    return client.post(
        "/api/v1/ingest/csv",
        files={"file": ("t.csv", body, "text/csv")},
        data={"cte_type": "harvesting"},
    )


# ---------------------------------------------------------------------------
# The published contract must describe what actually goes on the wire
# ---------------------------------------------------------------------------


def _csv_ingest_response_schema() -> dict:
    spec = _build_app().openapi()
    content = spec["paths"]["/api/v1/ingest/csv"]["post"]["responses"]["200"]["content"]
    ref = content["application/json"]["schema"]["$ref"]
    return spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]


class TestPublishedSchema:
    def test_schema_documents_kde_warnings(self):
        props = _csv_ingest_response_schema()["properties"]
        assert "kde_warnings" in props, (
            "kde_warnings is sent on the wire but missing from the OpenAPI schema — "
            "generated SDKs drop the only signal for incomplete FSMA key data elements"
        )
        assert "kde_warning_count" in props

    def test_schema_keeps_the_base_ingest_fields(self):
        props = _csv_ingest_response_schema()["properties"]
        for field in ("accepted", "rejected", "total", "events", "ingestion_timestamp"):
            assert field in props

    def test_new_fields_are_not_required_so_replayed_bodies_stay_valid(self):
        """Idempotency replays a 24h-cached body verbatim across a deploy.

        A pre-deploy body has no kde_warnings key. If the schema marked the
        new fields required, a strict generated client would reject its own
        replayed response. Defaults keep them out of ``required``.
        """
        schema = _csv_ingest_response_schema()
        required = set(schema.get("required", []))
        assert "kde_warnings" not in required
        assert "kde_warning_count" not in required


# ---------------------------------------------------------------------------
# Wire shape
# ---------------------------------------------------------------------------


class TestWireShape:
    def test_warnings_still_returned_when_present(self):
        # 'L0T1O23' trips the lot-code character-swap heuristic.
        rows = [["L0T1O23", "Kale", "10", "lbs", "2026-04-17", "Farm A", "REF"]]
        resp = _post(TestClient(_build_app()), _csv(rows))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["kde_warning_count"] == len(body["kde_warnings"])
        assert any("character swap" in w for w in body["kde_warnings"])

    def test_clean_upload_reports_zero_warnings_explicitly(self):
        resp = _post(TestClient(_build_app()), _csv([["TLC1", "Kale", "10", "lbs", "2026-04-17", "Farm A", "REF"]]))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # An integrator should be able to read the field unconditionally
        # rather than inferring "no warnings" from an absent key.
        assert body["kde_warnings"] == []
        assert body["kde_warning_count"] == 0

    def test_base_fields_unchanged(self):
        resp = _post(TestClient(_build_app()), _csv([["TLC1", "Kale", "10", "lbs", "2026-04-17", "Farm A", "REF"]]))
        body = resp.json()
        assert body["accepted"] == 1
        assert body["rejected"] == 0
        assert body["total"] == 1
        assert isinstance(body["ingestion_timestamp"], str)
        assert body["events"][0]["traceability_lot_code"] == "TLC1"


# ---------------------------------------------------------------------------
# The declared model must actually be enforced, not decorative
# ---------------------------------------------------------------------------


class TestResponseModelIsEnforced:
    def test_declared_response_model_carries_the_warning_fields(self):
        """``response_model`` is the single source of truth for the shape."""
        route = next(
            r for r in router.routes if str(getattr(r, "path", "")).endswith("/ingest/csv")
        )
        model = route.response_model
        assert model is not None
        assert "kde_warnings" in model.model_fields
        assert "kde_warning_count" in model.model_fields
        # Still a superset of the shared ingest response.
        for field in IngestResponse.model_fields:
            assert field in model.model_fields
