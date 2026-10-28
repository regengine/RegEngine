"""Unit tests for ``app.epcis.extraction`` — empty and malformed inputs only.

Lot precedence, identifier parsing, and coercion of a present value need a
real EPCIS record. Those paths are not exercised here.
"""

from __future__ import annotations

import sys
from pathlib import Path

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.epcis.extraction import (  # noqa: E402
    _extract_event_lot,
    _extract_location_id,
    _extract_lot_data,
    _extract_party_id,
    _identifier_strings,
    _ilmd_dict,
    _lot_from_identifier,
    _lot_level_identifiers,
)


class TestExtractLotData:
    def test_none_ilmd_returns_two_empty_strings(self):
        lot_code, tlc = _extract_lot_data(None)
        assert lot_code == ""
        assert tlc == ""

    def test_empty_dict_returns_two_empty_strings(self):
        assert _extract_lot_data({}) == ("", "")

    def test_none_lot_number_falls_through(self):
        assert _extract_lot_data({"cbvmda:lotNumber": None}) == ("", "")

    def test_empty_string_lot_number_falls_through(self):
        assert _extract_lot_data({"cbvmda:lotNumber": ""}) == ("", "")

    def test_both_lot_variants_missing_returns_empty(self):
        assert _extract_lot_data({"other": "field"}) == ("", "")


class TestExtractLocationId:
    def test_missing_key_returns_empty(self):
        assert _extract_location_id({"other": 1}, "readPoint") == ""

    def test_non_dict_value_returns_empty(self):
        assert _extract_location_id({"readPoint": "oops"}, "readPoint") == ""
        assert _extract_location_id({"readPoint": None}, "readPoint") == ""
        assert _extract_location_id({"readPoint": []}, "readPoint") == ""

    def test_empty_dict_returns_empty(self):
        assert _extract_location_id({"readPoint": {}}, "readPoint") == ""

    def test_none_id_returns_empty(self):
        assert _extract_location_id({"readPoint": {"id": None}}, "readPoint") == ""

    def test_empty_id_returns_empty(self):
        assert _extract_location_id({"readPoint": {"id": ""}}, "readPoint") == ""


class TestExtractPartyId:
    def test_missing_top_key_returns_empty(self):
        assert _extract_party_id({}, "sourceList", "source") == ""

    def test_non_list_value_returns_empty(self):
        assert _extract_party_id({"sourceList": {}}, "sourceList", "source") == ""
        assert _extract_party_id({"sourceList": None}, "sourceList", "source") == ""
        assert _extract_party_id({"sourceList": "x"}, "sourceList", "source") == ""

    def test_empty_list_returns_empty(self):
        assert _extract_party_id({"sourceList": []}, "sourceList", "source") == ""

    def test_first_item_not_dict_returns_empty(self):
        assert _extract_party_id({"sourceList": ["str-not-dict"]}, "sourceList", "source") == ""
        assert _extract_party_id({"sourceList": [123]}, "sourceList", "source") == ""

    def test_missing_nested_key_returns_empty(self):
        assert _extract_party_id({"sourceList": [{"other": "x"}]}, "sourceList", "source") == ""

    def test_none_nested_value_returns_empty(self):
        assert _extract_party_id({"sourceList": [{"source": None}]}, "sourceList", "source") == ""

    def test_empty_nested_value_returns_empty(self):
        assert _extract_party_id({"sourceList": [{"source": ""}]}, "sourceList", "source") == ""


class TestEmptyEventHelpers:
    def test_identifier_helpers_on_empty_input(self):
        assert _lot_from_identifier(None) is None
        assert _lot_from_identifier("") is None
        assert _lot_from_identifier("   ") is None
        assert _identifier_strings(None) == []
        assert _lot_level_identifiers({}) == []
        assert _ilmd_dict({}) is None
        assert _extract_event_lot({}) == ("", "")


class TestLosslessLotIdentitySel598:
    """Legacy path keeps the full class URI as TLC (SEL-598)."""

    def test_lgtin_tlc_is_full_uri_not_segment(self):
        lgtin = "urn:epc:class:lgtin:0614141.107346.LotA"
        lot_code, tlc = _extract_event_lot(
            {"type": "ObjectEvent", "quantityList": [{"epcClass": lgtin, "quantity": 1}]}
        )
        assert lot_code == "LotA"
        assert tlc == lgtin

    def test_digital_link_tlc_is_full_uri(self):
        dl = "https://id.gs1.org/01/00012345678905/10/LotRebuild"
        lot_code, tlc = _lot_from_identifier(dl)
        assert lot_code == "LotRebuild"
        assert tlc == dl

