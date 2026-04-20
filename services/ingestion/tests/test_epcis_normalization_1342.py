"""Unit tests for ``app.epcis.normalization`` — issue #1342.

Boosts coverage from 26% to 100% by exercising every branch in the
five helpers and the ``_EVENT_TYPE_MAP`` bizStep lookup.

Pinned behaviour:
  - ``_event_idempotency_key``: uses explicit ``eventID`` when
    present (stringified); otherwise sha256 of canonical JSON
    (sorted keys, compact separators) so two semantically-equal
    events collide to the same key regardless of input ordering.
  - ``_normalize_epcis_to_cte``:
      * Unmapped bizStep raises HTTPException(400) with the
        allowed_bizsteps list sorted — never silently defaults
        (the `growing` / planting bug in #1153 was exactly this
        regression).
      * Both CBV and FSMA URIs resolve; parameterized over every
        entry in ``_EVENT_TYPE_MAP``.
      * ilmd is pulled from the event root or the extension; lot
        data, EPC list first element, bizLocation→readPoint
        fallback, source/destination lists, and quantityList[0]
        all populate the canonical event.
  - ``_extract_kdes``:
      * Namespaced keys (``fsma:field``, ``cbvmda:field``) strip
        the namespace — downstream consumers key by bare name.
      * None values skipped (EPCIS wild-west defensive pattern).
      * Required flag set only for traceabilityLotCode / lotNumber.
  - ``_kde_completeness``: populated_required / required_count;
    always positive (no div-by-zero on empty KDE list — the
    ``or 1`` guards).
  - ``_compliance_alerts``: three rules (missing TLC critical,
    incomplete shipping/receiving route warning, no ILMD KDEs
    warning). Rules fire independently and combine.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))
# Module imports services.ingestion.app.epcis.extraction (absolute);
# add repo root so that resolves.
repo_root = service_dir.parent.parent
sys.path.insert(0, str(repo_root))


from app.epcis.normalization import (  # noqa: E402
    _EVENT_TYPE_MAP,
    _compliance_alerts,
    _event_idempotency_key,
    _extract_kdes,
    _kde_completeness,
    _normalize_epcis_to_cte,
)


# ---------------------------------------------------------------------------
# _event_idempotency_key
# ---------------------------------------------------------------------------


class TestEventIdempotencyKey:
    def test_explicit_event_id_wins(self):
        ev = {"eventID": "urn:uuid:abc-123", "bizStep": "x"}
        assert _event_idempotency_key(ev) == "urn:uuid:abc-123"

    def test_integer_event_id_stringified(self):
        # Some EPCIS producers emit an int; str-coerce so downstream
        # Redis keys are strings.
        ev = {"eventID": 42}
        assert _event_idempotency_key(ev) == "42"

    def test_missing_event_id_falls_back_to_sha256(self):
        ev = {"bizStep": "urn:epcglobal:cbv:bizstep:shipping"}
        expected = hashlib.sha256(
            json.dumps(ev, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert _event_idempotency_key(ev) == expected
        # Shape check: lowercase hex, 64 chars.
        assert len(_event_idempotency_key(ev)) == 64

    def test_empty_event_id_falls_through_to_sha(self):
        # Empty string is falsy — ``if explicit`` skips to sha256.
        ev = {"eventID": "", "bizStep": "x"}
        out = _event_idempotency_key(ev)
        assert out != ""
        assert len(out) == 64  # sha256 hex

    def test_reorder_yields_same_key(self):
        # Canonical JSON (sort_keys=True) must make these collide —
        # if downstream dedup relied on insertion order, duplicate
        # events would slip through.
        a = {"bizStep": "x", "eventTime": "2026-04-19T00:00:00Z"}
        b = {"eventTime": "2026-04-19T00:00:00Z", "bizStep": "x"}
        assert _event_idempotency_key(a) == _event_idempotency_key(b)


# ---------------------------------------------------------------------------
# _normalize_epcis_to_cte — bizStep mapping
# ---------------------------------------------------------------------------


class TestNormalizeBizStepMapping:
    @pytest.mark.parametrize("biz_step,cte", sorted(_EVENT_TYPE_MAP.items()))
    def test_every_bizstep_maps_to_expected_cte(self, biz_step, cte):
        # Parameterized against the live map so adding a new entry
        # auto-tightens the test.
        ev = {"bizStep": biz_step}
        out = _normalize_epcis_to_cte(ev)
        assert out["event_type"] == cte

    def test_unmapped_bizstep_raises_http_400(self):
        # #1153 regression: silently defaulting to ``receiving`` would
        # corrupt recall lookback graphs. The rejection must be loud.
        with pytest.raises(HTTPException) as ei:
            _normalize_epcis_to_cte({"bizStep": "urn:unknown:bogus"})
        assert ei.value.status_code == 400
        detail = ei.value.detail
        assert detail["error"] == "unmapped_bizstep"
        assert detail["bizStep"] == "urn:unknown:bogus"
        assert "FSMA 204" in detail["message"]
        # allowed_bizsteps is sorted; the caller uses it to render a
        # helpful 400 body.
        assert detail["allowed_bizsteps"] == sorted(_EVENT_TYPE_MAP.keys())

    def test_missing_bizstep_also_unmapped(self):
        # ``str(event.get("bizStep") or "")`` → "" which isn't in
        # the map → raise. Pin so a refactor doesn't silently default.
        with pytest.raises(HTTPException) as ei:
            _normalize_epcis_to_cte({})
        assert ei.value.status_code == 400
        assert ei.value.detail["bizStep"] == ""


# ---------------------------------------------------------------------------
# _normalize_epcis_to_cte — full event shape
# ---------------------------------------------------------------------------


class TestNormalizeFullShape:
    def _shipping_event(self, **overrides):
        ev = {
            "type": "ObjectEvent",
            "action": "OBSERVE",
            "bizStep": "urn:epcglobal:cbv:bizstep:shipping",
            "eventTime": "2026-04-19T12:00:00Z",
            "eventTimeZoneOffset": "-05:00",
            "epcList": ["urn:epc:id:sgtin:0614141.107346.2017"],
            "bizLocation": {"id": "urn:epc:id:sgln:BIZ"},
            "readPoint": {"id": "urn:epc:id:sgln:READ"},
            "sourceList": [{"source": "urn:epc:id:sgln:SRC"}],
            "destinationList": [{"destination": "urn:epc:id:sgln:DST"}],
            "ilmd": {
                "cbvmda:lotNumber": "LOT-A",
                "fsma:traceabilityLotCode": "TLC-A",
            },
            "extension": {
                "quantityList": [{"quantity": 12, "uom": "KGM"}],
            },
        }
        ev.update(overrides)
        return ev

    def test_full_happy_shipping_event(self):
        out = _normalize_epcis_to_cte(self._shipping_event())
        assert out["event_type"] == "shipping"
        assert out["epcis_event_type"] == "ObjectEvent"
        assert out["epcis_action"] == "OBSERVE"
        assert out["epcis_biz_step"] == "urn:epcglobal:cbv:bizstep:shipping"
        assert out["event_time"] == "2026-04-19T12:00:00Z"
        assert out["event_timezone"] == "-05:00"
        assert out["lot_code"] == "LOT-A"
        assert out["tlc"] == "TLC-A"
        assert out["product_id"] == "urn:epc:id:sgtin:0614141.107346.2017"
        # bizLocation wins over readPoint when both present.
        assert out["location_id"] == "urn:epc:id:sgln:BIZ"
        assert out["source_location_id"] == "urn:epc:id:sgln:SRC"
        assert out["dest_location_id"] == "urn:epc:id:sgln:DST"
        assert out["quantity"] == 12
        assert out["unit_of_measure"] == "KGM"
        assert out["data_source"] == "api"
        assert out["validation_status"] == "valid"

    def test_ilmd_in_extension_fallback(self):
        # Some EPCIS 1.2 producers tuck ilmd inside `extension` —
        # both locations must work.
        ev = self._shipping_event()
        ev.pop("ilmd")
        ev["extension"]["ilmd"] = {"lotNumber": "EXT-LOT"}
        out = _normalize_epcis_to_cte(ev)
        assert out["lot_code"] == "EXT-LOT"
        assert out["tlc"] == "EXT-LOT"  # tlc defaults to lot_code

    def test_empty_eventtime_zone_offset_defaults_to_utc(self):
        ev = self._shipping_event()
        ev.pop("eventTimeZoneOffset")
        out = _normalize_epcis_to_cte(ev)
        assert out["event_timezone"] == "+00:00"

    def test_readpoint_used_when_bizlocation_empty(self):
        # Fallback chain: bizLocation first, readPoint second.
        ev = self._shipping_event()
        ev["bizLocation"] = {}  # empty → location_id ""
        out = _normalize_epcis_to_cte(ev)
        assert out["location_id"] == "urn:epc:id:sgln:READ"

    def test_no_locations_returns_empty_string(self):
        ev = self._shipping_event()
        ev["bizLocation"] = {}
        ev["readPoint"] = {}
        out = _normalize_epcis_to_cte(ev)
        assert out["location_id"] == ""

    def test_empty_epc_list_yields_none_product_id(self):
        ev = self._shipping_event()
        ev["epcList"] = []
        out = _normalize_epcis_to_cte(ev)
        assert out["product_id"] is None

    def test_missing_epc_list_yields_none_product_id(self):
        ev = self._shipping_event()
        ev.pop("epcList")
        out = _normalize_epcis_to_cte(ev)
        assert out["product_id"] is None

    def test_non_list_epc_list_yields_none(self):
        # EPCIS sometimes emits a dict or string — guard against
        # ``epcList[0]`` exploding.
        ev = self._shipping_event()
        ev["epcList"] = "not-a-list"
        out = _normalize_epcis_to_cte(ev)
        assert out["product_id"] is None

    def test_no_quantity_list(self):
        ev = self._shipping_event()
        ev["extension"] = {}
        out = _normalize_epcis_to_cte(ev)
        assert out["quantity"] is None
        assert out["unit_of_measure"] is None

    def test_non_list_quantity_list(self):
        ev = self._shipping_event()
        ev["extension"]["quantityList"] = {"nope": "wrong shape"}
        out = _normalize_epcis_to_cte(ev)
        assert out["quantity"] is None
        assert out["unit_of_measure"] is None

    def test_first_quantity_item_not_dict(self):
        ev = self._shipping_event()
        ev["extension"]["quantityList"] = ["malformed"]
        out = _normalize_epcis_to_cte(ev)
        assert out["quantity"] is None


# ---------------------------------------------------------------------------
# _extract_kdes
# ---------------------------------------------------------------------------


class TestExtractKdes:
    def test_empty_ilmd_returns_empty(self):
        assert _extract_kdes({}) == []
        assert _extract_kdes({"ilmd": {}}) == []

    def test_extracts_fields_with_namespace_stripped(self):
        ev = {"ilmd": {"fsma:traceabilityLotCode": "TLC-1"}}
        kdes = _extract_kdes(ev)
        assert len(kdes) == 1
        # kde_type is the post-colon portion — downstream doesn't
        # care about the namespace prefix.
        assert kdes[0]["kde_type"] == "traceabilityLotCode"
        assert kdes[0]["kde_value"] == "TLC-1"
        assert kdes[0]["required"] is True  # TLC is required

    def test_bare_key_without_namespace(self):
        ev = {"ilmd": {"lotNumber": "LOT-2"}}
        kdes = _extract_kdes(ev)
        assert kdes[0]["kde_type"] == "lotNumber"
        assert kdes[0]["required"] is True

    def test_non_required_kde(self):
        ev = {"ilmd": {"cbvmda:bestBeforeDate": "2026-05-01"}}
        kdes = _extract_kdes(ev)
        assert kdes[0]["kde_type"] == "bestBeforeDate"
        assert kdes[0]["required"] is False

    def test_none_values_skipped(self):
        ev = {
            "ilmd": {
                "lotNumber": "LOT-1",
                "cbvmda:bestBeforeDate": None,  # skipped
                "cbvmda:growingArea": "Field 3",
            }
        }
        kdes = _extract_kdes(ev)
        types = {k["kde_type"] for k in kdes}
        assert types == {"lotNumber", "growingArea"}

    def test_integer_value_stringified(self):
        ev = {"ilmd": {"quantity": 42}}
        kdes = _extract_kdes(ev)
        assert kdes[0]["kde_value"] == "42"

    def test_ilmd_in_extension(self):
        # Same fallback path as _normalize_epcis_to_cte uses.
        ev = {"extension": {"ilmd": {"lotNumber": "LOT-EXT"}}}
        kdes = _extract_kdes(ev)
        assert len(kdes) == 1
        assert kdes[0]["kde_value"] == "LOT-EXT"


# ---------------------------------------------------------------------------
# _kde_completeness
# ---------------------------------------------------------------------------


class TestKdeCompleteness:
    def test_all_required_populated(self):
        kdes = [
            {"kde_type": "lotNumber", "kde_value": "A", "required": True},
            {"kde_type": "traceabilityLotCode", "kde_value": "B", "required": True},
        ]
        assert _kde_completeness(kdes) == 1.0

    def test_partial_population_rounded_two_decimals(self):
        kdes = [
            {"kde_type": "lotNumber", "kde_value": "A", "required": True},
            {"kde_type": "traceabilityLotCode", "kde_value": "", "required": True},
            {"kde_type": "other", "kde_value": "C", "required": False},
        ]
        # 1 populated / 2 required = 0.5
        assert _kde_completeness(kdes) == 0.5

    def test_empty_list_returns_zero(self):
        # ``or 1`` guards against div-by-zero. Zero populated over
        # 1 required-denominator = 0.0.
        assert _kde_completeness([]) == 0.0

    def test_no_required_kdes_returns_zero(self):
        # When required_count is 0, ``or 1`` turns denominator into
        # 1; populated_required is 0, so 0/1 = 0.0. Pin so a refactor
        # doesn't regress into ZeroDivisionError.
        kdes = [
            {"kde_type": "notes", "kde_value": "x", "required": False},
        ]
        assert _kde_completeness(kdes) == 0.0

    def test_rounding_to_two_decimals(self):
        kdes = [
            {"kde_type": "a", "kde_value": "x", "required": True},
            {"kde_type": "b", "kde_value": "x", "required": True},
            {"kde_type": "c", "kde_value": "", "required": True},
        ]
        # 2/3 = 0.666... → round(..., 2) = 0.67
        assert _kde_completeness(kdes) == 0.67


# ---------------------------------------------------------------------------
# _compliance_alerts
# ---------------------------------------------------------------------------


class TestComplianceAlerts:
    def test_no_alerts_when_event_complete(self):
        normalized = {
            "tlc": "TLC-1",
            "event_type": "shipping",
            "source_location_id": "SRC",
            "dest_location_id": "DST",
        }
        kdes = [
            {"kde_type": "traceabilityLotCode", "kde_value": "TLC-1", "required": True}
        ]
        assert _compliance_alerts(normalized, kdes) == []

    def test_missing_tlc_fires_critical(self):
        normalized = {
            "tlc": "",
            "event_type": "receiving",
            "source_location_id": "SRC",
            "dest_location_id": "DST",
        }
        kdes = [{"kde_type": "x", "kde_value": "y", "required": False}]
        alerts = _compliance_alerts(normalized, kdes)
        assert any(
            a["severity"] == "critical" and a["alert_type"] == "missing_kde"
            for a in alerts
        )

    def test_incomplete_shipping_route_warning(self):
        # shipping event without source OR dest fires a warning.
        normalized = {
            "tlc": "TLC-1",
            "event_type": "shipping",
            "source_location_id": "",
            "dest_location_id": "DST",
        }
        kdes = [{"kde_type": "x", "kde_value": "y", "required": False}]
        alerts = _compliance_alerts(normalized, kdes)
        assert any(a["alert_type"] == "incomplete_route" for a in alerts)

    def test_incomplete_receiving_route_warning(self):
        # Receiving also gets the route check.
        normalized = {
            "tlc": "TLC-1",
            "event_type": "receiving",
            "source_location_id": "SRC",
            "dest_location_id": "",
        }
        kdes = [{"kde_type": "x", "kde_value": "y", "required": False}]
        alerts = _compliance_alerts(normalized, kdes)
        assert any(a["alert_type"] == "incomplete_route" for a in alerts)

    def test_non_route_event_type_skips_route_check(self):
        # harvesting doesn't need source/dest — no route alert.
        normalized = {
            "tlc": "TLC-1",
            "event_type": "harvesting",
            "source_location_id": "",
            "dest_location_id": "",
        }
        kdes = [{"kde_type": "x", "kde_value": "y", "required": False}]
        alerts = _compliance_alerts(normalized, kdes)
        assert all(a["alert_type"] != "incomplete_route" for a in alerts)

    def test_empty_kde_list_fires_warning(self):
        normalized = {"tlc": "TLC-1", "event_type": "harvesting"}
        alerts = _compliance_alerts(normalized, [])
        assert any(
            a["severity"] == "warning"
            and a["alert_type"] == "missing_kde"
            and "ILMD" in a["message"]
            for a in alerts
        )

    def test_multiple_alerts_accumulate(self):
        # No TLC + incomplete route + no KDEs → all three.
        normalized = {
            "tlc": "",
            "event_type": "shipping",
            "source_location_id": "",
            "dest_location_id": "",
        }
        alerts = _compliance_alerts(normalized, [])
        types = {a["alert_type"] for a in alerts}
        # missing_kde (critical) + incomplete_route + missing_kde (warning)
        assert "incomplete_route" in types
        assert "missing_kde" in types
        # The two missing_kde alerts have different severities so both exist.
        severities = [a["severity"] for a in alerts if a["alert_type"] == "missing_kde"]
        assert "critical" in severities
        assert "warning" in severities
