"""The EDI and webhook GLN gates agree on empty and algorithmic inputs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.edi_ingestion.utils import _valid_gln_or_none  # noqa: E402
from app.webhook_models import validate_gln as webhook_validate_gln  # noqa: E402
from shared.fsma_validation import (  # noqa: E402
    calculate_gs1_check_digit,
    validate_gln as shared_validate_gln,
)


def test_empty_gln_fails_both_validators() -> None:
    assert _valid_gln_or_none("") is None
    assert webhook_validate_gln("")[0] is False
    assert shared_validate_gln("").is_valid is False


def test_validators_never_disagree_across_check_digits() -> None:
    # An all-zero body exercises check-digit math without implying a location.
    body = "0" * 12
    expected = calculate_gs1_check_digit(body)
    for digit in range(10):
        gln = body + str(digit)
        is_valid = digit == expected
        assert (_valid_gln_or_none(gln) == gln) is is_valid
        assert webhook_validate_gln(gln)[0] is is_valid
        assert shared_validate_gln(gln).is_valid is is_valid


def test_check_digit_helper_rejects_empty_body() -> None:
    with pytest.raises(ValueError):
        calculate_gs1_check_digit("")
