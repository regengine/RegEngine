"""Unit tests for ``app.epcis.normalization`` on empty input and the map.

Full-event shape, KDE extraction of present values, and a complete event
with no alerts need a real EPCIS record.
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

_FSMA_204_CTES = frozenset(
    {
        "growing",
        "harvesting",
        "cooling",
        "initial_packing",
        "first_land_based_receiving",
        "shipping",
        "receiving",
        "transformation",
    }
)


class TestEventIdempotencyKey:
    def test_missing_event_id_falls_back_to_sha256(self):
        expected = hashlib.sha256(json.dumps({}, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        assert _event_idempotency_key({}) == expected
        assert len(_event_idempotency_key({})) == 64

    def test_empty_event_id_falls_through_to_sha(self):
        out = _event_idempotency_key({"eventID": ""})
        assert out != ""
        assert len(out) == 64

    def test_reorder_yields_same_key(self):
        assert _event_idempotency_key({"a": 1, "b": 2}) == _event_idempotency_key({"b": 2, "a": 1})


class TestNormalizeBizStepMapping:
    @pytest.mark.parametrize("biz_step,cte", sorted(_EVENT_TYPE_MAP.items()))
    def test_every_bizstep_maps_to_expected_cte(self, biz_step, cte):
        assert _EVENT_TYPE_MAP[biz_step] == cte
        assert cte in _FSMA_204_CTES

    def test_unmapped_bizstep_raises_http_400(self):
        with pytest.raises(HTTPException) as ei:
            _normalize_epcis_to_cte({})
        assert ei.value.status_code == 400
        detail = ei.value.detail
        assert detail["error"] == "unmapped_bizstep"
        assert detail["bizStep"] == ""
        assert "FSMA 204" in detail["message"]
        assert detail["allowed_bizsteps"] == sorted(_EVENT_TYPE_MAP.keys())

    def test_missing_bizstep_also_unmapped(self):
        with pytest.raises(HTTPException) as ei:
            _normalize_epcis_to_cte({})
        assert ei.value.status_code == 400
        assert ei.value.detail["bizStep"] == ""


class TestExtractKdes:
    def test_empty_ilmd_returns_empty(self):
        assert _extract_kdes({}) == []
        assert _extract_kdes({"ilmd": {}}) == []

    def test_none_values_skipped(self):
        assert _extract_kdes({"ilmd": {"note": None}}) == []


class TestKdeCompleteness:
    def test_all_required_populated(self):
        kdes = [
            {"required": True, "kde_value": "yes"},
            {"required": True, "kde_value": "yes"},
        ]
        assert _kde_completeness(kdes) == 1.0

    def test_partial_population_rounded_two_decimals(self):
        kdes = [
            {"required": True, "kde_value": "yes"},
            {"required": True, "kde_value": ""},
            {"required": False, "kde_value": "yes"},
        ]
        assert _kde_completeness(kdes) == 0.5

    def test_empty_list_returns_zero(self):
        assert _kde_completeness([]) == 0.0

    def test_no_required_kdes_returns_zero(self):
        assert _kde_completeness([{"required": False, "kde_value": "yes"}]) == 0.0

    def test_rounding_to_two_decimals(self):
        kdes = [
            {"required": True, "kde_value": "yes"},
            {"required": True, "kde_value": "yes"},
            {"required": True, "kde_value": ""},
        ]
        assert _kde_completeness(kdes) == 0.67


class TestComplianceAlerts:
    def test_missing_tlc_fires_critical(self):
        normalized = {
            "tlc": "",
            "event_type": "receiving",
            "source_location_id": "",
            "dest_location_id": "",
        }
        alerts = _compliance_alerts(normalized, [{"required": False, "kde_value": "yes"}])
        assert any(a["severity"] == "critical" and a["alert_type"] == "missing_kde" for a in alerts)

    def test_incomplete_shipping_route_warning(self):
        normalized = {
            "tlc": "",
            "event_type": "shipping",
            "source_location_id": "",
            "dest_location_id": "",
        }
        alerts = _compliance_alerts(normalized, [{"required": False, "kde_value": "yes"}])
        assert any(a["alert_type"] == "incomplete_route" for a in alerts)

    def test_incomplete_receiving_route_warning(self):
        normalized = {
            "tlc": "",
            "event_type": "receiving",
            "source_location_id": "",
            "dest_location_id": "",
        }
        alerts = _compliance_alerts(normalized, [{"required": False, "kde_value": "yes"}])
        assert any(a["alert_type"] == "incomplete_route" for a in alerts)

    def test_non_route_event_type_skips_route_check(self):
        normalized = {
            "tlc": "",
            "event_type": "harvesting",
            "source_location_id": "",
            "dest_location_id": "",
        }
        alerts = _compliance_alerts(normalized, [{"required": False, "kde_value": "yes"}])
        assert all(a["alert_type"] != "incomplete_route" for a in alerts)

    def test_empty_kde_list_fires_warning(self):
        alerts = _compliance_alerts({"tlc": "", "event_type": "harvesting"}, [])
        assert any(
            a["severity"] == "warning" and a["alert_type"] == "missing_kde" and "ILMD" in a["message"] for a in alerts
        )

    def test_multiple_alerts_accumulate(self):
        normalized = {
            "tlc": "",
            "event_type": "shipping",
            "source_location_id": "",
            "dest_location_id": "",
        }
        alerts = _compliance_alerts(normalized, [])
        types = {a["alert_type"] for a in alerts}
        assert "incomplete_route" in types
        assert "missing_kde" in types
        severities = [a["severity"] for a in alerts if a["alert_type"] == "missing_kde"]
        assert "critical" in severities
        assert "warning" in severities
