"""Unit tests for ``app.epcis.extraction`` — issue #1342.

Thin extraction helpers with zero prior test coverage. Callers in
``app.epcis.{validation,persistence,normalization}`` rely on these
for lot / location / party ID extraction out of EPCIS payloads.

The module has three pure helpers:
  - ``_extract_lot_data``: picks lot_code (``cbvmda:lotNumber`` or
    ``lotNumber``) and TLC (``fsma:traceabilityLotCode`` or lot_code).
  - ``_extract_location_id``: pulls ``.id`` out of a nested dict.
  - ``_extract_party_id``: pulls ``.<nested_key>`` out of the first
    item of a list.

All three return ``""`` on missing / malformed input rather than
raising — EPCIS payloads in the wild are inconsistently shaped and
the pipeline must degrade gracefully instead of 500'ing on a missing
lot ID.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


from app.epcis.extraction import (  # noqa: E402
    _extract_lot_data,
    _extract_location_id,
    _extract_party_id,
)


# ---------------------------------------------------------------------------
# _extract_lot_data
# ---------------------------------------------------------------------------


class TestExtractLotData:
    def test_none_ilmd_returns_two_empty_strings(self):
        # None input — pipeline passes this when the EPCIS event has
        # no ilmd block at all. Must not raise AttributeError.
        lot_code, tlc = _extract_lot_data(None)
        assert lot_code == ""
        assert tlc == ""

    def test_empty_dict_returns_two_empty_strings(self):
        # ``if not ilmd`` matches empty dict too.
        assert _extract_lot_data({}) == ("", "")

    def test_cbvmda_lot_number_preferred(self):
        # CBV-namespaced key wins over the bare one (EPCIS 2.0 standard
        # format). Pin the precedence so a cleanup can't silently flip.
        ilmd = {
            "cbvmda:lotNumber": "LOT-A",
            "lotNumber": "LOT-B",
        }
        lot_code, tlc = _extract_lot_data(ilmd)
        assert lot_code == "LOT-A"
        # TLC defaults to lot_code when fsma field is absent.
        assert tlc == "LOT-A"

    def test_falls_back_to_bare_lot_number(self):
        ilmd = {"lotNumber": "LOT-123"}
        lot_code, tlc = _extract_lot_data(ilmd)
        assert lot_code == "LOT-123"
        assert tlc == "LOT-123"

    def test_fsma_tlc_overrides_lot_code_as_tlc(self):
        # FSMA's traceabilityLotCode is a separate concept from the
        # packaging lot number; when present it becomes the TLC while
        # lot_code stays on the packaging identifier.
        ilmd = {
            "lotNumber": "PACK-LOT-1",
            "fsma:traceabilityLotCode": "TLC-XYZ",
        }
        lot_code, tlc = _extract_lot_data(ilmd)
        assert lot_code == "PACK-LOT-1"
        assert tlc == "TLC-XYZ"

    def test_fsma_tlc_without_lot_code(self):
        # FSMA field present but neither lot_number variant — tlc is
        # still populated, lot_code is "".
        ilmd = {"fsma:traceabilityLotCode": "TLC-ONLY"}
        lot_code, tlc = _extract_lot_data(ilmd)
        assert lot_code == ""
        assert tlc == "TLC-ONLY"

    def test_integer_lot_number_coerced_to_string(self):
        # ``str(...)`` wrap — not all EPCIS producers emit strings for
        # numeric lot numbers.
        ilmd = {"lotNumber": 42}
        lot_code, tlc = _extract_lot_data(ilmd)
        assert lot_code == "42"
        assert tlc == "42"

    def test_none_lot_number_falls_through(self):
        # Explicit ``None`` in the dict — the ``or`` short-circuits
        # to the next key / default.
        ilmd = {
            "cbvmda:lotNumber": None,
            "lotNumber": "LOT-REAL",
        }
        lot_code, tlc = _extract_lot_data(ilmd)
        assert lot_code == "LOT-REAL"

    def test_empty_string_lot_number_falls_through(self):
        # Empty string is also falsy — falls through to the next
        # candidate. Defensible because EPCIS schemas sometimes emit
        # empty elements for "field known to exist but blank".
        ilmd = {"cbvmda:lotNumber": "", "lotNumber": "LOT-REAL"}
        lot_code, tlc = _extract_lot_data(ilmd)
        assert lot_code == "LOT-REAL"

    def test_both_lot_variants_missing_returns_empty(self):
        ilmd = {"other": "field"}
        assert _extract_lot_data(ilmd) == ("", "")


# ---------------------------------------------------------------------------
# _extract_location_id
# ---------------------------------------------------------------------------


class TestExtractLocationId:
    def test_returns_id_from_nested_dict(self):
        payload = {"readPoint": {"id": "urn:epc:id:sgln:0123.456.789"}}
        assert (
            _extract_location_id(payload, "readPoint")
            == "urn:epc:id:sgln:0123.456.789"
        )

    def test_missing_key_returns_empty(self):
        # ``.get(key, {})`` — missing top-level key returns empty dict,
        # which has no ``id``, so "".
        assert _extract_location_id({"other": 1}, "readPoint") == ""

    def test_non_dict_value_returns_empty(self):
        # Defensive against EPCIS producers emitting ``readPoint:
        # "foo"`` instead of the canonical object form.
        assert _extract_location_id({"readPoint": "oops"}, "readPoint") == ""
        assert _extract_location_id({"readPoint": None}, "readPoint") == ""
        assert _extract_location_id({"readPoint": []}, "readPoint") == ""

    def test_empty_dict_returns_empty(self):
        assert _extract_location_id({"readPoint": {}}, "readPoint") == ""

    def test_none_id_returns_empty(self):
        # ``if value`` — None is falsy, so empty string return.
        assert _extract_location_id({"readPoint": {"id": None}}, "readPoint") == ""

    def test_empty_id_returns_empty(self):
        # Empty string id is falsy too.
        assert _extract_location_id({"readPoint": {"id": ""}}, "readPoint") == ""

    def test_integer_id_coerced_to_string(self):
        assert _extract_location_id({"readPoint": {"id": 42}}, "readPoint") == "42"

    def test_key_parameter_selects_the_field(self):
        # Same function services both ``readPoint`` and ``bizLocation``
        # — pin that the key parameter actually does the lookup.
        payload = {
            "readPoint": {"id": "READ"},
            "bizLocation": {"id": "BIZ"},
        }
        assert _extract_location_id(payload, "readPoint") == "READ"
        assert _extract_location_id(payload, "bizLocation") == "BIZ"


# ---------------------------------------------------------------------------
# _extract_party_id
# ---------------------------------------------------------------------------


class TestExtractPartyId:
    def test_pulls_nested_key_from_first_list_item(self):
        payload = {
            "sourceList": [
                {"source": "urn:epc:id:gln:A"},
                {"source": "urn:epc:id:gln:B"},
            ]
        }
        assert (
            _extract_party_id(payload, "sourceList", "source")
            == "urn:epc:id:gln:A"
        )

    def test_missing_top_key_returns_empty(self):
        assert _extract_party_id({}, "sourceList", "source") == ""

    def test_non_list_value_returns_empty(self):
        # Guards against EPCIS producers emitting ``sourceList: {...}``
        # (object) instead of list.
        assert _extract_party_id({"sourceList": {}}, "sourceList", "source") == ""
        assert _extract_party_id({"sourceList": None}, "sourceList", "source") == ""
        assert _extract_party_id({"sourceList": "x"}, "sourceList", "source") == ""

    def test_empty_list_returns_empty(self):
        assert _extract_party_id({"sourceList": []}, "sourceList", "source") == ""

    def test_first_item_not_dict_returns_empty(self):
        # ``first = items[0] if isinstance(items[0], dict) else {}`` —
        # non-dict first item falls through to empty-dict lookup,
        # returning "".
        assert (
            _extract_party_id(
                {"sourceList": ["str-not-dict"]}, "sourceList", "source"
            )
            == ""
        )
        assert (
            _extract_party_id(
                {"sourceList": [123]}, "sourceList", "source"
            )
            == ""
        )

    def test_missing_nested_key_returns_empty(self):
        assert (
            _extract_party_id(
                {"sourceList": [{"other": "x"}]}, "sourceList", "source"
            )
            == ""
        )

    def test_none_nested_value_returns_empty(self):
        assert (
            _extract_party_id(
                {"sourceList": [{"source": None}]}, "sourceList", "source"
            )
            == ""
        )

    def test_empty_nested_value_returns_empty(self):
        assert (
            _extract_party_id(
                {"sourceList": [{"source": ""}]}, "sourceList", "source"
            )
            == ""
        )

    def test_integer_nested_value_coerced_to_string(self):
        assert (
            _extract_party_id(
                {"sourceList": [{"source": 9}]}, "sourceList", "source"
            )
            == "9"
        )

    def test_second_item_ignored(self):
        # Pin first-item-only behavior — if later callers need "all
        # sources" they'll have to add a new helper instead of
        # silently changing this one.
        payload = {
            "sourceList": [
                {"source": "A"},
                {"source": "B"},
            ]
        }
        assert _extract_party_id(payload, "sourceList", "source") == "A"

    @pytest.mark.parametrize(
        "key,nested,expected",
        [
            ("sourceList", "source", "urn:epc:id:sgln:SRC"),
            ("destinationList", "destination", "urn:epc:id:sgln:DST"),
        ],
    )
    def test_key_and_nested_key_parameters_select_fields(
        self, key, nested, expected
    ):
        # Function services sourceList/destinationList with
        # source/destination nested keys. Parameterize to pin both
        # paths exercise the same code.
        payload = {
            "sourceList": [{"source": "urn:epc:id:sgln:SRC"}],
            "destinationList": [{"destination": "urn:epc:id:sgln:DST"}],
        }
        assert _extract_party_id(payload, key, nested) == expected
