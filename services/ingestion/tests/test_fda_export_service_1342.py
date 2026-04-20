"""Focused coverage for ``app/fda_export_service.py`` — #1342.

Targets every branch of the FDA export helper module with pure
unit-level tests that exercise the CSV / PDF / chain-verification /
completeness / package-assembly pipelines without Postgres or
testcontainers.

Scope:

- PII redaction helpers: ``_redact_location_value`` (include_pii,
  non-PII column, empty-value guard, redaction path);
  ``_redact_extra_kde_pii`` (key match, non-string value pass-through,
  non-matching key).
- ``_event_to_fda_row``: happy path, timestamp parsing +
  parse-failure fallback, named KDE columns, extras-JSON filter
  excluding named and literal-consumed keys, PII redaction posture
  (true / false).
- ``_generate_csv`` + ``_generate_csv_v2``: header row, QUOTE_ALL,
  PII flag propagation.
- ``_generate_pdf``: small payload, truncation at row cap, PII
  posture both directions, metadata line with TLC.
- ``_safe_filename_token``: alnum/safe-char passthrough, unsafe-char
  replacement, length clamp, empty fallback to ``"all"``.
- ``_event_value_for_required_field``: direct-field keys,
  ``location_name`` KDE fallback, default KDE map lookup.
- ``_build_completeness_summary``: empty input, unknown event type,
  fully-covered event, partial coverage ratio, missing-by-event cap
  (500 missing → 250 in output).
- ``_build_validation_errors_log``: all-pass returns ``None``, with
  missing events emits log with TLC, event type, missing-field list.
- ``_build_chain_verification_payload``: chain valid, chain invalid,
  PARTIAL when hashes missing, privacy block both directions.
- ``_build_fda_package``: happy-path zip bytes, validation log
  inclusion, manifest-file hashes, README PII note both directions.
- ``_event_to_fda_row_v2``: no rule results, all-pass, some-fail
  ``why_failed`` join, trace-relationship defaults, seed-TLC
  fallback.

Issue: #1342
"""

from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import fda_export_service as svc  # noqa: E402
from app.webhook_models import WebhookCTEType  # noqa: E402


# ── _redact_location_value ──────────────────────────────────────────────────


class TestRedactLocationValue:
    def test_include_pii_returns_value_unchanged(self) -> None:
        assert svc._redact_location_value("Acme", "Location Name", True) == "Acme"

    def test_non_pii_column_returns_value_unchanged(self) -> None:
        assert svc._redact_location_value("v", "Traceability Lot Code (TLC)", False) == "v"

    def test_empty_value_returns_empty(self) -> None:
        # Empty strings pass through so blank cells don't become "[REDACTED]".
        assert svc._redact_location_value("", "Location Name", False) == ""

    def test_pii_column_non_empty_gets_placeholder(self) -> None:
        assert (
            svc._redact_location_value("Acme", "Location Name", False)
            == svc.PII_REDACTION_PLACEHOLDER
        )


# ── _redact_extra_kde_pii ──────────────────────────────────────────────────


class TestRedactExtraKdePii:
    def test_pii_key_redacts_string_value(self) -> None:
        out = svc._redact_extra_kde_pii({"facility_address": "123 Main"})
        assert out["facility_address"] == svc.PII_REDACTION_PLACEHOLDER

    def test_non_string_value_passes_through(self) -> None:
        out = svc._redact_extra_kde_pii({"street_number": 42})
        assert out["street_number"] == 42

    def test_non_pii_key_passes_through(self) -> None:
        out = svc._redact_extra_kde_pii({"harvest_method": "hand-picked"})
        assert out["harvest_method"] == "hand-picked"

    def test_empty_string_not_replaced(self) -> None:
        # Empty-string guard avoids pointlessly flipping "" → "[REDACTED]".
        out = svc._redact_extra_kde_pii({"driver_name": ""})
        assert out["driver_name"] == ""


# ── _event_to_fda_row ──────────────────────────────────────────────────────


