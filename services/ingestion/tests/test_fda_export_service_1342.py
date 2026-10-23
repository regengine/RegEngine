"""Data-free FDA export service checks."""

from __future__ import annotations

import csv
import hashlib
import io
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import fda_export_service as svc  # noqa: E402


def test_empty_value_returns_empty() -> None:
    assert svc._redact_location_value("", "Location Name", False) == ""


def test_pii_column_non_empty_gets_placeholder() -> None:
    assert svc._redact_location_value(" ", "Location Name", False) == svc.PII_REDACTION_PLACEHOLDER


def test_empty_extra_kdes_remain_empty() -> None:
    assert svc._redact_extra_kde_pii({}) == {}


def test_no_timestamp_leaves_date_blank() -> None:
    row = svc._event_to_fda_row({})
    assert row["Event Date"] == ""
    assert row["Event Time"] == ""
    assert set(row) == set(svc.FDA_COLUMNS)


def test_empty_events_yields_header_only() -> None:
    rows = list(csv.reader(io.StringIO(svc._generate_csv([]))))
    assert rows == [svc.FDA_COLUMNS]


def test_pdf_with_no_events_is_a_pdf() -> None:
    assert svc._generate_pdf([]).startswith(b"%PDF")


def test_empty_filename_token_falls_back_to_all() -> None:
    assert svc._safe_filename_token("") == "all"


def test_missing_required_field_resolves_to_none() -> None:
    assert svc._event_value_for_required_field({}, "location_name") is None
    assert svc._event_value_for_required_field({}, "traceability_lot_code") is None


def test_empty_completeness_has_no_checks() -> None:
    summary = svc._build_completeness_summary([])
    assert summary["required_checks_total"] == 0
    assert summary["required_kde_coverage_ratio"] == 1.0
    assert summary["missing_required_events"] == []


def test_empty_field_event_is_unchecked() -> None:
    summary = svc._build_completeness_summary([{}])
    assert summary["events_unchecked_type"] == 1
    assert summary["required_kde_coverage_ratio"] == 0.0


def test_no_missing_returns_none() -> None:
    assert svc._build_validation_errors_log([], svc._build_completeness_summary([])) is None


def test_chain_payload_has_zero_record_counts() -> None:
    summary = svc._build_completeness_summary([])
    chain = SimpleNamespace(valid=True, chain_length=0, errors=[], checked_at=None)
    payload = svc._build_chain_verification_payload(
        tenant_id="", tlc=None, events=[], csv_hash="", chain_verification=chain,
        completeness_summary=summary,
    )
    assert payload["record_count"] == 0
    assert payload["row_hash_coverage"]["missing_record_hashes"] == 0
    assert payload["verification_status"] == "VERIFIED"
    assert payload["privacy"]["pii_redacted"] is True


def test_empty_package_manifest_has_no_records() -> None:
    events = []
    csv_content = svc._generate_csv(events)
    summary = svc._build_completeness_summary(events)
    digest = hashlib.sha256(csv_content.encode()).hexdigest()
    chain = SimpleNamespace(valid=True, chain_length=0, errors=[], checked_at=None)
    payload = svc._build_chain_verification_payload(
        tenant_id="", tlc=None, events=events, csv_hash=digest,
        chain_verification=chain, completeness_summary=summary,
    )
    data, metadata = svc._build_fda_package(
        events=events, csv_content=csv_content, csv_hash=digest,
        chain_payload=payload, completeness_summary=summary,
        tenant_id="", tlc=None, query_start_date=None, query_end_date=None,
    )
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        assert package.testzip() is None
        assert package.read(metadata["csv_name"]).decode() == csv_content
    assert metadata["manifest"]["summary"]["record_count"] == 0
    assert metadata["manifest"]["privacy"]["pii_redacted"] is True


def test_v2_empty_events_yields_header_only() -> None:
    rows = list(csv.reader(io.StringIO(svc._generate_csv_v2([]))))
    assert rows == [svc.FDA_COLUMNS_V2]
