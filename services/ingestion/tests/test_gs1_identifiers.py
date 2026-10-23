"""SEL-429: offline GS1 GTIN, GLN and SSCC validation.

Data free by design: no real, sample or invented identifiers. Positive cases
are all zero strings (whose GS1 mod-10 check digit is 0) and values whose last
digit comes from ``compute_gs1_check_digit`` itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.gs1_identifiers import (  # noqa: E402
    GLN_LENGTHS,
    GTIN_LENGTHS,
    SSCC_LENGTHS,
    compute_gs1_check_digit,
    describe_row_issue,
    validate_gln,
    validate_gtin,
    validate_sscc,
)

CASES = [
    (validate_gtin, "GTIN", GTIN_LENGTHS),
    (validate_gln, "GLN", GLN_LENGTHS),
    (validate_sscc, "SSCC", SSCC_LENGTHS),
]
VALID = [(fn, kind, n) for fn, kind, lengths in CASES for n in lengths]
DASHES = ("-", "‐", "‑", "‒", "–", "—", "−")


def _assert_plain(message: str | None) -> None:
    assert message
    for dash in DASHES:
        assert dash not in message


@pytest.mark.parametrize("fn,kind,n", VALID)
def test_all_zero_string_of_each_valid_length_passes_silently(fn, kind, n):
    result = fn("0" * n)
    assert result.is_valid
    assert result.kind == kind
    assert result.value == "0" * n
    assert result.error is None


@pytest.mark.parametrize("fn,kind,n", VALID)
@pytest.mark.parametrize("last", range(1, 10))
def test_changing_only_the_check_digit_fails(fn, kind, n, last):
    result = fn("0" * (n - 1) + str(last))
    assert not result.is_valid
    assert result.value is None
    assert "check digit" in result.error
    _assert_plain(result.error)


@pytest.mark.parametrize("fn,kind,n", VALID)
def test_round_trip_with_computed_check_digit(fn, kind, n):
    body = "0" * (n - 1)
    assert fn(body + str(compute_gs1_check_digit(body))).is_valid


@pytest.mark.parametrize("fn,kind,n", VALID)
@pytest.mark.parametrize("pos", [0, -2])
def test_round_trip_with_one_nonzero_body_digit(fn, kind, n, pos):
    # Exercises both GS1 weights (3 and 1) without inventing an identifier.
    for d in range(1, 10):
        body = list("0" * (n - 1))
        body[pos] = str(d)
        body_s = "".join(body)
        check = compute_gs1_check_digit(body_s)
        assert fn(body_s + str(check)).is_valid
        assert not fn(body_s + str((check + 1) % 10)).is_valid


def test_compute_check_digit_of_all_zero_body_is_zero():
    for n in range(1, 18):
        assert compute_gs1_check_digit("0" * n) == 0


@pytest.mark.parametrize("bad", ["", "000 0", "0a", None])
def test_compute_check_digit_rejects_non_digit_body(bad):
    with pytest.raises(ValueError):
        compute_gs1_check_digit(bad)


@pytest.mark.parametrize("fn,kind,lengths", CASES)
@pytest.mark.parametrize("raw", [None, "", " ", "\t\n  "])
def test_none_empty_and_whitespace_only_are_flagged_as_empty(fn, kind, lengths, raw):
    result = fn(raw)
    assert not result.is_valid
    assert result.error.startswith(f"{kind} is empty")
    _assert_plain(result.error)


@pytest.mark.parametrize("fn,kind,lengths", CASES)
def test_wrong_lengths_are_flagged(fn, kind, lengths):
    for n in range(1, 21):
        if n in lengths:
            continue
        result = fn("0" * n)
        assert not result.is_valid, n
        assert f"has {n} digits" in result.error
        _assert_plain(result.error)


@pytest.mark.parametrize("fn,kind,n", VALID)
def test_surrounding_whitespace_is_trimmed(fn, kind, n):
    result = fn(f"  {'0' * n}\t")
    assert result.is_valid
    assert result.value == "0" * n


@pytest.mark.parametrize("fn,kind,n", VALID)
@pytest.mark.parametrize(
    "inject",
    [
        "a",
        "-",
        ".",
        "٠",  # ARABIC-INDIC DIGIT ZERO: isdigit() is True, but not 0 to 9
        "²",  # SUPERSCRIPT TWO
    ],
)
def test_non_digit_characters_are_flagged(fn, kind, n, inject):
    zeros = "0" * n
    for value in (inject + zeros[1:], zeros[: n // 2] + inject + zeros[n // 2 + 1 :]):
        result = fn(value)
        assert not result.is_valid, repr(value)
        assert "characters other than digits" in result.error
        _assert_plain(result.error)


@pytest.mark.parametrize("fn,kind,n", VALID)
@pytest.mark.parametrize("space", [" ", "\t", " "])
def test_internal_whitespace_is_flagged(fn, kind, n, space):
    zeros = "0" * n
    result = fn(zeros[: n // 2] + space + zeros[n // 2 :])
    assert not result.is_valid
    assert "characters other than digits" in result.error
    _assert_plain(result.error)


@pytest.mark.parametrize("fn,kind,lengths", CASES)
def test_non_string_input_is_flagged(fn, kind, lengths):
    result = fn(0)
    assert not result.is_valid
    assert "as text" in result.error
    _assert_plain(result.error)


def test_row_issue_names_field_supplier_and_row():
    result = validate_gln("0" * 12 + "1")
    message = describe_row_issue(result, field="ship_from_gln", row=7, supplier="Supplier A")
    assert message.startswith("Row 7 from Supplier A, field ship_from_gln: GLN check digit")
    _assert_plain(message)


def test_row_issue_without_supplier():
    message = describe_row_issue(validate_sscc(""), field="sscc", row=2)
    assert message.startswith("Row 2, field sscc: SSCC is empty")
