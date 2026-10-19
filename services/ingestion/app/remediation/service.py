"""Manifest intake, staging, revalidation, granular release, and metrics.

Preserve before transforming: the exact uploaded bytes land in
fsma.manifest_blobs and a wired fsma.ingestion_runs row carries the
SHA-256. Rows are staged in fsma.manifest_records; only rows that pass
validation are ever appended to the canonical store (persist-on-release),
so one defective line never quarantines its valid siblings.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from shared.canonical_event import IngestionRun, IngestionSource, ProvenanceMetadata, TraceabilityEvent
from shared.canonical_persistence.writer import CanonicalEventStore
from shared.exception_queue import ExceptionQueueService
from shared.tenant_context import set_tenant_guc
from sqlalchemy import text

from ..csv_templates import _normalize_uom, _parse_date_flexible
from . import validation as v
from .audit_utils import audit_event
from .state import transition

logger = logging.getLogger("remediation.service")

MAX_MANIFEST_ROWS = 500
CASE_DUE_HOURS = 72

_CTE_DATE_KDE = {
    "receiving": "receive_date",
    "shipping": "ship_date",
    "harvesting": "harvest_date",
    "cooling": "cooling_date",
    "initial_packing": "packing_date",
    "first_land_based_receiving": "landing_date",
    "transformation": "transformation_date",
}


def _require_uuid_tenant(tenant_id: str) -> str:
    """The remediation slice supports UUID tenants only (RLS-backed tables)."""
    import uuid

    try:
        return str(uuid.UUID(tenant_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="Remediation requires a UUID tenant id",
        )


def _decode_manifest_bytes(raw_bytes: bytes) -> str:
    # utf-8-sig strips a byte-order mark when present and behaves as plain
    # UTF-8 otherwise. Spreadsheet tools (Excel, Sheets exports) commonly
    # prepend a BOM; without this the mark fuses with the first header name
    # and that column silently stops matching, failing the whole manifest.
    # Hashing and byte preservation still use the untouched raw_bytes.
    try:
        return raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Manifest must be UTF-8 encoded CSV")


def ingest_manifest(
    db,
    *,
    tenant_id: str,
    raw_bytes: bytes,
    filename: str,
    content_type: Optional[str],
    uploaded_by: Optional[str],
    supplier_org: str,
) -> Dict[str, Any]:
    tenant_id = _require_uuid_tenant(tenant_id)
    set_tenant_guc(db, tenant_id)

    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    text_content = _decode_manifest_bytes(raw_bytes)

    reader = csv.DictReader(io.StringIO(text_content))
    raw_rows = list(reader)
    if not raw_rows:
        raise HTTPException(status_code=400, detail="Manifest contains no data rows")
    if len(raw_rows) > MAX_MANIFEST_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Manifest exceeds the {MAX_MANIFEST_ROWS}-row limit",
        )

    store = CanonicalEventStore(db)
    run = IngestionRun(
        tenant_id=tenant_id,
        source_system=IngestionSource.CSV_UPLOAD,
        source_file_name=filename,
        source_file_hash=sha256,
        source_file_size=len(raw_bytes),
        record_count=len(raw_rows),
        initiated_by=uploaded_by,
    )
    run_id = store.create_ingestion_run(run)

    db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO fsma.manifest_blobs
                (ingestion_run_id, tenant_id, raw_bytes, sha256,
                 original_filename, content_type, uploaded_by)
            VALUES
                (CAST(:run_id AS uuid), CAST(:tenant_id AS uuid), :raw_bytes,
                 :sha256, :filename, :content_type, :uploaded_by)
            """
        ),
        {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "raw_bytes": raw_bytes,
            "sha256": sha256,
            "filename": filename,
            "content_type": content_type,
            "uploaded_by": uploaded_by,
        },
    )

    # Optional off-box mirror; the bytea row remains the authoritative copy.
    try:
        from ..s3_utils import RAW_INGEST_BUCKET, is_object_storage_configured, put_bytes

        if is_object_storage_configured():
            storage_url = put_bytes(
                RAW_INGEST_BUCKET,
                f"remediation/{tenant_id}/{run_id}/{filename}",
                raw_bytes,
                content_type or "text/csv",
            )
            db.execute(
                # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
                text(
                    """
                    UPDATE fsma.manifest_blobs SET storage_url = :storage_url
                    WHERE ingestion_run_id = CAST(:run_id AS uuid)
                      AND tenant_id = CAST(:tenant_id AS uuid)
                    """
                ),
                {"storage_url": storage_url, "run_id": run_id, "tenant_id": tenant_id},
            )
    except Exception as exc:  # pragma: no cover — mirror is best-effort
        logger.warning("manifest_blob_mirror_failed run=%s error=%s", run_id, exc)

    seen_fingerprints: Dict[str, int] = {}
    records: List[Dict[str, Any]] = []
    passed = failed = 0
    run_errors: List[Dict[str, Any]] = []

    for index, raw_row in enumerate(raw_rows, start=1):
        clean_row = {(k or ""): (val or "") for k, val in raw_row.items()}
        fingerprint = v.row_fingerprint(clean_row)
        event, provenance, service_failures = v.build_event_from_row(clean_row)

        first_seen = seen_fingerprints.get(fingerprint)
        if first_seen is not None:
            service_failures.append(
                v._service_failure(
                    "duplicate_row",
                    field="row",
                    source_column=None,
                    why=f"Row {index} is byte-identical to row {first_seen} in this manifest.",
                    remediation="Remove the duplicate row or correct it to a distinct shipment line.",
                )
            )
        else:
            seen_fingerprints[fingerprint] = index
            if _released_fingerprint_exists(db, tenant_id, fingerprint):
                service_failures.append(
                    v._service_failure(
                        "duplicate_event",
                        field="row",
                        source_column=None,
                        why=f"Row {index} matches a record already released in a previous manifest.",
                        remediation="Do not resubmit already-released records.",
                    )
                )

        alias_failures, alias_applied = v.check_product_alias(db, tenant_id, event)
        service_failures.extend(alias_failures)
        if alias_applied:
            provenance["kdes.product_code"] = {
                **provenance.get("kdes.product_code", {}),
                **alias_applied,
            }

        kde_errors, summary = v.validate_event(event)
        failures, warnings, blocking = v.snapshot_failures(kde_errors, summary, service_failures)

        record_id = _stage_record(
            db,
            tenant_id=tenant_id,
            run_id=run_id,
            row_number=index,
            raw_row=clean_row,
            event=event,
            provenance=provenance,
            fingerprint=fingerprint,
            failures=failures,
            blocking=blocking,
        )

        case_id = None
        exception_case_id = None
        if blocking:
            failed += 1
            case_id, exception_case_id = _open_case(
                db,
                tenant_id=tenant_id,
                record_id=record_id,
                run_id=run_id,
                row_number=index,
                filename=filename,
                supplier_org=supplier_org,
                failures=failures,
                provenance=provenance,
            )
            run_errors.append({"row": index, "issues": [f["issue_id"] for f in failures]})
        else:
            passed += 1

        records.append(
            {
                "record_id": record_id,
                "row_number": index,
                "validation_status": "failed" if blocking else "passed",
                "release_status": "staged",
                "blocking": blocking,
                "failures": failures,
                "warnings": warnings,
                "remediation_case_id": case_id,
                "released_event_id": None,
            }
        )

    store.complete_ingestion_run(run_id, tenant_id, accepted=passed, rejected=failed, errors=run_errors or None)
    audit_event(
        db,
        tenant_id=tenant_id,
        event_type="remediation.manifest.ingest",
        action="remediation.manifest.ingest",
        actor_id=uploaded_by,
        resource_type="ingestion_run",
        resource_id=run_id,
        metadata={"sha256": sha256, "rows": len(raw_rows), "passed": passed, "failed": failed},
    )

    return {
        "ingestion_run_id": run_id,
        "source_sha256": sha256,
        "original_filename": filename,
        "ruleset_hash": v.RULESET_HASH,
        "total_rows": len(raw_rows),
        "passed": passed,
        "failed": failed,
        "records": records,
    }