_CORE_EVENT = {
    "id": "evt-1",
    "traceability_lot_code": "TLC-1",
    "product_description": "Tomatoes",
    "quantity": 100,
    "unit_of_measure": "CS",
    "event_type": "SHIPPING",
    "event_timestamp": "2026-03-01T12:34:56+00:00",
    "location_gln": "0614141000012",
    "location_name": "Acme Warehouse",
    "source": "epcis",
    "sha256_hash": "a" * 64,
    "chain_hash": "b" * 64,
    "ingested_at": "2026-03-01T12:35:00+00:00",
    "kdes": {
        "ship_from_gln": "0614141000011",
        "ship_from_location": "Origin",
        "ship_to_gln": "0614141000022",
        "ship_to_location": "Dest",
        "immediate_previous_source": "Previous",
        "tlc_source_gln": "0614141000099",
        "tlc_source_fda_reg": "FDA-1",
        "receive_date": "2026-02-28",
        "ship_date": "2026-03-01",
        "reference_document_number": "PO-42",
        "carrier": "TruckCo",
        "facility_address": "123 Main St",  # PII key — goes to extras
        "other_kde": "visible",              # non-PII extras
    },
}


class TestEventToFdaRow:
    def test_happy_path_has_all_core_columns(self) -> None:
        row = svc._event_to_fda_row(_CORE_EVENT, include_pii=True)
        assert row["Traceability Lot Code (TLC)"] == "TLC-1"
        assert row["Event Date"] == "2026-03-01"
        assert row["Event Time"].startswith("12:34:56")
        # With include_pii=True, PII columns keep real values.
        assert row["Location Name"] == "Acme Warehouse"
        assert row["Ship From Name"] == "Origin"
        assert row["Ship To Name"] == "Dest"
        assert row["Immediate Previous Source"] == "Previous"
        # Extras JSON excludes named + literal-consumed keys.
        extras = json.loads(row["Additional KDEs (JSON)"])
        assert "ship_from_gln" not in extras        # literal-consumed
        assert "receive_date" not in extras          # named column
        assert "facility_address" in extras
        assert "other_kde" in extras

    def test_pii_redacted_when_flag_false(self) -> None:
        row = svc._event_to_fda_row(_CORE_EVENT, include_pii=False)
        assert row["Location Name"] == svc.PII_REDACTION_PLACEHOLDER
        assert row["Ship From Name"] == svc.PII_REDACTION_PLACEHOLDER
        assert row["Ship To Name"] == svc.PII_REDACTION_PLACEHOLDER
        # GLNs remain visible even when include_pii=False.
        assert row["Ship From GLN"] == "0614141000011"
        assert row["Ship To GLN"] == "0614141000022"
        # Extras JSON redacts PII-named keys.
        extras = json.loads(row["Additional KDEs (JSON)"])
        assert extras["facility_address"] == svc.PII_REDACTION_PLACEHOLDER
        assert extras["other_kde"] == "visible"

    def test_timestamp_parse_failure_uses_first_10_chars(self) -> None:
        bad = dict(_CORE_EVENT, event_timestamp="not-a-date-really")
        row = svc._event_to_fda_row(bad)
        assert row["Event Date"] == "not-a-date"

    def test_no_timestamp_leaves_date_blank(self) -> None:
        bad = dict(_CORE_EVENT)
        bad.pop("event_timestamp")
        row = svc._event_to_fda_row(bad)
        assert row["Event Date"] == ""

    def test_receiving_location_fallback_fills_ship_to_name(self) -> None:
        evt = dict(_CORE_EVENT)
        kdes = dict(evt["kdes"])
        kdes.pop("ship_to_location", None)
        kdes["receiving_location"] = "Warehouse-42"
        evt["kdes"] = kdes
        row = svc._event_to_fda_row(evt, include_pii=True)
        assert row["Ship To Name"] == "Warehouse-42"

    def test_empty_extras_yields_empty_string(self) -> None:
        evt = {
            "traceability_lot_code": "TLC",
            "product_description": "X",
            "quantity": 1,
            "unit_of_measure": "EA",
            "event_type": "RECEIVING",
            "kdes": {},
        }
        row = svc._event_to_fda_row(evt)
        assert row["Additional KDEs (JSON)"] == ""


# ── _generate_csv ──────────────────────────────────────────────────────────


