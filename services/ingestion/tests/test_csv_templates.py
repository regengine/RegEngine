"""Unit tests for CSV template definitions (app/csv_templates.py)."""

import csv
import io
import sys
from pathlib import Path

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

import pytest
from app.csv_templates import _CTE_TYPE_ALIASES, CTE_COLUMNS, _generate_csv_template, _validate_kde_completeness
from app.webhook_models import REQUIRED_KDES_BY_CTE, IngestEvent, WebhookCTEType

EXPECTED_CTE_TYPES = {
    "growing",
    "harvesting",
    "cooling",
    "initial_packing",
    "first_land_based_receiving",
    "shipping",
    "receiving",
    "transformation",
}


class TestCTEColumns:
    """Tests for the CTE_COLUMNS template definitions."""

    def test_all_cte_types_exist(self):
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


class TestTemplateValidatorDrift:
    """Drift guard: the served CSV templates must cover REQUIRED_KDES_BY_CTE.

    Rows built from the official templates were rejected at
    POST /api/v1/ingest/csv with "Missing required KDE" because the
    templates omitted mandatory columns (harvester_business_name for
    initial_packing, tlc_source_reference for shipping/receiving,
    reference_document for most types). sample_data/ drifted the same
    way (fixed in PR #2631). These tests pin template <-> validator
    parity so the two can never diverge again.
    """

    @pytest.mark.parametrize(
        "cte_enum",
        sorted(REQUIRED_KDES_BY_CTE, key=lambda c: c.value),
        ids=lambda c: c.value,
    )
    def test_served_template_header_covers_required_kdes(self, cte_enum):
        """Every KDE the validator requires must be a served template column."""
        assert cte_enum.value in CTE_COLUMNS, (
            f"REQUIRED_KDES_BY_CTE defines '{cte_enum.value}' but no CSV template exists for it"
        )
        header = next(csv.reader(io.StringIO(_generate_csv_template(cte_enum.value))))
        missing = set(REQUIRED_KDES_BY_CTE[cte_enum]) - set(header)
        assert not missing, (
            f"Template for '{cte_enum.value}' is missing required KDE column(s) "
            f"{sorted(missing)} — rows built from it would be rejected at ingest. "
            f"Add the column(s) to CTE_COLUMNS in app/csv_templates.py."
        )

    @pytest.mark.parametrize(
        "cte_enum",
        sorted(REQUIRED_KDES_BY_CTE, key=lambda c: c.value),
        ids=lambda c: c.value,
    )
    def test_template_example_row_has_required_kde_values(self, cte_enum):
        """The template's example row must fill every required KDE (non-empty)."""
        rows = list(csv.reader(io.StringIO(_generate_csv_template(cte_enum.value))))
        header, example = rows[0], rows[1]
        example_by_col = dict(zip(header, example))
        empty = [kde for kde in REQUIRED_KDES_BY_CTE[cte_enum] if not example_by_col.get(kde, "").strip()]
        assert not empty, (
            f"Template example row for '{cte_enum.value}' leaves required KDE(s) "
            f"{empty} empty — the example would be rejected at ingest."
        )

    @pytest.mark.parametrize("template_key", sorted(CTE_COLUMNS))
    def test_every_served_template_covers_its_effective_cte_kdes(self, template_key):
        """Templates served under a legacy alias (growing → harvesting) must
        also cover the required KDEs of the CTE type their rows ingest as —
        the two tests above only see templates named after a canonical CTE."""
        effective_cte = WebhookCTEType(_CTE_TYPE_ALIASES[template_key])
        rows = list(csv.reader(io.StringIO(_generate_csv_template(template_key))))
        header, example = rows[0], rows[1]
        example_by_col = dict(zip(header, example))
        required = REQUIRED_KDES_BY_CTE[effective_cte]
        missing = set(required) - set(header)
        assert not missing, (
            f"Template '{template_key}' ingests as '{effective_cte.value}' but is missing "
            f"required KDE column(s) {sorted(missing)} — rows built from it would be rejected."
        )
        empty = [kde for kde in required if not example_by_col.get(kde, "").strip()]
        assert not empty, f"Template '{template_key}' example row leaves required KDE(s) {empty} empty."


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