def _released_fingerprint_exists(db, tenant_id: str, fingerprint: str) -> bool:
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT 1 FROM fsma.manifest_records
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND row_fingerprint = :fingerprint
              AND release_status = 'released'
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "fingerprint": fingerprint},
    ).fetchone()
    return row is not None


def _stage_record(
    db,
    *,
    tenant_id: str,
    run_id: str,
    row_number: int,
    raw_row: Dict[str, Any],
    event: Dict[str, Any],
    provenance: Dict[str, Any],
    fingerprint: str,
    failures: List[Dict[str, Any]],
    blocking: bool,
) -> str:
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO fsma.manifest_records
                (tenant_id, ingestion_run_id, row_number, raw_row,
                 normalized_payload, field_provenance, row_fingerprint,
                 validation_status, rule_failures, ruleset_hash, last_validated_at)
            VALUES
                (CAST(:tenant_id AS uuid), CAST(:run_id AS uuid), :row_number,
                 CAST(:raw_row AS jsonb), CAST(:event AS jsonb),
                 CAST(:provenance AS jsonb), :fingerprint, :validation_status,
                 CAST(:failures AS jsonb), :ruleset_hash, now())
            RETURNING id
            """
        ),
        {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "row_number": row_number,
            "raw_row": json.dumps(raw_row),
            "event": json.dumps(event),
            "provenance": json.dumps(provenance),
            "fingerprint": fingerprint,
            "validation_status": "failed" if blocking else "passed",
            "failures": json.dumps(failures),
            "ruleset_hash": v.RULESET_HASH,
        },
    ).fetchone()
    return str(row[0])


def _open_case(
    db,
    *,
    tenant_id: str,
    record_id: str,
    run_id: str,
    row_number: int,
    filename: str,
    supplier_org: str,
    failures: List[Dict[str, Any]],
    provenance: Dict[str, Any],
) -> tuple:
    """Create the exception case + remediation case for a blocked record."""
    exc_service = ExceptionQueueService(db)
    top_severity = "critical" if any(f["severity"] == "critical" for f in failures) else "warning"
    remediation_text = "\n".join(f"[{f['rule_title']}] {f.get('remediation') or f['why_failed']}" for f in failures)
    import uuid as _uuid

    exception_case = exc_service.create_exception(
        tenant_id=tenant_id,
        severity=top_severity,
        rule_category=failures[0]["category"] if failures else "kde_presence",
        recommended_remediation=remediation_text,
        linked_event_ids=[_uuid.UUID(record_id)],
        source_supplier=supplier_org,
    )
    exception_case_id = str(exception_case.case_id)

    allowed_fields = v.correctable_fields(failures)
    due_at = datetime.now(timezone.utc) + timedelta(hours=CASE_DUE_HOURS)
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO fsma.remediation_cases
                (tenant_id, manifest_record_id, exception_case_id, supplier_org,
                 manifest_ref, line_ref, validation_issue_ids, allowed_fields, due_at)
            VALUES
                (CAST(:tenant_id AS uuid), CAST(:record_id AS uuid),
                 CAST(:exception_case_id AS uuid), :supplier_org, :manifest_ref,
                 :line_ref, CAST(:issue_ids AS jsonb), CAST(:allowed_fields AS jsonb),
                 :due_at)
            RETURNING id
            """
        ),
        {
            "tenant_id": tenant_id,
            "record_id": record_id,
            "exception_case_id": exception_case_id,
            "supplier_org": supplier_org,
            "manifest_ref": filename,
            "line_ref": f"row {row_number}",
            "issue_ids": json.dumps([f["issue_id"] for f in failures]),
            "allowed_fields": json.dumps(allowed_fields),
            "due_at": due_at,
        },
    ).fetchone()
    case_id = str(row[0])

    db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            UPDATE fsma.manifest_records
            SET remediation_case_id = CAST(:case_id AS uuid), updated_at = now()
            WHERE id = CAST(:record_id AS uuid)
              AND tenant_id = CAST(:tenant_id AS uuid)
            """
        ),
        {"case_id": case_id, "record_id": record_id, "tenant_id": tenant_id},
    )

    audit_event(
        db,
        tenant_id=tenant_id,
        event_type="remediation.case.create",
        action="remediation.case.create",
        resource_type="remediation_case",
        resource_id=case_id,
        metadata={
            "manifest_record_id": record_id,
            "ingestion_run_id": run_id,
            "row_number": row_number,
            "issue_ids": [f["issue_id"] for f in failures],
        },
    )

    auto_attempted = any(p.get("source") == "auto_normalization" for p in provenance.values())
    current = "detected"
    if auto_attempted:
        transition(
            db,
            tenant_id=tenant_id,
            case_id=case_id,
            to_status="auto_resolution_attempted",
            expected_from=current,
            actor="system",
        )
        current = "auto_resolution_attempted"
    transition(
        db,
        tenant_id=tenant_id,
        case_id=case_id,
        to_status="supplier_action_required",
        expected_from=current,
        actor="system",
    )
    return case_id, exception_case_id


def load_record(db, *, tenant_id: str, record_id: str) -> Dict[str, Any]:
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT id, ingestion_run_id, row_number, raw_row, normalized_payload,
                   field_provenance, row_fingerprint, validation_status,
                   release_status, released_event_id, remediation_case_id,
                   rule_failures, ruleset_hash
            FROM fsma.manifest_records
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND id = CAST(:record_id AS uuid)
            """
        ),
        {"tenant_id": tenant_id, "record_id": record_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")
    return {
        "id": str(row[0]),
        "ingestion_run_id": str(row[1]),
        "row_number": row[2],
        "raw_row": row[3],
        "normalized_payload": row[4],
        "field_provenance": row[5],
        "row_fingerprint": row[6],
        "validation_status": row[7],
        "release_status": row[8],
        "released_event_id": str(row[9]) if row[9] else None,
        "remediation_case_id": str(row[10]) if row[10] else None,
        "rule_failures": row[11],
        "ruleset_hash": row[12],
    }


def revalidate_record(db, *, tenant_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
    """Re-run validation for one record only (FR-8).

    Every intake check re-runs here — corrections must not be able to
    launder a failure class that only fired at intake. Deterministic
    coercions applied to corrected values are recorded back into
    field_provenance so it never disagrees with the released payload.
    """
    event = record["normalized_payload"]
    provenance = dict(record.get("field_provenance") or {})
    service_failures: List[Dict[str, Any]] = []

    def _coerced(field_path: str, value: Any, rule: str) -> None:
        entry = provenance.get(field_path)
        entry = {**entry} if isinstance(entry, dict) else {"source": "auto_normalization"}
        entry["value"] = value
        entry["rule"] = rule
        provenance[field_path] = entry

    quantity = event.get("quantity")
    if isinstance(quantity, str):
        try:
            parsed = float(quantity)
            if not math.isfinite(parsed):
                raise ValueError("non-finite quantity")
            event["quantity"] = parsed
            _coerced("quantity", parsed, "quantity_cast")
        except (TypeError, ValueError):
            service_failures.append(
                v._service_failure(
                    "invalid_quantity",
                    field="quantity",
                    source_column=None,
                    why=f"Quantity '{quantity}' is not a finite number.",
                    remediation="Provide a positive numeric quantity.",
                )
            )
    if isinstance(event.get("quantity"), float) and event["quantity"] <= 0:
        service_failures.append(
            v._service_failure(
                "invalid_quantity",
                field="quantity",
                source_column=None,
                why=f"Quantity {event['quantity']} must be greater than zero.",
                remediation="Provide a positive numeric quantity.",
            )
        )

    uom = event.get("unit_of_measure")
    if isinstance(uom, str) and uom:
        normalized_uom = _normalize_uom(uom)
        if normalized_uom != uom:
            event["unit_of_measure"] = normalized_uom
            _coerced("unit_of_measure", normalized_uom, "uom_alias")

    timestamp = event.get("timestamp")
    if isinstance(timestamp, str) and timestamp.strip():
        iso_ts, warning = _parse_date_flexible(timestamp)
        if warning is not None:
            service_failures.append(
                v._service_failure(
                    "invalid_date",
                    field="timestamp",
                    source_column=None,
                    why=f"Date '{timestamp}' could not be parsed: {warning}.",
                    remediation="Provide the date as YYYY-MM-DD.",
                )
            )
        elif iso_ts != timestamp:
            event["timestamp"] = iso_ts
            _coerced("timestamp", iso_ts, "date_format")

    for key, value in list((event.get("kdes") or {}).items()):
        if key.endswith("date") and isinstance(value, str) and value.strip():
            iso_ts, warning = _parse_date_flexible(value)
            if warning is not None:
                service_failures.append(
                    v._service_failure(
                        "invalid_date",
                        field=f"kdes.{key}",
                        source_column=None,
                        why=f"Date '{value}' could not be parsed: {warning}.",
                        remediation="Provide the date as YYYY-MM-DD.",
                    )
                )
            elif iso_ts != value:
                event["kdes"][key] = iso_ts
                _coerced(f"kdes.{key}", iso_ts, "date_format")

    tlc = event.get("traceability_lot_code")
    if isinstance(tlc, str) and 0 < len(tlc) < 3:
        service_failures.append(
            v._service_failure(
                "invalid_tlc",
                field="traceability_lot_code",
                source_column=None,
                why=f"Traceability lot code '{tlc}' is too short (minimum 3 characters).",
                remediation="Provide the full traceability lot code (at least 3 characters).",
            )
        )

    # Duplicate findings can never be corrected away: corrections do not
    # touch raw_row, so the fingerprint is unchanged by design.
    dup_row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT row_number FROM fsma.manifest_records
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND ingestion_run_id = CAST(:run_id AS uuid)
              AND row_fingerprint = :fingerprint
              AND row_number < :row_number
            ORDER BY row_number LIMIT 1
            """
        ),
        {
            "tenant_id": tenant_id,
            "run_id": record["ingestion_run_id"],
            "fingerprint": record["row_fingerprint"],
            "row_number": record["row_number"],
        },
    ).fetchone()
    if dup_row:
        service_failures.append(
            v._service_failure(
                "duplicate_row",
                field="row",
                source_column=None,
                why=f"Row {record['row_number']} is byte-identical to row {dup_row[0]} in this manifest.",
                remediation="Remove the duplicate row or correct it to a distinct shipment line.",
            )
        )
    dup_released = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT 1 FROM fsma.manifest_records
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND row_fingerprint = :fingerprint
              AND release_status = 'released'
              AND id != CAST(:record_id AS uuid)
            LIMIT 1
            """
        ),
        {
            "tenant_id": tenant_id,
            "fingerprint": record["row_fingerprint"],
            "record_id": record["id"],
        },
    ).fetchone()
    if dup_released:
        service_failures.append(
            v._service_failure(
                "duplicate_event",
                field="row",
                source_column=None,
                why="This row matches a record already released in a previous manifest.",
                remediation="Do not resubmit already-released records.",
            )
        )

    alias_failures, _applied = v.check_product_alias(db, tenant_id, event)
    service_failures.extend(alias_failures)

    kde_errors, summary = v.validate_event(event)
    failures, warnings, blocking = v.snapshot_failures(kde_errors, summary, service_failures)

    record["field_provenance"] = provenance
    db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            UPDATE fsma.manifest_records
            SET normalized_payload = CAST(:event AS jsonb),
                field_provenance = CAST(:provenance AS jsonb),
                rule_failures = CAST(:failures AS jsonb),
                validation_status = :validation_status,
                ruleset_hash = :ruleset_hash,
                last_validated_at = now(),
                updated_at = now()
            WHERE id = CAST(:record_id AS uuid)
              AND tenant_id = CAST(:tenant_id AS uuid)
            """
        ),
        {
            "event": json.dumps(event),
            "provenance": json.dumps(provenance),
            "failures": json.dumps(failures),
            "validation_status": "failed" if blocking else "passed",
            "ruleset_hash": v.RULESET_HASH,
            "record_id": record["id"],
            "tenant_id": tenant_id,
        },
    )
    audit_event(
        db,
        tenant_id=tenant_id,
        event_type="remediation.revalidate",
        action="remediation.revalidate",
        resource_type="manifest_record",
        resource_id=record["id"],
        metadata={
            "ruleset_hash": v.RULESET_HASH,
            "blocking": blocking,
            "failed_issue_ids": [f["issue_id"] for f in failures],
        },
    )
    return {"blocking": blocking, "failures": failures, "warnings": warnings, "event": event}


def _build_traceability_event(
    tenant_id: str,
    record: Dict[str, Any],
    event: Dict[str, Any],
    cte_type: str,
    kdes: Dict[str, Any],
    event_timestamp: Any,
    source_meta: Dict[str, Any],
    normalization_rules: List[str],
) -> TraceabilityEvent:
    return TraceabilityEvent(
        tenant_id=tenant_id,
        source_system=IngestionSource.CSV_UPLOAD,
        source_record_id=str(record["row_number"]),
        ingestion_run_id=record["ingestion_run_id"],
        event_type=cte_type,
        event_timestamp=event_timestamp,
        traceability_lot_code=event.get("traceability_lot_code", ""),
        product_reference=event.get("product_description"),
        quantity=event.get("quantity"),
        unit_of_measure=event.get("unit_of_measure", ""),
        from_entity_reference=kdes.get("immediate_previous_source"),
        from_facility_reference=event.get("location_gln")
        or kdes.get("ship_from_location")
        or event.get("location_name"),
        to_facility_reference=kdes.get("ship_to_location") or kdes.get("receiving_location"),
        kdes=kdes,
        raw_payload=record["raw_row"],
        provenance_metadata=ProvenanceMetadata(
            source_file_hash=source_meta.get("sha256"),
            source_file_name=source_meta.get("filename"),
            mapper_name="supplier_remediation_csv",
            mapper_version="1.0.0",
            normalization_rules_applied=normalization_rules,
            original_format="csv",
        ),
    )


def release_record(db, *, tenant_id: str, record: Dict[str, Any], source_meta: Dict[str, Any]) -> str:
    """Append one validated record to the canonical store and mark it released."""
    event = record["normalized_payload"]
    cte_type = event.get("cte_type", "")
    kdes = event.get("kdes") or {}
    event_timestamp = event.get("timestamp") or kdes.get(_CTE_DATE_KDE.get(cte_type, ""), None)
    if not event_timestamp:
        raise HTTPException(status_code=409, detail="Record has no event timestamp; cannot release")

    normalization_rules = sorted(
        {p["rule"] for p in (record["field_provenance"] or {}).values() if isinstance(p, dict) and p.get("rule")}
    )
    from pydantic import ValidationError

    try:
        te = _build_traceability_event(
            tenant_id, record, event, cte_type, kdes, event_timestamp, source_meta, normalization_rules
        )
    except ValidationError as exc:
        # Validation and the canonical model should agree; if they ever
        # drift, fail closed with an intelligible 409 instead of a 500
        # that rolls back the supplier's patch mid-request.
        raise HTTPException(
            status_code=409,
            detail=f"Record failed canonical validation and stays blocked: {str(exc)[:400]}",
        )
    store = CanonicalEventStore(db)
    result = store.persist_event(te)
    if not result.success:
        raise HTTPException(status_code=502, detail=f"Canonical persistence failed: {result.errors}")
    event_id = str(result.event_id)

    db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            UPDATE fsma.manifest_records
            SET release_status = 'released',
                released_event_id = CAST(:event_id AS uuid),
                updated_at = now()
            WHERE id = CAST(:record_id AS uuid)
              AND tenant_id = CAST(:tenant_id AS uuid)
            """
        ),
        {"event_id": event_id, "record_id": record["id"], "tenant_id": tenant_id},
    )
    audit_event(
        db,
        tenant_id=tenant_id,
        event_type="remediation.release",
        action="remediation.release",
        resource_type="manifest_record",
        resource_id=record["id"],
        metadata={"released_event_id": event_id, "row_number": record["row_number"]},
    )
    return event_id


