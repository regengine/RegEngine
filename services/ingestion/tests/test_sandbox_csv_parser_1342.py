"""
Regression coverage for ``app/sandbox/csv_parser.py``.

This module normalizes messy customer CSV input into canonical FSMA 204
event dicts. It has four moving parts:

* ``get_erp_presets`` — enumerates available ERP header-mapping presets.
* ``_parse_csv_to_events`` — converts CSV text into event dicts, resolving
  header aliases (top-level + KDE), parsing quantities/lists, applying ERP
  presets, normalizing CTE-type value aliases, and optionally tracking
  normalization actions for the "what did we change?" audit trail.
* ``_collect_value_normalizations`` — post-hoc diff of raw vs canonical
  events to surface UOM and CTE-type value shifts for the audit log.
* ``_normalize_for_rules`` — converts a parsed event into the canonical
  shape the rules engine expects (facility/entity references, UUID
  event_id, kdes passthrough).

Tracks GitHub issue #1342 (ingestion test coverage).
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.sandbox.csv_parser import (
    _collect_value_normalizations,
    _normalize_for_rules,
    _parse_csv_to_events,
    get_erp_presets,
)


# ===========================================================================
# get_erp_presets
# ===========================================================================

class TestGetErpPresets:

    def test_returns_dict_with_known_presets(self):
        presets = get_erp_presets()
        assert isinstance(presets, dict)
        assert "generic" in presets
        assert "produce_pro" in presets
        assert "sap_b1" in presets
        assert "aptean" in presets

    def test_presets_have_human_labels(self):
        presets = get_erp_presets()
        assert presets["generic"] == "Generic / Auto-detect"
        assert presets["produce_pro"] == "Produce Pro"
        assert presets["sap_b1"] == "SAP Business One"
        assert presets["aptean"] == "Aptean (Freshlynx)"

    def test_returns_fresh_dict_each_call(self):
        """Callers must be able to mutate without leaking state."""
        a = get_erp_presets()
        b = get_erp_presets()
        a["generic"] = "MUTATED"
        assert b["generic"] != "MUTATED"


# ===========================================================================
# _parse_csv_to_events — basic happy paths
# ===========================================================================

class TestParseCsvBasics:

    def test_empty_csv_returns_empty_list(self):
        assert _parse_csv_to_events("") == []

    def test_header_only_returns_empty_list(self):
        """A header row with no data rows produces zero events."""
        assert _parse_csv_to_events("cte_type,tlc\n") == []

    def test_single_canonical_row(self):
        csv = (
            "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure\n"
            "harvesting,LOT-1,Romaine,100,cases\n"
        )
        events = _parse_csv_to_events(csv)
        assert len(events) == 1
        e = events[0]
        assert e["cte_type"] == "harvesting"
        assert e["traceability_lot_code"] == "LOT-1"
        assert e["product_description"] == "Romaine"
        assert e["quantity"] == 100.0  # parsed to float
        assert e["unit_of_measure"] == "cases"

    def test_multiple_rows_produce_multiple_events(self):
        csv = (
            "cte_type,tlc\n"
            "harvesting,LOT-A\n"
            "shipping,LOT-B\n"
            "receiving,LOT-C\n"
        )
        events = _parse_csv_to_events(csv)
        assert len(events) == 3
        assert events[0]["traceability_lot_code"] == "LOT-A"
        assert events[2]["traceability_lot_code"] == "LOT-C"

    def test_quantity_non_numeric_falls_back_to_string(self):
        csv = "cte_type,quantity\nharvesting,not-a-number\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["quantity"] == "not-a-number"

    def test_blank_cells_are_ignored(self):
        """Empty/whitespace cells must not overwrite sibling fields."""
        csv = (
            "cte_type,traceability_lot_code,product\n"
            "harvesting,LOT-1,  \n"  # product blank → should not appear
        )
        events = _parse_csv_to_events(csv)
        assert "product_description" not in events[0]

    def test_blank_column_name_is_ignored(self):
        """A header row with an empty column name skips that column without crashing."""
        csv = (
            "cte_type,,product\n"
            "harvesting,ghost,Cheese\n"
        )
        events = _parse_csv_to_events(csv)
        assert events[0]["cte_type"] == "harvesting"
        # "ghost" cell under the blank column is dropped
        assert events[0]["product_description"] == "Cheese"

    def test_whitespace_trimmed_on_values(self):
        csv = "cte_type,tlc\n  harvesting  ,  LOT-1  \n"
        events = _parse_csv_to_events(csv)
        assert events[0]["cte_type"] == "harvesting"
        assert events[0]["traceability_lot_code"] == "LOT-1"

    def test_default_timestamp_when_missing(self):
        csv = "cte_type,tlc\nharvesting,LOT-1\n"
        events = _parse_csv_to_events(csv)
        # Should contain a parseable ISO 8601 string
        ts = events[0]["timestamp"]
        assert isinstance(ts, str)
        assert "T" in ts  # ISO 8601 format


# ===========================================================================
# _parse_csv_to_events — header alias mapping
# ===========================================================================

class TestParseCsvHeaderAliases:

    def test_cte_type_aliases_map_to_canonical(self):
        """'event_type', 'type', etc. all map to cte_type."""
        csv = "event_type,tlc\nharvesting,LOT-1\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["cte_type"] == "harvesting"

    def test_tlc_aliases_map_to_canonical(self):
        csv = "cte_type,lot_number\nharvesting,LOT-42\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["traceability_lot_code"] == "LOT-42"

    def test_product_aliases_map_to_canonical(self):
        csv = "cte_type,tlc,commodity\nharvesting,LOT-1,Blueberries\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["product_description"] == "Blueberries"

    def test_quantity_alias_qty(self):
        csv = "cte_type,tlc,qty\nharvesting,LOT-1,50\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["quantity"] == 50.0

    def test_uom_alias(self):
        csv = "cte_type,tlc,uom\nharvesting,LOT-1,kg\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["unit_of_measure"] == "kg"

    def test_location_name_alias(self):
        csv = "cte_type,tlc,facility\nharvesting,LOT-1,Farm A\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["location_name"] == "Farm A"

    def test_timestamp_alias_event_date(self):
        csv = "cte_type,tlc,event_date\nharvesting,LOT-1,2026-01-01\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["timestamp"] == "2026-01-01"

    def test_supplier_aliases_to_location_name(self):
        csv = "cte_type,tlc,supplier\nharvesting,LOT-1,Acme Produce\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["location_name"] == "Acme Produce"

    def test_column_header_case_insensitive(self):
        csv = "CTE_Type,TLC\nHarvesting,LOT-1\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["cte_type"] == "harvesting"
        assert events[0]["traceability_lot_code"] == "LOT-1"

    def test_column_header_spaces_normalized(self):
        """Headers like 'Event Type' should resolve to 'event_type' → cte_type."""
        csv = "Event Type,TLC\nharvesting,LOT-1\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["cte_type"] == "harvesting"


# ===========================================================================
# _parse_csv_to_events — KDE aliases
# ===========================================================================

class TestParseCsvKdeAliases:

    def test_harvest_date_alias_goes_to_kdes(self):
        csv = "cte_type,tlc,harvest_date\nharvesting,LOT-1,2026-01-01\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["kdes"]["harvest_date"] == "2026-01-01"

    def test_ship_from_location_alias(self):
        csv = "cte_type,tlc,origin\nshipping,LOT-1,Warehouse A\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["kdes"]["ship_from_location"] == "Warehouse A"

    def test_ship_to_location_alias(self):
        csv = "cte_type,tlc,destination\nshipping,LOT-1,Store B\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["kdes"]["ship_to_location"] == "Store B"

    def test_carrier_alias(self):
        csv = "cte_type,tlc,trucker\nshipping,LOT-1,ABC Trucking\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["kdes"]["carrier"] == "ABC Trucking"

    def test_reference_document_alias_bol(self):
        csv = "cte_type,tlc,bol\nshipping,LOT-1,BOL-12345\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["kdes"]["reference_document"] == "BOL-12345"

    def test_input_tlcs_comma_split_into_list(self):
        """Transformation input TLCs are parsed into a list when comma-separated."""
        csv = "cte_type,tlc,input_tlcs\ntransformation,LOT-MEGA,LOT-A,LOT-B\n"
        # Note: the csv above has LOT-B trailing; it will NOT be treated as a
        # new column because csv.DictReader packs extras into None key.
        # Use a quoted form instead for clarity:
        csv = (
            'cte_type,tlc,input_tlcs\n'
            'transformation,LOT-MEGA,"LOT-A,LOT-B"\n'
        )
        events = _parse_csv_to_events(csv)
        assert events[0]["kdes"]["input_traceability_lot_codes"] == ["LOT-A", "LOT-B"]

    def test_input_tlcs_single_value_stays_string(self):
        csv = "cte_type,tlc,input_tlcs\ntransformation,LOT-MEGA,LOT-A\n"
        events = _parse_csv_to_events(csv)
        # Single value with no comma — stored as string
        assert events[0]["kdes"]["input_traceability_lot_codes"] == "LOT-A"

    def test_temperature_alias(self):
        csv = "cte_type,tlc,temp\ncooling,LOT-1,34\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["kdes"]["temperature"] == "34"

    def test_harvester_alias(self):
        csv = "cte_type,tlc,grower\nharvesting,LOT-1,Sunny Farms\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["kdes"]["harvester_business_name"] == "Sunny Farms"


# ===========================================================================
# _parse_csv_to_events — unknown columns
# ===========================================================================

class TestParseCsvUnknownColumns:

    def test_unknown_column_goes_into_kdes_as_is(self):
        """Unrecognized columns must be preserved, not dropped."""
        csv = "cte_type,tlc,custom_field\nharvesting,LOT-1,custom-value\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["kdes"]["custom_field"] == "custom-value"

    def test_unknown_column_lowercased(self):
        csv = "cte_type,tlc,MyWeirdField\nharvesting,LOT-1,hello\n"
        events = _parse_csv_to_events(csv)
        # lowercased + spaces → underscores
        assert events[0]["kdes"]["myweirdfield"] == "hello"


# ===========================================================================
# _parse_csv_to_events — CTE type value normalization
# ===========================================================================

class TestParseCsvCteTypeNormalization:

    @pytest.mark.parametrize("raw,canonical", [
        ("harvest", "harvesting"),
        ("harvested", "harvesting"),
        ("pick", "harvesting"),
        ("h", "harvesting"),
        ("cool", "cooling"),
        ("cooled", "cooling"),
        ("precool", "cooling"),
        ("pack", "initial_packing"),
        ("packed", "initial_packing"),
        ("ip", "initial_packing"),
        ("flbr", "first_land_based_receiving"),
        ("first_receiver", "first_land_based_receiving"),
        ("dock", "first_land_based_receiving"),
        ("ship", "shipping"),
        ("shipped", "shipping"),
        ("dispatch", "shipping"),
        ("receive", "receiving"),
        ("received", "receiving"),
        ("receipt", "receiving"),
        ("rcv", "receiving"),
        ("transform", "transformation"),
        ("process", "transformation"),
        ("mfg", "transformation"),
    ])
    def test_cte_type_alias_normalizes(self, raw, canonical):
        csv = f"cte_type,tlc\n{raw},LOT-1\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["cte_type"] == canonical

    def test_canonical_cte_type_unchanged(self):
        csv = "cte_type,tlc\nharvesting,LOT-1\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["cte_type"] == "harvesting"

    def test_cte_type_dashes_converted_to_underscores(self):
        """Dash-separated CTE values get normalized via the replace("-", "_") step.

        Note: the ``pre-cool`` alias key in _CTE_TYPE_ALIASES uses a dash, so
        after normalization to ``pre_cool`` the lookup misses and the value
        passes through as ``pre_cool`` (a latent data-quality bug in the
        alias table). We assert the observed behavior rather than the
        ideal one to prevent test churn until the alias map is cleaned up.
        """
        csv = "cte_type,tlc\npre-cool,LOT-1\n"
        events = _parse_csv_to_events(csv)
        # Dashes are normalized to underscores by the source code path even
        # if the downstream lookup misses.
        assert events[0]["cte_type"] == "pre_cool"

    def test_cte_type_spaces_converted_to_underscores(self):
        csv = "cte_type,tlc\nfirst receiver,LOT-1\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["cte_type"] == "first_land_based_receiving"

    def test_cte_type_without_alias_passes_through_lowercased(self):
        """Unknown CTE values are lowercased+normalized but not remapped."""
        csv = "cte_type,tlc\nCUSTOMCTE,LOT-1\n"
        events = _parse_csv_to_events(csv)
        assert events[0]["cte_type"] == "customcte"

    def test_row_without_cte_type_skipped_entirely(self):
        """Rows lacking a cte_type must be dropped — they can't be evaluated."""
        csv = "tlc,product\nLOT-1,Apples\n"
        events = _parse_csv_to_events(csv)
        assert events == []


