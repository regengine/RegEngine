"""Regression tests for #1259 — GLN check-digit failure must reject
mandatory-location events rather than degrading to a warning alert.

Prior behavior silently persisted events with malformed GLNs, which
broke GS1 registry lookup at FDA-export time and let a supplier's
typo render their entire shipment chain unverifiable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.epcis.validation import (  # noqa: E402
    _enforce_mandatory_gln_check_digits,
    _validate_epcis_glns,
    _validate_gln_format,
)


# ---------------------------------------------------------------------------
# GS1 check-digit reference values
# ---------------------------------------------------------------------------
#
# ``0614141999996`` is a 13-digit GLN whose body (061414199999) hashes to
# check digit 6 under the standard GS1 mod-10 algorithm, so it is valid.
# The invalid variants below map to the three cases #1259 names:
# (a) flipped check digit, (b) transposed body digits, (c) all-zeros
# (semantically invalid but passes the check-digit test — out of scope
# for this gate, flagged here so the regression surface is explicit).
_VALID_GLN = "0614141999996"
_INVALID_CHECK_DIGIT = "0614141999990"   # (a) last digit tampered 6→0
_TRANSPOSED_DIGITS = "0614141999892"     # (b) body-digit tamper (98→89)
_ALL_ZEROS = "0000000000000"             # (c) check digit 0 is valid;
                                         # caller must still guard against
                                         # semantically-empty GLNs.


# ---------------------------------------------------------------------------
# _validate_gln_format — shared-validator delegation
# ---------------------------------------------------------------------------


def test_valid_gln_accepted():
    assert _validate_gln_format(_VALID_GLN) is True


def test_bad_check_digit_rejected():
    assert _validate_gln_format(_INVALID_CHECK_DIGIT) is False


def test_transposed_digits_rejected():
    assert _validate_gln_format(_TRANSPOSED_DIGITS) is False


def test_non_numeric_rejected():
    assert _validate_gln_format("ABC1234567890") is False


def test_wrong_length_rejected():
    assert _validate_gln_format("12345") is False
    assert _validate_gln_format("12345678901234") is False  # 14 digits


def test_empty_rejected():
    assert _validate_gln_format("") is False


# ---------------------------------------------------------------------------
# _enforce_mandatory_gln_check_digits — rejects mandatory failures
# ---------------------------------------------------------------------------


def test_enforcer_passes_on_valid_glns():
    normalized = {
        "location_id": _VALID_GLN,
        "source_location_id": None,
        "dest_location_id": None,
    }
    # Must not raise.
    _enforce_mandatory_gln_check_digits(normalized)


def test_enforcer_rejects_invalid_location_id():
    normalized = {
        "location_id": _INVALID_CHECK_DIGIT,
        "source_location_id": None,
        "dest_location_id": None,
    }
    with pytest.raises(HTTPException) as exc:
        _enforce_mandatory_gln_check_digits(normalized)

    assert exc.value.status_code == 422
    assert exc.value.detail["error"] == "invalid_gln_check_digit"
    failures = exc.value.detail["failures"]
    assert len(failures) == 1
    assert failures[0]["field"] == "location_id"
    assert failures[0]["gln"] == _INVALID_CHECK_DIGIT


def test_enforcer_rejects_invalid_source_and_dest():
    """Multiple failures are accumulated into one 422."""
    normalized = {
        "location_id": None,
        "source_location_id": _INVALID_CHECK_DIGIT,
        "dest_location_id": _TRANSPOSED_DIGITS,
    }
    with pytest.raises(HTTPException) as exc:
        _enforce_mandatory_gln_check_digits(normalized)

    assert exc.value.status_code == 422
    fields = {f["field"] for f in exc.value.detail["failures"]}
    assert fields == {"source_location_id", "dest_location_id"}


def test_enforcer_ignores_non_gln_shaped_values():
    """Non-GLN-shaped identifiers (URN form, wrong length) are out of
    scope — they're caught by upstream format validators with a different
    error shape."""
    normalized = {
        "location_id": "urn:epc:id:sgln:0614141.00002.0",
        "source_location_id": "not-a-gln",
        "dest_location_id": "12345",
    }
    _enforce_mandatory_gln_check_digits(normalized)


def test_enforcer_tolerates_missing_fields():
    """All three slots empty: no-op, no exception."""
    _enforce_mandatory_gln_check_digits({})


# ---------------------------------------------------------------------------
# _validate_epcis_glns (advisory) still catches what the enforcer missed
# ---------------------------------------------------------------------------


def test_advisory_still_emits_warning_for_malformed_glns():
    """Legacy callers that skip the enforcer still get a warning alert —
    never silent acceptance (#1259)."""
    normalized = {
        "location_id": _INVALID_CHECK_DIGIT,
        "source_location_id": None,
        "dest_location_id": None,
    }
    warnings = _validate_epcis_glns(normalized)
    assert len(warnings) == 1
    assert _INVALID_CHECK_DIGIT in warnings[0]
    assert "location_id" in warnings[0]
