"""Data-free FDA export service checks."""

from __future__ import annotations

import csv
import hashlib
import io
import json
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


# ---------------------------------------------------------------------------
# S7: evidence_context member — rule versions and known gaps in the package
# ---------------------------------------------------------------------------


def _package_with_context(**overrides):
    events = [{"id": "evt-1", "traceability_lot_code": "TLC-1", "event_type": "shipping"}]
    csv_content = svc._generate_csv(events)
    summary = svc._build_completeness_summary(events)
    digest = hashlib.sha256(csv_content.encode()).hexdigest()
    chain = SimpleNamespace(valid=True, chain_length=1, errors=[], checked_at=None)
    payload = svc._build_chain_verification_payload(
        tenant_id="t", tlc="TLC-1", events=events, csv_hash=digest,
        chain_verification=chain, completeness_summary=summary,
    )
    kwargs = dict(
        events=events, csv_content=csv_content, csv_hash=digest,
        chain_payload=payload, completeness_summary=summary,
        tenant_id="t", tlc="TLC-1", query_start_date=None, query_end_date=None,
    )
    kwargs.update(overrides)
    return svc._build_fda_package(**kwargs), summary, payload


def _read_member(data: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        return package.read(name)


def test_evidence_context_member_is_hashed_and_under_merkle_root() -> None:
    rule_versions = {
        "snapshot_at": "2026-10-28T00:00:00+00:00",
        "enforcement_mode": "off",
        "catalog": {"rule-a": {"version": 3, "title": "A", "severity": "critical", "category": "kde"}},
        "catalog_status": "ok",
        "evaluated": [{"rule_id": "rule-a", "rule_version": 2, "evaluation_count": 1}],
        "evaluated_status": "ok",
    }
    (data, meta), summary, payload = _package_with_context(rule_versions=rule_versions)
    name = meta["evidence_context_name"]
    assert name.startswith("evidence_context_TLC-1_") and name.endswith(".json")
    assert not name.startswith(("fda_spreadsheet_", "chain_verification_"))

    manifest = meta["manifest"]
    entry = next(f for f in manifest["files"] if f["name"] == name)
    body = _read_member(data, name)
    assert entry["path"] == name
    assert entry["size"] == len(body)
    assert entry["sha256"] == hashlib.sha256(body).hexdigest()
    assert entry["sha256"] in manifest["merkle"]["leaves"]
    assert manifest["evidence_context"]["path"] == name
    assert manifest["evidence_context"]["sha256"] == entry["sha256"]
    assert manifest["evidence_context"]["rules_enforcement_mode"] == "off"
    assert manifest["evidence_context"]["coverage_gate_bypassed"] is False

    context = json.loads(body)
    assert context["version"] == "1.0"
    assert context["rule_versions"] == rule_versions
    gaps = context["known_gaps"]
    assert gaps["rules_catalog_status"] == "ok"
    assert gaps["rules_evaluated_status"] == "ok"
    assert gaps["coverage_gate_bypassed"] is False
    assert gaps["verification_status"] == payload["verification_status"]
    assert gaps["required_kde_coverage_ratio"] == summary["required_kde_coverage_ratio"]
    assert gaps["events_with_missing_required_fields"] == summary["events_with_missing_required_fields"]
    assert gaps["missing_required_events_truncated"] is False
    assert any("paper" in note for note in gaps["notes"])


def test_evidence_context_written_even_without_rule_versions() -> None:
    (data, meta), _, _ = _package_with_context()
    context = json.loads(_read_member(data, meta["evidence_context_name"]))
    assert context["rule_versions"]["catalog_status"] == "unavailable"
    assert context["rule_versions"]["evaluated_status"] == "not_requested"
    assert context["known_gaps"]["rules_catalog_status"] == "unavailable"
    readme = _read_member(data, meta["readme_name"]).decode()
    assert "evidence_context_*.json" in readme


def test_coverage_gate_bypass_is_recorded_in_package() -> None:
    (data, meta), _, _ = _package_with_context(coverage_gate_bypassed=True)
    context = json.loads(_read_member(data, meta["evidence_context_name"]))
    assert context["known_gaps"]["coverage_gate_bypassed"] is True
    assert meta["manifest"]["evidence_context"]["coverage_gate_bypassed"] is True


def test_known_gaps_states_capped_missing_event_list() -> None:
    gaps = svc._build_known_gaps(
        completeness_summary={
            "required_kde_coverage_ratio": 0.5,
            "events_with_missing_required_fields": 300,
            "missing_required_events": [{"x": 1}] * 250,
            "missing_required_by_field": {"location_gln": 300},
            "events_unchecked_type": 2,
            "unchecked_event_types": ["unknown"],
        },
        chain_payload={
            "verification_status": "PARTIAL",
            "row_hash_coverage": {"missing_record_hashes": 1, "missing_chain_hashes": 2},
        },
        coverage_gate_bypassed=True,
        rule_versions=None,
    )
    assert gaps["missing_required_events_listed"] == 250
    assert gaps["missing_required_events_truncated"] is True
    assert gaps["events_unchecked_type"] == 2
    assert gaps["unchecked_event_types"] == ["unknown"]
    assert gaps["missing_record_hashes"] == 1
    assert gaps["missing_chain_hashes"] == 2
    assert gaps["verification_status"] == "PARTIAL"
    assert gaps["rules_enforcement_mode"] is None
    assert gaps["rules_catalog_status"] == "unavailable"


def test_known_gaps_tolerates_partial_inputs() -> None:
    gaps = svc._build_known_gaps(
        completeness_summary={}, chain_payload={}, coverage_gate_bypassed=False, rule_versions={}
    )
    assert gaps["events_with_missing_required_fields"] == 0
    assert gaps["missing_required_events_truncated"] is False
    assert gaps["verification_status"] is None
    json.dumps(gaps)


def test_rule_versions_for_events_degrades_when_snapshot_fails(monkeypatch) -> None:
    import shared.rules.versions as versions_mod

    def _boom(*_a, **_k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(versions_mod, "snapshot_rule_versions", _boom)
    snap = svc._rule_versions_for_events(object(), "t", [{"id": "e1"}])
    assert snap["catalog_status"] == "unavailable"
    assert snap["evaluated_status"] == "unavailable"


def test_rule_versions_for_events_passes_event_ids(monkeypatch) -> None:
    import shared.rules.versions as versions_mod

    seen = {}

    def _fake(db, tenant_id=None, event_ids=None):
        seen.update(db=db, tenant_id=tenant_id, event_ids=event_ids)
        return {"catalog_status": "ok"}

    monkeypatch.setattr(versions_mod, "snapshot_rule_versions", _fake)
    db = object()
    out = svc._rule_versions_for_events(db, "tenant-9", [{"id": "e1"}, {"id": None}, {}, "not-a-dict"])
    assert out == {"catalog_status": "ok"}
    assert seen == {"db": db, "tenant_id": "tenant-9", "event_ids": ["e1"]}
