"""Coverage-sweep tests for ``app.webhook_models.IngestEvent.validate_gln_format``
(#1342).

The existing ``tests/test_webhook_models.py`` only ever constructs
``IngestEvent`` with ``location_gln=None`` — so the early-return on
line 167 is all that's tested for the GLN validator. Lines 168-176
(strip, validate, strict-mode branch, permissive branch) are
untouched.

This file covers:
    168     — ``clean = re.sub(r"\\D", "", v)`` normalization
    169     — ``validate_gln`` call + wrong-length fallback
    170-173 — strict mode raises ValueError on invalid GLN
    174-175 — permissive mode logs + returns
    176     — valid 13-digit GLN returns the cleaned form
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.webhook_models import IngestEvent, WebhookCTEType  # noqa: E402


# A valid 13-digit GLN with correct mod-10 check digit. ``0614141000006``
# is a well-known GS1 demo GLN used in many FSMA test fixtures.
VALID_GLN = "0614141000005"


def _make_event_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "cte_type": WebhookCTEType.SHIPPING,
        "traceability_lot_code": "TLC-2026-ABC",
        "product_description": "Romaine Lettuce",
        "quantity": 10,
        "unit_of_measure": "cases",
        "timestamp": "2026-04-15T12:00:00Z",
        "location_name": "Metro DC",
    }
    base.update(overrides)
    return base


class TestValidateGlnFormat:
    def test_valid_gln_returned_in_cleaned_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Line 176: happy path — valid GLN passes and returns cleaned.
        # Dashes/spaces get stripped out (line 168).
        monkeypatch.setenv("STRICT_GLN_VALIDATION", "true")
        event = IngestEvent(**_make_event_kwargs(location_gln="061-414-100-0005"))
        assert event.location_gln == VALID_GLN

    def test_wrong_length_raises_in_strict_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Line 169 wrong-length branch → (False, ...) → strict mode raises.
        monkeypatch.setenv("STRICT_GLN_VALIDATION", "true")
        with pytest.raises(ValidationError) as exc:
            IngestEvent(**_make_event_kwargs(location_gln="12345"))
        assert "GLN must be exactly 13 digits" in str(exc.value)

    def test_bad_check_digit_raises_in_strict_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Line 169 valid-length but bad check digit → (False, ...) → raises.
        # 0614141000007 — last digit is wrong (correct is 6).
        monkeypatch.setenv("STRICT_GLN_VALIDATION", "true")
        with pytest.raises(ValidationError) as exc:
            IngestEvent(**_make_event_kwargs(location_gln="0614141000007"))
        assert "check digit invalid" in str(exc.value)

    def test_permissive_mode_accepts_invalid_gln(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Lines 174-175: STRICT_GLN_VALIDATION=false logs and returns.
        monkeypatch.setenv("STRICT_GLN_VALIDATION", "false")
        caplog.set_level("WARNING", logger="gln-validation")
        event = IngestEvent(**_make_event_kwargs(location_gln="0614141000007"))
        # 13 digits → returns cleaned form.
        assert event.location_gln == "0614141000007"
        assert any(
            "invalid_gln" in rec.message or "invalid_gln" in rec.getMessage()
            for rec in caplog.records
        )

    def test_permissive_mode_wrong_length_returns_raw(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Line 175 ``else v`` branch — wrong length, permissive mode, non-13
        # cleaned length → returns the original string.
        monkeypatch.setenv("STRICT_GLN_VALIDATION", "false")
        event = IngestEvent(**_make_event_kwargs(location_gln="12345"))
        assert event.location_gln == "12345"

    def test_whitespace_only_gln_short_circuits(self) -> None:
        # Line 166 early-return (pre-existing coverage) — sanity check
        # that introducing the new tests doesn't regress the None/empty path.
        event = IngestEvent(**_make_event_kwargs(location_gln="   "))
        assert event.location_gln == "   "
