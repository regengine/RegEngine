"""Regression tests for EDI UTF-8 decode handling (issue #1170).

Before the fix, `_decode_edi_bytes` used ``errors="ignore"`` which
silently discarded invalid or non-ASCII bytes. A shipment from
"Distribuidora Espanola" (using the latin-1-encoded "n with tilde")
would decode to "Distribuidora Espaola" with no log signal -- the
operator had no way to know their partner-name matching was silently
drifting.

The fix (landed on main) switched to ``errors="replace"`` which
substitutes U+FFFD (REPLACEMENT CHARACTER) for unrepresentable bytes.
The function also emits a WARN-level log with the replacement count
and the total byte count so the corruption is visible in observability
pipelines.

This suite locks that contract in. A regression that reverts to
``errors="ignore"`` (silent data loss) would fail
``test_latin1_encoded_bytes_become_replacement_char``; a regression
that drops the warning log would fail ``test_replacement_emits_warn``.

The function lives in `services/ingestion/app/edi_ingestion/routes.py`
(`_decode_edi_bytes`) and is called from the main EDI upload endpoints
at lines 230 and 512.
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
# Happy path: clean UTF-8 passes through with no replacement chars
# ---------------------------------------------------------------------------


class TestValidUtf8_Issue1170:
    def test_ascii_passes_through_unchanged(self):
        raw = b"ISA*00*          *00*          ~"
        decoded = _decode_edi_bytes(raw)
        assert decoded == raw.decode("ascii")
        assert "\ufffd" not in decoded

    def test_utf8_multibyte_preserved(self):
        """Proper UTF-8 multi-byte sequences must survive intact. This
        is the counter-case to the latin-1 bug -- if the source sends
        UTF-8 correctly, nothing should ever be lost or replaced."""
        raw = "Distribuidora Espa\u00f1ola".encode("utf-8")
        decoded = _decode_edi_bytes(raw)
        assert decoded == "Distribuidora Espa\u00f1ola"
        assert "\ufffd" not in decoded

    def test_clean_utf8_emits_no_warning(self, caplog):
        """Valid UTF-8 must not emit the edi_utf8_decode_replacements
        warning. The warning is an observability signal -- false
        positives would drown out real encoding drift."""
        with caplog.at_level(logging.WARNING, logger="edi-ingestion"):
            _decode_edi_bytes("N1*ST*SHIPPER CO~".encode("utf-8"))
        replacement_warnings = [
            r for r in caplog.records
            if "edi_utf8_decode_replacements" in r.getMessage()
        ]
        assert replacement_warnings == [], (
            f"Clean UTF-8 must not emit replacement warning; saw: {replacement_warnings}"
        )


# ---------------------------------------------------------------------------
# Invalid bytes: replacement, not silent drop
# ---------------------------------------------------------------------------


class TestInvalidBytesReplaced_Issue1170:
    def test_latin1_encoded_bytes_become_replacement_char(self):
        """The concrete #1170 scenario: a latin-1 encoded name flows
        into a UTF-8 decode. The invalid byte (0xf1 for 'n-tilde') must
        NOT be dropped silently -- it must become U+FFFD so the length
        is preserved and the operator has a signal."""
        # "Espaola" with byte 0xf1 spliced in where the 'n-tilde' sits.
        latin1_bytes = b"Distribuidora Espa\xf1ola"
        decoded = _decode_edi_bytes(latin1_bytes)

        # The bad byte must have been REPLACED with U+FFFD, not dropped.
        assert "\ufffd" in decoded, (
            "errors='replace' must substitute U+FFFD for invalid bytes; "
            "regression to errors='ignore' would silently drop them"
        )

        # The bytes that ARE valid ASCII must survive verbatim.
        assert decoded.startswith("Distribuidora Espa")
        assert decoded.endswith("ola")

    def test_replacement_preserves_string_structure(self):
        """The silent-drop behavior concatenated adjacent legal chars.
        Replacement must insert a placeholder so the reader sees where
        the corruption happened."""
        # A mid-string bad byte.
        raw = b"PO-A" + b"\xff" + b"B-7"
        decoded = _decode_edi_bytes(raw)
        # Good: 'A' and 'B' are still separated by a visible marker.
        assert "A" in decoded and "B" in decoded
        assert "\ufffd" in decoded
        # Specifically: the replacement sits between A and B.
        assert decoded.index("A") < decoded.index("\ufffd") < decoded.index("B")

    def test_trailing_orphan_bytes_replaced_not_truncated(self):
        """An incomplete multi-byte sequence mid-buffer must become a
        replacement char, not silently truncate legal bytes around it.

        Construction: a lone UTF-8 lead byte (0xc3 expects a continuation
        byte of 0x80-0xbf but we give it an ASCII space instead), then
        legal ASCII. Under errors='ignore' the 0xc3 would just vanish;
        under errors='replace' the 0xc3 becomes U+FFFD while every
        legal byte survives.
        """
        raw = b"PO-\xc3 END"  # 0xc3 is a lead byte with no valid follower
        decoded = _decode_edi_bytes(raw)
        assert "\ufffd" in decoded, (
            f"lone lead byte must be replaced, got: {decoded!r}"
        )
        assert decoded.endswith(" END"), (
            "trailing legal bytes must not be chopped off along with the "
            "invalid bytes -- that was exactly the #1170 bug"
        )
        assert decoded.startswith("PO-"), "leading legal bytes must survive"


# ---------------------------------------------------------------------------
# Observability: warning log with byte count
# ---------------------------------------------------------------------------


class TestReplacementWarning_Issue1170:
    def test_replacement_emits_warn(self, caplog):
        """When any replacement occurs, a WARN-level log must be
        emitted on the ``edi-ingestion`` logger so the operator can
        see the corruption in their log aggregator."""
        latin1 = b"Distribuidora Espa\xf1ola"
        with caplog.at_level(logging.WARNING, logger="edi-ingestion"):
            _decode_edi_bytes(latin1)
        warning_records = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "edi_utf8_decode_replacements" in r.getMessage()
        ]
        assert len(warning_records) == 1, (
            f"Expected exactly one WARN 'edi_utf8_decode_replacements' "
            f"log, got {len(warning_records)}"
        )

    def test_warning_includes_replacement_count_and_byte_count(self, caplog):
        """The warning must include both the replacement count (how
        many bytes were lossy) and the total byte count (denominator
        for alerting thresholds). Without both, an operator can't
        judge severity."""
        raw = b"A\xff\xff\xff_VALID"
        with caplog.at_level(logging.WARNING, logger="edi-ingestion"):
            _decode_edi_bytes(raw)
        message = next(
            r.getMessage() for r in caplog.records
            if "edi_utf8_decode_replacements" in r.getMessage()
        )
        # Three replacements, ten total bytes.
        assert "count=3" in message, f"message missing count=3: {message!r}"
        assert f"bytes={len(raw)}" in message, (
            f"message missing bytes={len(raw)}: {message!r}"
        )

    def test_no_replacements_no_warning(self, caplog):
        """Negative control for the warning: no replacements happened,
        no warning must fire. This is what keeps the signal clean."""
        clean_raw = b"ISA*00*          *00*          ~"
        with caplog.at_level(logging.WARNING, logger="edi-ingestion"):
            _decode_edi_bytes(clean_raw)
        replacement_warnings = [
            r for r in caplog.records
            if "edi_utf8_decode_replacements" in r.getMessage()
        ]
        assert replacement_warnings == []


# ---------------------------------------------------------------------------
# Contract invariants that catch the exact #1170 regression mode
# ---------------------------------------------------------------------------


class TestErrorsReplaceNotIgnore_Issue1170:
    """If a future refactor silently swaps ``errors="replace"`` back to
    ``errors="ignore"``, the replacement character disappears. Every
    test in this class FAILS under that regression, making the flip
    impossible to miss."""

    def test_latin1_ntilde_is_not_dropped(self):
        """The exact motivating scenario in the issue."""
        raw = b"Distribuidora Espa\xf1ola"
        decoded = _decode_edi_bytes(raw)
        # Under errors='ignore' this would produce "Distribuidora Espaola"
        # (len 18). Under errors='replace' it produces the same-visible-
        # length string but with U+FFFD in the gap.
        assert "Espa\ufffdola" in decoded, (
            "The n-tilde byte must be replaced with U+FFFD (one char) "
            "so 'Distribuidora Espaola' cannot silently substitute for "
            "'Distribuidora Espa\u00f1ola' in partner-name matching"
        )

    def test_byte_loss_is_visible_in_length(self):
        """len(decoded) must equal the original byte count whenever
        the input is pure single-byte encoding (ASCII + one bad byte).
        Under errors='ignore' the bad byte is dropped and length
        shortens -- the presence of the character preserves length."""
        raw = b"A" + b"\xff" + b"B"
        decoded = _decode_edi_bytes(raw)
        assert len(decoded) == len(raw), (
            "errors='replace' preserves character count (1 bad byte -> "
            "1 U+FFFD); errors='ignore' would drop to len=2"
        )
