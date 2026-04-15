"""
CSV/PDF/ZIP generation logic and response builders for FDA exports.

Extracted from fda_export_router.py — pure structural refactor.
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone

from fastapi.responses import StreamingResponse

from app.fda_export_service import (
    _build_chain_verification_payload,
    _build_completeness_summary,
    _build_fda_package,
    _generate_csv,
    _generate_csv_v2,
    _generate_pdf,
    _safe_filename_token,
)


def generate_csv_and_hash(events: list[dict]) -> tuple[str, str]:
    """Generate FDA-compliant CSV content and its SHA-256 hash."""
    csv_content = _generate_csv(events)
    export_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
    return csv_content, export_hash


def generate_csv_v2_and_hash(events: list[dict]) -> tuple[str, str]:
    """Generate v2 CSV content (with compliance columns) and its SHA-256 hash."""
    csv_content = _generate_csv_v2(events)
    export_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
    return csv_content, export_hash


def build_compliance_headers(
    completeness_summary: dict,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build X-KDE-* and X-Compliance-Warning headers from a completeness summary."""
    kde_coverage = completeness_summary["required_kde_coverage_ratio"]
    kde_warnings = completeness_summary["events_with_missing_required_fields"]
    headers: dict[str, str] = {
        "X-KDE-Coverage": str(kde_coverage),
        "X-KDE-Warnings": str(kde_warnings),
    }
    if kde_coverage < 0.80:
        headers["X-Compliance-Warning"] = "KDE coverage below 80% threshold"
    if extra:
        headers.update(extra)
    return headers


def build_csv_response(
    csv_content: str,
    filename: str,
    export_hash: str,
    record_count: int,
    chain_valid: bool,
    extra_headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """Build a StreamingResponse for a CSV export."""
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "X-Export-Hash": export_hash,
        "X-Record-Count": str(record_count),
        "X-Chain-Integrity": "VERIFIED" if chain_valid else "UNVERIFIED",
    }
    if extra_headers:
        headers.update(extra_headers)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers=headers,
    )


def build_pdf_response(
    events: list[dict],
    metadata: dict,
    filename: str,
    export_hash: str,
    record_count: int,
    chain_valid: bool,
    extra_headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """Build a StreamingResponse for a PDF export."""
    pdf_bytes = _generate_pdf(events, metadata=metadata)
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "X-Export-Hash": export_hash,
        "X-Record-Count": str(record_count),
        "X-Chain-Integrity": "VERIFIED" if chain_valid else "UNVERIFIED",
    }
    if extra_headers:
        headers.update(extra_headers)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=headers,
    )


def build_package_response(
    events: list[dict],
    csv_content: str,
    export_hash: str,
    chain_verification,
    completeness_summary: dict,
    tenant_id: str,
    tlc: str | None,
    start_date: str | None,
    end_date: str | None,
    filename: str,
    extra_headers: dict[str, str] | None = None,
    chain_payload_extras: dict | None = None,
) -> StreamingResponse:
    """Build a StreamingResponse for a ZIP package export."""
    chain_payload = _build_chain_verification_payload(
        tenant_id=tenant_id,
        tlc=tlc,
        events=events,
        csv_hash=export_hash,
        chain_verification=chain_verification,
        completeness_summary=completeness_summary,
    )
    if chain_payload_extras:
        chain_payload.update(chain_payload_extras)

    package_bytes, package_meta = _build_fda_package(
        events=events,
        csv_content=csv_content,
        csv_hash=export_hash,
        chain_payload=chain_payload,
        completeness_summary=completeness_summary,
        tenant_id=tenant_id,
        tlc=tlc,
        query_start_date=start_date,
        query_end_date=end_date,
    )
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "X-Export-Hash": export_hash,
        "X-Package-Hash": package_meta["package_hash"],
        "X-Record-Count": str(len(events)),
        "X-Chain-Integrity": "VERIFIED" if chain_verification.valid else "UNVERIFIED",
    }
    if extra_headers:
        headers.update(extra_headers)
    return StreamingResponse(
        io.BytesIO(package_bytes),
        media_type="application/zip",
        headers=headers,
    )


def make_timestamp() -> str:
    """Return a UTC timestamp string suitable for filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


# Re-export helpers that other modules may need directly
completeness_summary = _build_completeness_summary
safe_filename_token = _safe_filename_token
