"""Read-only, bounded supplier-file preview using the canonical CSV parser.

No event is persisted, accepted, corrected, or assigned here. Only allowlisted
aggregate observations may leave the process for optional semantic review.
"""

from __future__ import annotations

import csv
import io
import itertools
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .authz import IngestionPrincipal, require_permission
from .shared.tenant_resolution import resolve_principal_tenant_id
from .shared.upload_limits import MAX_CSV_FILE_SIZE_BYTES, read_upload_with_limit
from .shared.xlsx_rows import is_xlsx_upload, reject_unsupported_excel, xlsx_to_csv_text
from .webhook_models import REQUIRED_KDES_BY_CTE

router = APIRouter()
MAX_REVIEW_CLUSTERS = 8
_REASONS = frozenset(
    {
        "bad_date",
        "bad_input_quantities",
        "bad_quantity",
        "blank_row",
        "comment_row",
        "cte_type_from_upload",
        "date_guessed",
        "duplicate_column",
        "extra_fields",
        "header_guess_applied",
        "location_normalized",
        "mapped_cte_not_recognized",
        "missing_column",
        "missing_cte_type",
        "missing_header",
        "missing_quantity",
        "missing_required_columns",
        "missing_unit_of_measure",
        "parse_exception",
        "row_limit_exceeded",
        "row_limit_overflow",
        "unit_normalized",
        "unknown_cte_type",
        "unreadable_csv",
        "unreadable_overflow_tail",
        "unrecognized_column",
        "missing_kde",
    }
)
_FIELDS = frozenset({field for fields in REQUIRED_KDES_BY_CTE.values() for field in fields}) | {
    "cte_type",
    "location_gln",
    "timestamp",
    "input_lot_codes",
    "input_quantities",
    "input_units_of_measure",
}


class DiagnosticIssue(BaseModel):
    cluster_id: str
    reason: str
    field: Optional[str] = None
    disposition: Literal["rejected", "flagged", "skipped"]
    row_indices: list[int]
    affected_row_count: int
    file_level: bool
    semantic_review: dict[str, Any] = Field(default_factory=lambda: {"status": "not_requested"})


class PilotDiagnosticResponse(BaseModel):
    status: Literal["preview"] = "preview"
    input_format: Literal["csv", "xlsx"]
    row_index_basis: Literal["csv_record_index_including_header", "converted_xlsx_record_index_including_header"]
    row_limit: int
    parsed_record_count: int
    valid_event_count: int
    rejected_record_count: int
    skipped_record_count: int
    unparsed_record_count: int
    parse_error_count: int
    workbook_warning_count: int
    issues: list[DiagnosticIssue]
    semantic_review: dict[str, Any]
    automatic_assignment_enabled: Literal[False] = False
    persisted_event_count: Literal[0] = 0
    regulatory_completeness: Literal["not_determined"] = "not_determined"


def _parse_preview(text: str, fallback_cte: Optional[str]) -> tuple[dict[str, Any], list[str]]:
    # Import lazily: csv_templates registers this router after defining the parser.
    from . import csv_templates as ct

    try:
        count = len(list(itertools.islice(csv.DictReader(io.StringIO(text)), ct.MAX_CSV_ROWS + 1)))
    except (csv.Error, UnicodeError):
        raise HTTPException(status_code=400, detail="File is not a readable CSV") from None
    if count > ct.MAX_CSV_ROWS:
        raise HTTPException(status_code=413, detail=f"Diagnostic preview accepts at most {ct.MAX_CSV_ROWS} records")

    row_log: list = []
    source_rows: list[int] = []
    events, errors, _warnings = ct.parse_csv_rows(text, fallback_cte, row_log=row_log, event_source_rows=source_rows)
    grouped: dict[tuple[str, Optional[str], str, bool], set[int]] = {}

    def add(reason: str, field: Optional[str], disposition: str, row: int) -> None:
        safe_reason = reason if reason in _REASONS else "unclassified_parser_issue"
        safe_field = field if field in _FIELDS else None
        key = (safe_reason, safe_field, disposition, row < 2)
        grouped.setdefault(key, set()).update([row] if row >= 2 else [])

    for entry in row_log:
        if entry.disposition in {"rejected", "flagged", "skipped"}:
            add(entry.reason, entry.field, entry.disposition, entry.row_number)
    for row, event in zip(source_rows, events):
        for field in ct._validate_kde_completeness(event.cte_type.value, event, event.kdes):
            add("missing_kde", field, "flagged", row)
    if errors and not grouped:
        add("unclassified_parser_issue", None, "rejected", 0)

    issues = [
        DiagnosticIssue(
            cluster_id=f"issue_{i}",
            reason=reason,
            field=field,
            disposition=disposition,
            row_indices=sorted(rows),
            affected_row_count=len(rows),
            file_level=file_level,
        )
        for i, ((reason, field, disposition, file_level), rows) in enumerate(grouped.items(), start=1)
    ]
    rejected = {e.row_number for e in row_log if e.disposition == "rejected" and e.row_number >= 2}
    skipped = {e.row_number for e in row_log if e.disposition == "skipped" and e.row_number >= 2}
    return {
        "row_limit": ct.MAX_CSV_ROWS,
        "parsed_record_count": count,
        "valid_event_count": len(events),
        "rejected_record_count": len(rejected),
        "skipped_record_count": len(skipped),
        "unparsed_record_count": max(0, count - len(events) - len(rejected) - len(skipped)),
        "parse_error_count": len(errors),
        "issues": issues,
    }, sorted({event.cte_type.value for event in events})


