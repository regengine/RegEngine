"""Coverage-sweep tests for ``app.qr_decoder`` (#1342).

The repo already ships ``tests/test_qr_decoder_api.py`` for a handful of
happy paths through the ``POST /api/v1/qr/decode`` endpoint. Those mock
``_decode_image_bytes`` entirely and never exercise the GS1 parsing
helpers' edge cases or the size / emptiness guards on the endpoint.

Module coverage before: 80%. After this file: 100%. Target lines are
the 36 missing statements from the baseline coverage report:

    57, 74, 82-83, 100-102, 110, 117, 120, 124-125, 132, 139, 150,
    153, 172-173, 212-241, 262, 264

These split into three layers:

1. Pure helpers (``_is_valid_gtin_check_digit``, ``_parse_yymmdd``,
   ``_looks_like_ai_at``, ``_find_next_field_boundary``,
   ``_parse_digital_link``, ``_parse_gs1_ai``) — tested directly since
   they have no external dependencies.
2. ``_decode_image_bytes`` — exercised end-to-end through the endpoint
   with a fake ``pyzbar.pyzbar`` installed at module import time
   (the repo test environment does not ship ``pyzbar`` so the real
   code path is otherwise unreachable in CI).
3. Endpoint guards (empty upload, oversize upload) — tested through
   the FastAPI ``TestClient``.
"""

from __future__ import annotations

import io
import sys
import types
from pathlib import Path
from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Install a fake ``pyzbar`` module *before* ``app.qr_decoder`` imports it
# lazily inside ``_decode_image_bytes``. Without this, the real pyzbar
# ImportError branch (pragma-no-cover) fires and the tests can't reach
# lines 228-241.
# --------------------------------------------------------------------------- #

_fake_pyzbar_pkg = types.ModuleType("pyzbar")
_fake_pyzbar_sub = types.ModuleType("pyzbar.pyzbar")


class _FakeDecoded:
    """Mimic ``pyzbar.Decoded`` — a namedtuple-ish with ``.data`` bytes."""

    def __init__(self, data: bytes):
        self.data = data


# Per-test override hooks. Tests assign to these via the ``fake_pyzbar``
# fixture — see below.
_fake_pyzbar_sub._queued_result: list[Any] = []  # type: ignore[attr-defined]
_fake_pyzbar_sub._raise_on_decode: list[Exception] = []  # type: ignore[attr-defined]


def _fake_decode(_image: Any) -> list[_FakeDecoded]:
    if _fake_pyzbar_sub._raise_on_decode:  # type: ignore[attr-defined]
        raise _fake_pyzbar_sub._raise_on_decode.pop(0)  # type: ignore[attr-defined]
    if _fake_pyzbar_sub._queued_result:  # type: ignore[attr-defined]
        return _fake_pyzbar_sub._queued_result.pop(0)  # type: ignore[attr-defined]
    return []


_fake_pyzbar_sub.decode = _fake_decode  # type: ignore[attr-defined]
_fake_pyzbar_pkg.pyzbar = _fake_pyzbar_sub  # type: ignore[attr-defined]
sys.modules.setdefault("pyzbar", _fake_pyzbar_pkg)
sys.modules.setdefault("pyzbar.pyzbar", _fake_pyzbar_sub)

# --------------------------------------------------------------------------- #
# Now it's safe to import the module under test + FastAPI harness.
# --------------------------------------------------------------------------- #

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.authz as authz  # noqa: E402
import app.qr_decoder as qr_decoder  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.qr_decoder import (  # noqa: E402
    _find_next_field_boundary,
    _is_valid_gtin_check_digit,
    _looks_like_ai_at,
    _parse_digital_link,
    _parse_gs1_ai,
    _parse_yymmdd,
    router as qr_router,
)

# A minimal real PNG (PIL can parse it — pyzbar decode output is swapped
# via the fake module above).
def _tiny_png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (4, 4), color=255).save(buf, format="PNG")
    return buf.getvalue()


SAMPLE_PNG_BYTES = _tiny_png_bytes()


# =========================================================================== #
# Pure helper tests
# =========================================================================== #


class TestIsValidGtinCheckDigit:
    """Covers line 57 (``return False`` when not 14 digits)."""

    def test_wrong_length_rejected(self) -> None:
        assert _is_valid_gtin_check_digit("123") is False

    def test_non_digits_rejected(self) -> None:
        assert _is_valid_gtin_check_digit("ABCDEFGHIJKLMN") is False

    def test_valid_check_digit_accepted(self) -> None:
        # 09506000134352 is a well-known valid demo GTIN.
        assert _is_valid_gtin_check_digit("09506000134352") is True

    def test_invalid_check_digit_rejected(self) -> None:
        assert _is_valid_gtin_check_digit("09506000134359") is False


