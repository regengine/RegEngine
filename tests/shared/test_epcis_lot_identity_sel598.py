"""SEL-598 lossless lot identity (Preview).

Synthetic fixtures only. No partner data. No production ingest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from shared.canonical_event import normalize_epcis_event
from shared.epcis_lot_identity import (
    derive_lot_token,
    identity_from_parts,
    normalize_from_epcis_event,
    parse_class_uri,
)
from shared.fsma_validation import validate_tlc

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "services" / "ingestion" / "tests" / "fixtures" / "sel598"

# Export helpers live under services/ingestion/app.
sys.path.insert(0, str(REPO / "services" / "ingestion"))
sys.path.insert(0, str(REPO / "services"))


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_both_pass_fixture_round_trip_full_id():
    fixture = _load("both_pass.json")
    identity = normalize_from_epcis_event(fixture["epcis_event"])
    expected = "https://id.gs1.org/01/00012345678901/10/00012345678901-LotA"
    assert identity.canonical_id == expected
    assert identity.lot_token == "00012345678901-LotA"
    assert identity.gtin == "00012345678901"
    assert validate_tlc(identity.lot_token, strict=False).is_valid
    assert validate_tlc(identity.lot_token, strict=True).is_valid

    event = normalize_epcis_event(fixture["epcis_event"], str(uuid4()))
    assert event.traceability_lot_code == expected
    again = parse_class_uri(event.traceability_lot_code)
    assert again is not None
    assert again.canonical_id == expected
    assert again.lot_token == "00012345678901-LotA"


def test_lenient_only_fixture_preserves_raw_tlc_and_gtin():
    fixture = _load("lenient_only.json")
    identity = normalize_from_epcis_event(fixture["epcis_event"])
    assert identity.lot_token == "LOT-ROM-2026-0312A"
    assert identity.gtin == "00012345678905"
    assert identity.canonical_id == (
        "https://id.gs1.org/01/00012345678905/10/LOT-ROM-2026-0312A"
    )
    assert validate_tlc(identity.lot_token, strict=False).is_valid
    assert not validate_tlc(identity.lot_token, strict=True).is_valid

    event = normalize_epcis_event(fixture["epcis_event"], str(uuid4()))
    assert event.traceability_lot_code == identity.canonical_id
    assert derive_lot_token(event.traceability_lot_code) == "LOT-ROM-2026-0312A"


def test_same_lot_different_gtin_are_distinct():
    a = identity_from_parts(tlc="LOT-SHARED", gtin="00012345678905")
    b = identity_from_parts(tlc="LOT-SHARED", gtin="00012345678912")
    assert a is not None and b is not None
    assert a.lot_token == b.lot_token == "LOT-SHARED"
    assert a.canonical_id != b.canonical_id
    assert a.gtin != b.gtin


def test_full_uri_not_passed_as_lot_arg_to_epc_class():
    from app.epcis_export import _epc_class

    full = "https://id.gs1.org/01/00012345678905/10/LotRebuild"
    out = _epc_class({"traceability_lot_code": full, "gtin": "00012345678905"})
    assert out == full
    assert "/10/https" not in (out or "")

    rebuilt = _epc_class({"traceability_lot_code": "LotRebuild", "gtin": "00012345678905"})
    assert rebuilt == full


def test_lgtin_canonical_not_truncated_on_canonical_path(monkeypatch):
    monkeypatch.delenv("LOT_IDENTITY_LOSSLESS", raising=False)
    lgtin = "urn:epc:class:lgtin:0614141.107346.LotA"
    event = {
        "type": "ObjectEvent",
        "action": "ADD",
        "bizStep": "urn:epcglobal:cbv:bizstep:commissioning",
        "eventTime": "2026-03-12T15:00:00.000Z",
        "eventTimeZoneOffset": "+00:00",
        "quantityList": [{"epcClass": lgtin, "quantity": 1, "uom": "KGM"}],
    }
    identity = normalize_from_epcis_event(event)
    assert identity.canonical_id == lgtin
    assert identity.lot_token == "LotA"
    canonical = normalize_epcis_event(event, str(uuid4()))
    assert canonical.traceability_lot_code == lgtin

    monkeypatch.setenv("LOT_IDENTITY_LOSSLESS", "0")
    rolled = normalize_from_epcis_event(event)
    assert rolled.canonical_id == "LotA"
    assert rolled.lot_token == "LotA"


def test_legacy_extraction_still_returns_full_uri_as_tlc():
    from app.epcis.extraction import _extract_event_lot

    dl = "https://id.gs1.org/01/00012345678905/10/00012345678905-LotA"
    lot_code, tlc = _extract_event_lot(
        {
            "type": "ObjectEvent",
            "quantityList": [{"epcClass": dl, "quantity": 1}],
        }
    )
    assert lot_code == "00012345678905-LotA"
    assert tlc == dl