def get_run_meta(db, *, tenant_id: str, run_id: str) -> Dict[str, Any]:
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT b.sha256, b.original_filename, b.raw_bytes, r.status,
                   r.record_count, r.accepted_count, r.rejected_count
            FROM fsma.manifest_blobs b
            JOIN fsma.ingestion_runs r ON r.id = b.ingestion_run_id
            WHERE b.ingestion_run_id = CAST(:run_id AS uuid)
              AND b.tenant_id = CAST(:tenant_id AS uuid)
              AND r.tenant_id = CAST(:tenant_id AS uuid)
            """
        ),
        {"run_id": run_id, "tenant_id": tenant_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Manifest not found")
    return {
        "sha256": row[0],
        "filename": row[1],
        "raw_bytes": bytes(row[2]),
        "run_status": row[3],
        "record_count": row[4],
        "accepted_count": row[5],
        "rejected_count": row[6],
    }


def list_run_records(db, *, tenant_id: str, run_id: str) -> List[Dict[str, Any]]:
    rows = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT id FROM fsma.manifest_records
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND ingestion_run_id = CAST(:run_id AS uuid)
            ORDER BY row_number ASC
            """
        ),
        {"tenant_id": tenant_id, "run_id": run_id},
    ).fetchall()
    return [load_record(db, tenant_id=tenant_id, record_id=str(r[0])) for r in rows]


