"""Tests for the EPIC-L (#1655) shared FDA export primitives.

Covers the five public surfaces documented in the EPIC:

* ``safe_cell`` — formula-prefix escaping
* ``safe_filename`` / ``safe_filename_token`` — ASCII-only filenames
* ``validate_export_window`` — both dates required, 90-day cap,
  UTC normalization
* ``redact_pii_row`` — placeholder + hash strategies, scope gating
* ``paginate`` — async generator, hard-cap refusal rather than silent
  truncation
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import pytest

from shared.fda_export import (
    ExportWindowError,
    MAX_EXPORT_WINDOW_DAYS,
    PII_PERMISSION,
    PII_REDACTION_PLACEHOLDER,
    hash_pii_value,
    paginate,
    redact_pii_row,
    safe_cell,
    safe_filename,
    safe_filename_token,
    safe_row,
    safe_sequence,
    validate_export_window,
)
from shared.fda_export.pii import redact_pii_extras


# ---------------------------------------------------------------------------
# safe_cell
# ---------------------------------------------------------------------------


class TestSafeCell:
    def test_none_returns_empty(self) -> None:
        assert safe_cell(None) == ""

    def test_safe_values_pass_through(self) -> None:
        assert safe_cell("Romaine Hearts") == "Romaine Hearts"
        assert safe_cell(42) == "42"
        assert safe_cell(3.14) == "3.14"

    @pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
    def test_dangerous_prefixes_get_quoted(self, prefix: str) -> None:
        value = prefix + "WEBSERVICE(\"http://evil/\")"
        result = safe_cell(value)
        assert result.startswith("'")
        # Original value must still be recoverable after stripping the
        # literal-text marker.
        assert result[1:] == value

    def test_empty_string_pass_through(self) -> None:
        assert safe_cell("") == ""

    def test_safe_row_escapes_every_value(self) -> None:
        row = {"col1": "=HACK()", "col2": "ok", "col3": None}
        out = safe_row(row)
        assert out == {"col1": "'=HACK()", "col2": "ok", "col3": ""}

    def test_safe_sequence_escapes_every_element(self) -> None:
        out = safe_sequence(["=HACK()", "ok", None])
        assert out == ["'=HACK()", "ok", ""]


# ---------------------------------------------------------------------------
# safe_filename / safe_filename_token
# ---------------------------------------------------------------------------


class TestSafeFilenameToken:
    def test_empty_falls_back_to_all(self) -> None:
        assert safe_filename_token("") == "all"
        assert safe_filename_token(None) == "all"

    def test_ascii_alphanumerics_pass(self) -> None:
        assert safe_filename_token("TLC-12345_abc.v2") == "TLC-12345_abc.v2"

    def test_non_whitelisted_chars_become_underscore(self) -> None:
        # CRLF / quote / path-separator injection vectors all collapse.
        out = safe_filename_token('foo"\r\n/\\bar')
        assert set(out) <= set("foo_bar")

    def test_traversal_collapsed(self) -> None:
        out = safe_filename_token("../../etc/passwd")
        assert ".." not in out

    def test_length_capped(self) -> None:
        out = safe_filename_token("a" * 500, max_len=32)
        assert len(out) == 32


class TestSafeFilename:
    def test_basic_shape(self) -> None:
        out = safe_filename("fda_export", scope="lot-1", start=date(2026, 1, 1), end=date(2026, 1, 31))
        assert out == "fda_export_lot-1_2026-01-01_2026-01-31.csv"

    def test_crlf_in_scope_neutralized(self) -> None:
        out = safe_filename("fda_export", scope="bad\r\nHeader: x")
        # No CRLF, no colon survives past the token filter.
        assert "\r" not in out and "\n" not in out and ":" not in out

    def test_datetime_converts_to_date(self) -> None:
        out = safe_filename(
            "pkg",
            start=datetime(2026, 3, 1, 12, 30, tzinfo=timezone.utc),
            end=datetime(2026, 3, 5, 0, 0, tzinfo=timezone.utc),
        )
        assert "2026-03-01" in out and "2026-03-05" in out

    def test_extension_sanitized(self) -> None:
        out = safe_filename("pkg", extension="zip")
        assert out.endswith(".zip")
        # Path-separator / dot-injection in the extension is defused.
        out = safe_filename("pkg", extension="../sh")
        assert "/" not in out and ".." not in out


# ---------------------------------------------------------------------------
# validate_export_window
# ---------------------------------------------------------------------------


class TestValidateExportWindow:
    def test_happy_path(self) -> None:
        w = validate_export_window("2026-01-01", "2026-01-31")
        assert w.start == date(2026, 1, 1)
        assert w.end == date(2026, 1, 31)
        assert w.span_days == 30

    def test_both_dates_required(self) -> None:
        with pytest.raises(ExportWindowError, match="start_date is required"):
            validate_export_window(None, "2026-01-31")
        with pytest.raises(ExportWindowError, match="end_date is required"):
            validate_export_window("2026-01-01", None)
        with pytest.raises(ExportWindowError):
            validate_export_window("", "2026-01-31")

    def test_end_before_start_rejected(self) -> None:
        with pytest.raises(ExportWindowError, match="on or after"):
            validate_export_window("2026-02-01", "2026-01-15")

    def test_span_cap(self) -> None:
        with pytest.raises(ExportWindowError, match="exceeds"):
            validate_export_window("2026-01-01", "2026-12-31")
        # Exactly at the cap is fine.
        w = validate_export_window(
            date(2026, 1, 1),
            date(2026, 1, 1) + __import__("datetime").timedelta(days=MAX_EXPORT_WINDOW_DAYS),
        )
        assert w.span_days == MAX_EXPORT_WINDOW_DAYS

    def test_malformed_iso_rejected(self) -> None:
        with pytest.raises(ExportWindowError, match="ISO-8601"):
            validate_export_window("not-a-date", "2026-01-31")

    def test_datetime_with_z_normalized(self) -> None:
        w = validate_export_window("2026-01-01T00:00:00Z", "2026-01-05T00:00:00Z")
        assert w.start == date(2026, 1, 1)
        assert w.end == date(2026, 1, 5)

    def test_date_instance_accepted(self) -> None:
        w = validate_export_window(date(2026, 1, 1), date(2026, 1, 15))
        assert w.span_days == 14


# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------


class TestRedactPiiRow:
    def test_default_scopes_redact_pii_columns(self) -> None:
        row = {
            "Location Name": "Sunrise Farms",
            "Ship From Name": "Valley Co",
            "TLC Source GLN": "0614141000005",  # not PII
            "Product Description": "Romaine",  # not PII
        }
        out = redact_pii_row(row, caller_scopes=["fda.export"])
        assert out["Location Name"] == PII_REDACTION_PLACEHOLDER
        assert out["Ship From Name"] == PII_REDACTION_PLACEHOLDER
        assert out["TLC Source GLN"] == "0614141000005"
        assert out["Product Description"] == "Romaine"

    def test_full_pii_permission_returns_row_unchanged(self) -> None:
        row = {"Location Name": "Sunrise Farms", "Ship From Name": "Valley"}
        out = redact_pii_row(row, caller_scopes=[PII_PERMISSION, "fda.export"])
        assert out == row

    def test_alias_permission_also_works(self) -> None:
        row = {"Location Name": "X"}
        out = redact_pii_row(row, caller_scopes=["fda.export.pii"])
        assert out["Location Name"] == "X"

    def test_wildcard_scope_grants_full_pii(self) -> None:
        row = {"Location Name": "X"}
        out = redact_pii_row(row, caller_scopes=["*"])
        assert out["Location Name"] == "X"

    def test_empty_values_stay_empty(self) -> None:
        row = {"Location Name": ""}
        out = redact_pii_row(row, caller_scopes=[])
        assert out["Location Name"] == ""

    def test_none_scopes_redacts(self) -> None:
        row = {"Location Name": "Farm X"}
        out = redact_pii_row(row, caller_scopes=None)
        assert out["Location Name"] == PII_REDACTION_PLACEHOLDER

    def test_hash_strategy_produces_correlatable_hashes(self) -> None:
        row1 = {"Location Name": "Sunrise Farms"}
        row2 = {"Location Name": "Sunrise Farms"}
        row3 = {"Location Name": "Valley Co"}
        out1 = redact_pii_row(row1, caller_scopes=[], strategy="hash")
        out2 = redact_pii_row(row2, caller_scopes=[], strategy="hash")
        out3 = redact_pii_row(row3, caller_scopes=[], strategy="hash")
        assert out1["Location Name"] == out2["Location Name"]
        assert out1["Location Name"] != out3["Location Name"]
        assert out1["Location Name"].startswith("pii_")

    def test_override_pii_columns(self) -> None:
        row = {"custom_col": "secret", "Location Name": "Farm"}
        out = redact_pii_row(row, caller_scopes=[], pii_columns={"custom_col"})
        assert out["custom_col"] == PII_REDACTION_PLACEHOLDER
        # Location Name no longer in the override set — stays visible.
        assert out["Location Name"] == "Farm"


class TestHashPiiValue:
    def test_empty_returns_empty(self) -> None:
        assert hash_pii_value("") == ""
        assert hash_pii_value(None) == ""  # type: ignore[arg-type]

    def test_stable(self) -> None:
        assert hash_pii_value("Sunrise Farms") == hash_pii_value("Sunrise Farms")

    def test_different_values_differ(self) -> None:
        assert hash_pii_value("A") != hash_pii_value("B")


class TestRedactPiiExtras:
    def test_pii_keys_redacted(self) -> None:
        extras = {
            "facility_address": "100 Main St",
            "driver_name": "Alice",
            "carrier_speed_mph": "45",  # not PII
        }
        out = redact_pii_extras(extras, caller_scopes=[])
        assert out["facility_address"] == PII_REDACTION_PLACEHOLDER
        assert out["driver_name"] == PII_REDACTION_PLACEHOLDER
        assert out["carrier_speed_mph"] == "45"

    def test_full_pii_permission_leaves_extras_alone(self) -> None:
        extras = {"facility_address": "100 Main St"}
        out = redact_pii_extras(extras, caller_scopes=[PII_PERMISSION])
        assert out == extras


# ---------------------------------------------------------------------------
# paginate
# ---------------------------------------------------------------------------


class TestPaginate:
    def _collect(self, agen):
        async def runner():
            return [batch async for batch in agen]
        return asyncio.run(runner())

    def test_single_page(self) -> None:
        async def fetcher(*, cursor, limit):
            return ([1, 2, 3], None)
        batches = self._collect(paginate(fetcher, batch_size=10))
        assert batches == [[1, 2, 3]]

    def test_multiple_pages(self) -> None:
        calls: list[tuple] = []
        pages = [[1, 2], [3, 4], [5]]
        cursors = ["c1", "c2", None]

        async def fetcher(*, cursor, limit):
            calls.append((cursor, limit))
            idx = len(calls) - 1
            return (pages[idx], cursors[idx])

        batches = self._collect(paginate(fetcher, batch_size=2))
        assert batches == [[1, 2], [3, 4], [5]]
        assert calls[0][0] is None
        assert calls[1][0] == "c1"
        assert calls[2][0] == "c2"

    def test_empty_first_page_terminates(self) -> None:
        async def fetcher(*, cursor, limit):
            return ([], None)
        batches = self._collect(paginate(fetcher, batch_size=10))
        assert batches == []

    def test_hard_cap_refuses_rather_than_truncating(self) -> None:
        async def fetcher(*, cursor, limit):
            return ([1, 2, 3, 4, 5], "more")

        async def runner():
            out = []
            async for batch in paginate(fetcher, batch_size=5, max_events=3):
                out.append(batch)
            return out

        with pytest.raises(ValueError, match="hard cap"):
            asyncio.run(runner())

    def test_invalid_batch_size(self) -> None:
        async def fetcher(*, cursor, limit):
            return ([], None)

        async def runner():
            async for _ in paginate(fetcher, batch_size=0):
                pass

        with pytest.raises(ValueError, match="positive"):
            asyncio.run(runner())
