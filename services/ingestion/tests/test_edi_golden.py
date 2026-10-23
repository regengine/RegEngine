"""Data-free X12 parser and extractor shape checks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.edi_ingestion.extractors import _extract_fields_for_set  # noqa: E402
from app.edi_ingestion.parser import (  # noqa: E402
    _detect_transaction_set,
    _parse_x12_segments,
    _split_transaction_sets,
)
from app.edi_ingestion.transaction_sets import _SUPPORTED_TRANSACTION_SETS  # noqa: E402


def test_empty_input_has_no_transaction_sets() -> None:
    segments = _parse_x12_segments("")
    assert segments == []
    assert _detect_transaction_set(segments) is None
    assert _split_transaction_sets(segments) == []


def test_empty_headers_have_no_transaction_sets() -> None:
    segments = _parse_x12_segments("ISA*~GS~GE~IEA~")
    assert [segment[0] for segment in segments] == ["ISA", "GS", "GE", "IEA"]
    assert _detect_transaction_set(segments) is None
    assert _split_transaction_sets(segments) == []


@pytest.mark.parametrize("transaction_set", sorted(_SUPPORTED_TRANSACTION_SETS))
def test_extractors_return_empty_shapes_without_records(transaction_set: str) -> None:
    extracted = _extract_fields_for_set(transaction_set, [])
    assert isinstance(extracted, dict)
    assert extracted
    assert extracted["sender_id"] is None
    assert extracted["receiver_id"] is None
    assert extracted["envelope_mismatch"] is False
    assert all(value is None or value is False or value == [] or value == {} for value in extracted.values())


def test_unsupported_extractor_returns_no_fields() -> None:
    assert _extract_fields_for_set("", []) == {}