def list_runs(db, *, tenant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Manifest submissions for the buyer view (FR-9), newest first."""
    rows = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT b.ingestion_run_id, b.original_filename, b.sha256, r.status,
                   r.record_count, r.started_at, r.completed_at,
                   COALESCE(agg.passed_staged, 0), COALESCE(agg.blocked, 0),
                   COALESCE(agg.released, 0)
            FROM fsma.manifest_blobs b
            JOIN fsma.ingestion_runs r ON r.id = b.ingestion_run_id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) FILTER (WHERE m.validation_status = 'passed'
                                          AND m.release_status = 'staged') AS passed_staged,
                       COUNT(*) FILTER (WHERE m.validation_status = 'failed'
                                          AND m.release_status = 'staged') AS blocked,
                       COUNT(*) FILTER (WHERE m.release_status = 'released') AS released
                FROM fsma.manifest_records m
                WHERE m.tenant_id = CAST(:tenant_id AS uuid)
                  AND m.ingestion_run_id = b.ingestion_run_id
            ) agg ON TRUE
            WHERE b.tenant_id = CAST(:tenant_id AS uuid)
              AND r.tenant_id = CAST(:tenant_id AS uuid)
            ORDER BY b.created_at DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "limit": limit},
    ).fetchall()
    return [
        {
            "ingestion_run_id": str(r[0]),
            "original_filename": r[1],
            "source_sha256": r[2],
            "run_status": r[3],
            "total_rows": r[4],
            "started_at": r[5].isoformat() if r[5] else None,
            "completed_at": r[6].isoformat() if r[6] else None,
            "ready_to_release": r[7],
            "blocked": r[8],
            "released": r[9],
            # Display-only data hold (Product Principle 7): blocked rows are
            # withheld from export/release; no fees, rejections, or threats.
            "data_hold": r[8] > 0,
        }
        for r in rows
    ]


def list_run_cases(db, *, tenant_id: str, run_id: str) -> Dict[str, Dict[str, Any]]:
    """Remediation-case status keyed by manifest_record_id, for the buyer view."""
    rows = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT c.manifest_record_id, c.id, c.status, c.due_at,
                   EXISTS (
                       SELECT 1 FROM fsma.notification_outbox n
                       WHERE n.tenant_id = CAST(:tenant_id AS uuid) AND n.case_id = c.id
                   ) AS notified
            FROM fsma.remediation_cases c
            WHERE c.tenant_id = CAST(:tenant_id AS uuid)
              AND c.manifest_record_id IN (
                  SELECT m.id FROM fsma.manifest_records m
                  WHERE m.tenant_id = CAST(:tenant_id AS uuid)
                    AND m.ingestion_run_id = CAST(:run_id AS uuid)
              )
            """
        ),
        {"tenant_id": tenant_id, "run_id": run_id},
    ).fetchall()
    return {
        str(r[0]): {
            "case_id": str(r[1]),
            "case_status": r[2],
            "due_at": r[3].isoformat() if r[3] else None,
            "notified": bool(r[4]),
        }
        for r in rows
    }


