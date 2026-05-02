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

from .shared.csv_safety import sanitize_cell
from .webhook_models import REQUIRED_KDES_BY_CTE, WebhookCTEType
from shared.fda_export import safe_filename_token as _shared_safe_filename_token


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
    "Growing Area",
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
    "growing_area_name": "Growing Area",
}

# KDE keys consumed by the literal dict block inside ``_event_to_fda_row``
# (Ship From/To GLN+Name, Immediate Previous Source, TLC Source GLN/FDA
# Reg). These must also be excluded from the "Additional KDEs (JSON)"
# extras blob or they leak their values — including PII-bearing
# ship_from_location / ship_to_location / immediate_previous_source —
# through a back channel even when the named columns are redacted
# (issue #1219).
_LITERAL_CONSUMED_KDES = frozenset(
    {
        "ship_from_gln",
        "ship_from_location",
        "ship_to_gln",
        "ship_to_location",
        "immediate_previous_source",
        "tlc_source_gln",
        "tlc_source_fda_reg",
    }
)


# ---------------------------------------------------------------------------
# PII Redaction (issue #1219)
# ---------------------------------------------------------------------------
# Facility *names* and street/shipping *locations* are customer PII: they
# identify the business that owns the lot, which is a competitive-intel
# leak when exports are shared outside the regulated entity (e.g.
# operator dashboards, exception workflows, downstream reviewers who
# aren't the FDA).
#
# GLN and FDA registration numbers are registered business identifiers —
# they're regulatory primary keys and the FDA's expected join-key. We
# keep them visible so the export is still usable for FSMA-204 recall
# scoping.
#
# Default behavior: redact these columns to ``[REDACTED]``. An export
# with ``include_pii=True`` (gated in the router by the ``fda.export.pii``
# permission and logged in the audit trail) emits full values.

PII_REDACTION_PLACEHOLDER = "[REDACTED]"

_PII_LOCATION_COLUMNS = frozenset(
    {
        "Location Name",
        "Ship From Name",
        "Ship To Name",
        "Immediate Previous Source",
        "Receiving Location",
    }
)


def _redact_location_value(value: str, column_name: str, include_pii: bool) -> str:
    """Redact customer-identifying location values unless ``include_pii=True``.

    Returns ``PII_REDACTION_PLACEHOLDER`` when:
      • ``include_pii`` is False, AND
      • ``column_name`` is in :data:`_PII_LOCATION_COLUMNS`, AND
      • ``value`` is non-empty (empty strings stay empty so blank columns
        don't become a confusing "[REDACTED]" string in the CSV).

    Otherwise returns ``value`` unchanged. The returned value is *not*
    re-passed through ``sanitize_cell`` — callers are expected to have
    already sanitized ``value`` before calling this helper.
    """
    if include_pii:
        return value
    if column_name not in _PII_LOCATION_COLUMNS:
        return value
    if not value:
        return value
    return PII_REDACTION_PLACEHOLDER


# Extended column spec: original FDA columns + compliance + traceability graph columns
FDA_COLUMNS_V2 = FDA_COLUMNS + [
    "Compliance Status",
    "Rule Failures",
    # Transformation traceability (added Phase 2)
    "Trace Relationship",   # "queried" | "linked_via_transformation"
    "Trace Seed TLC",       # The TLC originally queried (useful when this row is a linked lot)
]


