"""SEL-444: GS1-128 label encoding.

Identifiers are all zeros plus computed check digits. Dates come from
today's date and lot values from the length limits. No randomness. Assertions check structure.
"""

from __future__ import annotations

import calendar
import sys
from datetime import date
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.gs1_identifiers import compute_gs1_check_digit  # noqa: E402
from app.labels.gs1_128 import (  # noqa: E402
    Gs1LabelError,
    element_string,
    encode_gs1_128,
    human_readable,
    to_pdf,
    to_zpl,
)

_FIXED = ("00", "01", "02", "11", "13", "15", "17", "410", "414")
_VARIABLE = ("10", "21", "37")
_ENTRYPOINTS = (encode_gs1_128, human_readable, element_string, to_pdf, to_zpl)

# Code 128 symbol values. Independent of the encoder's private names.
_START_C = 105
_FNC1 = 102
_CODE_C = 99
_CODE_B = 100
_STOP = 106

# Dates are built from today's date. Nothing below is a fixed calendar date.
_TODAY = date.today()
_YY = _TODAY.strftime("%y")
_LEAP_YEAR = next(y for y in range(_TODAY.year, _TODAY.year + 8) if calendar.isleap(y))
_NON_LEAP_YEAR = next(y for y in range(_TODAY.year, _TODAY.year + 8) if not calendar.isleap(y))


def _yymmdd(year: int, month: int, day: int) -> str:
    return f"{year % 100:02d}{month:02d}{day:02d}"


# Day 00 means the whole month and is allowed.
_PLAIN_DATE = _TODAY.strftime("%y%m%d")
_DAY_ZERO = _yymmdd(_TODAY.year, _TODAY.month, 0)
_LEAP_DAY = _yymmdd(_LEAP_YEAR, 2, calendar.monthrange(_LEAP_YEAR, 2)[1])
# One day past the end of the month: Feb 29 in a non-leap year, and the
# day after the last day of this month.
_NON_LEAP_DAY = _yymmdd(_NON_LEAP_YEAR, 2, calendar.monthrange(_LEAP_YEAR, 2)[1])
_PAST_MONTH_END = _yymmdd(_TODAY.year, _TODAY.month, calendar.monthrange(_TODAY.year, _TODAY.month)[1] + 1)
_MONTH_ZERO = _yymmdd(_TODAY.year, 0, 1)

# Lot, serial and count values are built from the AI length limits.
_TEXT_MAX = 20  # AI 10 and AI 21
_COUNT_MAX = 8  # AI 37
_LOT = "0"
# ">" is ZPL's escape character. A serial ending in it forces a Code B latch
# (">6") and the escape (">0") in the ZPL field.
_ZPL_ESCAPE = ">"
_SERIAL_WITH_ESCAPE = "0" + _ZPL_ESCAPE
_NON_DIGIT = next(c for c in map(chr, range(33, 127)) if not c.isdigit())


def _zero_identifier(body_length: int) -> str:
    """All-zero body plus the mod-10 digit from compute_gs1_check_digit."""
    body = "0" * body_length
    return body + str(compute_gs1_check_digit(body))


def _bad_check(value: str) -> str:
    """Change only the last digit, deterministically: (d + 1) mod 10."""
    updated = (int(value[-1]) + 1) % 10
    return value[:-1] + str(updated)


_GTIN14 = _zero_identifier(13)
_GTIN8 = _zero_identifier(7)
_SSCC = _zero_identifier(17)
_GLN = _zero_identifier(12)

# Every supported AI. Input order is not fixed-then-variable, so the encoder
# still has to regroup. Serial ends in ">" so ZPL must latch to Code B (">6")
# and escape ">" as ">0". An all-zero label would stay in Code C and emit neither.
_ALL_AIS = [
    ("21", _SERIAL_WITH_ESCAPE),
    ("17", _PLAIN_DATE),
    ("10", _LOT),
    ("01", _GTIN14),
    ("00", _SSCC),
    ("37", _LOT),
    ("11", _DAY_ZERO),
    ("02", _GTIN14),
    ("13", _LEAP_DAY),
    ("410", _GLN),
    ("15", _PLAIN_DATE),
    ("414", _GLN),
]


