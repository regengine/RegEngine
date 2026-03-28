"""Unit tests for CSV template definitions (app/csv_templates.py)."""

import sys
from pathlib import Path

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

import pytest

from app.csv_templates import CTE_COLUMNS, _validate_kde_completeness
from app.webhook_models import IngestEvent, WebhookCTEType


EXPECTED_CTE_TYPES = {
    "harvesting", "cooling", "initial_packing",
    "first_land_based_receiving", "shipping",
    "receiving", "transformation",
}


class TestCTEColumns:
    """Tests for the CTE_COLUMNS template definitions."""

    def test_all_seven_cte_types_exist(self):
        assert set(CTE_COLUMNS.keys()) == EXPECTED_CTE_TYPES

    def test_flbr_template_has_correct_columns(self):
        flbr = CTE_COLUMNS["first_land_based_receiving"]
        col_names = [col[0] for col in flbr]
        assert len(flbr) == 11
        assert "landing_date" in col_names
        assert "event_time" in col_names

    def test_every_template_includes_event_time(self):
        for cte_type, columns in CTE_COLUMNS.items():
            col_names = [col[0] for col in columns]
            assert "event_time" in col_names, f"{cte_type} template missing event_time"

    def test_columns_are_three_tuples(self):
        """Every column definition should be (name, example, description)."""
        for cte_type, columns in CTE_COLUMNS.items():
            for col in columns:
                assert len(col) == 3, f"{cte_type}: column {col} is not a 3-tuple"
                assert isinstance(col[0], str)
                assert isinstance(col[1], str)
                assert isinstance(col[2], str)


class TestValidateKdeCompleteness:
    """Tests for _validate_kde_completeness."""

    def _make_event(self, cte_type_str, **kdes_extra):
        """Build a minimal IngestEvent for a given CTE type."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        # Pick a location field that satisfies the model validator
        loc_kwargs = {}
        if cte_type_str in ("shipping",):
            loc_kwargs["kdes"] = {"ship_from_location": "Origin", "ship_to_location": "Dest"}
        elif cte_type_str in ("receiving", "first_land_based_receiving"):
            loc_kwargs["kdes"] = {"receiving_location": "Dock 4"}
        else:
            loc_kwargs["location_name"] = "Test Facility"
            loc_kwargs["kdes"] = {}

        loc_kwargs["kdes"].update(kdes_extra)

        return IngestEvent(
            cte_type=WebhookCTEType(cte_type_str),
            traceability_lot_code="LOT-001",
            product_description="Test Product",
            quantity=10.0,
            unit_of_measure="cases",
            timestamp=now.isoformat(),
            **loc_kwargs,
        )

    def test_returns_missing_fields_for_incomplete_data(self):
        event = self._make_event("harvesting")
        # We pass empty kdes so required fields like harvest_date, reference_document are missing
        missing = _validate_kde_completeness("harvesting", event, {})
        assert "harvest_date" in missing
        assert "reference_document" in missing

    def test_returns_empty_for_complete_data(self):
        event = self._make_event(
            "harvesting",
            harvest_date="2026-02-26",
            reference_document="REF-001",
        )
        kdes = {
            "traceability_lot_code": "LOT-001",
            "product_description": "Test Product",
            "quantity": "10",
            "unit_of_measure": "cases",
            "harvest_date": "2026-02-26",
            "location_name": "Test Facility",
            "reference_document": "REF-001",
        }
        missing = _validate_kde_completeness("harvesting", event, kdes)
        assert missing == []

    def test_unknown_cte_type_returns_empty(self):
        """An unrecognized CTE type should return no missing fields."""
        event = self._make_event("harvesting")
        missing = _validate_kde_completeness("nonexistent_type", event, {})
        assert missing == []
