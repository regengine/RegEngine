"""SEL-598 / H2: lossless EPCIS lot identity (structural + synthetic URIs).

Synthetic identifiers only (A-2165). No partner data. No compliance claims.
"""

from __future__ import annotations

import os

import pytest
from shared.canonical_event import (
    _epcis_traceability_lot_code,
    _epcis_transformation_inputs,
    _legacy_epcis_traceability_lot_code,
    _legacy_epcis_transformation_inputs,
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
# EPC Pure Identity 0614141.123452 → indicator 1 + check digit
SYN_GTIN_FROM_LGTIN = "10614141234520"
SYN_LOT = "LOT-ROM-2026-0312A"
SYN_LGTIN = f"urn:epc:class:lgtin:0614141.123452.{SYN_LOT}"
SYN_DL = f"https://id.gs1.org/01/{SYN_GTIN14}/10/{SYN_LOT}"
SYN_LGTIN_OTHER_GTIN = f"urn:epc:class:lgtin:0614141.999990.{SYN_LOT}"



@pytest.fixture(autouse=True)
def _lossless_on(monkeypatch):
    """The H2 behaviour under test is opt-in; tests that need it off say so."""
    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "1")


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
    assert rebuilt.canonical_id == SYN_DL


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
    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "1")
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
    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "1")
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


def test_lgtin_company_item_rebuilds_indicator_and_check_digit():
    parsed = parse_class_uri(SYN_LGTIN)
    assert parsed is not None
    assert parsed.gtin == SYN_GTIN_FROM_LGTIN
    # Must not use the naive 0+company+item concatenation
    assert parsed.gtin != "00614141123452"


def test_bare_ilmd_tlc_preserved_with_sgtin_epc(monkeypatch):
    """SGTIN + bare ILMD lot must not fabricate a Digital Link TLC."""
    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "1")
    sgtin = "urn:epc:id:sgtin:0614141.123452.SERIAL9"
    event = {
        "epcList": [sgtin],
        "ilmd": {"cbvmda:lotNumber": SYN_LOT},
    }
    tlc, gtin = _epcis_traceability_lot_code(event)
    assert tlc == SYN_LOT
    assert "://" not in tlc
    assert gtin == SYN_GTIN_FROM_LGTIN


def test_transformation_inputs_same_lot_different_gtin_kept(monkeypatch):
    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "1")
    event = {
        "inputQuantityList": [
            {"epcClass": SYN_LGTIN, "quantity": 1, "uom": "EA"},
            {"epcClass": SYN_LGTIN_OTHER_GTIN, "quantity": 2, "uom": "EA"},
        ],
    }
    inputs = _epcis_transformation_inputs(event)
    assert len(inputs) == 2
    codes = {i["traceability_lot_code"] for i in inputs}
    assert codes == {SYN_LGTIN, SYN_LGTIN_OTHER_GTIN}


def test_export_rejects_invalid_class_uri_from_lenient_parse():
    from ingestion.app.epcis_export import _epc_class

    # Bad company+item length — lenient parser may accept; export must not emit.
    bad = "urn:epc:class:lgtin:1.2.LOT1"
    row = {"traceability_lot_code": bad, "gtin": None, "epc_class": None, "product_id": None}
    assert _epc_class(row) is None

    # Digital Link with invalid check digit
    bad_dl = "https://id.gs1.org/01/09506000134351/10/LOT1"
    row2 = {"traceability_lot_code": bad_dl, "gtin": None, "epc_class": None, "product_id": None}
    assert _epc_class(row2) is None


def test_lossless_is_opt_in_by_default(monkeypatch):
    monkeypatch.delenv("LOT_IDENTITY_LOSSLESS", raising=False)
    assert lossless_enabled() is False
    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "true")
    assert lossless_enabled() is True


@pytest.mark.parametrize(
    "event",
    [
        {"quantityList": [{"epcClass": SYN_LGTIN, "quantity": 1, "uom": "EA"}], "ilmd": {}},
        {"epcList": ["urn:epc:id:sgtin:0614141.123452.SERIAL9"], "ilmd": {"cbvmda:lotNumber": SYN_LOT}},
        {"quantityList": [{"epcClass": SYN_LGTIN_OTHER_GTIN, "quantity": 1}], "ilmd": {"fsma:traceabilityLotCode": "TLC-ILMD-1"}},
        {"traceability_lot_code": " FLAT-LOT-9 "},
    ],
)
def test_flag_off_resolver_is_pre_h2_unchanged(monkeypatch, event):
    """Flag off must keep TLC and GTIN KDE (and so hash/idempotency) as before H2."""
    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "0")
    assert _epcis_traceability_lot_code(event) == _legacy_epcis_traceability_lot_code(event)


