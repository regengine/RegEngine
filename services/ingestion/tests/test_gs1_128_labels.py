"""SEL-444: GS1-128 label encoding.

Data free by design. Digit strings are built at runtime and their check
digits come from compute_gs1_check_digit. Assertions check structure.
"""

from __future__ import annotations

import calendar
import random
import sys
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


def _rng(*parts: object) -> random.Random:
    return random.Random("sel444:" + ":".join(str(part) for part in parts))


def _digits(rng: random.Random, length: int) -> str:
    return "".join(str(rng.randrange(10)) for _ in range(length))


def _with_check(rng: random.Random, body_length: int) -> str:
    body = _digits(rng, body_length)
    return body + str(compute_gs1_check_digit(body))


def _flip_check(rng: random.Random, value: str) -> str:
    updated = (int(value[-1]) + rng.randrange(1, 10)) % 10
    return value[:-1] + str(updated)


def _ymd(year: int, month: int, day: int) -> str:
    return f"{year:02d}{month:02d}{day:02d}"


def _date(rng: random.Random, *, day_zero: bool = False) -> str:
    year = rng.randrange(100)
    month = rng.randrange(1, 13)
    if day_zero:
        return _ymd(year, month, 0)
    # Years 2000 through 2099, the same calendar the encoder uses.
    last = calendar.monthrange(2000 + year, month)[1]
    return _ymd(year, month, rng.randrange(1, last + 1))


def _letters(rng: random.Random, length: int) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "".join(rng.choice(alphabet) for _ in range(length))


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


def _sample(rng: random.Random) -> list[tuple[str, str]]:
    """One of every supported AI, shuffled. Values exist only at runtime."""
    elements = [
        ("00", _with_check(rng, 17)),
        ("01", _with_check(rng, 13)),
        ("02", _with_check(rng, 13)),
        ("11", _date(rng, day_zero=True)),
        ("13", _date(rng)),
        ("15", _date(rng)),
        ("17", _date(rng)),
        ("410", _with_check(rng, 12)),
        ("414", _with_check(rng, 12)),
        ("10", _letters(rng, rng.randrange(1, 21))),
        # The extra ">" must stay inside the 20-character serial limit.
        ("21", _letters(rng, rng.randrange(1, 20)) + ">"),
        ("37", _digits(rng, rng.randrange(1, 9))),
    ]
    rng.shuffle(elements)
    return elements


@pytest.mark.parametrize("fn", _ENTRYPOINTS)
@pytest.mark.parametrize("raw", [None, [], ()])
def test_empty_input_raises(fn, raw):
    with pytest.raises(Gs1LabelError):
        fn(raw)


def test_error_is_a_value_error():
    assert issubclass(Gs1LabelError, ValueError)


@pytest.mark.parametrize("fn", _ENTRYPOINTS)
def test_unknown_ai_raises_without_echoing_the_value(fn):
    rng = _rng("unknown", fn.__name__)
    value = _letters(rng, 8)
    with pytest.raises(Gs1LabelError) as caught:
        fn([("ZZ", value)])
    assert value not in str(caught.value)
    assert "ZZ" not in str(caught.value)


@pytest.mark.parametrize("ai,body_length", [("01", 13), ("02", 13), ("00", 17), ("410", 12), ("414", 12)])
def test_runtime_identifiers_pass_and_a_mutated_check_digit_raises(ai, body_length):
    rng = _rng("check", ai, body_length)
    good = _with_check(rng, body_length)
    assert int(good[-1]) == compute_gs1_check_digit(good[:-1])
    assert human_readable([(ai, good)]) == f"({ai}){good}"
    bad = _flip_check(rng, good)
    assert bad != good
    with pytest.raises(Gs1LabelError) as caught:
        encode_gs1_128([(ai, bad)])
    message = str(caught.value)
    assert "check digit" in message
    assert bad not in message
    assert good not in message