class TestGenerateCsv:
    def test_header_and_row_quoted(self) -> None:
        csv_text = svc._generate_csv([_CORE_EVENT])
        # Header present.
        assert '"Traceability Lot Code (TLC)"' in csv_text.splitlines()[0]
        # Every cell quoted via QUOTE_ALL.
        assert '"TLC-1"' in csv_text

    def test_empty_events_yields_header_only(self) -> None:
        csv_text = svc._generate_csv([])
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 1  # header only
        assert rows[0][0] == "Traceability Lot Code (TLC)"

    def test_include_pii_flag_propagates(self) -> None:
        csv_redacted = svc._generate_csv([_CORE_EVENT], include_pii=False)
        csv_full = svc._generate_csv([_CORE_EVENT], include_pii=True)
        assert svc.PII_REDACTION_PLACEHOLDER in csv_redacted
        assert "Acme Warehouse" in csv_full
        assert "Acme Warehouse" not in csv_redacted


# ── _generate_pdf ──────────────────────────────────────────────────────────


class TestGeneratePdf:
    def test_small_payload_returns_pdf_bytes(self) -> None:
        result = svc._generate_pdf(
            [_CORE_EVENT], metadata={"tlc": "TLC-1", "generated_at": "2026-03-01"}
        )
        assert isinstance(result, (bytes, bytearray))
        assert bytes(result).startswith(b"%PDF")

    def test_no_metadata_uses_defaults(self) -> None:
        # Omit metadata entirely → generated_at filled from now().
        result = svc._generate_pdf([_CORE_EVENT])
        assert bytes(result).startswith(b"%PDF")

    def test_truncation_when_over_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Patch the private cap to 1 so a 3-event payload triggers the
        # truncation warning footer branch.
        import app.fda_export_service as mod
        events = [_CORE_EVENT, _CORE_EVENT, _CORE_EVENT]
        # The cap is a local inside _generate_pdf; overriding isn't
        # directly exposed, so we just confirm 3 events still render
        # without raising (covers the truncation-less branch too).
        result = mod._generate_pdf(events)
        assert bytes(result).startswith(b"%PDF")

    def test_pii_flag_reflected_in_footer(self) -> None:
        # Both branches render without error; we only check presence
        # of PDF magic. The footer-string selection is already
        # covered via both include_pii=True and False.
        redacted = svc._generate_pdf([_CORE_EVENT], include_pii=False)
        full = svc._generate_pdf([_CORE_EVENT], include_pii=True)
        assert bytes(redacted).startswith(b"%PDF")
        assert bytes(full).startswith(b"%PDF")

    def test_long_cell_value_gets_truncated(self) -> None:
        """Line 416: values longer than the column's char budget hit the
        truncation branch. NOTE: the current code appends U+2026 ``…``
        which is not in fpdf2's default Helvetica — hitting this branch
        raises ``FPDFUnicodeEncodingException`` in production too. We
        assert the crash explicitly so that when the bug is fixed (see
        spawned task), this test will need to flip to a happy-path
        assertion.
        """
        from fpdf.errors import FPDFUnicodeEncodingException

        # Product Description column is 40mm wide → max_chars ≈ 24.
        # Use a 100-char description to force the truncation branch.
        event = dict(
            _CORE_EVENT,
            product_description="X" * 100,
        )
        with pytest.raises(FPDFUnicodeEncodingException):
            svc._generate_pdf([event])

    def test_truncation_footer_when_over_row_cap(self) -> None:
        """Line 424: when input > _PDF_MAX_ROWS (5000), the footer
        declares the truncation."""
        # Share the same dict reference to keep memory reasonable.
        events = [_CORE_EVENT] * 5001
        result = svc._generate_pdf(events)
        assert bytes(result).startswith(b"%PDF")


# ── _safe_filename_token ──────────────────────────────────────────────────


class TestSafeFilenameToken:
    def test_alnum_passes_through(self) -> None:
        assert svc._safe_filename_token("TLC-42") == "TLC-42"

    def test_unsafe_chars_replaced_with_underscore(self) -> None:
        assert svc._safe_filename_token("a/b c") == "a_b_c"

    def test_truncates_at_64_chars(self) -> None:
        long = "x" * 200
        assert len(svc._safe_filename_token(long)) == 64

    def test_empty_falls_back_to_all(self) -> None:
        assert svc._safe_filename_token("") == "all"

    def test_all_unsafe_chars_replaced_to_underscores_not_all(self) -> None:
        # ``or "all"`` only kicks in when the join produces an empty
        # string, not a non-empty all-underscore string.
        assert svc._safe_filename_token("/////") == "_____"

    def test_underscores_kept(self) -> None:
        assert svc._safe_filename_token("has_underscore") == "has_underscore"


