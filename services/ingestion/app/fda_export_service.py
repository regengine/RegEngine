"""
FDA Export Service — helper functions and constants.

Extracted from fda_export_router.py to separate business logic (CSV generation,
FDA formatting, chain verification, completeness analysis) from HTTP route
handling.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.webhook_models import REQUIRED_KDES_BY_CTE, WebhookCTEType


# ---------------------------------------------------------------------------
# FDA Spreadsheet Column Spec
# ---------------------------------------------------------------------------
# These columns align with FDA's expected format for FSMA 204 traceability
# records. The column names match the FDA's IFT spreadsheet specification.

FDA_COLUMNS = [
    "Traceability Lot Code (TLC)",
    "Product Description",
    "Quantity",
    "Unit of Measure",
    "Event Type (CTE)",
    "Event Date",
    "Event Time",
    "Location GLN",
    "Location Name",
    "Ship From GLN",
    "Ship From Name",
    "Ship To GLN",
    "Ship To Name",
    "Immediate Previous Source",
    "TLC Source GLN",
    "TLC Source FDA Registration",
    "Source Document",
    "Record Hash (SHA-256)",
    "Chain Hash",
    # KDE columns — FSMA 204 requires all KDEs in export
    "Reference Document Number",
    "Receive Date",
    "Ship Date",
    "Harvest Date",
    "Cooling Date",
    "Packing Date",
    "Transformation Date",
    "Landing Date",
    "Receiving Location",
    "Temperature (°F)",
    "Carrier",
    "Additional KDEs (JSON)",
    # FSMA 204 §1.1455(c): date/time event entered into system
    "System Entry Timestamp",
]


# KDE keys that get their own named columns in the FDA export
_NAMED_KDE_COLUMNS = {
    "reference_document_number": "Reference Document Number",
    "receive_date": "Receive Date",
    "ship_date": "Ship Date",
    "harvest_date": "Harvest Date",
    "cooling_date": "Cooling Date",
    "packing_date": "Packing Date",
    "transformation_date": "Transformation Date",
    "landing_date": "Landing Date",
    "receiving_location": "Receiving Location",
    "temperature": "Temperature (°F)",
    "carrier": "Carrier",
}


# Extended column spec: original FDA columns + compliance + traceability graph columns
FDA_COLUMNS_V2 = FDA_COLUMNS + [
    "Compliance Status",
    "Rule Failures",
    # Transformation traceability (added Phase 2)
    "Trace Relationship",   # "queried" | "linked_via_transformation"
    "Trace Seed TLC",       # The TLC originally queried (useful when this row is a linked lot)
]


def _event_to_fda_row(event: dict) -> dict:
    """Convert a persisted CTE event to an FDA spreadsheet row."""
    kdes = event.get("kdes", {})
    timestamp = event.get("event_timestamp", "")

    # Split timestamp into date and time
    event_date = ""
    event_time = ""
    if timestamp:
        try:
            ts = str(timestamp)
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            event_date = dt.strftime("%Y-%m-%d")
            event_time = dt.strftime("%H:%M:%S %Z")
        except (ValueError, AttributeError):
            event_date = str(timestamp)[:10]

    row = {
        "Traceability Lot Code (TLC)": event.get("traceability_lot_code", ""),
        "Product Description": event.get("product_description", ""),
        "Quantity": event.get("quantity", ""),
        "Unit of Measure": event.get("unit_of_measure", ""),
        "Event Type (CTE)": event.get("event_type", ""),
        "Event Date": event_date,
        "Event Time": event_time,
        "Location GLN": event.get("location_gln", "") or "",
        "Location Name": event.get("location_name", "") or "",
        "Ship From GLN": kdes.get("ship_from_gln", ""),
        "Ship From Name": kdes.get("ship_from_location", ""),
        "Ship To GLN": kdes.get("ship_to_gln", ""),
        "Ship To Name": kdes.get("ship_to_location", kdes.get("receiving_location", "")),
        "Immediate Previous Source": kdes.get("immediate_previous_source", ""),
        "TLC Source GLN": kdes.get("tlc_source_gln", ""),
        "TLC Source FDA Registration": kdes.get("tlc_source_fda_reg", ""),
        "Source Document": event.get("source", ""),
        "Record Hash (SHA-256)": event.get("sha256_hash", ""),
        "Chain Hash": event.get("chain_hash", ""),
    }

    # Map named KDE columns
    for kde_key, col_name in _NAMED_KDE_COLUMNS.items():
        row[col_name] = str(kdes.get(kde_key, "")) if kdes.get(kde_key) else ""

    # Remaining KDEs not in named columns → JSON blob
    extra_kdes = {k: v for k, v in kdes.items() if k not in _NAMED_KDE_COLUMNS}
    row["Additional KDEs (JSON)"] = json.dumps(extra_kdes) if extra_kdes else ""

    # FSMA 204 requires "system entry timestamp" — when the record was entered
    # into the traceability system (distinct from when the physical event occurred).
    # This maps to the ingested_at column which defaults to NOW() on INSERT.
    row["System Entry Timestamp"] = event.get("ingested_at", "") or ""

    return row


def _generate_csv(events: list[dict]) -> str:
    """Generate FDA-compliant CSV from a list of CTE events."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FDA_COLUMNS)
    writer.writeheader()

    for event in events:
        writer.writerow(_event_to_fda_row(event))

    return output.getvalue()