def test_day_zero_is_allowed_and_impossible_dates_raise():
    rng = _rng("dates")
    gtin = _with_check(rng, 13)
    human_readable([("11", _date(rng, day_zero=True)), ("01", gtin)])
    leap = rng.randrange(0, 25) * 4
    human_readable([("13", _ymd(leap, 2, 29))])
    with pytest.raises(Gs1LabelError):
        human_readable([("13", _ymd(leap + 1, 2, 29))])
    with pytest.raises(Gs1LabelError):
        human_readable([("15", _ymd(rng.randrange(100), 4, 31))])
    human_readable([("17", _ymd(rng.randrange(100), 4, 0))])
    with pytest.raises(Gs1LabelError):
        human_readable([("11", _ymd(rng.randrange(100), 0, 1))])


def test_variable_fields_accept_limits_and_reject_bad_shape():
    rng = _rng("variable")
    gtin = _with_check(rng, 13)
    human_readable([("10", _letters(rng, 20)), ("01", gtin)])
    human_readable([("37", _digits(rng, 8)), ("01", gtin)])
    with pytest.raises(Gs1LabelError):
        human_readable([("10", _letters(rng, 21)), ("01", gtin)])
    with pytest.raises(Gs1LabelError):
        human_readable([("10", " "), ("01", gtin)])
    with pytest.raises(Gs1LabelError):
        human_readable([("37", _letters(rng, 2)), ("01", gtin)])
    with pytest.raises(Gs1LabelError):
        human_readable([("37", _digits(rng, 9)), ("01", gtin)])
    with pytest.raises(Gs1LabelError):
        human_readable([("21", ""), ("01", gtin)])


def test_charset_is_exactly_82_printable_characters():
    rng = _rng("charset")
    gtin = _with_check(rng, 13)
    accepted = []
    for code in range(32, 127):
        character = chr(code)
        try:
            human_readable([("10", character), ("01", gtin)])
        except Gs1LabelError:
            continue
        accepted.append(character)
    assert len(accepted) == 82
    assert " " not in accepted
    assert all(character.isprintable() for character in accepted)


def test_ordering_puts_fixed_fields_first_and_gs_only_between_variable_fields():
    rng = _rng("order")
    elements = [
        ("21", _letters(rng, 4)),
        ("17", _date(rng)),
        ("10", _letters(rng, 6)),
        ("01", _with_check(rng, 13)),
        ("37", _digits(rng, 3)),
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


@pytest.mark.parametrize("salt", range(8))
def test_code128_round_trip_checksum_start_and_stop(salt):
    rng = _rng("code128", salt)
    elements = _sample(rng)
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
    rng = _rng("shape")
    gtin = _with_check(rng, 13)
    short = _with_check(rng, 7)
    assert len(short) == 8
    assert int(short[-1]) == compute_gs1_check_digit(short[:-1])
    with pytest.raises(Gs1LabelError) as caught:
        encode_gs1_128([("01", short)])
    assert short not in str(caught.value)
    assert human_readable([("01", f"  {gtin}\n")]) == f"(01){gtin}"
    other = _with_check(rng, 13)
    with pytest.raises(Gs1LabelError) as repeated:
        human_readable([("01", gtin), ("01", other)])
    assert gtin not in str(repeated.value)
    assert other not in str(repeated.value)


def test_all_digit_label_stays_in_code_c_with_one_leading_fnc1():
    rng = _rng("numeric")
    elements = [("17", _date(rng)), ("01", _with_check(rng, 13))]
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
    rng = _rng("latch-pair")
    pair = f"{_CODE_C:02d}"
    body = pair + _digits(rng, 11)
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
    rng = _rng("dict")
    gtin = _with_check(rng, 13)
    lot = _letters(rng, 5)
    pairs = [("10", lot), ("01", gtin)]
    as_dicts = [{"ai": ai, "value": value} for ai, value in pairs]
    assert human_readable(as_dicts) == human_readable(pairs)
    assert encode_gs1_128(as_dicts) == encode_gs1_128(pairs)


def test_zpl_framing_and_fnc1_markers():
    rng = _rng("zpl")
    elements = _sample(rng)
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
    rng = _rng("pdf")
    elements = _sample(rng)
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