def _event_to_fda_row(event: dict, *, include_pii: bool = False) -> dict:
    """Convert a persisted CTE event to an FDA spreadsheet row.

    Every string-valued cell passes through :func:`sanitize_cell` before
    being written so that any tenant-controlled free-text field (e.g.
    ``product_description``, ``ship_from_location``) cannot carry a
    spreadsheet formula into the FDA auditor's workstation. Hash fields
    are SHA-256 hex digests and cannot start with a formula prefix, but
    we sanitize them defensively for symmetry (issue #1081).

    PII redaction (issue #1219): by default, facility *names* and
    shipping *location* strings are replaced with
    :data:`PII_REDACTION_PLACEHOLDER`. GLNs and FDA registration numbers
    remain visible because they are the regulatory primary keys the FDA
    uses to join exports to registered business entities. Pass
    ``include_pii=True`` (router-gated on ``fda.export.pii`` permission
    + audit-logged) to emit the raw values.
    """
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

    # Sanitize first, then apply PII redaction. Order matters:
    # sanitize_cell neutralizes spreadsheet-formula prefixes on the raw
    # tenant value, and _redact_location_value then replaces the whole
    # sanitized string with the placeholder when include_pii=False.
    row = {
        "Traceability Lot Code (TLC)": sanitize_cell(event.get("traceability_lot_code", "")),
        "Product Description": sanitize_cell(event.get("product_description", "")),
        "Quantity": sanitize_cell(event.get("quantity", "")),
        "Unit of Measure": sanitize_cell(event.get("unit_of_measure", "")),
        "Event Type (CTE)": sanitize_cell(event.get("event_type", "")),
        "Event Date": sanitize_cell(event_date),
        "Event Time": sanitize_cell(event_time),
        "Location GLN": sanitize_cell(event.get("location_gln", "") or ""),
        "Location Name": _redact_location_value(
            sanitize_cell(event.get("location_name", "") or ""),
            "Location Name",
            include_pii,
        ),
        "Ship From GLN": sanitize_cell(kdes.get("ship_from_gln", "") or ""),
        "Ship From Name": _redact_location_value(
            sanitize_cell(kdes.get("ship_from_location", "") or ""),
            "Ship From Name",
            include_pii,
        ),
        "Ship To GLN": sanitize_cell(kdes.get("ship_to_gln", "") or ""),
        "Ship To Name": _redact_location_value(
            sanitize_cell(kdes.get("ship_to_location", kdes.get("receiving_location", "")) or ""),
            "Ship To Name",
            include_pii,
        ),
        "Immediate Previous Source": _redact_location_value(
            sanitize_cell(kdes.get("immediate_previous_source", "") or ""),
            "Immediate Previous Source",
            include_pii,
        ),
        "TLC Source GLN": sanitize_cell(kdes.get("tlc_source_gln", "") or ""),
        "TLC Source FDA Registration": sanitize_cell(kdes.get("tlc_source_fda_reg", "") or ""),
        "Source Document": sanitize_cell(event.get("source", "")),
        "Record Hash (SHA-256)": sanitize_cell(event.get("sha256_hash", "")),
        "Chain Hash": sanitize_cell(event.get("chain_hash", "")),
    }

    # Map named KDE columns. Apply PII redaction on the named columns
    # that land in _PII_LOCATION_COLUMNS (e.g. "Receiving Location").
    for kde_key, col_name in _NAMED_KDE_COLUMNS.items():
        raw = kdes.get(kde_key)
        sanitized = sanitize_cell(raw) if raw else ""
        row[col_name] = _redact_location_value(sanitized, col_name, include_pii)

    # Remaining KDEs not in named columns → JSON blob.
    # A JSON-encoded string can still begin with ``=`` once a spreadsheet
    # renders it into a cell, so sanitize the whole blob as well.
    #
    # Exclude both:
    #   • keys already surfaced via ``_NAMED_KDE_COLUMNS`` (explicit map
    #     of KDE → named column), AND
    #   • keys surfaced via the literal dict block above (Ship From/To
    #     Name, Immediate Previous Source, TLC Source GLN/FDA Reg, etc.).
    # Without the second filter, those PII-bearing KDEs would leak into
    # the extras blob as a back-channel even after we redacted the named
    # columns (issue #1219).
    #
    # PII redaction for the JSON blob: the "extras" map can carry arbitrary
    # customer-supplied keys, some of which (``facility_address``,
    # ``receiver_address``, ``origin_address``) are PII. When
    # ``include_pii=False`` we strip any key whose name contains a PII
    # signal (``address``, ``street``, ``location``, ``phone``,
    # ``contact``) before encoding. This is a defensive default — the
    # primary PII columns are already redacted above; this catches the
    # long tail of unknown-shape KDE data.
    extra_kdes = {
        k: v
        for k, v in kdes.items()
        if k not in _NAMED_KDE_COLUMNS and k not in _LITERAL_CONSUMED_KDES
    }
    if extra_kdes and not include_pii:
        extra_kdes = _redact_extra_kde_pii(extra_kdes)
    row["Additional KDEs (JSON)"] = sanitize_cell(json.dumps(extra_kdes)) if extra_kdes else ""

    # FSMA 204 requires "system entry timestamp" — when the record was entered
    # into the traceability system (distinct from when the physical event occurred).
    # This maps to the ingested_at column which defaults to NOW() on INSERT.
    row["System Entry Timestamp"] = sanitize_cell(event.get("ingested_at", "") or "")

    return row