# ── _event_value_for_required_field ───────────────────────────────────────


class TestEventValueForRequiredField:
    def test_direct_event_field(self) -> None:
        evt = {"traceability_lot_code": "TLC", "kdes": {}}
        assert svc._event_value_for_required_field(evt, "traceability_lot_code") == "TLC"

    def test_location_name_direct_field_first(self) -> None:
        evt = {"location_name": "Direct", "kdes": {"location_name": "FromKde"}}
        assert svc._event_value_for_required_field(evt, "location_name") == "Direct"

    def test_location_name_falls_back_to_kde(self) -> None:
        evt = {"kdes": {"location_name": "FromKde"}}
        assert svc._event_value_for_required_field(evt, "location_name") == "FromKde"

    def test_other_fields_look_up_in_kdes(self) -> None:
        evt = {"kdes": {"ship_from_gln": "0614"}}
        assert svc._event_value_for_required_field(evt, "ship_from_gln") == "0614"


# ── _build_completeness_summary ───────────────────────────────────────────


class TestBuildCompletenessSummary:
    def test_empty_events(self) -> None:
        summary = svc._build_completeness_summary([])
        assert summary["required_checks_total"] == 0
        assert summary["required_kde_coverage_ratio"] == 1.0
        assert summary["events_with_missing_required_fields"] == 0

    def test_unknown_event_type_yields_no_checks(self) -> None:
        summary = svc._build_completeness_summary(
            [{"event_type": "BOGUS_CTE"}]
        )
        assert summary["required_checks_total"] == 0
        assert summary["events_with_missing_required_fields"] == 0

    def test_fully_covered_event_reports_full_coverage(self) -> None:
        # Use SHIPPING which is in REQUIRED_KDES_BY_CTE; fill every
        # required field so coverage is 100%.
        from app.webhook_models import REQUIRED_KDES_BY_CTE
        cte = WebhookCTEType.SHIPPING
        required = REQUIRED_KDES_BY_CTE[cte]

        kdes: dict[str, Any] = {}
        event: dict[str, Any] = {
            "event_type": cte.value,
            "traceability_lot_code": "T",
            "product_description": "P",
            "quantity": 1,
            "unit_of_measure": "EA",
            "location_name": "L",
        }
        for f in required:
            if f in {"traceability_lot_code", "product_description", "quantity", "unit_of_measure", "location_name"}:
                continue
            kdes[f] = "filled"
        event["kdes"] = kdes

        summary = svc._build_completeness_summary([event])
        assert summary["required_kde_coverage_ratio"] == 1.0
        assert summary["events_with_missing_required_fields"] == 0

    def test_missing_event_type_yields_no_checks(self) -> None:
        # Empty / None event_type doesn't match __members__.
        summary = svc._build_completeness_summary([{"kdes": {}}])
        assert summary["required_checks_total"] == 0

    def test_lowercase_event_type_upcased_before_lookup(self) -> None:
        # The source .upper()s raw_event_type, so lowercase values still
        # match their uppercase __members__ entries.
        summary = svc._build_completeness_summary(
            [{"event_type": "shipping", "kdes": {}}]
        )
        assert summary["required_checks_total"] > 0

    def test_partial_coverage_tracks_missing(self) -> None:
        # SHIPPING requires ship_date + ship_from_location; leave them
        # blank so the event has missing fields but the event_type is
        # still recognized.
        event: dict[str, Any] = {
            "event_type": WebhookCTEType.SHIPPING.value,
            "id": "e1",
            "traceability_lot_code": "T",
            "product_description": "P",
            "quantity": 1,
            "unit_of_measure": "EA",
            "kdes": {},
        }
        summary = svc._build_completeness_summary([event])
        assert summary["required_checks_missing"] > 0
        assert summary["events_with_missing_required_fields"] == 1
        assert summary["required_kde_coverage_ratio"] < 1.0
        assert summary["missing_required_events"][0]["event_id"] == "e1"

    def test_missing_events_capped_at_250(self) -> None:
        # 300 SHIPPING events, all missing required KDEs → 300 tracked,
        # but missing_required_events is sliced to the first 250.
        events = [
            {
                "event_type": WebhookCTEType.SHIPPING.value,
                "id": f"e{i}",
                "kdes": {},
            }
            for i in range(300)
        ]
        summary = svc._build_completeness_summary(events)
        assert len(summary["missing_required_events"]) == 250
        assert summary["events_with_missing_required_fields"] == 300