def _safe_filename_token(raw: str) -> str:
    """Normalize user-provided identifiers for filenames."""
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in raw)[:64] or "all"


def _event_value_for_required_field(event: dict, required_field: str) -> Any:
    """Resolve required field values from direct event fields or KDE map."""
    kdes = event.get("kdes", {})
    if required_field in {"traceability_lot_code", "product_description", "quantity", "unit_of_measure"}:
        return event.get(required_field)
    if required_field == "location_name":
        return event.get("location_name") or kdes.get("location_name")
    return kdes.get(required_field)


def _build_completeness_summary(events: list[dict]) -> dict:
    """
    Assess required KDE coverage across exported events.

    Completeness is computed against REQUIRED_KDES_BY_CTE.
    """
    missing_by_field: dict[str, int] = {}
    missing_by_event: list[dict[str, Any]] = []
    checks_total = 0
    checks_missing = 0

    for event in events:
        raw_event_type = str(event.get("event_type", "")).upper()
        required_fields = []
        if raw_event_type in WebhookCTEType.__members__:
            required_fields = REQUIRED_KDES_BY_CTE[WebhookCTEType[raw_event_type]]

        missing_fields = []
        for required_field in required_fields:
            checks_total += 1
            value = _event_value_for_required_field(event, required_field)
            missing = value is None or str(value).strip() == ""
            if missing:
                checks_missing += 1
                missing_fields.append(required_field)
                missing_by_field[required_field] = missing_by_field.get(required_field, 0) + 1

        if missing_fields:
            missing_by_event.append(
                {
                    "event_id": event.get("id"),
                    "event_type": event.get("event_type"),
                    "traceability_lot_code": event.get("traceability_lot_code"),
                    "missing_fields": missing_fields,
                }
            )

    checks_passed = checks_total - checks_missing
    coverage_ratio = 1.0 if checks_total == 0 else round(checks_passed / checks_total, 4)

    return {
        "required_checks_total": checks_total,
        "required_checks_passed": checks_passed,
        "required_checks_missing": checks_missing,
        "required_kde_coverage_ratio": coverage_ratio,
        "events_with_missing_required_fields": len(missing_by_event),
        "missing_required_by_field": missing_by_field,
        "missing_required_events": missing_by_event[:250],
    }


def _build_validation_errors_log(events: list[dict], completeness_summary: dict) -> str | None:
    """Generate a VALIDATION_ERRORS.log for events with missing required KDEs.

    Returns None if all events pass validation (no log needed).
    """
    missing_events = completeness_summary.get("missing_required_events", [])
    if not missing_events:
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    coverage = completeness_summary["required_kde_coverage_ratio"]
    total_events = len(events)
    events_with_errors = completeness_summary["events_with_missing_required_fields"]

    lines = [
        f"VALIDATION ERRORS — Generated {timestamp}",
        f"{'=' * 60}",
        "",
        f"Total events exported: {total_events}",
        f"Events with validation errors: {events_with_errors}",
        f"KDE Coverage: {coverage * 100:.1f}%",
        "",
        "NOTE: These errors do NOT block the export. FDA may need whatever",
        "data is available. Fix these issues to improve compliance score.",
        "",
        "-" * 60,
        "",
    ]

    for entry in missing_events:
        tlc = entry.get("traceability_lot_code") or "UNKNOWN"
        event_type = entry.get("event_type") or "UNKNOWN"
        missing = ", ".join(entry.get("missing_fields", []))
        lines.append(f"Event TLC: {tlc} | Type: {event_type} | Missing: {missing}")

    lines.append("")
    lines.append(f"Total: {events_with_errors} events with validation errors out of {total_events} exported")
    lines.append(f"KDE Coverage: {coverage * 100:.1f}%")
    lines.append("")

    return "\n".join(lines)