def _order(elements: list[tuple[str, str]]) -> list[tuple[str, str]]:
    fixed = [element for element in elements if element[0] in _FIXED]
    variable = [element for element in elements if element[0] in _VARIABLE]
    return fixed + variable


def _expect_human(elements: list[tuple[str, str]]) -> str:
    return "".join(f"({ai}){value}" for ai, value in _order(elements))


def _expect_element(elements: list[tuple[str, str]]) -> str:
    ordered = _order(elements)
    variable = [element for element in ordered if element[0] in _VARIABLE]
    chunks: list[str] = []
    seen = 0
    for ai, value in ordered:
        chunks.append(ai + value)
        if ai in _VARIABLE:
            seen += 1
            if seen < len(variable):
                chunks.append("\x1d")
    return "".join(chunks)


def _checksum(symbols: list[int]) -> int:
    total = symbols[0]
    for position, value in enumerate(symbols[1:], start=1):
        total += position * value
    return total % 103


def _decode(codewords: list[int]) -> str:
    assert codewords[0] == _START_C
    assert codewords[1] == _FNC1
    assert codewords[-1] == _STOP
    mode = "C"
    chars: list[str] = []
    for codeword in codewords[2:-2]:
        # In Code C, symbol 99 is the digit pair 99. The same number latches
        # to Code C only while the encoder is in Code B.
        if mode == "C":
            if codeword == _CODE_B:
                mode = "B"
            elif codeword == _FNC1:
                chars.append("\x1d")
            else:
                assert 0 <= codeword <= 99
                chars.append(f"{codeword:02d}")
            continue
        if codeword == _CODE_C:
            mode = "C"
        elif codeword == _FNC1:
            chars.append("\x1d")
        else:
            assert 0 <= codeword <= 95
            chars.append(chr(codeword + 32))
    return "".join(chars)


def _barcode_field(zpl: str) -> str:
    marker = "^FD>;>8"
    start = zpl.index(marker) + len("^FD")
    return zpl[start : zpl.index("^FS", start)]


@pytest.mark.parametrize("fn", _ENTRYPOINTS)
@pytest.mark.parametrize("raw", [None, [], ()])
def test_empty_input_raises(fn, raw):
    with pytest.raises(Gs1LabelError):
        fn(raw)


def test_error_is_a_value_error():
    assert issubclass(Gs1LabelError, ValueError)


@pytest.mark.parametrize("fn", _ENTRYPOINTS)
def test_unknown_ai_raises_without_echoing_the_value(fn):
    value = _LOT
    with pytest.raises(Gs1LabelError) as caught:
        fn([("ZZ", value)])
    assert value not in str(caught.value)
    assert "ZZ" not in str(caught.value)


@pytest.mark.parametrize("ai,body_length", [("01", 13), ("02", 13), ("00", 17), ("410", 12), ("414", 12)])
def test_runtime_identifiers_pass_and_a_mutated_check_digit_raises(ai, body_length):
    good = _zero_identifier(body_length)
    assert int(good[-1]) == compute_gs1_check_digit(good[:-1])
    assert human_readable([(ai, good)]) == f"({ai}){good}"
    bad = _bad_check(good)
    assert bad != good
    with pytest.raises(Gs1LabelError) as caught:
        encode_gs1_128([(ai, bad)])
    message = str(caught.value)
    assert "check digit" in message
    assert bad not in message
    assert good not in message


def test_day_zero_is_allowed_and_impossible_dates_raise():
    human_readable([("11", _DAY_ZERO), ("01", _GTIN14)])
    human_readable([("13", _LEAP_DAY)])
    human_readable([("17", _PLAIN_DATE)])
    with pytest.raises(Gs1LabelError):
        human_readable([("13", _NON_LEAP_DAY)])
    with pytest.raises(Gs1LabelError):
        human_readable([("15", _PAST_MONTH_END)])
    with pytest.raises(Gs1LabelError):
        human_readable([("11", _MONTH_ZERO)])


