"""Tests for services.graph.app.exporters.safe_text helpers.

Covers RE-SEC-001 (XML), RE-SEC-002 (CSV-as-Excel), RE-SEC-003
(Content-Disposition filename), RE-SEC-004 (ZPL).
"""

from __future__ import annotations

import csv
import defusedxml.ElementTree as ET
import io
import sys
from pathlib import Path

import defusedxml.ElementTree as ET
import pytest

# Make the repo root importable so `services.graph...` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.exporters.safe_text import (  # noqa: E402
    csv_safe,
    header_filename,
    rfc5987_filename,
    xml_escape,
    zpl_safe,
)


# ---------------------------------------------------------------------------
# xml_escape
# ---------------------------------------------------------------------------

class TestXmlEscape:
    def test_clean_input_passes_through(self):
        assert xml_escape("Romaine Lettuce") == "Romaine Lettuce"

    def test_none_returns_empty_string(self):
        assert xml_escape(None) == ""

    @pytest.mark.parametrize(
        "raw",
        ["a < b", "Tom & Jerry", '"quoted"', "it's", "<script>alert(1)</script>"],
    )
    def test_round_trip_via_elementtree(self, raw):
        # The whole point: after escape, parsing as XML must round-trip.
        xml = f"<x>{xml_escape(raw)}</x>"
        parsed = ET.fromstring(xml)
        assert parsed.text == raw

    def test_attack_neutralized(self):
        attack = "</tlc><inject>x</inject><tlc>"
        out = xml_escape(attack)
        # No raw '<' or '>' should survive.
        assert "<" not in out
        assert ">" not in out


# ---------------------------------------------------------------------------
# csv_safe
# ---------------------------------------------------------------------------

class TestCsvSafe:
    def test_clean_input_passes_through(self):
        assert csv_safe("LOT-12345") == "LOT-12345"

    def test_none_returns_empty_string(self):
        assert csv_safe(None) == ""

    @pytest.mark.parametrize(
        "attack",
        [
            "=HYPERLINK(\"http://evil/\",\"click\")",
            "+1+1",
            "-2+3",
            "@SUM(A1:A2)",
            "\t=cmd|'/c calc'!A1",
            "\rmalice",
        ],
    )
    def test_formula_prefix_neutralized(self, attack):
        out = csv_safe(attack)
        assert out.startswith("'"), f"missing leading quote for {attack!r}"

    def test_csv_writer_round_trip(self):
        # The helper does not own quoting; csv.writer does. Ensure they
        # compose correctly.
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([csv_safe("=BAD()"), csv_safe("ok"), csv_safe("a,b")])
        text = buf.getvalue()
        # csv.writer should have quoted the embedded comma.
        assert '"a,b"' in text
        assert "'=BAD()" in text


# ---------------------------------------------------------------------------
# header_filename / rfc5987_filename
# ---------------------------------------------------------------------------

class TestHeaderFilename:
    def test_clean_filename_passes_through(self):
        assert header_filename("report.csv") == "report.csv"

    def test_strips_crlf_attack(self):
        out = header_filename("foo\r\nX-Inject: bar.csv")
        assert "\r" not in out
        assert "\n" not in out
        # Defense in depth: the colon and space were also removed (non-safe).
        assert "X-Inject" in out  # alphanumerics survive
        assert ": " not in out

    def test_truncates(self):
        out = header_filename("a" * 500, max_len=50)
        assert len(out) <= 50

    def test_empty_yields_default(self):
        assert header_filename("") == "download"

    def test_quote_in_name_stripped(self):
        out = header_filename('a"b.csv')
        assert '"' not in out


class TestRfc5987:
    def test_ascii_clean(self):
        assert rfc5987_filename("file.csv") == "file.csv"

    def test_non_ascii_percent_encoded(self):
        # é = 0xC3 0xA9 in UTF-8 → %C3%A9
        out = rfc5987_filename("café.csv")
        assert out == "caf%C3%A9.csv"


# ---------------------------------------------------------------------------
# zpl_safe
# ---------------------------------------------------------------------------

class TestZplSafe:
    def test_clean_input_passes_through(self):
        assert zpl_safe("Romaine 8oz") == "Romaine 8oz"

    def test_none_returns_empty_string(self):
        assert zpl_safe(None) == ""

    def test_caret_attack_stripped(self):
        out = zpl_safe("^XZ^XA^FO0,0^GFA")
        assert "^" not in out

    def test_tilde_attack_stripped(self):
        out = zpl_safe("~JA~CC")
        assert "~" not in out

    def test_control_bytes_stripped(self):
        out = zpl_safe("ok\x00\x01\x1ftext")
        assert all(ord(c) >= 0x20 for c in out)

    def test_truncates_after_stripping(self):
        # Carets are stripped first, then truncated. The "XZ" content
        # survives (no command prefix), and truncation lands at 30 chars.
        attack = "^XZ" + ("A" * 50)
        out = zpl_safe(attack, max_len=30)
        assert "^" not in out
        assert len(out) == 30
        assert out == "XZ" + ("A" * 28)

    def test_truncate_cannot_be_evaded_by_caret_padding(self):
        # If carets counted toward the budget (the old [:30] approach),
        # an attacker could pad with ^^^^ then place a real ^XA after the
        # cutoff. After zpl_safe(), no ^ ever survives — even with 100 of
        # them in the input.
        attack = ("^" * 100) + "PAYLOAD"
        out = zpl_safe(attack, max_len=30)
        assert "^" not in out
        assert out == "PAYLOAD"
