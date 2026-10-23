"""Data-free validation and empty-payload checks for QR decoding."""

from __future__ import annotations

from app.qr_decoder import (
    _AI_FIXED_LENGTH,
    QRDecodedFields,
    _find_next_field_boundary,
    _is_valid_gtin_check_digit,
    _looks_like_ai_at,
    _parse_digital_link,
    _parse_gs1_ai,
    _parse_yymmdd,
    router,
)


def test_wrong_length_gtin_rejected() -> None:
    assert _is_valid_gtin_check_digit("") is False


def test_non_digits_gtin_rejected() -> None:
    assert _is_valid_gtin_check_digit(" " * 14) is False


def test_empty_date_rejected() -> None:
    assert _parse_yymmdd("") is None


def test_invalid_calendar_date_rejected() -> None:
    assert _parse_yymmdd("000000") is None


def test_fixed_length_ai_requires_complete_field() -> None:
    ai, length = next(iter(_AI_FIXED_LENGTH.items()))
    assert _looks_like_ai_at(ai, 0) is False
    assert _looks_like_ai_at(ai + " " * length, 0) is True


def test_empty_field_boundary() -> None:
    assert _find_next_field_boundary("", 0) == 0
    assert _find_next_field_boundary(chr(29), 0) == 0


def test_empty_digital_link_rejected() -> None:
    assert _parse_digital_link("") is None
    assert _parse_digital_link("   ") is None
    assert _parse_digital_link("/01/") is None


def test_empty_gs1_ai_has_no_fields() -> None:
    fields = _parse_gs1_ai("")
    assert fields == QRDecodedFields(source_format="gs1_ai")


def test_router_registers_decode() -> None:
    assert "/api/v1/qr/decode" in {route.path for route in router.routes}