def test_flag_off_transformation_inputs_are_pre_h2_unchanged(monkeypatch):
    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "0")
    event = {
        "inputQuantityList": [
            {"epcClass": SYN_LGTIN, "quantity": 1, "uom": "EA"},
            {"epcClass": SYN_LGTIN_OTHER_GTIN, "quantity": 2, "uom": "EA"},
        ],
        "inputEPCList": ["urn:epc:id:sgtin:0614141.123452.SERIAL9"],
    }
    assert _epcis_transformation_inputs(event) == _legacy_epcis_transformation_inputs(event)


@pytest.mark.parametrize("bare", ["SGTINLOT-7", "PLGTIN.A", "lot-lgtin"])
def test_lot_token_only_keeps_bare_lot_containing_gtin_words(bare):
    assert lot_token_only(bare) == bare


def test_export_lot_filter_bare_lot_reads_both_shapes():
    from ingestion.app.epcis_export import _lot_code_filter, _row_matches_lot

    predicate, params = _lot_code_filter(SYN_LOT)
    assert "e.traceability_lot_code = :lot_code" in predicate
    assert params["lot_token"] == SYN_LOT
    assert "urn:epc:class:lgtin:%" in predicate
    assert "https://id.gs1.org/01/%" in predicate
    assert _row_matches_lot(SYN_LOT, SYN_LOT)
    assert _row_matches_lot(SYN_DL, SYN_LOT)
    assert _row_matches_lot(SYN_LGTIN, SYN_LOT)
    # Same suffix, different lot: excluded after the coarse SQL match.
    assert not _row_matches_lot(f"urn:epc:class:lgtin:0614141.123452.X.{SYN_LOT}", SYN_LOT)
    assert not _row_matches_lot("OTHER-LOT", SYN_LOT)


def test_export_lot_filter_full_uri_also_reads_bare_rows():
    from ingestion.app.epcis_export import _lot_code_filter, _row_matches_lot

    predicate, params = _lot_code_filter(SYN_DL)
    assert params == {"lot_code": SYN_DL, "lot_token": SYN_LOT}
    assert "e.traceability_lot_code = :lot_token" in predicate
    assert _row_matches_lot(SYN_DL, SYN_DL)
    assert _row_matches_lot(SYN_LOT, SYN_DL)
    # A different GTIN's URI with the same lot is not the requested class.
    assert not _row_matches_lot(SYN_LGTIN_OTHER_GTIN, SYN_DL)


def test_transformation_instance_inputs_preserve_product_and_serial():
    first = "urn:epc:id:sgtin:0614141.123452.SERIAL9"
    second = "urn:epc:id:sgtin:0614141.999990.SERIAL9"
    inputs = _epcis_transformation_inputs({"inputEPCList": [first, second, f" {first} "]})
    assert [item["traceability_lot_code"] for item in inputs] == [first, second]
    assert [item["lot_token"] for item in inputs] == ["SERIAL9", "SERIAL9"]
    assert [item["quantity"] for item in inputs] == [1.0, 1.0]


@pytest.mark.parametrize("requested", [" LOT/A ", "LOT/A\n", "urn:epc:id:sgtin:0614141.123452.LOT/A"])
def test_export_transformed_token_still_fetches_class_candidates(requested):
    from ingestion.app.epcis_export import _lot_code_filter, _row_matches_lot

    stored = f"https://id.gs1.org/01/{SYN_GTIN14}/10/LOT%2fA"
    predicate, params = _lot_code_filter(requested)
    assert "https://id.gs1.org/01/%" in predicate
    assert params["lot_token"] == "LOT/A"
    assert _row_matches_lot(stored, requested)
    assert not _row_matches_lot(stored.replace("LOT", "lot"), requested)


@pytest.mark.parametrize("enabled", [False, True])
def test_sgtin_normalizer_retains_full_identity_only_when_enabled(monkeypatch, enabled):
    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "1" if enabled else "0")
    epc = "urn:epc:id:sgtin:0614141.123452.SERIAL9"
    identity = normalize_epcis_lot(f" {epc} ")
    assert identity.canonical_id == (epc if enabled else "SERIAL9")
    assert identity.lot_token == "SERIAL9"
    assert identity.gtin == SYN_GTIN_FROM_LGTIN
