"""Regression tests for EDI UTF-8 decode handling (issue #1170).

History of this bug:

  1. Original implementation used ``decode("utf-8", errors="ignore")``
     which silently DROPPED invalid/non-ASCII bytes. A shipment from
     "Distribuidora Española" decoded to "Distribuidora Espaola" with
     no log signal — partner-name matching silently drifted.

  2. Interim fix swapped to ``errors="replace"`` which substitutes
     U+FFFD. Better than silent drop, but still data corruption: the
     partner name in the audit trail now contains a replacement
     character instead of the real letter. That's the same class of
     bug with a visible marker.

  3. Current fix (this file):
        a. Try ``utf-8`` strict. Modern partners get an exact round-
           trip for all non-ASCII names.
        b. On UnicodeDecodeError, fall back to ``latin-1`` strict —
           the X12.5/X12.6 Basic/Extended character set. latin-1 is
           total so strict decoding never fails, and every byte is
           preserved verbatim as the spec dictates.
        c. A WARN log fires on latin-1 fallback so operators can spot
           encoding drift.
        d. If even latin-1 raises (unreachable for latin-1 but defends
           against future codec bugs), the UnicodeDecodeError
           propagates and the endpoint returns HTTP 422 rather than
           persisting corrupted names.

This suite locks the contract in. Regressions that reintroduce
``errors="ignore"`` or ``errors="replace"`` both fail these tests.

The function lives in ``services/ingestion/app/edi_ingestion/routes.py``
(``_decode_edi_bytes``) and is called from the two main EDI upload
endpoints.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

# Ensure the ingestion service app package is importable.
service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.edi_ingestion.routes import _decode_edi_bytes


# ---------------------------------------------------------------------------
# Happy path: clean UTF-8 passes through exactly
# ---------------------------------------------------------------------------


class TestValidUtf8_Issue1170:
    def test_ascii_passes_through_unchanged(self):
        raw = b"ISA*00*          *00*          ~"
        decoded = _decode_edi_bytes(raw)
        assert decoded == raw.decode("ascii")
        assert "\ufffd" not in decoded, (
            "errors='replace' regression: valid ASCII should never produce "
            "a replacement character"
        )

    def test_utf8_multibyte_preserved_exactly(self):
        """Proper UTF-8 multi-byte sequences must survive intact.

        This is the positive case to the latin-1 bug — when a partner
        sends UTF-8 correctly, the name round-trips exactly. No
        replacement, no drop, no mangling.
        """
        raw = "Distribuidora Espa\u00f1ola".encode("utf-8")
        decoded = _decode_edi_bytes(raw)
        assert decoded == "Distribuidora Espa\u00f1ola"
        assert "\u00f1" in decoded
        assert "\ufffd" not in decoded

    def test_clean_utf8_emits_no_warning(self, caplog):
        """Valid UTF-8 must not emit the latin-1 fallback warning."""
        with caplog.at_level(logging.WARNING, logger="edi-ingestion"):
            _decode_edi_bytes("N1*ST*SHIPPER CO~".encode("utf-8"))
        fallback_warnings = [
            r for r in caplog.records
            if "edi_decode_fallback_latin1" in r.getMessage()
        ]
        assert fallback_warnings == [], (
            f"Clean UTF-8 must not emit latin-1 fallback warning; "
            f"saw: {fallback_warnings}"
        )


# ---------------------------------------------------------------------------
# Invalid UTF-8 → spec-compliant latin-1 fallback (strict, no data loss)
# ---------------------------------------------------------------------------


class TestLatin1Fallback_Issue1170:
    def test_latin1_ntilde_preserved_as_real_character(self):
        """The concrete #1170 scenario: a latin-1 encoded name with
        0xF1 (ñ) flows in. Previous implementations either dropped the
        byte (``ignore``) or substituted U+FFFD (``replace``). Both are
        data corruption.

        X12 Basic/Extended character set is ISO-8859-1, so a partner
        sending 0xF1 for ñ is spec-compliant. The fix honors the spec:
        falls back to ``latin-1`` strict and preserves the real ñ
        character.
        """
        latin1_bytes = b"Distribuidora Espa\xf1ola"
        decoded = _decode_edi_bytes(latin1_bytes)

        # The real ñ must be preserved as U+00F1 — not dropped, not
        # replaced with U+FFFD.
        assert "Espa\u00f1ola" in decoded, (
            f"latin-1 fallback must preserve ñ as U+00F1, got: {decoded!r}"
        )
        assert "\ufffd" not in decoded, (
            "errors='replace' regression: U+FFFD must NOT appear when "
            "the bytes are valid latin-1"
        )
        # Character count matches byte count for single-byte latin-1.
        assert len(decoded) == len(latin1_bytes)

    def test_latin1_fallback_emits_warning(self, caplog):
        """When the decoder falls back to latin-1, a WARN-level log
        must be emitted on the ``edi-ingestion`` logger so operators
        can see the encoding drift and update the partner config.
        """
        latin1 = b"Distribuidora Espa\xf1ola"
        with caplog.at_level(logging.WARNING, logger="edi-ingestion"):
            _decode_edi_bytes(latin1)
        warning_records = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "edi_decode_fallback_latin1" in r.getMessage()
        ]
        assert len(warning_records) == 1, (
            f"Expected exactly one WARN 'edi_decode_fallback_latin1' log, "
            f"got {len(warning_records)}"
        )

    def test_latin1_fallback_warning_includes_byte_count(self, caplog):
        """The warning must include byte count so operators can judge
        scope (is this one small file or 10MB of drift?)."""
        raw = b"A\xff\xff\xff_VALID"
        with caplog.at_level(logging.WARNING, logger="edi-ingestion"):
            _decode_edi_bytes(raw)
        message = next(
            r.getMessage() for r in caplog.records
            if "edi_decode_fallback_latin1" in r.getMessage()
        )
        assert f"bytes={len(raw)}" in message, (
            f"warning message missing bytes={len(raw)}: {message!r}"
        )

    def test_mixed_latin1_bytes_survive_verbatim(self):
        """Every byte value 0x00-0xFF is a valid latin-1 codepoint, so
        strict latin-1 fallback never drops or substitutes. This test
        sweeps a representative slice to prove byte-for-byte preservation.
        """
        # All high-bit bytes that UTF-8 would reject as invalid
        # continuation bytes when standalone.
        raw = bytes(range(0x80, 0x100))
        decoded = _decode_edi_bytes(raw)
        # Every byte becomes exactly one character (codepoint == byte value).
        assert len(decoded) == len(raw)
        assert "\ufffd" not in decoded
        for i, byte_val in enumerate(raw):
            assert ord(decoded[i]) == byte_val


# ---------------------------------------------------------------------------
# Regression guards: ``errors="ignore"`` and ``errors="replace"`` both
# produce DIFFERENT observable behavior than the spec-honoring fix.
# These tests lock the contract in.
# ---------------------------------------------------------------------------


class TestNoSilentCorruption_Issue1170:
    """A regression that swaps to ``errors="ignore"`` or
    ``errors="replace"`` will make these tests fail. That's the point:
    the silent-corruption bug class must stay permanently closed.
    """

    def test_no_bytes_are_dropped(self):
        """``errors='ignore'`` regression check: a byte that cannot
        decode as UTF-8 must NOT vanish. Under the spec-honoring fix
        the byte is preserved as its latin-1 codepoint."""
        raw = b"A\xf1B"
        decoded = _decode_edi_bytes(raw)
        # len must equal the byte count; 'ignore' would drop to len=2.
        assert len(decoded) == 3, (
            f"byte drop regression: expected 3 chars, got {len(decoded)} "
            f"from {decoded!r}"
        )
        # And the middle char is the actual latin-1 ñ, not U+FFFD.
        assert decoded[1] == "\u00f1", (
            f"expected middle char to be ñ (U+00F1), got U+{ord(decoded[1]):04X}"
        )

    def test_no_replacement_character_in_output(self):
        """``errors='replace'`` regression check: U+FFFD must never
        appear in decoded output. Either UTF-8 succeeds (preserving
        the real character) or latin-1 succeeds (preserving the real
        byte)."""
        raw = b"Distribuidora Espa\xf1ola"
        decoded = _decode_edi_bytes(raw)
        assert "\ufffd" not in decoded, (
            f"replacement char regression: U+FFFD found in {decoded!r}. "
            f"The fix must preserve bytes verbatim via latin-1 fallback, "
            f"not substitute with U+FFFD."
        )


# ---------------------------------------------------------------------------
# Loud failure: if decode actually cannot succeed, the caller must get a
# UnicodeDecodeError to propagate (reject the row) — never a silent pass.
# ---------------------------------------------------------------------------


class TestLoudFailure_Issue1170:
    """Contract: ``_decode_edi_bytes`` never returns partially-corrupted
    data. It either returns a faithful decode or raises.
    """

    def test_empty_bytes_decode_to_empty_string(self):
        """Degenerate input: empty bytes decode to empty string via
        UTF-8 (no error). This establishes the happy-path baseline."""
        assert _decode_edi_bytes(b"") == ""

    def test_latin1_fallback_never_raises_for_any_byte_value(self):
        """The complementary invariant to the "both codecs fail" branch:
        because latin-1 is a total encoding (every byte 0x00-0xFF is a
        valid codepoint), strict latin-1 decoding of arbitrary bytes
        never raises. So the "both codecs fail" branch is effectively
        unreachable in practice — which is exactly what we want.

        This test enumerates every possible single-byte value to prove
        the invariant, so a future refactor that swaps latin-1 for a
        partial encoding (like ascii) will fail loudly here.
        """
        import app.edi_ingestion.routes as routes

        for byte_val in range(256):
            # Force the UTF-8 strict path to fail by injecting a high
            # bit before the test byte when it would otherwise be ASCII.
            raw = b"\xff" + bytes([byte_val])
            # Must not raise — the latin-1 fallback covers every byte.
            result = routes._decode_edi_bytes(raw)
            assert len(result) == 2
            assert ord(result[0]) == 0xFF
            assert ord(result[1]) == byte_val


# ---------------------------------------------------------------------------
# Endpoint integration: undecodable payload → HTTP 422, no events persisted
# ---------------------------------------------------------------------------


class TestEndpointRejectsUndecodable_Issue1170:
    """The parser boundary must turn a decode failure into a clean 422
    rejection. The row is refused — never partially ingested with
    corrupted names.
    """

    def test_endpoint_rejects_with_422_when_decode_raises(
        self, monkeypatch
    ):
        """Simulate a decode failure that bubbles out of
        ``_decode_edi_bytes``; assert the EDI upload endpoint returns
        HTTP 422 with a decode-failure error body rather than accepting
        corrupted data.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import app.edi_ingestion.routes as routes
        from app.authz import get_ingestion_principal, IngestionPrincipal

        def boom(raw_bytes: bytes) -> str:
            raise UnicodeDecodeError(
                "utf-8", raw_bytes, 0, 1, "simulated decode failure",
            )

        monkeypatch.setattr(routes, "_decode_edi_bytes", boom)
        monkeypatch.setattr(
            routes, "_resolve_tenant_id",
            lambda *args, **kwargs: "tenant-1170-test",
        )
        monkeypatch.setattr(routes, "_verify_partner_id", lambda _pid: None)
        monkeypatch.setattr(routes, "is_edi_content", lambda _b: True)

        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_ingestion_principal] = (
            lambda: IngestionPrincipal(
                key_id="test-key", scopes=["*"], auth_mode="test",
            )
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ingest/edi/document",
                data={
                    "traceability_lot_code": "LOT-TEST-1170",
                    "tenant_id": "tenant-1170-test",
                },
                files={
                    "file": (
                        "bad.edi",
                        b"ISA*00*   ~",
                        "application/edi-x12",
                    ),
                },
                headers={"X-Partner-ID": "TEST_PARTNER"},
            )

        assert response.status_code == 422, (
            f"undecodable EDI must be rejected with 422; got "
            f"{response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["detail"]["error"] == "edi_decode_failed", (
            f"response body missing edi_decode_failed marker: {body!r}"
        )
