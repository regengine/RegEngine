"""Data-free checks for FSMAEvent lot-level TLC acceptance.

No identifier records. Blank and short input fail; production-pattern misses
warn and preserve the input. Pattern-shape checks remain independent of
acceptance, including anchoring and the percent-decoded AI (10) limit.
"""

from __future__ import annotations

import re
import warnings
from typing import Annotated

import pytest
from pydantic import TypeAdapter
from shared.schemas import (
    _DL_CUSTOM_STEM,
    _DL_LOT_RAW_CLASS,
    _GS1_AI_82_CHARS,
    _LGTIN_LOT_RAW_CLASS,
    _PCT_ESCAPE,
    _TLC_DIGITAL_LINK_RE,
    _TLC_LGTIN_RE,
    FSMAEvent,
    _decoded_ai10_lot_within_limit,
)

_BLANK = ("", " ", "\t", "\n", "\r\n", " \t ", " " * 15, "\t" * 15)
_BARE_PREFIXES = (
    "urn:epc:class:lgtin:",
    "urn:epc:class:lgtin:..",
    "https:///01//10/",
)


@pytest.mark.parametrize("value", (*_BLANK, *(value + "\n" for value in _BLANK)))
def test_empty_and_whitespace_tlc_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="blank|at least 3 characters"):
        FSMAEvent.validate_tlc_format(value)


@pytest.mark.parametrize("value", ("A", "A" * 2, " A "))
def test_short_tlc_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="at least 3 characters"):
        FSMAEvent.validate_tlc_format(value)


@pytest.mark.parametrize(
    "value",
    (
        "A" * 3,
        *_BARE_PREFIXES,
        *(prefix + "\n" for prefix in _BARE_PREFIXES),
        *(prefix + "%" for prefix in _BARE_PREFIXES),
    ),
)
def test_production_pattern_miss_warns_and_preserves_value(value: str) -> None:
    with pytest.warns(UserWarning, match="Warning:.*production pattern"):
        assert FSMAEvent.validate_tlc_format(value) == value


def test_production_pattern_match_has_no_warning() -> None:
    value = "0" * 14 + "A"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert FSMAEvent.validate_tlc_format(value) == value
    assert not caught


def test_lot_level_patterns_are_anchored() -> None:
    for pattern in (_TLC_LGTIN_RE, _TLC_DIGITAL_LINK_RE):
        assert isinstance(pattern, re.Pattern)
        assert pattern.pattern.startswith("^")
        assert pattern.pattern.endswith(r"\Z")
        assert pattern.flags & re.MULTILINE == 0


def test_identifier_digits_are_ascii() -> None:
    for pattern in (_TLC_LGTIN_RE, _TLC_DIGITAL_LINK_RE):
        assert r"\d" not in pattern.pattern
        assert "[0-9]" in pattern.pattern


def test_digital_link_pattern_has_optional_stem_before_01() -> None:
    pattern = _TLC_DIGITAL_LINK_RE.pattern
    assert _DL_CUSTOM_STEM in pattern
    assert pattern.index(_DL_CUSTOM_STEM) < pattern.index("/01/")
    assert "/01/[0-9]{14}/10/" in pattern


def test_lot_patterns_count_escapes_outside_the_length_quantifier() -> None:
    for pattern in (_TLC_LGTIN_RE, _TLC_DIGITAL_LINK_RE):
        assert "(?P<lot>" in pattern.pattern
        assert _PCT_ESCAPE in pattern.pattern
        assert "{1,20}" not in pattern.pattern
    assert _DL_LOT_RAW_CLASS in _TLC_DIGITAL_LINK_RE.pattern
    assert _LGTIN_LOT_RAW_CLASS in _TLC_LGTIN_RE.pattern
    for char in "!%&'()*+,/:;<=>?#":
        assert char not in _DL_LOT_RAW_CLASS
    for char in '"%&/<>?':
        assert char not in _LGTIN_LOT_RAW_CLASS


def test_ai82_charset_is_the_gs1_graphic_set() -> None:
    assert len(_GS1_AI_82_CHARS) == 82
    assert " " not in _GS1_AI_82_CHARS
    assert all(len(char) == 1 and char.isascii() and not char.isspace() for char in _GS1_AI_82_CHARS)


def test_ai10_length_limit_is_applied_after_percent_decode() -> None:
    assert _decoded_ai10_lot_within_limit("x" * 1)
    assert _decoded_ai10_lot_within_limit("x" * 20)
    assert not _decoded_ai10_lot_within_limit("x" * 21)
    assert _decoded_ai10_lot_within_limit("%41" * 20)
    assert not _decoded_ai10_lot_within_limit("%41" * 21)
    assert not _decoded_ai10_lot_within_limit("")
    assert not _decoded_ai10_lot_within_limit("%")


def test_tlc_field_minimum_does_not_reject_plain_three_character_value() -> None:
    field = FSMAEvent.model_fields["tlc"]
    adapter = TypeAdapter(Annotated[field.annotation, *field.metadata])
    assert adapter.validate_python("A" * 3) == "A" * 3
    with pytest.raises(ValueError):
        adapter.validate_python("A" * 2)
