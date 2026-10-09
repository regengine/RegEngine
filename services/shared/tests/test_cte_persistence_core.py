"""Coverage tests for services/shared/cte_persistence/core.py pure helpers.

core.py is the compatibility surface of the deprecated dual-write path
(see #1335). These tests lock in the behavior of its stateless helpers
(event-type guard, timestamp parsing, KDE serialization, validation-status
mapping, alert-row shaping) plus the CTEPersistence constructor and tenant
context delegation. No database is needed; everything runs on fakes.

The tests are deliberately consolidated into a few methods (loops instead
of parametrization) because this repo's pytest setup adds about half a
second of per-test overhead, and this file must stay under ~10 s.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from services.shared.cte_persistence.core import (
    ALERT_INSERT_SQL,
    DUAL_WRITE_RECONCILIATION_NEEDED,
    VALIDATION_STATUS_REJECTED,
    VALIDATION_STATUS_VALID,
    VALIDATION_STATUS_WARNING,
    CTEPersistence,
    _alert_insert_params,
    _derive_validation_status,
    _is_rejecting_validation_item,
    _jsonify_kde,
    _normalize_alert_type,
    _parse_timestamp,
    _validate_event_type,
)


class TestModuleConstants:
    def test_statuses_sql_and_dual_write_flag(self):
        assert len({VALIDATION_STATUS_VALID, VALIDATION_STATUS_WARNING, VALIDATION_STATUS_REJECTED}) == 3
        # The legacy shim is live until #1335 retires it.
        assert DUAL_WRITE_RECONCILIATION_NEEDED is True
        assert "fsma.compliance_alerts" in ALERT_INSERT_SQL
        assert ":tenant_id" in ALERT_INSERT_SQL
        assert ":alert_type" in ALERT_INSERT_SQL


class TestValidateEventType:
    _VALID = [
        "harvesting",
        "cooling",
        "initial_packing",
        "first_land_based_receiving",
        "shipping",
        "receiving",
        "transformation",
    ]

    def test_all_seven_cte_types_accepted(self):
        for event_type in self._VALID:
            assert _validate_event_type(event_type) == event_type

    def test_invalid_types_rejected(self):
        bad_values = [
            "HARVESTING",  # wrong case
            "Shipping",  # wrong case
            "shipping ",  # surrounding whitespace is not stripped
            "harvest",  # unknown token
            "growing",  # canonical-only type, legacy schema rejects it
            "",  # empty
            None,  # missing
            123,  # non-string
            ["shipping"],  # non-string
        ]
        for bad in bad_values:
            try:
                _validate_event_type(bad)
            except ValueError:
                continue
            raise AssertionError(f"event_type {bad!r} should have been rejected")


class TestParseTimestamp:
    def test_valid_inputs_parsed_to_utc(self):
        cases = [
            ("2026-01-15T10:00:00Z", datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)),
            ("2026-01-15T12:00:00+02:00", datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)),
            ("2020-01-01T00:00:00+00:00", datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)),  # backfill allowed
        ]
        for raw, expected in cases:
            assert _parse_timestamp(raw, field="event_timestamp") == expected
        as_dt = _parse_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc), field="event_timestamp")
        assert as_dt == datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)

    def test_bad_inputs_rejected(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        bad_values = [
            None,
            "",
            "   ",
            "not-a-date",
            "2026-13-45T99:99:99+00:00",
            12345,
            datetime(2026, 1, 15, 10, 0),  # naive datetime
            "2026-01-15T10:00:00",  # naive string
            future,  # beyond the clock-skew tolerance
        ]
        for bad in bad_values:
            try:
                _parse_timestamp(bad, field="event_timestamp")
            except ValueError:
                continue
            raise AssertionError(f"timestamp {bad!r} should have been rejected")

    def test_small_clock_skew_allowed(self):
        near = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
        assert _parse_timestamp(near, field="event_timestamp") is not None


class TestJsonifyKde:
    def test_values_serialize_to_valid_json(self):
        cases = [
            ({"gln": "123", "n": 1}, {"gln": "123", "n": 1}),
            ([1, "a"], [1, "a"]),
            (True, True),
            (None, None),
            (3.5, 3.5),
            ("hello", "hello"),
        ]
        for value, expected in cases:
            assert json.loads(_jsonify_kde(value)) == expected
        # Exotic types fall back to strings but must stay valid JSON.
        assert json.loads(_jsonify_kde(datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)))


class TestValidationStatus:
    def test_status_mapping(self):
        assert _derive_validation_status([], []) == VALIDATION_STATUS_VALID
        assert _derive_validation_status([]) == VALIDATION_STATUS_VALID
        warning = [{"severity": "warning", "alert_type": "chain_break", "message": "m"}]
        assert _derive_validation_status(warning) == VALIDATION_STATUS_WARNING
        assert _derive_validation_status([], [{"severity": "info", "message": "note"}]) == VALIDATION_STATUS_WARNING
        reject = [{"severity": "critical", "message": "failed check"}]
        assert _derive_validation_status([], reject) == VALIDATION_STATUS_REJECTED
        kde_alert = [{"severity": "info", "alert_type": "missing_required_kde"}]
        assert _derive_validation_status(kde_alert) == VALIDATION_STATUS_REJECTED

    def test_reject_severities(self):
        for severity in ["reject", "error", "critical", "REJECT", " Error "]:
            assert _is_rejecting_validation_item({"severity": severity}) is True
            status = _derive_validation_status([{"severity": severity, "alert_type": "x"}])
            assert status == VALIDATION_STATUS_REJECTED
        assert _is_rejecting_validation_item({"severity": "warning"}) is False
        assert _is_rejecting_validation_item({}) is False


class TestAlertParams:
    def test_normalize_and_params_shape(self):
        assert _normalize_alert_type("temperature_excursion") == "temperature_excursion"
        assert _normalize_alert_type("brand_new_type") == "missing_kde"
        assert _normalize_alert_type("") == "missing_kde"

        params = _alert_insert_params("tenant-1", "event-1", {"alert_type": "chain_break"})
        assert params["tenant_id"] == "tenant-1"
        assert params["org_id"] == "tenant-1"
        assert params["event_id"] == "event-1"
        assert params["cte_event_id"] == "event-1"
        assert params["severity"] == "warning"
        assert params["alert_type"] == "chain_break"
        assert params["title"] == "chain_break"
        assert params["message"] == ""

        folded = _alert_insert_params("t", "e", {"alert_type": "nope", "severity": "error", "message": "m"})
        assert folded["alert_type"] == "missing_kde"
        assert folded["severity"] == "error"
        assert folded["message"] == "m"


class TestCTEPersistenceInit:
    def test_constructor_and_tenant_context(self):
        session = MagicMock()
        persistence = CTEPersistence(session)
        assert persistence.session is session

        persistence.set_tenant_context(str(uuid4()))
        assert session.execute.called

        try:
            persistence.set_tenant_context("not-a-uuid")
        except ValueError:
            pass
        else:
            raise AssertionError("non-UUID tenant_id should have been rejected")
