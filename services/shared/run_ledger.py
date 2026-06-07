"""Read-model helpers for the ingestion run receipt ledger."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

SHA256_HEX_PATTERN = r"^[A-Fa-f0-9]{64}$"
SHA256_HEX_RE = re.compile(SHA256_HEX_PATTERN)


class StrictRunLedgerModel(BaseModel):
    """Base model for run-ledger read contracts."""

    model_config = ConfigDict(extra="forbid")


class IngestionRunSummary(StrictRunLedgerModel):
    """Operator-facing summary of an ingestion run."""

    id: str
    source_system: str | None = None
    source_file_name: str | None = None
    source_file_hash: str | None = None
    source_file_size: int | None = None
    record_count: int | None = None
    accepted_count: int | None = None
    rejected_count: int | None = None
    status: str | None = None
    mapper_version: str | None = None
    schema_version: str | None = None
    initiated_by: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    errors: list[Any] = Field(default_factory=list)


class IngestionRunReceipt(StrictRunLedgerModel):
    """One append-only receipt in an ingestion run timeline."""

    receipt_id: str
    sequence_num: int
    state: str
    occurred_at: datetime | None = None
    actor: str | None = None
    request_id: str | None = None
    canonical_event_id: str | None = None
    evidence_attachment_id: str | None = None
    rule_evaluation_id: str | None = None
    export_log_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str
    previous_receipt_hash: str | None = None
    receipt_hash: str
    created_at: datetime | None = None


class ReceiptChainVerification(StrictRunLedgerModel):
    """Result of verifying receipt ordering and hash links."""

    valid: bool
    chain_length: int
    head_receipt_hash: str | None = None
    errors: list[str] = Field(default_factory=list)


class IngestionRunTimeline(StrictRunLedgerModel):
    """Read-only operator view for an ingestion run and its receipt chain."""

    tenant_id: str
    run: IngestionRunSummary
    receipts: list[IngestionRunReceipt]
    verification: ReceiptChainVerification


def verify_receipt_chain(
    receipts: Sequence[IngestionRunReceipt | Mapping[str, Any]],
) -> ReceiptChainVerification:
    """Verify contiguous receipt ordering and previous-hash chaining.

    The database is the source of truth for computing receipt hashes. This
    helper intentionally performs read-side verification only: it checks that
    the stored rows form an ordered, unbroken chain suitable for operator and
    support workflows.
    """

    parsed_receipts: list[IngestionRunReceipt] = []
    errors: list[str] = []
    for position, receipt in enumerate(receipts, start=1):
        try:
            parsed_receipts.append(
                receipt if isinstance(receipt, IngestionRunReceipt) else IngestionRunReceipt.model_validate(receipt)
            )
        except ValidationError as exc:
            errors.append(f"position {position} invalid receipt: {exc.errors()}")

    previous: IngestionRunReceipt | None = None
    for expected_sequence, receipt in enumerate(parsed_receipts, start=1):
        if receipt.sequence_num != expected_sequence:
            errors.append(f"expected sequence {expected_sequence}, got {receipt.sequence_num}")

        if not _is_sha256_hex(receipt.payload_hash):
            errors.append(f"sequence {receipt.sequence_num} payload_hash is not a SHA-256 hex string")
        if not _is_sha256_hex(receipt.receipt_hash):
            errors.append(f"sequence {receipt.sequence_num} receipt_hash is not a SHA-256 hex string")
        if receipt.previous_receipt_hash is not None and not _is_sha256_hex(receipt.previous_receipt_hash):
            errors.append(f"sequence {receipt.sequence_num} previous_receipt_hash is not a SHA-256 hex string")

        if previous is None:
            if receipt.previous_receipt_hash is not None:
                errors.append(f"sequence {receipt.sequence_num} previous_receipt_hash must be null")
        elif receipt.previous_receipt_hash != previous.receipt_hash:
            errors.append(
                "sequence "
                f"{receipt.sequence_num} previous_receipt_hash does not match "
                f"sequence {previous.sequence_num} receipt_hash"
            )

        previous = receipt

    head_hash = parsed_receipts[-1].receipt_hash if parsed_receipts else None
    return ReceiptChainVerification(
        valid=not errors,
        chain_length=len(parsed_receipts),
        head_receipt_hash=head_hash,
        errors=errors,
    )


def fetch_ingestion_run_timeline(
    db_session: Any,
    tenant_id: str,
    run_id: str,
) -> IngestionRunTimeline | None:
    """Fetch an ingestion run and its append-only receipt timeline."""

    run_row = db_session.execute(
        text("""
            SELECT id, source_system, source_file_name, source_file_hash,
                   source_file_size, record_count, accepted_count, rejected_count,
                   status, mapper_version, schema_version, initiated_by,
                   started_at, completed_at, errors
            FROM fsma.ingestion_runs
            WHERE tenant_id = :tid AND id = :rid
        """),
        {"tid": tenant_id, "rid": run_id},
    ).fetchone()

    if not run_row:
        return None

    receipt_rows = db_session.execute(
        text("""
            SELECT receipt_id, sequence_num, state, occurred_at, actor, request_id,
                   canonical_event_id, evidence_attachment_id, rule_evaluation_id,
                   export_log_id, metadata, payload_hash, previous_receipt_hash,
                   receipt_hash, created_at
            FROM fsma.ingestion_run_receipts
            WHERE tenant_id = :tid AND ingestion_run_id = :rid
            ORDER BY sequence_num ASC
        """),
        {"tid": tenant_id, "rid": run_id},
    ).fetchall()

    receipts = [_receipt_from_row(row) for row in receipt_rows]
    return IngestionRunTimeline(
        tenant_id=tenant_id,
        run=_run_from_row(run_row),
        receipts=receipts,
        verification=verify_receipt_chain(receipts),
    )


def _run_from_row(row: Any) -> IngestionRunSummary:
    return IngestionRunSummary(
        id=str(row[0]),
        source_system=row[1],
        source_file_name=row[2],
        source_file_hash=row[3],
        source_file_size=row[4],
        record_count=row[5],
        accepted_count=row[6],
        rejected_count=row[7],
        status=row[8],
        mapper_version=row[9],
        schema_version=row[10],
        initiated_by=row[11],
        started_at=row[12],
        completed_at=row[13],
        errors=_coerce_json_array(row[14]),
    )


def _receipt_from_row(row: Any) -> IngestionRunReceipt:
    return IngestionRunReceipt(
        receipt_id=str(row[0]),
        sequence_num=row[1],
        state=row[2],
        occurred_at=row[3],
        actor=row[4],
        request_id=row[5],
        canonical_event_id=_string_or_none(row[6]),
        evidence_attachment_id=_string_or_none(row[7]),
        rule_evaluation_id=_string_or_none(row[8]),
        export_log_id=_string_or_none(row[9]),
        metadata=_coerce_json_object(row[10]),
        payload_hash=row[11],
        previous_receipt_hash=row[12],
        receipt_hash=row[13],
        created_at=row[14],
    )


def _is_sha256_hex(value: str) -> bool:
    return bool(SHA256_HEX_RE.fullmatch(value))


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _coerce_json_array(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else [parsed]
    return [value]


def _coerce_json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": value}