def compute_metrics(db, *, tenant_id: str) -> Dict[str, Any]:
    def _scalar(sql: str, **params) -> Any:
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        return db.execute(text(sql), {"tenant_id": tenant_id, **params}).scalar() or 0

    total_records = _scalar("SELECT COUNT(*) FROM fsma.manifest_records WHERE tenant_id = CAST(:tenant_id AS uuid)")
    first_pass = _scalar(
        """
        SELECT COUNT(*) FROM fsma.manifest_records m
        WHERE m.tenant_id = CAST(:tenant_id AS uuid)
          AND m.validation_status = 'passed'
          AND NOT EXISTS (
              SELECT 1 FROM fsma.correction_patches p
              WHERE p.tenant_id = CAST(:tenant_id AS uuid) AND p.manifest_record_id = m.id
          )
        """
    )
    cases_total = _scalar("SELECT COUNT(*) FROM fsma.remediation_cases WHERE tenant_id = CAST(:tenant_id AS uuid)")
    cases_released = _scalar(
        """
        SELECT COUNT(*) FROM fsma.remediation_cases
        WHERE tenant_id = CAST(:tenant_id AS uuid) AND status = 'released'
        """
    )
    supplier_resolved = _scalar(
        """
        SELECT COUNT(*) FROM fsma.remediation_cases c
        WHERE c.tenant_id = CAST(:tenant_id AS uuid)
          AND c.status = 'released'
          AND EXISTS (
              SELECT 1 FROM fsma.correction_patches p
              WHERE p.tenant_id = CAST(:tenant_id AS uuid) AND p.case_id = c.id
          )
          AND NOT EXISTS (
              SELECT 1 FROM fsma.correction_patches p
              WHERE p.tenant_id = CAST(:tenant_id AS uuid) AND p.case_id = c.id
                AND p.auth_method != 'remediation_token'
          )
        """
    )
    corrections_submitted = _scalar(
        "SELECT COUNT(*) FROM fsma.correction_patches WHERE tenant_id = CAST(:tenant_id AS uuid)"
    )
    auto_normalized = _scalar(
        """
        SELECT COUNT(*) FROM fsma.manifest_records
        WHERE tenant_id = CAST(:tenant_id AS uuid)
          AND field_provenance::text LIKE '%auto_normalization%'
        """
    )
    median_seconds = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT EXTRACT(EPOCH FROM percentile_cont(0.5)
                   WITHIN GROUP (ORDER BY updated_at - created_at))
            FROM fsma.remediation_cases
            WHERE tenant_id = CAST(:tenant_id AS uuid) AND status = 'released'
            """
        ),
        {"tenant_id": tenant_id},
    ).scalar()

    exceptions_by_rule: Dict[str, int] = {}
    rows = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT f->>'rule_id' AS rule_id, COUNT(*)
            FROM fsma.manifest_records m,
                 jsonb_array_elements(m.rule_failures) AS f
            WHERE m.tenant_id = CAST(:tenant_id AS uuid)
            GROUP BY 1 ORDER BY 2 DESC
            """
        ),
        {"tenant_id": tenant_id},
    ).fetchall()
    for r in rows:
        exceptions_by_rule[r[0]] = r[1]

    return {
        "total_records_processed": total_records,
        "first_pass_acceptance_rate": (first_pass / total_records) if total_records else None,
        "exceptions_by_rule": exceptions_by_rule,
        "auto_normalized_records": auto_normalized,
        "supplier_action_cases": cases_total,
        "supplier_corrections_submitted": corrections_submitted,
        "cases_released": cases_released,
        "resolved_without_buyer_intervention": supplier_resolved,
        "resolved_without_buyer_intervention_rate": (supplier_resolved / cases_total) if cases_total else None,
        "median_remediation_seconds": float(median_seconds) if median_seconds is not None else None,
        # Not yet instrumented — zero is the PRD-sanctioned initial value,
        # but consumers must not read these as measured.
        "false_blocks": 0,
        "mapping_reversals": 0,
        "not_yet_instrumented": ["false_blocks", "mapping_reversals"],
    }