def test_variable_fields_accept_limits_and_reject_bad_shape():
    human_readable([("10", "0" * _TEXT_MAX), ("01", _GTIN14)])
    human_readable([("37", "0" * _COUNT_MAX), ("01", _GTIN14)])
    with pytest.raises(Gs1LabelError):
        human_readable([("10", "0" * (_TEXT_MAX + 1)), ("01", _GTIN14)])
    with pytest.raises(Gs1LabelError):
        human_readable([("10", " "), ("01", _GTIN14)])
    with pytest.raises(Gs1LabelError):
        human_readable([("37", "0" + _NON_DIGIT), ("01", _GTIN14)])
    with pytest.raises(Gs1LabelError):
        human_readable([("37", "0" * (_COUNT_MAX + 1)), ("01", _GTIN14)])
    with pytest.raises(Gs1LabelError):
        human_readable([("21", ""), ("01", _GTIN14)])


def test_charset_is_exactly_82_printable_characters():
    accepted = []
    for code in range(32, 127):
        character = chr(code)
        try:
            human_readable([("10", character), ("01", _GTIN14)])
        except Gs1LabelError:
            continue
        accepted.append(character)
    assert len(accepted) == 82
    assert " " not in accepted
    assert all(character.isprintable() for character in accepted)


def test_ordering_puts_fixed_fields_first_and_gs_only_between_variable_fields():
    elements = [
        ("21", _LOT),
        ("17", _PLAIN_DATE),
        ("10", _LOT),
        ("01", _GTIN14),
        ("37", _LOT),
    ]
    assert human_readable(elements) == _expect_human(elements)
    encoded = element_string(elements)
    assert encoded == _expect_element(elements)
    assert encoded.count("\x1d") == 2
    assert not encoded.startswith("\x1d")
    assert not encoded.endswith("\x1d")
    # Fixed fields keep input order (17 then 01), not numeric AI order.
    readable = human_readable(elements)
    assert readable.index("(17)") < readable.index("(01)")
    assert readable.index("(01)") < readable.index("(21)")
    assert readable.index("(21)") < readable.index("(10)")
    assert readable.index("(10)") < readable.index("(37)")
    fixed_only = [("17", elements[1][1]), ("01", elements[3][1])]
    assert "\x1d" not in element_string(fixed_only)


def test_code128_round_trip_checksum_start_and_stop():
    elements = _ALL_AIS
    codewords = encode_gs1_128(elements)
    assert codewords[0] == _START_C
    assert codewords[1] == _FNC1
    assert codewords[-1] == _STOP
    assert _checksum(codewords[:-2]) == codewords[-2]
    assert _decode(codewords) == element_string(elements)
    assert not _decode(codewords).endswith("\x1d")
    for ai, value in elements:
        if ai in ("01", "02", "00", "410", "414"):
            assert int(value[-1]) == compute_gs1_check_digit(value[:-1])
            assert value in _decode(codewords)


def test_short_gtin_whitespace_and_repeats():
    assert len(_GTIN8) == 8
    assert int(_GTIN8[-1]) == compute_gs1_check_digit(_GTIN8[:-1])
    with pytest.raises(Gs1LabelError) as caught:
        encode_gs1_128([("01", _GTIN8)])
    assert _GTIN8 not in str(caught.value)
    assert human_readable([("01", f"  {_GTIN14}\n")]) == f"(01){_GTIN14}"
    with pytest.raises(Gs1LabelError) as repeated:
        human_readable([("01", _GTIN14), ("01", _GTIN14)])
    assert _GTIN14 not in str(repeated.value)


def test_all_digit_label_stays_in_code_c_with_one_leading_fnc1():
    elements = [("17", _PLAIN_DATE), ("01", _GTIN14)]
    codewords = encode_gs1_128(elements)
    assert codewords[0] == _START_C
    assert codewords[1] == _FNC1
    assert _CODE_B not in codewords[2:-2]
    assert _FNC1 not in codewords[2:-2]
    barcode = _barcode_field(to_zpl(elements))
    assert barcode.startswith(">;>8")
    assert barcode.count(">8") == 1
    assert ">6" not in barcode