# KDE-key substrings that signal PII in the freeform "Additional KDEs
# (JSON)" bucket. Case-insensitive substring match because upstream
# parsers normalize key casing inconsistently.
_PII_EXTRA_KDE_SUBSTRINGS = (
    "address",
    "street",
    "location_name",
    "facility_name",
    "contact",
    "phone",
    "email",
    "owner_name",
    "operator_name",
    "driver_name",
    "receiver_name",
    "consignee_name",
)


def _redact_extra_kde_pii(extra_kdes: dict) -> dict:
    """Replace PII values in the extras JSON blob with the placeholder.

    Preserves the key (so auditors see "this field existed but was
    redacted") and the surrounding structure; only the string value is
    replaced. Non-string values (numbers, dates) pass through unchanged
    because numeric PII is unusual in KDE data and the round-trip would
    be lossy.
    """
    redacted = {}
    for key, value in extra_kdes.items():
        key_lower = str(key).lower()
        is_pii = any(marker in key_lower for marker in _PII_EXTRA_KDE_SUBSTRINGS)
        if is_pii and isinstance(value, str) and value:
            redacted[key] = PII_REDACTION_PLACEHOLDER
        else:
            redacted[key] = value
    return redacted


def _generate_csv(events: list[dict], *, include_pii: bool = False) -> str:
    """Generate FDA-compliant CSV from a list of CTE events.

    Uses ``csv.QUOTE_ALL`` so every cell is wrapped in double quotes —
    a defense-in-depth measure on top of :func:`sanitize_cell` that
    neutralizes cells containing newlines, quotes, or commas regardless
    of the reader's field-splitting heuristics (issue #1081).

    ``include_pii=False`` (default) redacts location-name/address columns
    per :func:`_event_to_fda_row` (issue #1219).
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FDA_COLUMNS, quoting=csv.QUOTE_ALL)
    writer.writeheader()

    for event in events:
        writer.writerow(_event_to_fda_row(event, include_pii=include_pii))

    return output.getvalue()


def _generate_pdf(
    events: list[dict],
    metadata: dict | None = None,
    *,
    include_pii: bool = False,
) -> bytes:
    """Generate an FDA-compliant PDF report from CTE events.

    Returns PDF file bytes. Uses landscape A4 to accommodate the wide column set.
    Columns are a curated subset of the full FDA_COLUMNS to fit on the page.

    ``include_pii=False`` (default) redacts the ``Location Name`` column
    (the only PII column currently in the PDF subset) per :func:`_event_to_fda_row`
    (issue #1219). The footer also declares whether the PDF contains
    redacted values so a downstream reader sees the PII posture.
    """
    from fpdf import FPDF

    # Subset of columns that fit in landscape A4 at readable font sizes.
    # Full data is in the CSV; the PDF is a human-readable summary.
    PDF_COLUMNS = [
        "Traceability Lot Code (TLC)",
        "Product Description",
        "Event Type (CTE)",
        "Event Date",
        "Quantity",
        "Unit of Measure",
        "Location Name",
        "Record Hash (SHA-256)",
    ]
    COL_WIDTHS = [35, 40, 28, 22, 18, 20, 50, 64]  # mm

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "RegEngine - FDA FSMA 204 Traceability Report", ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    meta = metadata or {}
    generated = meta.get("generated_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    pdf.cell(0, 6, f"Generated: {generated}  |  Records: {len(events)}", ln=True, align="C")
    if meta.get("tlc"):
        pdf.cell(0, 6, f"TLC: {meta['tlc']}", ln=True, align="C")
    pdf.ln(4)

    # Table header
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_fill_color(240, 240, 240)
    for i, col in enumerate(PDF_COLUMNS):
        pdf.cell(COL_WIDTHS[i], 7, col, border=1, fill=True)
    pdf.ln()

    # Table rows — cap at 5000 to prevent memory exhaustion in PDF rendering
    _PDF_MAX_ROWS = 5000
    truncated = len(events) > _PDF_MAX_ROWS
    pdf.set_font("Helvetica", "", 6.5)
    for event in events[:_PDF_MAX_ROWS]:
        row = _event_to_fda_row(event, include_pii=include_pii)
        for i, col in enumerate(PDF_COLUMNS):
            value = str(row.get(col, ""))
            # Truncate hash for readability
            if col == "Record Hash (SHA-256)" and len(value) > 16:
                value = value[:16] + "..."
            # Truncate to fit column width
            max_chars = int(COL_WIDTHS[i] * 0.6)
            if len(value) > max_chars:
                value = value[:max_chars - 1] + "…"
            pdf.cell(COL_WIDTHS[i], 6, value, border=1)
        pdf.ln()

    # Footer with verification info
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 7)
    if truncated:
        pdf.cell(
            0, 5,
            f"WARNING: PDF limited to {_PDF_MAX_ROWS} rows out of {len(events)} total. "
            "Use the CSV or ZIP package export for the complete data set.",
            ln=True,
        )
    # Declare PII posture in the PDF footer (issue #1219) so a downstream
    # reader can tell at a glance whether facility names/addresses were
    # redacted. Auditors receive a version with PII; internal reviewers
    # receive the redacted version by default.
    if include_pii:
        pdf.cell(
            0, 5,
            "PII: This report includes customer facility names and locations. "
            "Handle according to your data-privacy agreements.",
            ln=True,
        )
    else:
        pdf.cell(
            0, 5,
            f"PII: Facility names and locations are redacted to '{PII_REDACTION_PLACEHOLDER}'. "
            "Use GLN / FDA Registration for entity identification.",
            ln=True,
        )
    pdf.cell(
        0, 5,
        "This report was generated by RegEngine. Each record is individually SHA-256 hashed "
        "and chain-verified for tamper detection. For the complete data set including all KDEs, "
        "use the CSV or ZIP package export.",
        ln=True,
    )

    return pdf.output()


def _safe_filename_token(raw: str) -> str:
    """Normalize user-provided identifiers for filenames.

    Thin shim over :func:`shared.fda_export.safe_filename_token` — the
    canonical implementation lives in the EPIC-L shared module so both
    services sanitize identically (#1655).
    """
    return _shared_safe_filename_token(raw)


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
    include_pii: bool = False,
) -> dict:
    """Build JSON payload used for independent package verification.

    ``include_pii`` controls the ``privacy.pii_redacted`` field; it
    should match the flag used to generate ``csv_content`` / the export
    (issue #1219).
    """
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
        # Issue #1219: record PII redaction posture so a chain-verifier can
        # distinguish "CSV with redacted names" from "CSV with full names"
        # when comparing content hashes across exports.
        "privacy": {
            "pii_redacted": not include_pii,
            "redaction_placeholder": PII_REDACTION_PLACEHOLDER,
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
    include_pii: bool = False,
) -> tuple[bytes, dict]:
    """Build zip package bytes and return package metadata.

    ``include_pii`` is recorded in the manifest under
    ``privacy.pii_redacted`` so downstream consumers can tell whether
    the CSV they received has facility names/locations visible or
    redacted. The flag does NOT re-generate ``csv_content``; the caller
    must pass a CSV that was generated with the same ``include_pii``
    setting (issue #1219).
    """
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
    pii_note = (
        f"PII: Facility names and shipping locations are redacted to "
        f"'{PII_REDACTION_PLACEHOLDER}'. Use GLN / FDA Registration for "
        f"entity identification. Re-export with include_pii=true (requires "
        f"fda.export.pii permission) for full values.\n"
        if not include_pii
        else (
            "PII: This export includes facility names and shipping "
            "locations. Handle according to your data-privacy agreements.\n"
        )
    )
    readme_bytes = (
        "RegEngine FDA Traceability Package\n"
        "=================================\n"
        "Contents:\n"
        "1) fda_spreadsheet_*.csv - FDA-sortable traceability rows\n"
        "2) chain_verification_*.json - chain integrity and hash coverage metadata\n"
        "3) manifest.json - package metadata and file checksums\n"
        + ("4) VALIDATION_ERRORS_*.log - KDE validation warnings per event\n" if validation_log else "")
        + "\n"
        + pii_note
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
        # Issue #1219: record PII redaction posture so downstream
        # consumers (auditors, compliance reviewers) can tell whether
        # facility names / shipping addresses are visible in the CSV.
        "privacy": {
            "pii_redacted": not include_pii,
            "redaction_placeholder": PII_REDACTION_PLACEHOLDER,
            "redacted_columns": sorted(_PII_LOCATION_COLUMNS),
            "note": (
                "Facility names and shipping locations are redacted by "
                "default. GLNs and FDA registration numbers remain "
                "visible as the FSMA-204 primary keys."
                if not include_pii
                else (
                    "This export includes facility names and shipping "
                    "locations. Handle according to your data-privacy "
                    "agreements."
                )
            ),
        },
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


def _event_to_fda_row_v2(event: dict, *, include_pii: bool = False) -> dict:
    """Convert a canonical traceability_event row (with rule results) to an FDA spreadsheet row.

    Accepts the same base fields as ``_event_to_fda_row`` plus:
    - ``rule_results``: list[dict] with keys ``rule_name``, ``passed``, ``why_failed``

    ``include_pii`` is forwarded to :func:`_event_to_fda_row` (issue #1219).
    """
    # Reuse the legacy mapper for core FDA columns
    base_row = _event_to_fda_row(event, include_pii=include_pii)

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

    # Sanitize compliance fields — ``why_failed`` reasons can include
    # tenant-controlled KDE values that reach the auditor's spreadsheet.
    base_row["Compliance Status"] = sanitize_cell(compliance_status)
    base_row["Rule Failures"] = sanitize_cell(rule_failures_text)
    # Transformation trace metadata (present when query_events_by_tlc expanded via links)
    base_row["Trace Relationship"] = sanitize_cell(event.get("trace_relationship", "queried"))
    base_row["Trace Seed TLC"] = sanitize_cell(
        event.get("trace_seed_tlc", event.get("traceability_lot_code", ""))
    )
    return base_row


def _generate_csv_v2(events: list[dict], *, include_pii: bool = False) -> str:
    """Generate FDA-compliant CSV from canonical model events (with compliance columns).

    ``csv.QUOTE_ALL`` is used for the same reason as :func:`_generate_csv`
    (issue #1081).

    ``include_pii=False`` (default) redacts location-name/address columns
    per :func:`_event_to_fda_row` (issue #1219).
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FDA_COLUMNS_V2, quoting=csv.QUOTE_ALL)
    writer.writeheader()

    for event in events:
        writer.writerow(_event_to_fda_row_v2(event, include_pii=include_pii))

    return output.getvalue()
