"""Regression tests for EDI envelope integrity (#1160 + #1165).

#1160: GS segment is required and wins over ISA for trading-partner
       identity. ISA/GS mismatch is rejected with HTTP 422.
#1165: ISA13 deduplication of retransmissions via Redis.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.edi_ingestion import dedup as dedup_mod
from app.edi_ingestion.extractors import (
    _extract_envelope_ids,
    _extract_856_fields,
    _extract_850_fields,
    _extract_810_fields,
    _extract_861_fields,
)
from app.edi_ingestion.parser import _parse_x12_segments


# Canonical X12 856 template with both ISA and GS.
#
# The _parse_x12_segments helper reads element separator from index 3 and
# segment terminator from index 105 of the compact byte stream. The ISA
# header is therefore fixed-width (exactly 106 chars terminated by ``~``).
_ISA_BASE = (
    # ISA*00*<10sp>*00*<10sp>*ZZ*SENDER_ID_10ch *ZZ*RECEIVER_ID_14sp*240417*1200*U*00401*000000123*0*P*>~
    "ISA*00*          *00*          *ZZ*SENDER_ID      "
    "*ZZ*RECEIVER_ID    *240417*1200*U*00401*000000123*0*P*>~"
)
assert len(_ISA_BASE) == 106, f"ISA header must be 106 chars (got {len(_ISA_BASE)})"

_GS_BASE = "GS*SH*GS_SENDER*GS_RECEIVER*20260417*1200*1*X*004010~"


def _build_isa(sender: str = "SENDER_ID", receiver: str = "RECEIVER_ID", isa13: str = "000000123") -> str:
    """Build a correctly-sized ISA header with substituted sender/receiver/isa13."""
    sender = sender.ljust(15)[:15]
    receiver = receiver.ljust(15)[:15]
    isa13 = isa13.rjust(9, "0")[:9]
    header = (
        f"ISA*00*          *00*          *ZZ*{sender}*ZZ*{receiver}"
        f"*240417*1200*U*00401*{isa13}*0*P*>~"
    )
    assert len(header) == 106, f"ISA header must be 106 chars (got {len(header)})"
    return header


def _make_856_edi(isa: str | None = None, gs: str = _GS_BASE) -> str:
    """Build a minimal valid 856 EDI string for tests."""
    if isa is None:
        isa = _build_isa()
    return (
        isa
        + gs
        + "ST*856*0001~"
        + "BSN*00*123*20260417*1200~"
        + "HL*1**S~"
        + "N1*SF*SenderCo*92*sender-gln~"
        + "N1*ST*ReceiverCo*92*receiver-gln~"
        + "SN1*1*100*CA~"
        + "SE*8*0001~"
        + "GE*1*1~"
        + "IEA*1*000000123~"
    )


# ---------------------------------------------------------------------------
# Envelope extraction
# ---------------------------------------------------------------------------


def test_envelope_extraction_prefers_gs_sender():
    """GS wins over ISA for canonical sender_id (#1160)."""
    raw = _make_856_edi()
    segments = _parse_x12_segments(raw)
    env = _extract_envelope_ids(segments)

    assert env["gs_sender_id"] == "GS_SENDER"
    assert env["isa_sender_id"] == "SENDER_ID"
    # Canonical = GS.
    assert env["sender_id"] == "GS_SENDER"
    assert env["envelope_mismatch"] is True  # ISA says SENDER_ID, GS says GS_SENDER


def test_envelope_extraction_captures_isa13():
    raw = _make_856_edi(isa=_build_isa(isa13="555000777"))
    segments = _parse_x12_segments(raw)
    env = _extract_envelope_ids(segments)

    assert env["isa13"] == "555000777"


def test_envelope_mismatch_detected():
    """If ISA and GS disagree, envelope_mismatch is True (#1160)."""
    isa = _build_isa(sender="PARTNER_A")
    gs = _GS_BASE.replace("GS_SENDER", "PARTNER_B")
    raw = _make_856_edi(isa=isa, gs=gs)
    segments = _parse_x12_segments(raw)
    env = _extract_envelope_ids(segments)

    assert env["isa_sender_id"] == "PARTNER_A"
    assert env["gs_sender_id"] == "PARTNER_B"
    assert env["envelope_mismatch"] is True


def test_envelope_no_mismatch_when_ids_align():
    isa = _build_isa(sender="PARTNER_X", receiver="RECEIVER_ID")
    gs = _GS_BASE.replace("GS_SENDER", "PARTNER_X").replace("GS_RECEIVER", "RECEIVER_ID")
    raw = _make_856_edi(isa=isa, gs=gs)
    segments = _parse_x12_segments(raw)
    env = _extract_envelope_ids(segments)

    assert env["envelope_mismatch"] is False


def test_all_four_extractors_populate_envelope():
    """856, 850, 810, 861 must all produce isa13 / gs_sender_id keys."""
    raw = _make_856_edi()
    segments = _parse_x12_segments(raw)

    for extractor in (
        _extract_856_fields,
        _extract_850_fields,
        _extract_810_fields,
        _extract_861_fields,
    ):
        data = extractor(segments)
        assert "isa13" in data
        assert "gs_sender_id" in data
        assert "envelope_mismatch" in data
        assert data["sender_id"] == "GS_SENDER"


# ---------------------------------------------------------------------------
# ISA13 dedup
# ---------------------------------------------------------------------------


def test_dedup_key_composition_distinct_per_isa13():
    k1 = dedup_mod._dedup_key("s1", "r1", "000000001")
    k2 = dedup_mod._dedup_key("s1", "r1", "000000002")
    assert k1 != k2


def test_dedup_key_distinct_across_senders():
    k1 = dedup_mod._dedup_key("s1", "r1", "000000001")
    k2 = dedup_mod._dedup_key("s2", "r1", "000000001")
    assert k1 != k2


def test_check_and_record_returns_duplicate_on_second_call():
    """First call -> (False, None). Second call -> (True, ...)."""
    fake = MagicMock()
    # First SET NX succeeds, second returns falsy.
    fake.set.side_effect = [True, False]
    fake.get.return_value = "seen"

    with patch.object(dedup_mod, "_redis_client", return_value=fake):
        first = dedup_mod.check_and_record_interchange("sender", "receiver", "isa-13-1")
        second = dedup_mod.check_and_record_interchange("sender", "receiver", "isa-13-1")

    assert first == (False, None)
    assert second == (True, "seen")


def test_check_and_record_returns_false_without_isa13():
    """Missing isa13 -> dedup skipped (downstream CTE hash handles it)."""
    fake = MagicMock()
    with patch.object(dedup_mod, "_redis_client", return_value=fake):
        result = dedup_mod.check_and_record_interchange("sender", "receiver", None)
    assert result == (False, None)
    fake.set.assert_not_called()


def test_check_and_record_returns_false_when_redis_unavailable():
    with patch.object(dedup_mod, "_redis_client", return_value=None):
        result = dedup_mod.check_and_record_interchange("sender", "receiver", "isa-13-3")
    assert result == (False, None)


# ---------------------------------------------------------------------------
# Partner allowlist
# ---------------------------------------------------------------------------


def test_allowlist_permits_when_env_unset(monkeypatch):
    """Tenants without configured allowlist let all GS senders through."""
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST_TENANT_FOO", raising=False)
    assert dedup_mod.verify_trading_partner_allowed("tenant-foo", "ANY_SENDER") is True


def test_allowlist_blocks_unknown_sender(monkeypatch):
    monkeypatch.setenv("EDI_PARTNER_ALLOWLIST_TENANT_FOO", "ALLOWED1,ALLOWED2")
    assert dedup_mod.verify_trading_partner_allowed("tenant-foo", "STRANGER") is False


def test_allowlist_permits_listed_sender(monkeypatch):
    monkeypatch.setenv("EDI_PARTNER_ALLOWLIST_TENANT_FOO", "ALLOWED1,ALLOWED2")
    assert dedup_mod.verify_trading_partner_allowed("tenant-foo", "ALLOWED2") is True


# ---------------------------------------------------------------------------
# _enforce_envelope_integrity integration
# ---------------------------------------------------------------------------


def test_enforce_rejects_envelope_mismatch():
    """ISA/GS mismatch -> HTTP 422."""
    from app.edi_ingestion.routes import _enforce_envelope_integrity

    extracted = {
        "envelope_mismatch": True,
        "isa_sender_id": "PARTNER_A",
        "gs_sender_id": "PARTNER_B",
        "isa_receiver_id": "RECV",
        "gs_receiver_id": "RECV",
        "sender_id": "PARTNER_B",
        "receiver_id": "RECV",
        "isa13": "000000001",
    }

    with pytest.raises(HTTPException) as exc:
        _enforce_envelope_integrity(extracted, "tenant-1", "856")
    assert exc.value.status_code == 422
    assert exc.value.detail["error"] == "edi_envelope_mismatch"


def test_enforce_rejects_duplicate_interchange():
    """Second retransmission of the same ISA13 -> HTTP 409."""
    from app.edi_ingestion import routes as routes_mod

    extracted = {
        "envelope_mismatch": False,
        "gs_sender_id": "PARTNER",
        "sender_id": "PARTNER",
        "receiver_id": "RECV",
        "isa13": "000000001",
    }

    with patch.object(routes_mod, "check_and_record_interchange", return_value=(True, "seen")):
        with pytest.raises(HTTPException) as exc:
            routes_mod._enforce_envelope_integrity(extracted, "tenant-1", "856")
    assert exc.value.status_code == 409
    assert exc.value.detail["idempotent_replay"] is True


def test_enforce_rejects_disallowed_trading_partner(monkeypatch):
    from app.edi_ingestion import routes as routes_mod

    monkeypatch.setenv("EDI_PARTNER_ALLOWLIST_TENANT_X", "ONLY_THIS_ONE")

    extracted = {
        "envelope_mismatch": False,
        "gs_sender_id": "NOT_ALLOWED",
        "sender_id": "NOT_ALLOWED",
        "receiver_id": "RECV",
        "isa13": "000000001",
    }

    with patch.object(routes_mod, "check_and_record_interchange", return_value=(False, None)):
        with pytest.raises(HTTPException) as exc:
            routes_mod._enforce_envelope_integrity(extracted, "tenant-x", "856")
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "trading_partner_not_allowed"


def test_enforce_passes_on_clean_envelope():
    """Valid, unique, allowed envelope -> no exception."""
    from app.edi_ingestion import routes as routes_mod

    extracted = {
        "envelope_mismatch": False,
        "gs_sender_id": "PARTNER",
        "sender_id": "PARTNER",
        "receiver_id": "RECV",
        "isa13": "000000999",
    }

    with patch.object(routes_mod, "check_and_record_interchange", return_value=(False, None)):
        # Should NOT raise.
        routes_mod._enforce_envelope_integrity(extracted, "tenant-1", "856")
