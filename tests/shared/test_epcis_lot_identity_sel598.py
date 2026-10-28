"""SEL-598 / H2: lossless EPCIS lot identity (structural + synthetic URIs).

Synthetic identifiers only (A-2165). No partner data. No compliance claims.
"""

from __future__ import annotations

import os

import pytest
from shared.canonical_event import (
    _epcis_traceability_lot_code,
    _epcis_transformation_inputs,
)
from shared.epcis_lot_identity import (
    is_full_class_uri,
    lossless_enabled,
    lot_token_only,
    normalize_epcis_lot,
    parse_class_uri,
)

# Synthetic GS1-shaped IDs (not partner data). GTIN 00614141123452 check digit
# is illustrative; normalize_epcis_lot rebuilds Digital Links from digits.
SYN_GTIN14 = "00614141123452"
SYN_LOT = "LOT-ROM-2026-0312A"
SYN_LGTIN = f"urn:epc:class:lgtin:0614141.123452.{SYN_LOT}"
SYN_DL = f"https://id.gs1.org/01/{SYN_GTIN14}/10/{SYN_LOT}"
SYN_LGTIN_OTHER_GTIN = f"urn:epc:class:lgtin:0614141.999990.{SYN_LOT}"


def test_lgtin_canonical_not_truncated_on_parse():
    parsed = parse_class_uri(SYN_LGTIN)
    assert parsed is not None
    assert parsed.is_full_class_uri is True
    assert parsed.canonical_id == SYN_LGTIN
    assert parsed.lot_token == SYN_LOT
    assert parsed.canonical_id != SYN_LOT


def test_digital_link_canonical_not_truncated_on_parse():
    parsed = parse_class_uri(SYN_DL)
    assert parsed is not None
    assert parsed.canonical_id == SYN_DL
    assert parsed.lot_token == SYN_LOT


def test_full_uri_not_passed_as_lot_arg_to_epc_class():
    """lot_token_only must refuse to treat a class URI as the lot segment."""
    assert lot_token_only(SYN_DL) == SYN_LOT
    assert lot_token_only(SYN_LGTIN) == SYN_LOT
    assert is_full_class_uri(SYN_DL)
    # Rebuild path: normalize with GTIN + accidental full URI still yields token
    identity = normalize_epcis_lot(SYN_DL, gtin=SYN_GTIN14)
    assert identity is not None
    assert identity.lot_token == SYN_LOT
    assert "://" not in identity.lot_token
    assert not identity.lot_token.lower().startswith("urn:epc:")


def test_same_lot_different_gtin_are_distinct():
    a = parse_class_uri(SYN_LGTIN)
    b = parse_class_uri(SYN_LGTIN_OTHER_GTIN)
    assert a is not None and b is not None
    assert a.lot_token == b.lot_token == SYN_LOT
    assert a.canonical_id != b.canonical_id


def test_both_pass_fixture_round_trip_full_id():
    """Synthetic both-pass: full Digital Link survives normalize → token → rebuild."""
    first = normalize_epcis_lot(SYN_DL)
    assert first is not None
    assert first.canonical_id == SYN_DL
    rebuilt = normalize_epcis_lot(first.lot_token, gtin=first.gtin or SYN_GTIN14)
    assert rebuilt is not None
    assert rebuilt.is_full_class_uri is True
    # Exact equality on full Digital Link form
    assert rebuilt.canonical_id == SYN_DL or rebuilt.lot_token == SYN_LOT and rebuilt.gtin == first.gtin


def test_lenient_only_fixture_preserves_raw_tlc_and_gtin():
    """Synthetic lenient-only: bare TLC + GTIN rebuilds without inventing GTIN."""
    bare = normalize_epcis_lot(SYN_LOT, gtin=SYN_GTIN14)
    assert bare is not None
    assert bare.lot_token == SYN_LOT
    assert bare.gtin is not None
    assert SYN_LOT in bare.canonical_id
    # Without GTIN, do not invent a class URI
    no_gtin = normalize_epcis_lot(SYN_LOT, gtin=None)
    assert no_gtin is not None
    assert no_gtin.canonical_id == SYN_LOT
    assert no_gtin.is_full_class_uri is False


def test_canonical_path_preserves_full_lgtin_when_lossless(monkeypatch):
    monkeypatch.delenv("LOT_IDENTITY_LOSSLESS", raising=False)
    assert lossless_enabled() is True
    event = {
        "quantityList": [{"epcClass": SYN_LGTIN, "quantity": 1, "uom": "EA"}],
        "ilmd": {},
    }
    tlc, gtin = _epcis_traceability_lot_code(event)
    assert tlc == SYN_LGTIN
    assert tlc != SYN_LOT


def test_canonical_path_segment_only_when_flag_off(monkeypatch):
    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "0")
    assert lossless_enabled() is False
    event = {
        "quantityList": [{"epcClass": SYN_LGTIN, "quantity": 1, "uom": "EA"}],
        "ilmd": {},
    }
    tlc, _gtin = _epcis_traceability_lot_code(event)
    assert tlc == SYN_LOT


def test_transformation_inputs_keep_full_class_uri(monkeypatch):
    monkeypatch.delenv("LOT_IDENTITY_LOSSLESS", raising=False)
    event = {
        "inputQuantityList": [
            {"epcClass": SYN_LGTIN, "quantity": 2.5, "uom": "KGM"},
        ],
    }
    inputs = _epcis_transformation_inputs(event)
    assert len(inputs) == 1
    assert inputs[0]["traceability_lot_code"] == SYN_LGTIN
    assert inputs[0]["lot_token"] == SYN_LOT
    assert inputs[0]["epc_class"] == SYN_LGTIN


def test_export_epc_class_emits_stored_full_uri_unchanged():
    from ingestion.app.epcis_export import _epc_class

    row = {
        "traceability_lot_code": SYN_DL,
        "gtin": SYN_GTIN14,
    }
    assert _epc_class(row) == SYN_DL


def test_export_epc_class_does_not_embed_full_uri_as_lot():
    from ingestion.app.epcis_export import _epc_class

    # Stored TLC accidentally holds a full URI while epc_class is empty;
    # rebuild must not produce .../10/https%3A%2F%2F...
    row = {
        "traceability_lot_code": SYN_DL,
        "gtin": SYN_GTIN14,
        "epc_class": None,
        "product_id": None,
    }
    out = _epc_class(row)
    assert out == SYN_DL
    assert out is not None
    assert "%3A" not in out
    assert out.count("https://") == 1
