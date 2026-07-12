"""Regression: the two EDI-ingestion GLN validators must agree, and both
must implement the standard GS1 mod-10 check-digit algorithm.

Background
----------
``edi_ingestion.utils._valid_gln_or_none`` decides whether a parsed GLN is
passed into ``IngestEvent``; ``webhook_models.validate_gln`` (via the
``IngestEvent.location_gln`` validator) then re-validates it. Historically the
two used *opposite* GS1 weightings:

  * ``_valid_gln_or_none``           weighted the rightmost data digit ×1 (wrong)
  * ``webhook_models.validate_gln``  weighted the rightmost data digit ×3 (right)

so they disagreed on ~80% of 13-digit inputs. A GLN accepted by the first and
rejected by the second 500'd the whole document ingest; a GLN accepted by the
wrong algorithm let an invalid GLN through. Both now delegate to
``shared.fsma_validation`` (rightmost data digit ×3), the GS1 standard.
"""

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

# GS1 spec ground truth (GLN/GTIN/SSCC share one mod-10 algorithm). These are
# real, published check digits — they only validate under the correct weighting.
GS1_SPEC_EXAMPLES = [
    ("400638133393", 1),  # textbook EAN-13 / GTIN-13 4006381333931
    ("0950600013435", 2),  # GS1 sample GTIN-14 09506000134352
    ("9638507", 4),  # GTIN-8 96385074
]

# 13-digit GLNs whose check digit is correct under the GS1 standard.
KNOWN_GOOD_GLNS = [
    "0614141000005",  # body 061414100000 -> check 5
    "0614141000036",  # body 061414100003 -> check 6 (old buggy utils computed 4 -> wrongly REJECTED)
    "0614141999996",  # body 061414199999 -> check 6
]

# 13-digit GLNs whose check digit is wrong under the GS1 standard.
KNOWN_BAD_GLNS = [
    "0614141000030",  # body 061414100003 -> correct check is 6, not 0
    "0614141000007",  # body 061414100000 -> correct check is 5 (old buggy utils computed 7 -> wrongly ACCEPTED)
    "0614141999990",  # body 061414199999 -> correct check is 6, not 0
]


@pytest.mark.parametrize("body,expected", GS1_SPEC_EXAMPLES)
def test_shared_helper_matches_gs1_spec_examples(body, expected):
    """The shared canonical helper reproduces published GS1 check digits."""
    assert calculate_gs1_check_digit(body) == expected


@pytest.mark.parametrize("gln", KNOWN_GOOD_GLNS)
def test_known_good_gln_passes_both_validators(gln):
    # utils gate: returns the cleaned digits (truthy) when valid
    assert _valid_gln_or_none(gln) == gln
    # webhook validator (re-run inside IngestEvent): accepts
    is_valid, err = webhook_validate_gln(gln)
    assert is_valid is True
    assert err is None
    # shared canonical: agrees
    assert shared_validate_gln(gln).is_valid is True


@pytest.mark.parametrize("gln", KNOWN_BAD_GLNS)
def test_known_bad_gln_fails_both_validators(gln):
    assert _valid_gln_or_none(gln) is None
    is_valid, err = webhook_validate_gln(gln)
    assert is_valid is False
    assert err is not None
    assert shared_validate_gln(gln).is_valid is False


def test_validators_never_disagree_across_check_digits():
    """Core invariant: for any 13-digit GLN, the utils gate and the webhook
    validator must reach the same accept/reject decision (they used opposite
    weightings before this fix)."""
    bodies = ["061414100003", "400638133393", "759512345670", "123456789012"]
    for body in bodies:
        for check in range(10):
            gln = body + str(check)
            utils_ok = _valid_gln_or_none(gln) is not None
            webhook_ok = webhook_validate_gln(gln)[0]
            shared_ok = shared_validate_gln(gln).is_valid
            assert utils_ok == webhook_ok == shared_ok, (
                f"validators disagree on {gln}: utils={utils_ok} webhook={webhook_ok} shared={shared_ok}"
            )