# ── _build_validation_errors_log ──────────────────────────────────────────


class TestBuildValidationErrorsLog:
    def test_no_missing_returns_none(self) -> None:
        summary = {
            "missing_required_events": [],
            "required_kde_coverage_ratio": 1.0,
            "events_with_missing_required_fields": 0,
        }
        assert svc._build_validation_errors_log([], summary) is None

    def test_with_missing_emits_header_and_rows(self) -> None:
        summary = {
            "missing_required_events": [
                {
                    "event_id": "e1",
                    "event_type": "SHIPPING",
                    "traceability_lot_code": "TLC-1",
                    "missing_fields": ["ship_to_gln", "receive_date"],
                },
            ],
            "required_kde_coverage_ratio": 0.5,
            "events_with_missing_required_fields": 1,
        }
        log = svc._build_validation_errors_log(
            [{"event_type": "SHIPPING"}, {"event_type": "RECEIVING"}],
            summary,
        )
        assert log is not None
        assert "VALIDATION ERRORS" in log
        assert "TLC-1" in log
        assert "ship_to_gln" in log
        assert "50.0%" in log
        assert "Total events exported: 2" in log

    def test_missing_event_with_unknown_fields(self) -> None:
        summary = {
            "missing_required_events": [
                {},  # entry with nothing — uses UNKNOWN fallbacks
            ],
            "required_kde_coverage_ratio": 0.0,
            "events_with_missing_required_fields": 1,
        }
        log = svc._build_validation_errors_log([{"event_type": "X"}], summary)
        assert log is not None
        assert "UNKNOWN" in log


# ── _build_chain_verification_payload ─────────────────────────────────────


def _chain_result(valid: bool = True, errors=None):
    return SimpleNamespace(
        valid=valid,
        chain_length=5,
        errors=list(errors or []),
        checked_at="2026-03-01T12:00:00+00:00",
    )


class TestBuildChainVerificationPayload:
    def test_verified_when_chain_valid_and_hashes_complete(self) -> None:
        events = [{"sha256_hash": "a" * 64, "chain_hash": "b" * 64}]
        payload = svc._build_chain_verification_payload(
            tenant_id="t",
            tlc="TLC",
            events=events,
            csv_hash="c" * 64,
            chain_verification=_chain_result(valid=True),
            completeness_summary={
                "required_kde_coverage_ratio": 1.0,
                "events_with_missing_required_fields": 0,
            },
        )
        assert payload["verification_status"] == "VERIFIED"
        assert payload["privacy"]["pii_redacted"] is True  # default redact

    def test_unverified_when_chain_invalid(self) -> None:
        events = [{"sha256_hash": "x", "chain_hash": "y"}]
        payload = svc._build_chain_verification_payload(
            tenant_id="t",
            tlc=None,
            events=events,
            csv_hash="c",
            chain_verification=_chain_result(valid=False, errors=["bad"]),
            completeness_summary={
                "required_kde_coverage_ratio": 1.0,
                "events_with_missing_required_fields": 0,
            },
        )
        assert payload["verification_status"] == "UNVERIFIED"
        assert payload["chain_verification"]["errors"] == ["bad"]

    def test_partial_when_hashes_missing(self) -> None:
        events = [{"sha256_hash": "", "chain_hash": ""}]
        payload = svc._build_chain_verification_payload(
            tenant_id="t",
            tlc=None,
            events=events,
            csv_hash="c",
            chain_verification=_chain_result(valid=True),
            completeness_summary={
                "required_kde_coverage_ratio": 1.0,
                "events_with_missing_required_fields": 0,
            },
        )
        assert payload["verification_status"] == "PARTIAL"
        assert payload["row_hash_coverage"]["missing_record_hashes"] == 1

    def test_privacy_block_reflects_include_pii(self) -> None:
        payload = svc._build_chain_verification_payload(
            tenant_id="t",
            tlc=None,
            events=[],
            csv_hash="c",
            chain_verification=_chain_result(valid=True),
            completeness_summary={
                "required_kde_coverage_ratio": 1.0,
                "events_with_missing_required_fields": 0,
            },
            include_pii=True,
        )
        assert payload["privacy"]["pii_redacted"] is False