def _build_chain_verification_payload(
    *,
    tenant_id: str,
    tlc: Optional[str],
    events: list[dict],
    csv_hash: str,
    chain_verification: Any,
    completeness_summary: dict,
) -> dict:
    """Build JSON payload used for independent package verification."""
    missing_record_hashes = sum(1 for event in events if not event.get("sha256_hash"))
    missing_chain_hashes = sum(1 for event in events if not event.get("chain_hash"))

    verification_status = "VERIFIED" if chain_verification.valid else "UNVERIFIED"
    if missing_record_hashes or missing_chain_hashes:
        verification_status = "PARTIAL"

    return {
        "version": "1.0",
        "snapshot_id": str(uuid4()),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "hash_algorithm": "SHA-256",
        "content_hash": csv_hash,
        "verification_status": verification_status,
        "tenant_id": tenant_id,
        "traceability_lot_code": tlc,
        "record_count": len(events),
        "chain_verification": {
            "valid": bool(chain_verification.valid),
            "chain_length": int(chain_verification.chain_length),
            "errors": list(chain_verification.errors),
            "checked_at": chain_verification.checked_at,
        },
        "row_hash_coverage": {
            "records_with_hash": len(events) - missing_record_hashes,
            "records_with_chain_hash": len(events) - missing_chain_hashes,
            "missing_record_hashes": missing_record_hashes,
            "missing_chain_hashes": missing_chain_hashes,
        },
        "completeness": {
            "required_kde_coverage_ratio": completeness_summary["required_kde_coverage_ratio"],
            "events_with_missing_required_fields": completeness_summary["events_with_missing_required_fields"],
        },
        "attestation": {
            "attested_by": "regengine-fda-export-router",
            "assertion": "Package generated from persisted fsma.cte_events with chain verification.",
        },
    }