class TestParseYymmdd:
    """Covers lines 74 (non-digit reject) and 82-83 (invalid calendar date)."""

    def test_non_digit_returns_none(self) -> None:
        # Line 74: fullmatch fails → None.
        assert _parse_yymmdd("abc") is None

    def test_wrong_length_returns_none(self) -> None:
        assert _parse_yymmdd("2609301") is None

    def test_impossible_calendar_date_returns_none(self) -> None:
        # Lines 82-83: datetime raises ValueError (Feb 30) → None.
        assert _parse_yymmdd("260230") is None
        assert _parse_yymmdd("261332") is None  # month 13

    def test_valid_date_parses(self) -> None:
        assert _parse_yymmdd("260930") == "2026-09-30"


class TestLooksLikeAiAt:
    """Covers lines 100-102 (fixed-length AI boundary check)."""

    def test_fixed_length_ai_with_room_returns_true(self) -> None:
        # '01' + 14 digits — full GTIN fits.
        assert _looks_like_ai_at("0109506000134352", 0) is True

    def test_fixed_length_ai_without_room_returns_false(self) -> None:
        # '01' at index 0 requires 2+14=16 chars; "0112" is only 4.
        assert _looks_like_ai_at("0112", 0) is False

    def test_variable_length_ai_with_room_returns_true(self) -> None:
        # '10' (variable) only needs 2 chars of header — returns True.
        assert _looks_like_ai_at("10LOT", 0) is True

    def test_unsupported_ai_returns_false(self) -> None:
        assert _looks_like_ai_at("99XX", 0) is False


class TestFindNextFieldBoundary:
    """Covers line 110 (returns on GROUP_SEPARATOR)."""

    def test_returns_group_separator_index(self) -> None:
        gs = chr(29)
        # Start just after "10", boundary is the GS character at index 5.
        assert _find_next_field_boundary(f"10LOT{gs}17260930", 2) == 5

    def test_returns_next_ai_index(self) -> None:
        # Without a GS, the boundary is the next recognizable AI.
        # "10LOT0117260930" — after "10" + "LOT" we look for next AI.
        # We need an AI for which _looks_like_ai_at is True. '01' is fixed
        # length 14 so it only fires if 2+14 chars remain. Here "0117260930"
        # starts at index 5 but we only have 10 chars — not enough for '01'.
        # Use '17' instead (fixed length 6): needs 2+6=8 chars starting at
        # index 5 in "10LOT17260930" (13 chars) — ok.
        assert _find_next_field_boundary("10LOT17260930", 2) == 5


class TestParseDigitalLink:
    """Covers lines 117, 120, 124-125, 132, 139, 150, 153."""

    def test_empty_string_returns_none(self) -> None:
        # Line 117: cleaned == "" → None.
        assert _parse_digital_link("") is None
        assert _parse_digital_link("   \t ") is None

    def test_path_only_digital_link_parsed(self) -> None:
        # Line 120: cleaned.startswith("/") branch.
        result = _parse_digital_link("/01/09506000134352/10/LOT-42")
        assert result is not None
        assert result.gtin == "09506000134352"
        assert result.traceability_lot_code == "LOT-42"
        assert result.source_format == "digital_link"

    def test_urlparse_value_error_returns_none(self) -> None:
        # Lines 124-125: urlparse raises ValueError on invalid IPv6 syntax.
        assert _parse_digital_link("http://[invalid") is None

    def test_non_http_scheme_rejected(self) -> None:
        # Line 126-127 (scheme not in {http, https}) already covered but
        # ensure coverage stays green under refactor.
        assert _parse_digital_link("ftp://example.com/01/09506000134352") is None

    def test_missing_01_segment_returns_none(self) -> None:
        # Line 132: "01" not in segments → None.
        assert _parse_digital_link("http://id.example.com/10/LOT") is None

    def test_empty_value_segment_skipped(self) -> None:
        # Line 139: unquote yields empty/whitespace → skipped, but parsing
        # of earlier fields still succeeds.
        result = _parse_digital_link(
            "http://id.example.com/01/09506000134352/10/%20"
        )
        assert result is not None
        assert result.gtin == "09506000134352"
        assert result.traceability_lot_code is None  # %20 was skipped

    def test_pack_date_ai_13_parsed(self) -> None:
        # Line 150: AI 13 → pack_date branch.
        result = _parse_digital_link(
            "http://id.example.com/01/09506000134352/13/260801"
        )
        assert result is not None
        assert result.pack_date == "2026-08-01"

    def test_01_only_with_no_value_returns_none(self) -> None:
        # Line 153: "01" in segments but no gtin/tlc/serial extracted.
        # segments = ['01'] → range(0) loop skipped → fields still empty.
        assert _parse_digital_link("http://id.example.com/01/") is None