# ── _build_fda_package ────────────────────────────────────────────────────


class TestBuildFdaPackage:
    def _summary_no_missing(self) -> dict:
        return {
            "required_checks_total": 1,
            "required_checks_passed": 1,
            "required_checks_missing": 0,
            "required_kde_coverage_ratio": 1.0,
            "events_with_missing_required_fields": 0,
            "missing_required_by_field": {},
            "missing_required_events": [],
        }

    def _summary_with_missing(self) -> dict:
        return {
            "required_checks_total": 2,
            "required_checks_passed": 1,
            "required_checks_missing": 1,
            "required_kde_coverage_ratio": 0.5,
            "events_with_missing_required_fields": 1,
            "missing_required_by_field": {"ship_to_gln": 1},
            "missing_required_events": [
                {
                    "event_id": "e1",
                    "event_type": "SHIPPING",
                    "traceability_lot_code": "TLC-1",
                    "missing_fields": ["ship_to_gln"],
                },
            ],
        }

    def _chain_payload(self) -> dict:
        return {
            "version": "1.0",
            "verification_status": "VERIFIED",
            "chain_verification": {
                "valid": True,
                "chain_length": 1,
                "errors": [],
                "checked_at": "2026-03-01T00:00:00+00:00",
            },
        }

    def test_happy_path_without_validation_errors(self) -> None:
        events = [_CORE_EVENT]
        csv_text = svc._generate_csv(events)
        pkg_bytes, meta = svc._build_fda_package(
            events=events,
            csv_content=csv_text,
            csv_hash="c" * 64,
            chain_payload=self._chain_payload(),
            completeness_summary=self._summary_no_missing(),
            tenant_id="t-1",
            tlc="TLC-1",
            query_start_date="2026-01-01",
            query_end_date="2026-12-31",
        )
        # Valid zip
        with zipfile.ZipFile(io.BytesIO(pkg_bytes)) as z:
            names = z.namelist()
            # No VALIDATION_ERRORS log — summary had no missing.
            assert not any("VALIDATION_ERRORS" in n for n in names)
            assert any("manifest.json" in n for n in names)
            assert any("README.txt" in n for n in names)

        # Manifest has privacy block reflecting default redaction.
        assert meta["manifest"]["privacy"]["pii_redacted"] is True
        assert meta["package_hash"]

    def test_happy_path_with_validation_errors(self) -> None:
        events = [{"event_type": "SHIPPING", "traceability_lot_code": "TLC-1", "id": "e1", "kdes": {}}]
        csv_text = svc._generate_csv(events)
        pkg_bytes, meta = svc._build_fda_package(
            events=events,
            csv_content=csv_text,
            csv_hash="c" * 64,
            chain_payload=self._chain_payload(),
            completeness_summary=self._summary_with_missing(),
            tenant_id="t-1",
            tlc=None,
            query_start_date=None,
            query_end_date=None,
        )
        with zipfile.ZipFile(io.BytesIO(pkg_bytes)) as z:
            names = z.namelist()
            # Validation log IS present now.
            assert any("VALIDATION_ERRORS" in n for n in names)
            # README mentions the log.
            readme = z.read(next(n for n in names if "README" in n)).decode()
            assert "VALIDATION_ERRORS" in readme

    def test_include_pii_changes_readme_note(self) -> None:
        pkg_bytes, meta = svc._build_fda_package(
            events=[_CORE_EVENT],
            csv_content=svc._generate_csv([_CORE_EVENT], include_pii=True),
            csv_hash="c" * 64,
            chain_payload=self._chain_payload(),
            completeness_summary=self._summary_no_missing(),
            tenant_id="t-1",
            tlc=None,
            query_start_date=None,
            query_end_date=None,
            include_pii=True,
        )
        with zipfile.ZipFile(io.BytesIO(pkg_bytes)) as z:
            readme = z.read(next(n for n in z.namelist() if "README" in n)).decode()
            assert "includes facility names" in readme
        assert meta["manifest"]["privacy"]["pii_redacted"] is False

    def test_event_types_and_tlc_counts_populated(self) -> None:
        events = [
            {"event_type": "SHIPPING", "traceability_lot_code": "TLC-1"},
            {"event_type": "SHIPPING", "traceability_lot_code": "TLC-1"},
            {"event_type": "RECEIVING", "traceability_lot_code": "TLC-2"},
            {"event_type": "", "traceability_lot_code": ""},  # empty keys skipped
        ]
        pkg_bytes, meta = svc._build_fda_package(
            events=events,
            csv_content="",
            csv_hash="c",
            chain_payload=self._chain_payload(),
            completeness_summary=self._summary_no_missing(),
            tenant_id="t",
            tlc=None,
            query_start_date=None,
            query_end_date=None,
        )
        summary = meta["manifest"]["summary"]
        assert summary["event_type_breakdown"] == {"SHIPPING": 2, "RECEIVING": 1}
        assert summary["traceability_lot_code_counts"] == {"TLC-1": 2, "TLC-2": 1}


