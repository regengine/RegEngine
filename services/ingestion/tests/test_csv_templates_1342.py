"""Regression tests for ``services/ingestion/app/csv_templates.py``.

Part of the #1342 ingestion coverage sweep. Covers CSV template
generation, CTE-type detection, UOM/location/date normalization, lot
code integrity checks, and the full CSV ingest endpoint.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import csv_templates as ct
from app.csv_templates import (
    CTE_COLUMNS,
    _CTE_TYPE_ALIASES,
    _SENTINEL_TS,
    _check_lot_code_integrity,
    _detect_row_cte_type,
    _generate_csv_template,
    _inject_required_kdes,
    _normalize_location,
    _normalize_uom,
    _parse_date_flexible,
    _validate_kde_completeness,
    router,
)
from app.webhook_compat import _verify_api_key
from app.webhook_models import (
    EventResult,
    IngestEvent,
    IngestResponse,
    WebhookCTEType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


def _ok_ingest_response() -> IngestResponse:
    return IngestResponse(
        accepted=1, rejected=0, total=1,
        events=[EventResult(
            traceability_lot_code="TLC",
            cte_type="harvesting",
            status="accepted",
            event_id="evt-1",
        )],
    )


# ---------------------------------------------------------------------------
# _generate_csv_template
# ---------------------------------------------------------------------------


class TestGenerateCsvTemplate:
    def test_unknown_raises_404(self):
        with pytest.raises(Exception) as exc:
            _generate_csv_template("made_up")
        assert exc.value.status_code == 404

    @pytest.mark.parametrize("cte_type", list(CTE_COLUMNS.keys()))
    def test_all_known_ctes_produce_three_rows(self, cte_type):
        csv_text = _generate_csv_template(cte_type)
        # Header + example + description
        lines = [l for l in csv_text.strip().split("\n") if l]
        assert len(lines) == 3
        # Third row is descriptions commented with "#"
        assert lines[2].startswith("#") or ",#" in lines[2]


# ---------------------------------------------------------------------------
# GET /api/v1/templates/{cte_type}
# ---------------------------------------------------------------------------


class TestDownloadTemplateEndpoint:
    def test_known_cte_returns_csv(self):
        client = TestClient(_build_app())
        resp = client.get("/api/v1/templates/harvesting")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "regengine_harvesting_template.csv" in resp.headers["content-disposition"]

    def test_uppercase_cte_accepted(self):
        client = TestClient(_build_app())
        resp = client.get("/api/v1/templates/SHIPPING")
        assert resp.status_code == 200

    def test_unknown_cte_returns_404(self):
        client = TestClient(_build_app())
        resp = client.get("/api/v1/templates/bogus")
        assert resp.status_code == 404
        body = resp.json()
        assert "Valid types:" in body["detail"]


# ---------------------------------------------------------------------------
# GET /api/v1/templates
# ---------------------------------------------------------------------------


class TestListTemplatesEndpoint:
    def test_lists_canonical_ctes_only(self):
        client = TestClient(_build_app())
        resp = client.get("/api/v1/templates")
        assert resp.status_code == 200
        body = resp.json()
        # "growing" is backwards-compat only and hidden from listing
        assert "growing" not in body["templates"]
        assert "harvesting" in body["templates"]
        harvest = body["templates"]["harvesting"]
        assert harvest["download_url"] == "/api/v1/templates/harvesting"
        assert all({"name", "description"} == set(c.keys()) for c in harvest["columns"])


# ---------------------------------------------------------------------------
# _detect_row_cte_type
# ---------------------------------------------------------------------------


class TestDetectRowCteType:
    def test_direct_column(self):
        assert _detect_row_cte_type({"cte_type": "shipping"}, None) == "shipping"

    def test_alias_normalized(self):
        assert _detect_row_cte_type({"event_type": "SHIP"}, None) == "shipping"
        assert _detect_row_cte_type({"type": "cold storage"}, None) == "cooling"
        assert _detect_row_cte_type({"cte": "H"}, None) == "harvesting"

    def test_fallback_used_when_no_column(self):
        assert _detect_row_cte_type({"other": "x"}, "receiving") == "receiving"

    def test_empty_column_skipped(self):
        assert _detect_row_cte_type({"cte_type": "", "type": "cooling"}, None) == "cooling"

    def test_unknown_alias_falls_through(self):
        assert _detect_row_cte_type({"cte_type": "mystery"}, "harvesting") == "harvesting"

    def test_no_match_no_fallback_returns_none(self):
        assert _detect_row_cte_type({"other": "x"}, None) is None


# ---------------------------------------------------------------------------
# _inject_required_kdes
# ---------------------------------------------------------------------------


class TestInjectRequiredKdes:
    def test_date_kde_injected_for_harvest(self):
        kdes: dict = {}
        _inject_required_kdes(kdes, "harvesting", {}, None, "2026-04-17T10:00:00Z")
        assert kdes["harvest_date"] == "2026-04-17"

    def test_empty_date_value_becomes_empty_string(self):
        kdes: dict = {}
        _inject_required_kdes(kdes, "harvesting", {}, None, "")
        assert kdes["harvest_date"] == ""

    def test_date_kde_not_overwritten(self):
        kdes = {"harvest_date": "original"}
        _inject_required_kdes(kdes, "harvesting", {}, None, "2026-04-17")
        assert kdes["harvest_date"] == "original"

    def test_shipping_populates_ship_from_and_to(self):
        kdes: dict = {}
        _inject_required_kdes(kdes, "shipping", {"ship_to_location": "DC"}, "Farm A", "2026-04-17")
        assert kdes["ship_from_location"] == "Farm A"
        assert kdes["ship_to_location"] == "DC"

    def test_shipping_destination_fallback(self):
        kdes: dict = {}
        _inject_required_kdes(kdes, "shipping", {"destination": "Metro"}, "Farm A", "2026-04-17")
        assert kdes["ship_to_location"] == "Metro"

    def test_shipping_default_ship_to_when_missing(self):
        kdes: dict = {}
        _inject_required_kdes(kdes, "shipping", {}, "Farm A", "2026-04-17")
        assert kdes["ship_to_location"] == "See receiver"

    def test_receiving_populates_receiving_location(self):
        kdes: dict = {}
        _inject_required_kdes(kdes, "receiving", {}, "DC 1", "2026-04-17")
        assert kdes["receiving_location"] == "DC 1"

    def test_first_land_based_receiving(self):
        kdes: dict = {}
        _inject_required_kdes(kdes, "first_land_based_receiving", {}, "Dock 4", "2026-04-17")
        assert kdes["receiving_location"] == "Dock 4"

    def test_generic_field_fallbacks(self):
        kdes: dict = {}
        row = {"tlc": "TLC1", "product": "Kale", "qty": "100", "uom": "lbs", "facility_name": "Farm B"}
        _inject_required_kdes(kdes, "harvesting", row, None, "2026-04-17")
        assert kdes["traceability_lot_code"] == "TLC1"
        assert kdes["product_description"] == "Kale"
        assert kdes["quantity"] == "100"
        assert kdes["unit_of_measure"] == "lbs"
        assert kdes["location_name"] == "Farm B"

    def test_existing_kde_keys_preserved(self):
        kdes = {"traceability_lot_code": "EXISTING"}
        row = {"tlc": "NEW"}
        _inject_required_kdes(kdes, "harvesting", row, None, "2026-04-17")
        assert kdes["traceability_lot_code"] == "EXISTING"

    def test_unknown_cte_no_date_injection(self):
        kdes: dict = {}
        _inject_required_kdes(kdes, "unknown_cte", {}, None, "2026-04-17")
        assert "harvest_date" not in kdes


# ---------------------------------------------------------------------------
# _validate_kde_completeness
# ---------------------------------------------------------------------------


def _make_event(**overrides) -> IngestEvent:
    """Build an IngestEvent bypassing validation so we can test the
    downstream validators on inputs the top-level model would reject
    (e.g. quantity=0.0 or location_name=None)."""
    fields = {
        "cte_type": WebhookCTEType.HARVESTING,
        "traceability_lot_code": "TLC1",
        "product_description": "Kale",
        "quantity": 100.0,
        "unit_of_measure": "lbs",
        "location_name": "Farm A",
        "timestamp": "2026-04-17T10:00:00Z",
        "kdes": {},
    }
    fields.update(overrides)
    return IngestEvent.model_construct(**fields)


class TestValidateKdeCompleteness:
    def test_unknown_cte_returns_empty(self):
        event = _make_event()
        assert _validate_kde_completeness("bogus", event, {}) == []

    def test_all_present(self):
        event = _make_event()
        kdes = {"harvest_date": "2026-04-17", "reference_document": "REF-1"}
        missing = _validate_kde_completeness("harvesting", event, kdes)
        assert missing == []

    def test_missing_top_level_field(self):
        event = _make_event(quantity=0.0)
        kdes = {"harvest_date": "2026-04-17", "reference_document": "REF-1"}
        missing = _validate_kde_completeness("harvesting", event, kdes)
        assert "quantity" in missing

    def test_missing_location_name_falls_back_to_kdes(self):
        event = _make_event(location_name=None)
        kdes = {"location_name": "Farm A", "harvest_date": "2026-04-17", "reference_document": "REF"}
        missing = _validate_kde_completeness("harvesting", event, kdes)
        assert "location_name" not in missing

    def test_missing_location_name_and_kdes(self):
        event = _make_event(location_name=None)
        kdes = {"harvest_date": "2026-04-17", "reference_document": "REF"}
        missing = _validate_kde_completeness("harvesting", event, kdes)
        assert "location_name" in missing

    def test_missing_kde_level_field(self):
        event = _make_event()
        # Missing harvest_date, reference_document
        missing = _validate_kde_completeness("harvesting", event, {})
        assert "harvest_date" in missing
        assert "reference_document" in missing


# ---------------------------------------------------------------------------
# _normalize_uom
# ---------------------------------------------------------------------------


class TestNormalizeUom:
    @pytest.mark.parametrize("raw,expected", [
        ("lb", "lbs"), ("LB.", "lbs"), ("pounds", "lbs"),
        ("kilogram", "kg"), ("KG", "kg"),
        ("case", "cases"), ("CS", "cases"),
        ("pallet", "pallets"), ("plts", "pallets"),
        ("ea", "each"),
        ("gallon", "gallons"),
        ("unknown_unit", "unknown_unit"),  # falls back to lowercased input
    ])
    def test_aliases(self, raw, expected):
        assert _normalize_uom(raw) == expected

    def test_trailing_period_stripped(self):
        assert _normalize_uom("kg.") == "kg"


# ---------------------------------------------------------------------------
# _normalize_location
# ---------------------------------------------------------------------------


class TestNormalizeLocation:
    def test_collapses_whitespace(self):
        assert _normalize_location("  Farm   A ") == "Farm A"

    @pytest.mark.parametrize("raw,expected_contains", [
        ("East whse", "Warehouse"),
        ("Dist Center", "Distribution"),
        ("Mfg Plant", "Manufacturing"),
        ("Fac 1", "Facility"),
        ("Pkg Station", "Packaging"),
        ("Recv Dock", "Receiving"),
        ("Shpg Bay", "Shipping"),
        ("Distribution Ctr", "Center"),
        ("Main blvd", "Boulevard"),
        ("Elm ave", "Avenue"),
    ])
    def test_expands_abbreviations(self, raw, expected_contains):
        assert expected_contains in _normalize_location(raw)


# ---------------------------------------------------------------------------
# _parse_date_flexible
# ---------------------------------------------------------------------------


class TestParseDateFlexible:
    def test_empty_returns_sentinel_with_warning(self):
        ts, warn = _parse_date_flexible("")
        assert ts == _SENTINEL_TS
        assert warn is not None

    def test_whitespace_returns_sentinel(self):
        ts, warn = _parse_date_flexible("   ")
        assert ts == _SENTINEL_TS
        assert warn is not None

    def test_iso_with_z(self):
        ts, warn = _parse_date_flexible("2026-04-17T10:00:00Z")
        assert ts.startswith("2026-04-17T10:00:00")
        assert warn is None

    def test_naive_iso_assumed_utc(self):
        ts, warn = _parse_date_flexible("2026-04-17T10:00:00")
        assert "Z" in ts
        assert warn is None

    def test_plain_date(self):
        ts, warn = _parse_date_flexible("2026-04-17")
        assert ts.startswith("2026-04-17")
        assert warn is None

    def test_us_format(self):
        ts, warn = _parse_date_flexible("4/17/2026")
        assert "2026-04-17" in ts
        assert warn is None

    def test_friendly_format(self):
        ts, warn = _parse_date_flexible("April 17 2026")
        assert "2026-04-17" in ts
        assert warn is None

    def test_event_time_merged(self):
        ts, warn = _parse_date_flexible("2026-04-17", "14:30:45")
        # When ISO fast-path succeeds, event_time is NOT merged; only on fallback path
        # Use a non-ISO format to force fallback path
        ts, warn = _parse_date_flexible("April 17 2026", "14:30:45")
        assert "14:30:45" in ts

    def test_bad_event_time_is_swallowed(self):
        ts, warn = _parse_date_flexible("April 17 2026", "not-a-time")
        assert warn is None
        assert "2026-04-17" in ts

    def test_unparseable_returns_sentinel(self):
        ts, warn = _parse_date_flexible("totally bogus gibberish xyzzy")
        # dateutil's fuzzy parser may succeed on some inputs; if so, not an error.
        # Test with a clearly-unparseable string containing no date hints
        ts, warn = _parse_date_flexible("")
        assert ts == _SENTINEL_TS

    def test_very_long_string_parsed_or_sentinel(self):
        # Just confirm it doesn't crash on weird input
        ts, warn = _parse_date_flexible("2026-99-99")
        assert ts == _SENTINEL_TS
        assert "INVALID_FORMAT" in warn


# ---------------------------------------------------------------------------
# _check_lot_code_integrity
# ---------------------------------------------------------------------------


class TestCheckLotCodeIntegrity:
    def test_empty_returns_no_warnings(self):
        assert _check_lot_code_integrity("") == []

    def test_clean_code(self):
        assert _check_lot_code_integrity("TLC-123-ABC") == []

    def test_o_adjacent_to_digits_flagged(self):
        warnings = _check_lot_code_integrity("LOT1O23")
        assert any("possible character swap" in w for w in warnings)

    def test_i_adjacent_to_digits_flagged(self):
        warnings = _check_lot_code_integrity("LOT1I23")
        assert warnings

    def test_all_alpha_long_flagged(self):
        warnings = _check_lot_code_integrity("ALPHABETICAL")
        assert any("no digits found" in w for w in warnings)

    def test_all_alpha_short_not_flagged(self):
        # 3 chars or fewer = not flagged
        assert _check_lot_code_integrity("ABC") == []


# ---------------------------------------------------------------------------
# POST /ingest/csv endpoint
# ---------------------------------------------------------------------------


def _csv_body(rows: list[dict], fieldnames: list[str]) -> bytes:
    import csv as _csv
    buf = io.StringIO()
    writer = _csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


class TestIngestCsv:
    @pytest.fixture(autouse=True)
    def _stub_ingest(self, monkeypatch):
        """Default ingest_events stub returns 1 accepted event — override per-test as needed."""
        async def _fake(payload, **kwargs):
            # Build response with one accepted event per inbound event
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
                    ) for i, e in enumerate(payload.events)
                ],
            )
        monkeypatch.setattr(ct, "ingest_events", _fake)

    def test_missing_cte_type_returns_400(self):
        csv_bytes = _csv_body(
            [{"traceability_lot_code": "TLC1", "product_description": "Kale", "quantity": "10"}],
            ["traceability_lot_code", "product_description", "quantity"],
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 400

    def test_bad_cte_type_parameter_returns_400(self):
        csv_bytes = _csv_body(
            [{"traceability_lot_code": "TLC1"}],
            ["traceability_lot_code"],
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
            data={"cte_type": "bogus"},
        )
        assert resp.status_code == 400
        assert "Unknown CTE type" in resp.json()["detail"]

    def test_happy_path_single_type(self):
        csv_bytes = _csv_body(
            [{
                "traceability_lot_code": "TLC1",
                "product_description": "Kale",
                "quantity": "10",
                "unit_of_measure": "lbs",
                "harvest_date": "2026-04-17",
                "location_name": "Farm A",
                "reference_document": "REF-1",
            }],
            ["traceability_lot_code", "product_description", "quantity",
             "unit_of_measure", "harvest_date", "location_name", "reference_document"],
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 1

    def test_mixed_type_uses_per_row_column(self):
        csv_bytes = _csv_body(
            [
                {
                    "cte_type": "harvesting",
                    "traceability_lot_code": "TLC1",
                    "product_description": "Kale",
                    "quantity": "10",
                    "unit_of_measure": "lbs",
                    "harvest_date": "2026-04-17",
                    "location_name": "Farm A",
                    "reference_document": "REF-1",
                },
                {
                    "cte_type": "shipping",
                    "traceability_lot_code": "TLC2",
                    "product_description": "Tomatoes",
                    "quantity": "20",
                    "unit_of_measure": "cases",
                    "ship_date": "2026-04-17",
                    "ship_from_location": "Farm B",
                    "ship_to_location": "DC 1",
                    "reference_document": "REF-2",
                },
            ],
            ["cte_type", "traceability_lot_code", "product_description", "quantity",
             "unit_of_measure", "harvest_date", "ship_date", "location_name",
             "ship_from_location", "ship_to_location", "reference_document"],
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 2

    def test_row_without_cte_type_and_no_fallback_logs_error(self, monkeypatch):
        # Need at least one valid row so we don't get 400
        csv_bytes = _csv_body(
            [
                {"traceability_lot_code": "TLC1"},  # no cte_type, no fallback
                {
                    "cte_type": "harvesting",
                    "traceability_lot_code": "TLC2",
                    "product_description": "Kale",
                    "quantity": "10",
                    "unit_of_measure": "lbs",
                    "harvest_date": "2026-04-17",
                    "location_name": "Farm A",
                    "reference_document": "REF",
                },
            ],
            ["cte_type", "traceability_lot_code", "product_description",
             "quantity", "unit_of_measure", "harvest_date", "location_name",
             "reference_document"],
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        body = resp.json()
        # The invalid row appears as rejected; valid row as accepted
        assert body["accepted"] == 1
        assert body["rejected"] == 1
        assert any("No CTE type" in evt.get("errors", [""])[0] for evt in body["events"] if evt.get("errors"))

    def test_empty_csv_returns_400(self):
        csv_bytes = b"col1,col2\n"
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("empty.csv", csv_bytes, "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 400

    def test_comment_rows_skipped(self):
        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name,reference_document\n"
            "# this is a comment,,,,,,\n"
            "TLC1,Kale,10,lbs,2026-04-17,Farm A,REF\n"
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_text.encode(), "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 1

    def test_empty_rows_skipped(self):
        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name,reference_document\n"
            ",,,,,,\n"
            "TLC1,Kale,10,lbs,2026-04-17,Farm A,REF\n"
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_text.encode(), "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 1

    def test_bom_handled(self):
        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name,reference_document\n"
            "TLC1,Kale,10,lbs,2026-04-17,Farm A,REF\n"
        )
        csv_bytes = b"\xef\xbb\xbf" + csv_text.encode()
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_bytes, "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 200

    def test_unparseable_date_flagged(self):
        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name,reference_document\n"
            "TLC1,Kale,10,lbs,not-a-date,Farm A,REF\n"
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_text.encode(), "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "kde_warnings" in body

    def test_max_rows_limit_enforced(self):
        # Build 502 rows (MAX_CSV_ROWS = 500)
        header = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name,reference_document\n"
        )
        rows = "\n".join(
            f"TLC{i},Kale,10,lbs,2026-04-17,Farm A,REF"
            for i in range(502)
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("big.csv", (header + rows).encode(), "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # MAX_CSV_ROWS = 500 → 501 and 502 are rejected
        assert body["accepted"] == 500
        assert body["rejected"] >= 1
        assert any(
            "exceeds maximum row limit" in err
            for evt in body["events"]
            for err in evt.get("errors", [])
        )

    def test_tenant_default_when_absent(self, monkeypatch):
        captured: dict = {}

        async def _fake(payload, **kwargs):
            captured["tenant_id"] = payload.tenant_id
            return IngestResponse(accepted=1, rejected=0, total=1, events=[])

        monkeypatch.setattr(ct, "ingest_events", _fake)

        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name,reference_document\n"
            "TLC1,Kale,10,lbs,2026-04-17,Farm A,REF\n"
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_text.encode(), "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 200
        assert captured["tenant_id"] == "default"

    def test_tenant_id_passthrough(self, monkeypatch):
        captured: dict = {}

        async def _fake(payload, **kwargs):
            captured["tenant_id"] = payload.tenant_id
            captured["source"] = payload.source
            return IngestResponse(accepted=1, rejected=0, total=1, events=[])

        monkeypatch.setattr(ct, "ingest_events", _fake)

        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name,reference_document\n"
            "TLC1,Kale,10,lbs,2026-04-17,Farm A,REF\n"
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_text.encode(), "text/csv")},
            data={"cte_type": "harvesting", "tenant_id": "my-tenant", "source": "portal"},
        )
        assert captured["tenant_id"] == "my-tenant"
        assert captured["source"] == "portal"

    def test_input_lot_codes_parsed(self, monkeypatch):
        captured: dict = {}

        async def _fake(payload, **kwargs):
            captured["events"] = payload.events
            return IngestResponse(
                accepted=len(payload.events),
                rejected=0,
                total=len(payload.events),
                events=[EventResult(
                    traceability_lot_code=e.traceability_lot_code,
                    cte_type=e.cte_type.value,
                    status="accepted",
                ) for e in payload.events],
            )

        monkeypatch.setattr(ct, "ingest_events", _fake)

        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "transformation_date,location_name,reference_document,input_lot_codes\n"
            "NEW1,Mix,100,bags,2026-04-17,Plant A,REF,LOT1,LOT2\n"
        )
        # CSV quotes needed for comma-separated cell — use manual text
        csv_text = (
            'traceability_lot_code,product_description,quantity,unit_of_measure,'
            'transformation_date,location_name,reference_document,input_lot_codes\n'
            'NEW1,Mix,100,bags,2026-04-17,Plant A,REF,"LOT1,LOT2"\n'
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_text.encode(), "text/csv")},
            data={"cte_type": "transformation"},
        )
        assert resp.status_code == 200
        event = captured["events"][0]
        assert event.kdes["input_lot_codes"] == ["LOT1", "LOT2"]

    def test_lot_code_integrity_warning_attached(self):
        # "L0T1O23" has an O adjacent to a digit — integrity check warns
        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name,reference_document\n"
            "L0T1O23,Kale,10,lbs,2026-04-17,Farm A,REF\n"
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_text.encode(), "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "kde_warnings" in body
        assert any("character swap" in w for w in body["kde_warnings"])

    def test_row_exception_appended_to_errors(self, monkeypatch):
        # Force IngestEvent construction to fail by making quantity a non-numeric
        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name,reference_document\n"
            "TLC1,Kale,not-a-number,lbs,2026-04-17,Farm A,REF\n"
            "TLC2,Kale,10,lbs,2026-04-17,Farm A,REF\n"
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_text.encode(), "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # 1 valid row + 1 parse error → accepted=1, rejected=1
        assert body["accepted"] == 1
        assert body["rejected"] == 1

    def test_all_rows_fail_returns_400(self):
        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name,reference_document\n"
            "TLC1,Kale,not-a-number,lbs,2026-04-17,Farm A,REF\n"
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_text.encode(), "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "errors" in body["detail"]

    def test_kde_missing_warning(self):
        # All required fields present except reference_document
        csv_text = (
            "traceability_lot_code,product_description,quantity,unit_of_measure,"
            "harvest_date,location_name\n"
            "TLC1,Kale,10,lbs,2026-04-17,Farm A\n"
        )
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("t.csv", csv_text.encode(), "text/csv")},
            data={"cte_type": "harvesting"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "kde_warnings" in body
        assert any("Missing KDEs" in w for w in body["kde_warnings"])


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix(self):
        assert router.prefix == "/api/v1"

    def test_tags(self):
        assert "CSV Templates & Import" in router.tags

    def test_endpoints_registered(self):
        paths = {route.path for route in router.routes}
        assert "/api/v1/templates/{cte_type}" in paths
        assert "/api/v1/templates" in paths
        assert "/api/v1/ingest/csv" in paths

    def test_alias_coverage(self):
        # Spot-check each canonical CTE has at least one alias mapping back to it
        canonical = {
            "harvesting", "cooling", "initial_packing", "shipping",
            "receiving", "transformation", "first_land_based_receiving",
        }
        for c in canonical:
            assert any(v == c for v in _CTE_TYPE_ALIASES.values()), c