def _build_fda_package(
    *,
    events: list[dict],
    csv_content: str,
    csv_hash: str,
    chain_payload: dict,
    completeness_summary: dict,
    tenant_id: str,
    tlc: Optional[str],
    query_start_date: Optional[str],
    query_end_date: Optional[str],
) -> tuple[bytes, dict]:
    """Build zip package bytes and return package metadata."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scope = _safe_filename_token(tlc or "all")
    csv_name = f"fda_spreadsheet_{scope}_{timestamp}.csv"
    chain_name = f"chain_verification_{scope}_{timestamp}.json"
    validation_name = f"VALIDATION_ERRORS_{scope}_{timestamp}.log"
    manifest_name = "manifest.json"
    readme_name = "README.txt"

    csv_bytes = csv_content.encode("utf-8")
    chain_bytes = json.dumps(chain_payload, indent=2, sort_keys=True).encode("utf-8")
    validation_log = _build_validation_errors_log(events, completeness_summary)
    validation_bytes = validation_log.encode("utf-8") if validation_log else None
    readme_bytes = (
        "RegEngine FDA Traceability Package\n"
        "=================================\n"
        "Contents:\n"
        "1) fda_spreadsheet_*.csv - FDA-sortable traceability rows\n"
        "2) chain_verification_*.json - chain integrity and hash coverage metadata\n"
        "3) manifest.json - package metadata and file checksums\n"
        + ("4) VALIDATION_ERRORS_*.log - KDE validation warnings per event\n" if validation_log else "")
        + "\n"
        "Verification:\n"
        "- Compare manifest file hashes with local SHA-256 calculations.\n"
        "- Validate chain_verification.verification_status == VERIFIED or PARTIAL.\n"
    ).encode("utf-8")

    file_hashes = {
        csv_name: hashlib.sha256(csv_bytes).hexdigest(),
        chain_name: hashlib.sha256(chain_bytes).hexdigest(),
        readme_name: hashlib.sha256(readme_bytes).hexdigest(),
    }
    if validation_bytes:
        file_hashes[validation_name] = hashlib.sha256(validation_bytes).hexdigest()

    event_types: dict[str, int] = {}
    tlc_counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("event_type") or "")
        if event_type:
            event_types[event_type] = event_types.get(event_type, 0) + 1
        event_tlc = str(event.get("traceability_lot_code") or "")
        if event_tlc:
            tlc_counts[event_tlc] = tlc_counts.get(event_tlc, 0) + 1

    manifest = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "export_type": "fda_traceability_package",
        "tenant_id": tenant_id,
        "query": {
            "tlc": tlc,
            "start_date": query_start_date,
            "end_date": query_end_date,
        },
        "summary": {
            "record_count": len(events),
            "event_type_breakdown": event_types,
            "traceability_lot_codes": sorted(tlc_counts.keys()),
            "traceability_lot_code_counts": tlc_counts,
            "csv_content_hash": csv_hash,
        },
        "completeness": completeness_summary,
        "verification": {
            "status": chain_payload.get("verification_status"),
            "chain_valid": chain_payload.get("chain_verification", {}).get("valid"),
            "chain_length": chain_payload.get("chain_verification", {}).get("chain_length"),
        },
        "files": [
            {"name": name, "sha256": digest}
            for name, digest in file_hashes.items()
        ],
    }
    # Do not include a manifest self-hash entry: self-referential hashes cannot be
    # recomputed from final bytes without special canonicalization rules.
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, mode="w", compression=zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr(csv_name, csv_bytes)
        zipf.writestr(chain_name, chain_bytes)
        if validation_bytes:
            zipf.writestr(validation_name, validation_bytes)
        zipf.writestr(manifest_name, manifest_bytes)
        zipf.writestr(readme_name, readme_bytes)

    package_bytes = payload.getvalue()
    package_hash = hashlib.sha256(package_bytes).hexdigest()

    return package_bytes, {
        "csv_name": csv_name,
        "chain_name": chain_name,
        "manifest_name": manifest_name,
        "readme_name": readme_name,
        "package_hash": package_hash,
        "manifest": manifest,
    }


def _event_to_fda_row_v2(event: dict) -> dict:
    """Convert a canonical traceability_event row (with rule results) to an FDA spreadsheet row.

    Accepts the same base fields as ``_event_to_fda_row`` plus:
    - ``rule_results``: list[dict] with keys ``rule_name``, ``passed``, ``why_failed``
    """
    # Reuse the legacy mapper for core FDA columns
    base_row = _event_to_fda_row(event)

    # Compute compliance columns from attached rule results
    rule_results: list[dict] = event.get("rule_results", [])
    if not rule_results:
        compliance_status = "NO_RULES_EVALUATED"
        rule_failures_text = ""
    else:
        failed = [r for r in rule_results if not r.get("passed")]
        if not failed:
            compliance_status = "PASS"
            rule_failures_text = ""
        else:
            compliance_status = "FAIL"
            failure_descriptions = []
            for f in failed:
                name = f.get("rule_name", "unknown_rule")
                reason = f.get("why_failed", "no reason provided")
                failure_descriptions.append(f"{name}: {reason}")
            rule_failures_text = "; ".join(failure_descriptions)

    base_row["Compliance Status"] = compliance_status
    base_row["Rule Failures"] = rule_failures_text
    # Transformation trace metadata (present when query_events_by_tlc expanded via links)
    base_row["Trace Relationship"] = event.get("trace_relationship", "queried")
    base_row["Trace Seed TLC"] = event.get("trace_seed_tlc", event.get("traceability_lot_code", ""))
    return base_row


def _generate_csv_v2(events: list[dict]) -> str:
    """Generate FDA-compliant CSV from canonical model events (with compliance columns)."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FDA_COLUMNS_V2)
    writer.writeheader()

    for event in events:
        writer.writerow(_event_to_fda_row_v2(event))

    return output.getvalue()