def test_code_c_pair_matching_the_latch_value_stays_digits():
    """A Code C symbol equal to the latch value is still two digits in ZPL."""
    pair = "99"
    assert _CODE_C == int(pair)
    body = pair + "0" * 11
    gtin = body + str(compute_gs1_check_digit(body))
    assert len(gtin) == 14
    assert str(compute_gs1_check_digit(gtin[:-1])) == gtin[-1]
    codewords = encode_gs1_128([("01", gtin)])
    assert _CODE_C in codewords[2:-2]
    assert _CODE_B not in codewords[2:-2]
    barcode = _barcode_field(to_zpl([("01", gtin)]))
    assert barcode.startswith(f">;>801{pair}")
    assert ">5" not in barcode
    assert ">6" not in barcode
    assert barcode.count(">8") == 1
    payload = barcode[len(">;>8") :]
    assert payload.isdigit()
    assert payload == "01" + gtin


def test_dict_elements_match_pairs():
    pairs = [("10", _LOT), ("01", _GTIN14)]
    as_dicts = [{"ai": ai, "value": value} for ai, value in pairs]
    assert human_readable(as_dicts) == human_readable(pairs)
    assert encode_gs1_128(as_dicts) == encode_gs1_128(pairs)


def test_zpl_framing_and_fnc1_markers():
    elements = _ALL_AIS
    zpl = to_zpl(elements)
    assert zpl.startswith("^XA")
    assert zpl.endswith("^XZ")
    assert "^BC" in zpl
    assert "^PW812" in zpl
    assert "^LL1218" in zpl
    barcode = _barcode_field(zpl)
    assert barcode.startswith(">;>8")
    variable_count = sum(1 for ai, _value in elements if ai in _VARIABLE)
    # Leading FNC1 plus one separator between each variable field, and none after the last.
    assert barcode.count(">8") == variable_count
    # ">6" is the Code C to Code B latch. ">0" is subset B's encoding of ">".
    # Both come from the serial ending in ">". All-zero digits would not produce them.
    assert ">6" in barcode
    assert ">0" in barcode
    for ai, value in _order(elements):
        assert f"^FD({ai}){value}^FS" in zpl
    custom = to_zpl(elements[:1], width_dots=400, height_dots=600)
    assert custom.startswith("^XA")
    assert custom.endswith("^XZ")
    assert "^PW400" in custom
    assert "^LL600" in custom
    assert _barcode_field(custom).startswith(">;>8")


def test_pdf_header_trailer_and_xref_offsets():
    elements = _ALL_AIS
    pdf = to_pdf(elements)
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.endswith(b"%%EOF")
    assert f"/MediaBox [0 0 {4 * 72} {6 * 72}]".encode("ascii") in pdf
    assert b"/BaseFont /Helvetica" in pdf
    assert b" re f\n" in pdf
    for ai, value in _order(elements):
        line = f"({ai}){value}".encode("ascii").hex().upper().encode("ascii")
        assert line in pdf

    startxref = pdf.rfind(b"startxref")
    pointer = pdf[startxref:].splitlines()
    assert pointer[0] == b"startxref"
    xref_at = int(pointer[1])
    assert pdf[xref_at : xref_at + 4] == b"xref"
    section = pdf[xref_at:].splitlines()
    start_at, count = section[1].split()
    assert start_at == b"0"
    count_i = int(count)
    entries = section[2 : 2 + count_i]
    assert len(entries) == count_i
    assert entries[0] == b"0000000000 65535 f "
    for index, entry in enumerate(entries[1:], start=1):
        offset = int(entry.split()[0])
        header = f"{index} 0 obj".encode("ascii")
        assert pdf[offset : offset + len(header)] == header

    length_at = pdf.index(b"/Length ")
    length_end = pdf.index(b" ", length_at + len(b"/Length "))
    declared = int(pdf[length_at + len(b"/Length ") : length_end])
    stream_at = pdf.index(b"stream\n", length_at) + len(b"stream\n")
    assert pdf[stream_at : stream_at + declared]
    assert pdf[stream_at + declared :].startswith(b"\nendstream")
    assert to_pdf(elements) == pdf
