"""TD5 projection must read carrier data, not neighboring qualifier codes."""

import pytest
from app.edi_ingestion.extractors import _extract_856_fields


@pytest.mark.parametrize(
    ("segment", "expected"),
    [
        (["TD5", "", "2", "ColdExpress"], "ColdExpress"),
        (["TD5", "B", "2", "UPSN", "M", "Carrier name"], "UPSN"),
        (["TD5", "", "", "", "M", "Cold Express Logistics"], "Cold Express Logistics"),
        (["TD5", "", "2", " ", "M", "Cold Express Logistics"], "Cold Express Logistics"),
        (["TD5", "", "2"], None),
        (["TD5", "B", "", "", "M"], None),
        (["TD5", "B", "", "", "", "", "CC", "OR", "PDX"], None),
        (["TD5", "", "2", "  UPSN  "], "UPSN"),
        (["TD5"], None),
    ],
)
def test_carrier_uses_identification_or_routing_field(segment, expected):
    assert _extract_856_fields([segment])["carrier"] == expected


def test_empty_td5_cannot_mask_later_carrier():
    segments = [["TD5", "", "2"], ["TD5", "", "2", "UPSN"]]
    assert _extract_856_fields(segments)["carrier"] == "UPSN"


def test_first_source_carrier_is_preserved():
    segments = [["TD5", "", "2", "UPSN"], ["TD5", "", "2", "FDEG"]]
    assert _extract_856_fields(segments)["carrier"] == "UPSN"