# ===========================================================================
# _parse_csv_to_events — track_normalizations
# ===========================================================================

class TestParseCsvTrackNormalizations:

    def _extract(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return events[0].get("__normalizations__", []) if events else []

    def test_no_tracking_by_default(self):
        csv = "event_type,tlc\nharvesting,LOT-1\n"
        events = _parse_csv_to_events(csv)
        assert "__normalizations__" not in events[0]

    def test_header_alias_logged(self):
        csv = "event_type,tlc\nharvesting,LOT-1\n"
        events = _parse_csv_to_events(csv, track_normalizations=True)
        norms = self._extract(events)
        # event_type → cte_type is a rename; tlc → traceability_lot_code is too
        action_types = [n["action_type"] for n in norms]
        assert "header_alias" in action_types
        fields = [n["field"] for n in norms if n["action_type"] == "header_alias"]
        assert "cte_type" in fields
        assert "traceability_lot_code" in fields

    def test_header_alias_deduped(self):
        """Same alias seen on multiple rows logged only once."""
        csv = (
            "event_type,tlc\n"
            "harvesting,LOT-1\n"
            "shipping,LOT-2\n"
        )
        events = _parse_csv_to_events(csv, track_normalizations=True)
        norms = self._extract(events)
        cte_type_aliases = [n for n in norms
                            if n["field"] == "cte_type" and n["action_type"] == "header_alias"]
        assert len(cte_type_aliases) == 1

    def test_canonical_column_name_not_logged(self):
        """If the column already uses canonical name, no rename is recorded."""
        csv = "cte_type,traceability_lot_code\nharvesting,LOT-1\n"
        events = _parse_csv_to_events(csv, track_normalizations=True)
        norms = self._extract(events)
        header_aliases = [n for n in norms if n["action_type"] == "header_alias"]
        assert header_aliases == []

    def test_kde_alias_logged(self):
        csv = "cte_type,tlc,bol\nshipping,LOT-1,BOL-123\n"
        events = _parse_csv_to_events(csv, track_normalizations=True)
        norms = self._extract(events)
        kde_aliases = [n for n in norms
                       if n["action_type"] == "header_alias"
                       and n["field"] == "reference_document"]
        assert kde_aliases

    def test_kde_canonical_column_not_logged(self):
        csv = "cte_type,tlc,reference_document\nshipping,LOT-1,BOL-123\n"
        events = _parse_csv_to_events(csv, track_normalizations=True)
        norms = self._extract(events)
        kde_aliases = [n for n in norms
                       if n["action_type"] == "header_alias"
                       and n["field"] == "reference_document"]
        assert kde_aliases == []

    def test_cte_type_value_normalization_logged(self):
        csv = "cte_type,tlc\nreceipt,LOT-1\n"
        events = _parse_csv_to_events(csv, track_normalizations=True)
        norms = self._extract(events)
        cte_norm = [n for n in norms if n["action_type"] == "cte_type_normalize"]
        assert cte_norm
        assert cte_norm[0]["original"] == "receipt"
        assert cte_norm[0]["normalized"] == "receiving"

    def test_cte_type_canonical_value_not_logged(self):
        csv = "cte_type,tlc\nharvesting,LOT-1\n"
        events = _parse_csv_to_events(csv, track_normalizations=True)
        norms = self._extract(events)
        cte_norm = [n for n in norms if n["action_type"] == "cte_type_normalize"]
        assert cte_norm == []

    def test_cte_type_normalization_records_row_index(self):
        """Each row's CTE normalization records the row it came from."""
        csv = (
            "cte_type,tlc\n"
            "harvesting,LOT-1\n"  # canonical, not logged
            "receipt,LOT-2\n"     # normalized: row 1
            "ship,LOT-3\n"        # normalized: row 2
        )
        events = _parse_csv_to_events(csv, track_normalizations=True)
        norms = self._extract(events)
        cte_norms = [n for n in norms if n["action_type"] == "cte_type_normalize"]
        # Row indices 1 (receipt→receiving) and 2 (ship→shipping)
        indices = sorted(n["event_index"] for n in cte_norms)
        assert indices == [1, 2]

    def test_no_events_no_normalizations_attached(self):
        """Empty CSV with tracking enabled returns [] — no place to attach."""
        events = _parse_csv_to_events("", track_normalizations=True)
        assert events == []


# ===========================================================================
# _parse_csv_to_events — ERP presets
# ===========================================================================

class TestParseCsvErpPresets:

    def test_produce_pro_preset_maps_trans_type(self):
        csv = "trans_type,item_no,qty_shipped\nshipping,LOT-1,100\n"
        events = _parse_csv_to_events(csv, erp_preset="produce_pro")
        assert events[0]["cte_type"] == "shipping"
        assert events[0]["traceability_lot_code"] == "LOT-1"
        assert events[0]["quantity"] == 100.0

    def test_produce_pro_preset_maps_bol_no(self):
        """bol_no → reference_document via the preset column map.

        Since the preset routes ``bol_no`` through the top-level
        ``col_map`` lookup (not the KDE alias map), the result lands on
        the event dict directly rather than inside ``kdes``.
        """
        csv = "trans_type,item_no,bol_no\nshipping,LOT-1,BOL-X\n"
        events = _parse_csv_to_events(csv, erp_preset="produce_pro")
        assert events[0]["reference_document"] == "BOL-X"

    def test_sap_b1_preset_maps_itemcode(self):
        """sap_b1 has no CTE-type column alias, so the CSV must provide
        cte_type directly for the row to be emitted."""
        csv = "cte_type,itemcode,dscription\nshipping,LOT-SAP,Tomatoes\n"
        events = _parse_csv_to_events(csv, erp_preset="sap_b1")
        assert events[0]["traceability_lot_code"] == "LOT-SAP"
        assert events[0]["product_description"] == "Tomatoes"

    def test_aptean_preset_maps_transaction_type(self):
        csv = "transaction_type,lot_number,qty\nharvesting,LOT-APT,200\n"
        events = _parse_csv_to_events(csv, erp_preset="aptean")
        assert events[0]["cte_type"] == "harvesting"
        assert events[0]["traceability_lot_code"] == "LOT-APT"
        assert events[0]["quantity"] == 200.0

    def test_unknown_preset_silently_ignored(self):
        """An invalid preset name just uses the default column map."""
        csv = "cte_type,tlc\nharvesting,LOT-1\n"
        events = _parse_csv_to_events(csv, erp_preset="nonexistent")
        assert events[0]["cte_type"] == "harvesting"

    def test_preset_does_not_override_existing_canonical(self):
        """setdefault means default map takes precedence over preset."""
        csv = "cte_type,lot_no,qty\nharvesting,LOT-1,5\n"
        events = _parse_csv_to_events(csv, erp_preset="produce_pro")
        # lot_no → traceability_lot_code in BOTH maps, so the value is mapped
        assert events[0]["traceability_lot_code"] == "LOT-1"

    def test_preset_none_equivalent_to_no_preset(self):
        csv = "cte_type,tlc\nharvesting,LOT-1\n"
        a = _parse_csv_to_events(csv, erp_preset=None)
        b = _parse_csv_to_events(csv)
        assert a[0]["cte_type"] == b[0]["cte_type"]


# ===========================================================================
# _collect_value_normalizations
# ===========================================================================

class TestCollectValueNormalizations:

    def test_empty_inputs_return_empty(self):
        assert _collect_value_normalizations([], []) == []

    def test_no_uom_no_cte_changes_returns_empty(self):
        raw = [{"cte_type": "harvesting", "unit_of_measure": "lbs"}]
        canonical = [{"event_type": "harvesting", "unit_of_measure": "lbs"}]
        assert _collect_value_normalizations(raw, canonical) == []

    def test_uom_shift_recorded(self):
        raw = [{"cte_type": "harvesting", "unit_of_measure": "pounds"}]
        canonical = [{"event_type": "harvesting", "unit_of_measure": "lbs"}]
        norms = _collect_value_normalizations(raw, canonical)
        uom_norms = [n for n in norms if n["action_type"] == "uom_normalize"]
        assert len(uom_norms) == 1
        assert uom_norms[0]["original"] == "pounds"
        assert uom_norms[0]["normalized"] == "lbs"
        assert uom_norms[0]["event_index"] == 0

    def test_cte_type_shift_recorded(self):
        raw = [{"cte_type": "receipt", "unit_of_measure": ""}]
        canonical = [{"event_type": "receiving", "unit_of_measure": ""}]
        norms = _collect_value_normalizations(raw, canonical)
        cte_norms = [n for n in norms if n["action_type"] == "cte_type_normalize"]
        assert len(cte_norms) == 1
        assert cte_norms[0]["original"] == "receipt"
        assert cte_norms[0]["normalized"] == "receiving"

    def test_duplicate_uom_suppressed(self):
        """If the same UOM mapping appears in multiple rows, log it once."""
        raw = [
            {"cte_type": "harvesting", "unit_of_measure": "pounds"},
            {"cte_type": "harvesting", "unit_of_measure": "pounds"},
        ]
        canonical = [
            {"event_type": "harvesting", "unit_of_measure": "lbs"},
            {"event_type": "harvesting", "unit_of_measure": "lbs"},
        ]
        norms = _collect_value_normalizations(raw, canonical)
        uom_norms = [n for n in norms if n["action_type"] == "uom_normalize"]
        assert len(uom_norms) == 1

    def test_duplicate_cte_suppressed(self):
        raw = [
            {"cte_type": "receipt"},
            {"cte_type": "receipt"},
        ]
        canonical = [
            {"event_type": "receiving"},
            {"event_type": "receiving"},
        ]
        norms = _collect_value_normalizations(raw, canonical)
        cte_norms = [n for n in norms if n["action_type"] == "cte_type_normalize"]
        assert len(cte_norms) == 1

    def test_blank_raw_uom_skipped(self):
        raw = [{"unit_of_measure": ""}]
        canonical = [{"unit_of_measure": "lbs"}]
        norms = _collect_value_normalizations(raw, canonical)
        assert [n for n in norms if n["action_type"] == "uom_normalize"] == []

    def test_blank_canonical_uom_skipped(self):
        raw = [{"unit_of_measure": "pounds"}]
        canonical = [{"unit_of_measure": ""}]
        norms = _collect_value_normalizations(raw, canonical)
        assert [n for n in norms if n["action_type"] == "uom_normalize"] == []

    def test_blank_raw_cte_skipped(self):
        raw = [{"cte_type": ""}]
        canonical = [{"event_type": "receiving"}]
        norms = _collect_value_normalizations(raw, canonical)
        assert [n for n in norms if n["action_type"] == "cte_type_normalize"] == []

    def test_blank_canonical_cte_skipped(self):
        raw = [{"cte_type": "receipt"}]
        canonical = [{"event_type": ""}]
        norms = _collect_value_normalizations(raw, canonical)
        assert [n for n in norms if n["action_type"] == "cte_type_normalize"] == []

    def test_whitespace_trimmed_for_comparison(self):
        """Leading/trailing whitespace should not masquerade as a normalization."""
        raw = [{"cte_type": "  harvesting  ", "unit_of_measure": "  lbs  "}]
        canonical = [{"event_type": "harvesting", "unit_of_measure": "lbs"}]
        norms = _collect_value_normalizations(raw, canonical)
        assert norms == []

    def test_both_uom_and_cte_shifts_in_single_row(self):
        raw = [{"cte_type": "receipt", "unit_of_measure": "pounds"}]
        canonical = [{"event_type": "receiving", "unit_of_measure": "lbs"}]
        norms = _collect_value_normalizations(raw, canonical)
        action_types = {n["action_type"] for n in norms}
        assert action_types == {"uom_normalize", "cte_type_normalize"}

    def test_event_index_correct_across_rows(self):
        raw = [
            {"cte_type": "harvesting", "unit_of_measure": "kilos"},  # index 0
            {"cte_type": "receipt", "unit_of_measure": "lbs"},        # index 1
        ]
        canonical = [
            {"event_type": "harvesting", "unit_of_measure": "kg"},
            {"event_type": "receiving", "unit_of_measure": "lbs"},
        ]
        norms = _collect_value_normalizations(raw, canonical)
        uom = [n for n in norms if n["action_type"] == "uom_normalize"][0]
        cte = [n for n in norms if n["action_type"] == "cte_type_normalize"][0]
        assert uom["event_index"] == 0
        assert cte["event_index"] == 1


# ===========================================================================
# _normalize_for_rules
# ===========================================================================

class TestNormalizeForRules:

    def test_returns_dict_with_uuid_event_id(self):
        result = _normalize_for_rules({"cte_type": "harvesting"})
        assert "event_id" in result
        # UUID4 canonical form: 36 chars with dashes
        assert len(result["event_id"]) == 36

    def test_maps_cte_type_to_event_type(self):
        result = _normalize_for_rules({"cte_type": "shipping"})
        assert result["event_type"] == "shipping"

    def test_preserves_tlc_and_product(self):
        ev = {
            "cte_type": "harvesting",
            "traceability_lot_code": "LOT-1",
            "product_description": "Romaine",
        }
        result = _normalize_for_rules(ev)
        assert result["traceability_lot_code"] == "LOT-1"
        assert result["product_reference"] == "Romaine"

    def test_preserves_quantity_uom_and_timestamp(self):
        ev = {
            "cte_type": "harvesting",
            "quantity": 50.0,
            "unit_of_measure": "lbs",
            "timestamp": "2026-01-01T00:00:00Z",
        }
        result = _normalize_for_rules(ev)
        assert result["quantity"] == 50.0
        assert result["unit_of_measure"] == "lbs"
        assert result["event_timestamp"] == "2026-01-01T00:00:00Z"

    def test_from_facility_prefers_location_gln(self):
        ev = {
            "cte_type": "harvesting",
            "location_gln": "GLN-123",
            "location_name": "Farm A",
            "kdes": {"ship_from_gln": "GLN-OTHER"},
        }
        result = _normalize_for_rules(ev)
        assert result["from_facility_reference"] == "GLN-123"

    def test_from_facility_falls_back_to_ship_from_gln(self):
        ev = {
            "cte_type": "shipping",
            "kdes": {"ship_from_gln": "GLN-A"},
        }
        result = _normalize_for_rules(ev)
        assert result["from_facility_reference"] == "GLN-A"

    def test_from_facility_falls_back_to_ship_from_location(self):
        ev = {
            "cte_type": "shipping",
            "kdes": {"ship_from_location": "Warehouse A"},
        }
        result = _normalize_for_rules(ev)
        assert result["from_facility_reference"] == "Warehouse A"

    def test_from_facility_falls_back_to_location_name(self):
        ev = {"cte_type": "harvesting", "location_name": "Farm A"}
        result = _normalize_for_rules(ev)
        assert result["from_facility_reference"] == "Farm A"

    def test_to_facility_prefers_ship_to_gln(self):
        ev = {
            "cte_type": "shipping",
            "kdes": {
                "ship_to_gln": "GLN-B",
                "ship_to_location": "Store A",
                "receiving_location": "DC-1",
            },
        }
        result = _normalize_for_rules(ev)
        assert result["to_facility_reference"] == "GLN-B"

    def test_to_facility_falls_back_to_ship_to_location(self):
        ev = {
            "cte_type": "shipping",
            "kdes": {"ship_to_location": "Store A"},
        }
        result = _normalize_for_rules(ev)
        assert result["to_facility_reference"] == "Store A"

    def test_to_facility_falls_back_to_receiving_location(self):
        ev = {
            "cte_type": "receiving",
            "kdes": {"receiving_location": "DC-1"},
        }
        result = _normalize_for_rules(ev)
        assert result["to_facility_reference"] == "DC-1"

    def test_shipping_override_from_facility_from_location_name(self):
        """For shipping events, location_name is the fallback from-facility."""
        ev = {"cte_type": "shipping", "location_name": "Shipping Dock"}
        result = _normalize_for_rules(ev)
        assert result["from_facility_reference"] == "Shipping Dock"

    def test_receiving_override_to_facility_from_location_name(self):
        """For receiving events, location_name becomes the to-facility."""
        ev = {"cte_type": "receiving", "location_name": "Receiving Dock"}
        result = _normalize_for_rules(ev)
        assert result["to_facility_reference"] == "Receiving Dock"

    def test_receiving_override_to_facility_from_gln_when_no_name(self):
        """For receiving events with only GLN, it's used as the to-facility."""
        ev = {"cte_type": "receiving", "location_gln": "GLN-RCV"}
        result = _normalize_for_rules(ev)
        # The "from_facility" starts as location_gln, so to-facility fallback
        # is `event.get("location_gln")` — yes, same value.
        assert result["to_facility_reference"] == "GLN-RCV"

    def test_from_entity_from_kdes_ship_from_entity(self):
        ev = {
            "cte_type": "shipping",
            "kdes": {"ship_from_entity": "Entity A"},
        }
        result = _normalize_for_rules(ev)
        assert result["from_entity_reference"] == "Entity A"

    def test_from_entity_falls_back_to_harvester_business_name(self):
        ev = {
            "cte_type": "harvesting",
            "kdes": {"harvester_business_name": "Sunny Farms"},
        }
        result = _normalize_for_rules(ev)
        assert result["from_entity_reference"] == "Sunny Farms"

    def test_to_entity_from_ship_to_entity(self):
        ev = {
            "cte_type": "shipping",
            "kdes": {"ship_to_entity": "Buyer Co"},
        }
        result = _normalize_for_rules(ev)
        assert result["to_entity_reference"] == "Buyer Co"

    def test_to_entity_falls_back_to_immediate_previous_source(self):
        ev = {
            "cte_type": "receiving",
            "kdes": {"immediate_previous_source": "Supplier X"},
        }
        result = _normalize_for_rules(ev)
        assert result["to_entity_reference"] == "Supplier X"

    def test_transport_from_carrier(self):
        ev = {"cte_type": "shipping", "kdes": {"carrier": "ABC Trucking"}}
        result = _normalize_for_rules(ev)
        assert result["transport_reference"] == "ABC Trucking"

    def test_transport_falls_back_to_transport_reference(self):
        ev = {
            "cte_type": "shipping",
            "kdes": {"transport_reference": "TRANS-999"},
        }
        result = _normalize_for_rules(ev)
        assert result["transport_reference"] == "TRANS-999"

    def test_kdes_passthrough_copied_not_referenced(self):
        """kdes must be copied so callers can mutate without affecting input."""
        orig_kdes = {"foo": "bar"}
        ev = {"cte_type": "harvesting", "kdes": orig_kdes}
        result = _normalize_for_rules(ev)
        result["kdes"]["foo"] = "MUTATED"
        assert orig_kdes["foo"] == "bar"

    def test_empty_event_defaults(self):
        """An empty event still produces a valid shape with defaults."""
        result = _normalize_for_rules({})
        assert result["event_type"] == ""
        assert result["traceability_lot_code"] == ""
        assert result["product_reference"] == ""
        assert result["quantity"] is None
        assert result["unit_of_measure"] == ""
        assert result["event_timestamp"] == ""
        assert result["from_facility_reference"] is None
        assert result["to_facility_reference"] is None
        assert result["from_entity_reference"] is None
        assert result["to_entity_reference"] is None
        assert result["transport_reference"] is None
        assert result["kdes"] == {}

    def test_each_call_produces_unique_event_id(self):
        a = _normalize_for_rules({"cte_type": "harvesting"})
        b = _normalize_for_rules({"cte_type": "harvesting"})
        assert a["event_id"] != b["event_id"]
