"""Data-free checks for FSMAEvent lot-level TLC acceptance.

No identifier values, GTINs, lots, or records. These tests only reject
blank input and bare scheme prefixes, and check that the new patterns
are anchored.
"""

from __future__ import annotations

import re

import pytest
from shared.schemas import FSMAEvent, _TLC_DIGITAL_LINK_RE, _TLC_LGTIN_RE

_BLANK = ("", " ", "\t", "\n", "\r\n", " \t ", " " * 15, "\t" * 15)
_BARE_PREFIXES = (
    "urn:epc:class:lgtin:",
    "urn:epc:class:lgtin:..",
    "https:///01//10/",
)


@pytest.mark.parametrize("value", _BLANK)
def test_empty_and_whitespace_tlc_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="does not match FSMA 204 production pattern"):
        FSMAEvent.validate_tlc_format(value)


@pytest.mark.parametrize("value", _BARE_PREFIXES)
def test_bare_lot_level_prefixes_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="does not match FSMA 204 production pattern"):
        FSMAEvent.validate_tlc_format(value)


def test_lot_level_patterns_are_anchored() -> None:
    for pattern in (_TLC_LGTIN_RE, _TLC_DIGITAL_LINK_RE):
        assert isinstance(pattern, re.Pattern)
        assert pattern.pattern.startswith("^")
        assert pattern.pattern.endswith("$")
        assert pattern.flags & re.MULTILINE == 0
