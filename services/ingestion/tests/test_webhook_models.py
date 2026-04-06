"""Unit tests for webhook ingestion models (app/webhook_models.py)."""

import sys
from pathlib import Path

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.webhook_models import IngestEvent, WebhookCTEType, validate_gln


def _valid_event_kwargs(**overrides):
    """Return a minimal valid IngestEvent dict, with optional overrides."""
    now = datetime.now(timezone.utc)
    base = {
        "cte_type": "shipping",
        "traceability_lot_code": "LOT-001",
        "product_description": "Roma Tomatoes",
        "quantity": 100.0,
        "unit_of_measure": "cases",
        "location_name": "Warehouse A",
        "timestamp": now.isoformat(),
    }
    base.update(overrides)
    return base


class TestValidateGln:
    """Tests for the standalone validate_gln helper."""

    def test_valid_gln(self):
        # 0614141000036 is a well-known GS1 example GLN
        is_valid, err = validate_gln("0614141000036")
        assert is_valid is True
        assert err is None

    def test_wrong_check_digit(self):
        # Change last digit from 6 to 0
        is_valid, err = validate_gln("0614141000030")
        assert is_valid is False
        assert "check digit" in err.lower()

    def test_wrong_length_short(self):
        is_valid, err = validate_gln("061414")
        assert is_valid is False
        assert "13 digits" in err

    def test_wrong_length_long(self):
        is_valid, err = validate_gln("06141410000361")
        assert is_valid is False
        assert "13 digits" in err

    def test_strips_non_digit_characters(self):
        # validate_gln strips non-digits; "0614-1410-0003-6" has 13 digits
        is_valid, err = validate_gln("0614-1410-0003-6")
        assert is_valid is True


class TestWebhookCTEType:
    """Tests for WebhookCTEType enum."""

    def test_has_all_cte_types(self):
        assert len(WebhookCTEType) == 7

    def test_expected_members(self):
        expected = {
            "harvesting", "cooling", "initial_packing",
            "first_land_based_receiving", "shipping",
            "receiving", "transformation",
        }
        actual = {m.value for m in WebhookCTEType}
        assert actual == expected


class TestIngestEvent:
    """Tests for IngestEvent Pydantic model."""

    def test_accepts_valid_event(self):
        event = IngestEvent(**_valid_event_kwargs())
        assert event.cte_type == WebhookCTEType.SHIPPING
        assert event.quantity == 100.0

    def test_rejects_future_timestamp(self):
        future = datetime.now(timezone.utc) + timedelta(hours=48)
        with pytest.raises(ValidationError) as exc_info:
            IngestEvent(**_valid_event_kwargs(timestamp=future.isoformat()))
        errors = exc_info.value.errors()
        assert any("future" in str(e["msg"]).lower() for e in errors)

    def test_accepts_unknown_unit_of_measure_with_normalization(self):
        """Unknown units are accepted (warning-only) and lowercased."""
        event = IngestEvent(**_valid_event_kwargs(unit_of_measure="bushels_of_fun"))
        assert event.unit_of_measure == "bushels_of_fun"

    def test_accepts_valid_units(self):
        for unit in ["lbs", "kg", "cases", "pallets", "each"]:
            event = IngestEvent(**_valid_event_kwargs(unit_of_measure=unit))
            assert event.unit_of_measure == unit

    def test_requires_location_gln_or_name(self):
        """FSMA 204 requires at least one location identifier."""
        with pytest.raises(ValidationError) as exc_info:
            IngestEvent(**_valid_event_kwargs(
                location_name=None,
                location_gln=None,
            ))
        errors = exc_info.value.errors()
        assert any("location" in str(e["msg"]).lower() for e in errors)

    def test_location_kde_satisfies_requirement(self):
        """A location KDE (e.g. ship_from_location) should satisfy the location check."""
        event = IngestEvent(**_valid_event_kwargs(
            location_name=None,
            location_gln=None,
            kdes={"ship_from_location": "Some Warehouse"},
        ))
        assert event.location_name is None
        assert event.kdes["ship_from_location"] == "Some Warehouse"

    def test_accepts_historical_timestamp(self):
        past = datetime.now(timezone.utc) - timedelta(days=180)
        event = IngestEvent(**_valid_event_kwargs(timestamp=past.isoformat()))
        assert event.timestamp == past.isoformat()

    def test_rejects_invalid_iso_timestamp(self):
        with pytest.raises(ValidationError):
            IngestEvent(**_valid_event_kwargs(timestamp="not-a-date"))