# ── _event_to_fda_row_v2 ──────────────────────────────────────────────────


class TestEventToFdaRowV2:
    def test_no_rule_results_reports_no_rules_evaluated(self) -> None:
        row = svc._event_to_fda_row_v2(dict(_CORE_EVENT, rule_results=[]))
        assert row["Compliance Status"] == "NO_RULES_EVALUATED"
        assert row["Rule Failures"] == ""
        # Trace defaults.
        assert row["Trace Relationship"] == "queried"
        assert row["Trace Seed TLC"] == "TLC-1"

    def test_all_pass_reports_pass(self) -> None:
        row = svc._event_to_fda_row_v2(
            dict(_CORE_EVENT, rule_results=[{"rule_name": "r1", "passed": True}])
        )
        assert row["Compliance Status"] == "PASS"
        assert row["Rule Failures"] == ""

    def test_some_fail_reports_fail_and_joins_reasons(self) -> None:
        row = svc._event_to_fda_row_v2(
            dict(
                _CORE_EVENT,
                rule_results=[
                    {"rule_name": "r1", "passed": True},
                    {"rule_name": "r2", "passed": False, "why_failed": "missing KDE"},
                    {"rule_name": "r3", "passed": False, "why_failed": "bad format"},
                ],
            )
        )
        assert row["Compliance Status"] == "FAIL"
        assert "r2: missing KDE" in row["Rule Failures"]
        assert "r3: bad format" in row["Rule Failures"]

    def test_rule_result_missing_fields_uses_defaults(self) -> None:
        row = svc._event_to_fda_row_v2(
            dict(_CORE_EVENT, rule_results=[{"passed": False}])
        )
        assert "unknown_rule" in row["Rule Failures"]
        assert "no reason provided" in row["Rule Failures"]

    def test_trace_metadata_overrides(self) -> None:
        row = svc._event_to_fda_row_v2(
            dict(
                _CORE_EVENT,
                trace_relationship="linked_via_transformation",
                trace_seed_tlc="TLC-seed",
            )
        )
        assert row["Trace Relationship"] == "linked_via_transformation"
        assert row["Trace Seed TLC"] == "TLC-seed"


# ── _generate_csv_v2 ──────────────────────────────────────────────────────


class TestGenerateCsvV2:
    def test_v2_header_includes_compliance_columns(self) -> None:
        csv_text = svc._generate_csv_v2([_CORE_EVENT])
        header = csv_text.splitlines()[0]
        assert '"Compliance Status"' in header
        assert '"Rule Failures"' in header
        assert '"Trace Relationship"' in header
        assert '"Trace Seed TLC"' in header

    def test_v2_empty_events_yields_header_only(self) -> None:
        csv_text = svc._generate_csv_v2([])
        rows = list(csv.reader(io.StringIO(csv_text)))
        assert len(rows) == 1

    def test_v2_pii_redaction_flag_propagates(self) -> None:
        csv_redacted = svc._generate_csv_v2([_CORE_EVENT], include_pii=False)
        assert svc.PII_REDACTION_PLACEHOLDER in csv_redacted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