def _review_state(issue: DiagnosticIssue, count: int, cte_types: list[str], limit: int) -> dict[str, Any]:
    """Build new aggregate data; never forward parser text or uploaded values."""
    return {
        "pilot_scope": {"total_parsed_rows": count, "parser_row_limit": limit},
        "source_completeness": {"included_cte_types": cte_types, "full_operational_history_available": False},
        "error_cluster": {
            "cluster_id": issue.cluster_id,
            "affected_row_count": issue.affected_row_count,
            "parser_disposition": issue.disposition,
            "issue_reason": issue.reason,
            "field": issue.field,
            "homogeneity_verified": False,
            "deterministic_prechecks": {
                "missing_required_columns": [issue.field] if issue.reason == "missing_column" and issue.field else [],
                "blank_kde_fields_in_cluster": [issue.field] if issue.reason == "missing_kde" and issue.field else [],
            },
        },
        "evidence_context": {"records": [], "confirmed_remediation_steps": [], "customer_confirmed_owner_role": None},
    }


@router.post(
    "/ingest/csv/diagnostic",
    response_model=PilotDiagnosticResponse,
    summary="Preview supplier-file issues without ingestion",
)
async def preview_pilot_diagnostic(
    file: UploadFile = File(...),
    cte_type: Optional[str] = Form(default=None),
    tenant_id: Optional[str] = Form(default=None),
    sheet_name: Optional[str] = Form(default=None),
    semantic_review: bool = Form(
        default=False, description="Opt in to aggregate-only Jev review; never assigns owners"
    ),
    principal: IngestionPrincipal = Depends(require_permission("webhooks.ingest")),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> PilotDiagnosticResponse:
    resolve_principal_tenant_id(tenant_id, x_tenant_id, principal.tenant_id)
    from . import csv_templates as ct

    fallback_cte = None
    if cte_type:
        fallback_cte = ct._CTE_TYPE_ALIASES.get(cte_type.strip().lower().replace(" ", "_"))
        if fallback_cte is None:
            raise HTTPException(status_code=400, detail="Unknown CTE type")
    try:
        reject_unsupported_excel(file.filename, file.content_type)
        content = await read_upload_with_limit(file, max_bytes=MAX_CSV_FILE_SIZE_BYTES, label="Diagnostic file")
        is_xlsx = is_xlsx_upload(file.filename, file.content_type, content)
        if is_xlsx:
            text, workbook_warnings = await run_in_threadpool(
                xlsx_to_csv_text,
                content,
                sheet_name=sheet_name,
                max_data_rows=ct.MAX_CSV_ROWS,
                reject_on_scan_limit=True,
            )
        else:
            text, workbook_warnings = content.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded") from None
    except HTTPException as exc:
        # Workbook errors can contain arbitrary worksheet names or header text.
        raise HTTPException(
            status_code=exc.status_code, detail="File could not be read within the supported format and size limits"
        ) from None

    parsed, cte_types = await run_in_threadpool(_parse_preview, text, fallback_cte)
    attempted = reviewed = 0
    if semantic_review:
        from shared.jev.review_policy import review_pilot_diagnostic

        stop_reason = "cluster_limit"
        for issue in parsed["issues"][:MAX_REVIEW_CLUSTERS]:
            attempted += 1
            result = await review_pilot_diagnostic(
                _review_state(issue, parsed["parsed_record_count"], cte_types, parsed["row_limit"])
            )
            issue.semantic_review = result
            reviewed += result.get("status") == "review"
            if result.get("status") == "unavailable":
                stop_reason = "provider_unavailable"
                break
        for issue in parsed["issues"][attempted:]:
            issue.semantic_review = {
                "status": "unreviewed",
                "reason": stop_reason,
            }
    return PilotDiagnosticResponse(
        **parsed,
        input_format="xlsx" if is_xlsx else "csv",
        row_index_basis="converted_xlsx_record_index_including_header"
        if is_xlsx
        else "csv_record_index_including_header",
        workbook_warning_count=len(workbook_warnings),
        semantic_review={
            "requested": semantic_review,
            "cluster_limit": MAX_REVIEW_CLUSTERS,
            "attempted_cluster_count": attempted,
            "reviewed_cluster_count": reviewed,
            "omitted_cluster_count": max(0, len(parsed["issues"]) - attempted) if semantic_review else 0,
            "unreviewed_cluster_count": len(parsed["issues"]) - reviewed,
        },
    )
