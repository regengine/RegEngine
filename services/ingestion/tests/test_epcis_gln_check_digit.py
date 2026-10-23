"""GLN gate on empty and non-GLN-shaped values.

The GS1 check-digit accept and reject paths need a 13-digit GLN. No real
GLN is available, so those branches are not exercised.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.epcis.validation import (  # noqa: E402
    _enforce_mandatory_gln_check_digits,
    _validate_epcis_glns,
    _validate_gln_format,
)


def test_non_numeric_rejected():
    assert _validate_gln_format("not-a-gln") is False


def test_wrong_length_rejected():
    assert _validate_gln_format("12") is False
    assert _validate_gln_format("12345") is False


def test_empty_rejected():
    assert _validate_gln_format("") is False


def test_enforcer_ignores_non_gln_shaped_values():
    normalized = {
        "location_id": "not-a-gln",
        "source_location_id": "12",
        "dest_location_id": "12345",
    }
    _enforce_mandatory_gln_check_digits(normalized)


def test_enforcer_tolerates_missing_fields():
    _enforce_mandatory_gln_check_digits({})


def test_advisory_on_empty_normalized_returns_no_warnings():
    assert _validate_epcis_glns({}) == []
