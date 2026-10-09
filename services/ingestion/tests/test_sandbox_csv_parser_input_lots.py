"""Focused coverage for ``input_lot_codes`` in ``app/sandbox/csv_parser.py``.

The main CSV parsing entry points (``_parse_csv_to_events``,
``_normalize_for_rules``, ``_collect_value_normalizations``,
``get_erp_presets``) already have thorough coverage in
``test_sandbox_csv_parser_1342.py``. The one public helper with no direct
test is ``input_lot_codes``, which the tracer and evaluators use to read
transformation input lots from event KDEs, including the legacy sandbox
key spelling.
"""

from __future__ import annotations

from app.sandbox.csv_parser import _parse_csv_to_events, input_lot_codes


class TestInputLotCodes:
    def test_none_returns_empty_list(self):
        assert input_lot_codes(None) == []

    def test_empty_dict_returns_empty_list(self):
        assert input_lot_codes({}) == []

    def test_list_value_returned_as_is(self):
        assert input_lot_codes({"input_lot_codes": ["LOT-A", "LOT-B"]}) == ["LOT-A", "LOT-B"]

    def test_comma_separated_string_is_split(self):
        assert input_lot_codes({"input_lot_codes": "LOT-A,LOT-B"}) == ["LOT-A", "LOT-B"]

    def test_whitespace_is_trimmed_and_blanks_dropped(self):
        assert input_lot_codes({"input_lot_codes": "  LOT-A ,, LOT-B  "}) == ["LOT-A", "LOT-B"]

    def test_whitespace_only_string_returns_empty_list(self):
        assert input_lot_codes({"input_lot_codes": "   "}) == []

    def test_legacy_key_fallback(self):
        kdes = {"input_traceability_lot_codes": "LOT-A,LOT-B"}
        assert input_lot_codes(kdes) == ["LOT-A", "LOT-B"]

    def test_durable_key_wins_over_legacy_key(self):
        kdes = {
            "input_lot_codes": ["LOT-NEW"],
            "input_traceability_lot_codes": ["LOT-OLD"],
        }
        assert input_lot_codes(kdes) == ["LOT-NEW"]

    def test_empty_durable_value_falls_through_to_legacy(self):
        kdes = {"input_lot_codes": "", "input_traceability_lot_codes": "LOT-OLD"}
        assert input_lot_codes(kdes) == ["LOT-OLD"]

    def test_empty_list_durable_value_falls_through_to_legacy(self):
        kdes = {"input_lot_codes": [], "input_traceability_lot_codes": ["LOT-OLD"]}
        assert input_lot_codes(kdes) == ["LOT-OLD"]

    def test_tuple_and_set_values_are_coerced(self):
        assert input_lot_codes({"input_lot_codes": ("LOT-A", "LOT-B")}) == ["LOT-A", "LOT-B"]
        assert input_lot_codes({"input_lot_codes": {"LOT-A"}}) == ["LOT-A"]

    def test_unexpected_type_returns_empty_list(self):
        assert input_lot_codes({"input_lot_codes": 42}) == []
        assert input_lot_codes({"input_lot_codes": {"lot": "LOT-A"}}) == []

    def test_unrelated_kdes_return_empty_list(self):
        assert input_lot_codes({"carrier": "ABC Trucking"}) == []


class TestInputLotCodesRoundTrip:
    def test_parsed_transformation_row_feeds_input_lot_codes(self):
        csv_text = 'cte_type,tlc,input_tlcs\ntransformation,LOT-MEGA,"LOT-A,LOT-B"\n'
        events = _parse_csv_to_events(csv_text)
        assert len(events) == 1
        assert input_lot_codes(events[0]["kdes"]) == ["LOT-A", "LOT-B"]

    def test_row_without_inputs_has_no_input_lots(self):
        csv_text = "cte_type,tlc\nharvesting,LOT-1\n"
        events = _parse_csv_to_events(csv_text)
        assert input_lot_codes(events[0]["kdes"]) == []