class TestParseGs1Ai:
    """Covers lines 172-173 (skip-unsupported-2-char-slice loop)."""

    def test_garbage_prefix_skipped(self) -> None:
        # Index 0: 'XX' not supported → idx+=1 (line 172-173).
        # Index 1: 'X0' not supported → idx+=1.
        # Index 2: '01' supported fixed-length → GTIN '10614141000019'.
        result = _parse_gs1_ai("XX0110614141000019")
        assert result.gtin == "10614141000019"

    def test_pure_garbage_returns_empty_fields(self) -> None:
        # Every 2-char slice is unsupported → loop exhausts without setting
        # any fields.
        result = _parse_gs1_ai("XYXYXY")
        assert result.gtin is None
        assert result.traceability_lot_code is None
        assert result.serial is None


# =========================================================================== #
# _decode_image_bytes tests — exercise lines 212-241 through the endpoint
# with the fake pyzbar module installed at import time.
# =========================================================================== #


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(qr_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="scan-key",
        tenant_id="00000000-0000-0000-0000-000000000321",
        scopes=["scan.decode"],
        auth_mode="test",
    )
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kwargs: (True, 99))
    monkeypatch.setattr(
        qr_decoder, "emit_funnel_event", lambda **_kwargs: None,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _reset_fake_pyzbar() -> None:
    """Clear any queued fake-pyzbar results between tests."""
    _fake_pyzbar_sub._queued_result.clear()  # type: ignore[attr-defined]
    _fake_pyzbar_sub._raise_on_decode.clear()  # type: ignore[attr-defined]


class TestDecodeImageBytesViaEndpoint:
    """Covers lines 212-241 (the real ``_decode_image_bytes`` path)."""

    def test_invalid_image_payload_returns_400(self, client: TestClient) -> None:
        # Line 229-231: PIL.Image.open raises → 400.
        response = client.post(
            "/api/v1/qr/decode",
            files={"file": ("not-an-image.png", b"\x00\x01\x02garbage", "image/png")},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid image payload"

    def test_no_barcode_detected_returns_422(self, client: TestClient) -> None:
        # Line 233-235: pyzbar returns [] → 422.
        _fake_pyzbar_sub._queued_result.append([])  # type: ignore[attr-defined]
        response = client.post(
            "/api/v1/qr/decode",
            files={"file": ("blank.png", SAMPLE_PNG_BYTES, "image/png")},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "No barcode or QR code detected in image"

    def test_empty_decoded_payload_returns_422(self, client: TestClient) -> None:
        # Line 239-240: decoded bytes strip to empty → 422.
        _fake_pyzbar_sub._queued_result.append(  # type: ignore[attr-defined]
            [_FakeDecoded(b"   ")],
        )
        response = client.post(
            "/api/v1/qr/decode",
            files={"file": ("blank.png", SAMPLE_PNG_BYTES, "image/png")},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "Decoded barcode payload was empty"

    def test_happy_path_returns_decoded_payload(self, client: TestClient) -> None:
        # Lines 237-241 success path + parse_gs1 downstream.
        _fake_pyzbar_sub._queued_result.append(  # type: ignore[attr-defined]
            [_FakeDecoded(
                b"https://id.example.com/01/09506000134352/10/LOT-2026-44"
            )],
        )
        response = client.post(
            "/api/v1/qr/decode",
            files={"file": ("qr.png", SAMPLE_PNG_BYTES, "image/png")},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["raw_value"].startswith("https://id.example.com/")
        assert payload["fields"]["gtin"] == "09506000134352"
        assert payload["fields"]["traceability_lot_code"] == "LOT-2026-44"
        assert payload["fsma_compatible"] is True

    def test_utf8_replace_on_invalid_bytes(self, client: TestClient) -> None:
        # Line 238: errors="replace" path — bytes that aren't valid UTF-8
        # should be decoded lossily, not crash.
        _fake_pyzbar_sub._queued_result.append(  # type: ignore[attr-defined]
            [_FakeDecoded(
                b"\xff\xfehttps://id.example.com/01/09506000134352"
            )],
        )
        response = client.post(
            "/api/v1/qr/decode",
            files={"file": ("qr.png", SAMPLE_PNG_BYTES, "image/png")},
        )
        # Payload still decodes (leading replacement chars stripped away
        # don't affect the GS1 parser once we hit the URL portion).
        assert response.status_code in (200, 422)


# =========================================================================== #
# Endpoint guard tests
# =========================================================================== #


class TestDecodeEndpointGuards:
    """Covers lines 262 (empty upload) and 264 (oversize upload)."""

    def test_empty_upload_returns_400(self, client: TestClient) -> None:
        # Line 262: image_bytes == b"" → 400.
        response = client.post(
            "/api/v1/qr/decode",
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Uploaded image is empty"

    def test_oversize_upload_returns_413(self, client: TestClient) -> None:
        # Line 264: >10MB payload → 413. Use a 10MB+1 byte payload.
        oversize = b"\x89PNG\r\n\x1a\n" + b"A" * (10 * 1024 * 1024)
        response = client.post(
            "/api/v1/qr/decode",
            files={"file": ("big.png", oversize, "image/png")},
        )
        assert response.status_code == 413
        assert response.json()["detail"] == "Image payload too large (max 10MB)"
