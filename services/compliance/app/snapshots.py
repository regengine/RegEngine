"""Compliance Snapshots API — the real backend for the snapshots UI.

The frontend (frontend/src/app/compliance/snapshots/page.tsx) proxies
``/api/v1/compliance/snapshots/...`` to
``${COMPLIANCE_URL}/v1/compliance/snapshots/{tenant_id}...``; until now only
the dev-only in-memory fallback (frontend/src/lib/dev-compliance-snapshots.ts)
answered. This router implements that contract against
``fsma.compliance_evidence_snapshots`` (migration v101).

Tenant binding: the authenticated principal is the sole source of tenant
truth (``resolve_tenant_context``). The ``{tenant_id}`` path segment is
never trusted — the dependency 409s (E_TENANT_MISMATCH) when it disagrees
with the principal, and every query filters on the authenticated tenant.
RLS (``tenant_id = get_tenant_context()``, FORCE) is the DB-layer backstop;
the GUC is applied per-transaction by the #2461 begin-hook seeded from
``resolve_tenant_context``.

The content hash is sha256 over the canonical JSON of the identity fields
(tenant_id, snapshot_name, snapshot_reason, created_by, captured_at) —
the same shape the dev fallback used. ``verify`` recomputes it from the
stored row, so any post-freeze tampering with those fields flips
``hash_match`` / ``integrity_verified`` to false.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from shared.auth import require_api_key
from shared.database import get_db_session
from shared.tenant_context import TenantContext, resolve_tenant_context
from sqlalchemy import text

_logger = logging.getLogger(__name__)
_audit_logger = logging.getLogger("compliance-audit")

_TABLE = "fsma.compliance_evidence_snapshots"

_COLUMNS = (
    "id, tenant_id, snapshot_name, snapshot_reason, created_by, "
    "trigger_alert_id, is_auto_created, deadline, regulatory_citation, "
    "is_attested, attested_by, attested_at, attestation_title, "
    "compliance_status, active_alert_count, critical_alert_count, "
    "content_hash, snapshot_state, degradation_reason, captured_at"
)

_STATE_EMOJI = {"VALID": "🟢", "STALE": "🟠", "INVALID": "🔴"}
_STATUS_EMOJI = {"COMPLIANT": "✅", "AT_RISK": "⚠️", "NON_COMPLIANT": "🚨"}

router = APIRouter(prefix="/v1/compliance/snapshots", tags=["Compliance Snapshots"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SnapshotCreateRequest(BaseModel):
    snapshot_name: str = Field(min_length=1, max_length=200)
    snapshot_reason: Optional[str] = Field(None, max_length=2000)
    created_by: str = Field(min_length=1, max_length=320)


class SnapshotAttestRequest(BaseModel):
    attested_by: str = Field(min_length=1, max_length=320)
    attestation_title: str = Field(min_length=1, max_length=200)


class SnapshotRefreezeRequest(BaseModel):
    created_by: Optional[str] = Field(None, max_length=320)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _as_dt(value: Any) -> Optional[datetime]:
    """Coerce a driver value (datetime from Postgres, ISO text from SQLite)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value))


def _content_hash(
    tenant_id: str,
    snapshot_name: str,
    snapshot_reason: Optional[str],
    created_by: str,
    captured_at_iso: str,
) -> str:
    """Canonical identity hash. Key order and None-omission are part of the
    format — verify() recomputes with the same shape."""
    payload: dict[str, str] = {"tenant_id": tenant_id, "snapshot_name": snapshot_name}
    if snapshot_reason is not None:
        payload["snapshot_reason"] = snapshot_reason
    payload["created_by"] = created_by
    payload["captured_at"] = captured_at_iso
    canonical = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _row_hash(row: Mapping[str, Any]) -> str:
    captured = _as_dt(row["captured_at"])
    return _content_hash(
        tenant_id=str(row["tenant_id"]),
        snapshot_name=row["snapshot_name"],
        snapshot_reason=row["snapshot_reason"],
        created_by=row["created_by"],
        captured_at_iso=_iso(captured),
    )


def _countdown_display(seconds: int) -> str:
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _serialize(row: Mapping[str, Any]) -> dict[str, Any]:
    now = _now()
    captured = _as_dt(row["captured_at"])
    attested_at = _as_dt(row["attested_at"])
    deadline = _as_dt(row["deadline"])

    countdown_seconds: Optional[int] = None
    countdown_display: Optional[str] = None
    if deadline is not None:
        countdown_seconds = max(0, int((deadline - now).total_seconds()))
        countdown_display = _countdown_display(countdown_seconds)

    compliance_status = row["compliance_status"]
    snapshot_state = row["snapshot_state"]
    return {
        "id": str(row["id"]),
        "tenant_id": str(row["tenant_id"]),
        "snapshot_name": row["snapshot_name"],
        "snapshot_reason": row["snapshot_reason"],
        "created_by": row["created_by"],
        "trigger_alert_id": row["trigger_alert_id"],
        "is_auto_created": bool(row["is_auto_created"]),
        "deadline": _iso(deadline) if deadline else None,
        "countdown_seconds": countdown_seconds,
        "countdown_display": countdown_display,
        "regulatory_citation": row["regulatory_citation"],
        "is_attested": bool(row["is_attested"]),
        "attested_by": row["attested_by"],
        "attested_at": _iso(attested_at) if attested_at else None,
        "attestation_title": row["attestation_title"],
        "compliance_status": compliance_status,
        "compliance_status_emoji": _STATUS_EMOJI.get(compliance_status, "❓"),
        "active_alert_count": row["active_alert_count"],
        "critical_alert_count": row["critical_alert_count"],
        "content_hash": row["content_hash"],
        "integrity_verified": _row_hash(row) == row["content_hash"],
        "snapshot_state": snapshot_state,
        "state_emoji": _STATE_EMOJI.get(snapshot_state, "❓"),
        "age_hours": round(max(0.0, (now - captured).total_seconds() / 3600.0), 1),
        "degradation_reason": row["degradation_reason"],
        "captured_at": _iso(captured),
    }


def _require_db(db: Any) -> Any:
    if db is None:
        # Rule of the service: refuse rather than fabricate (fail-closed,
        # mirrors routes.py /validate).
        raise HTTPException(status_code=503, detail="Database unavailable")
    return db


def _fetch_snapshot(db: Any, tenant_id: str, snapshot_id: UUID) -> Mapping[str, Any]:
    row = (
        db.execute(
            text(f"SELECT {_COLUMNS} FROM {_TABLE} WHERE tenant_id = :tid AND id = :sid"),
            {"tid": tenant_id, "sid": str(snapshot_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return row


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}", dependencies=[Depends(require_api_key)])
def list_snapshots(
    tenant_id: UUID,
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Any = Depends(get_db_session),
) -> dict[str, Any]:
    """List the tenant's snapshots, newest capture first."""
    db = _require_db(db)
    rows = (
        db.execute(
            text(f"SELECT {_COLUMNS} FROM {_TABLE} WHERE tenant_id = :tid ORDER BY captured_at DESC"),
            {"tid": ctx.tenant_id},
        )
        .mappings()
        .all()
    )
    return {"items": [_serialize(row) for row in rows]}


@router.post("/{tenant_id}", dependencies=[Depends(require_api_key)], status_code=201)
def create_snapshot(
    tenant_id: UUID,
    payload: SnapshotCreateRequest,
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Any = Depends(get_db_session),
) -> dict[str, Any]:
    """Freeze a new manual snapshot."""
    db = _require_db(db)
    snapshot_id = uuid4()
    captured_iso = _iso(_now())
    content_hash = _content_hash(
        tenant_id=ctx.tenant_id,
        snapshot_name=payload.snapshot_name,
        snapshot_reason=payload.snapshot_reason,
        created_by=payload.created_by,
        captured_at_iso=captured_iso,
    )
    db.execute(
        text(
            f"""
            INSERT INTO {_TABLE}
                (id, tenant_id, snapshot_name, snapshot_reason, created_by,
                 content_hash, captured_at)
            VALUES
                (:id, :tid, :name, :reason, :created_by, :hash, :captured_at)
            """
        ),
        {
            "id": str(snapshot_id),
            "tid": ctx.tenant_id,
            "name": payload.snapshot_name,
            "reason": payload.snapshot_reason,
            "created_by": payload.created_by,
            "hash": content_hash,
            "captured_at": captured_iso,
        },
    )
    _audit_logger.info(
        "compliance_snapshot_created",
        extra={"tenant_id": ctx.tenant_id, "snapshot_id": str(snapshot_id), "actor": payload.created_by},
    )
    return _serialize(_fetch_snapshot(db, ctx.tenant_id, snapshot_id))


@router.get("/{tenant_id}/diff", dependencies=[Depends(require_api_key)])
def diff_snapshots(
    tenant_id: UUID,
    snapshot_a: UUID = Query(...),
    snapshot_b: UUID = Query(...),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Any = Depends(get_db_session),
) -> dict[str, Any]:
    """Compare two snapshots of the same tenant."""
    db = _require_db(db)
    left = _fetch_snapshot(db, ctx.tenant_id, snapshot_a)
    right = _fetch_snapshot(db, ctx.tenant_id, snapshot_b)

    changes: list[dict[str, str]] = []
    if left["snapshot_name"] != right["snapshot_name"]:
        changes.append(
            {
                "label": "Snapshot Name",
                "before": left["snapshot_name"],
                "after": right["snapshot_name"],
                "severity": "info",
            }
        )
    if (left["snapshot_reason"] or "") != (right["snapshot_reason"] or ""):
        changes.append(
            {
                "label": "Snapshot Reason",
                "before": left["snapshot_reason"] or "-",
                "after": right["snapshot_reason"] or "-",
                "severity": "info",
            }
        )
    if left["content_hash"] != right["content_hash"]:
        changes.append(
            {
                "label": "Content Hash",
                "before": left["content_hash"][:12],
                "after": right["content_hash"][:12],
                "severity": "positive",
            }
        )

    return {
        "snapshot_a": {"name": left["snapshot_name"]},
        "snapshot_b": {"name": right["snapshot_name"]},
        "changes": changes,
    }


@router.get("/{tenant_id}/{snapshot_id}/verify", dependencies=[Depends(require_api_key)])
def verify_snapshot(
    tenant_id: UUID,
    snapshot_id: UUID,
    verified_by: str = Query("unknown", max_length=320),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Any = Depends(get_db_session),
) -> dict[str, Any]:
    """Recompute the content hash and compare against the frozen one."""
    db = _require_db(db)
    row = _fetch_snapshot(db, ctx.tenant_id, snapshot_id)
    computed = _row_hash(row)
    hash_match = computed == row["content_hash"]
    return {
        "is_valid": hash_match,
        "stored_hash": row["content_hash"],
        "computed_hash": computed,
        "hash_match": hash_match,
        "verified_by": verified_by,
        "verified_at": _iso(_now()),
    }


@router.post("/{tenant_id}/{snapshot_id}/attest", dependencies=[Depends(require_api_key)])
def attest_snapshot(
    tenant_id: UUID,
    snapshot_id: UUID,
    payload: SnapshotAttestRequest,
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Any = Depends(get_db_session),
) -> dict[str, Any]:
    """Record a human attestation on a snapshot."""
    db = _require_db(db)
    result = db.execute(
        text(
            f"""
            UPDATE {_TABLE}
               SET is_attested = :attested,
                   attested_by = :attested_by,
                   attestation_title = :title,
                   attested_at = :attested_at
             WHERE tenant_id = :tid AND id = :sid
            """
        ),
        {
            "attested": True,
            "attested_by": payload.attested_by,
            "title": payload.attestation_title,
            "attested_at": _iso(_now()),
            "tid": ctx.tenant_id,
            "sid": str(snapshot_id),
        },
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    _audit_logger.info(
        "compliance_snapshot_attested",
        extra={"tenant_id": ctx.tenant_id, "snapshot_id": str(snapshot_id), "actor": payload.attested_by},
    )
    return _serialize(_fetch_snapshot(db, ctx.tenant_id, snapshot_id))


@router.post("/{tenant_id}/{snapshot_id}/refreeze", dependencies=[Depends(require_api_key)])
def refreeze_snapshot(
    tenant_id: UUID,
    snapshot_id: UUID,
    payload: Optional[SnapshotRefreezeRequest] = None,
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Any = Depends(get_db_session),
) -> dict[str, Any]:
    """Re-capture a snapshot: new timestamp, new hash, state back to VALID."""
    db = _require_db(db)
    row = _fetch_snapshot(db, ctx.tenant_id, snapshot_id)
    created_by = (payload.created_by if payload else None) or row["created_by"]
    captured_iso = _iso(_now())
    content_hash = _content_hash(
        tenant_id=ctx.tenant_id,
        snapshot_name=row["snapshot_name"],
        snapshot_reason=row["snapshot_reason"],
        created_by=created_by,
        captured_at_iso=captured_iso,
    )
    db.execute(
        text(
            f"""
            UPDATE {_TABLE}
               SET created_by = :created_by,
                   content_hash = :hash,
                   captured_at = :captured_at,
                   snapshot_state = 'VALID',
                   degradation_reason = NULL
             WHERE tenant_id = :tid AND id = :sid
            """
        ),
        {
            "created_by": created_by,
            "hash": content_hash,
            "captured_at": captured_iso,
            "tid": ctx.tenant_id,
            "sid": str(snapshot_id),
        },
    )
    _audit_logger.info(
        "compliance_snapshot_refrozen",
        extra={"tenant_id": ctx.tenant_id, "snapshot_id": str(snapshot_id), "actor": created_by},
    )
    return _serialize(_fetch_snapshot(db, ctx.tenant_id, snapshot_id))


@router.get("/{tenant_id}/{snapshot_id}/export", dependencies=[Depends(require_api_key)])
def export_snapshot(
    tenant_id: UUID,
    snapshot_id: UUID,
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Any = Depends(get_db_session),
) -> dict[str, Any]:
    """Structured export payload (the frontend renders it into a PDF)."""
    db = _require_db(db)
    row = _fetch_snapshot(db, ctx.tenant_id, snapshot_id)
    serialized = _serialize(row)
    return {
        "snapshot_id": serialized["id"],
        "tenant_id": serialized["tenant_id"],
        "snapshot_name": serialized["snapshot_name"],
        "snapshot_reason": serialized["snapshot_reason"],
        "created_by": serialized["created_by"],
        "captured_at": serialized["captured_at"],
        "export_date": _iso(_now()),
        "content_hash": serialized["content_hash"],
        "integrity_verified": serialized["integrity_verified"],
        "compliance_status": serialized["compliance_status"],
        "compliance_status_emoji": serialized["compliance_status_emoji"],
        "active_alert_count": serialized["active_alert_count"],
        "critical_alert_count": serialized["critical_alert_count"],
        "snapshot_state": serialized["snapshot_state"],
        "state_emoji": serialized["state_emoji"],
        "is_attested": serialized["is_attested"],
        "attested_by": serialized["attested_by"],
        "attested_at": serialized["attested_at"],
        "attestation_title": serialized["attestation_title"],
    }


@router.get("/{tenant_id}/{snapshot_id}/audit-pack", dependencies=[Depends(require_api_key)])
def audit_pack(
    tenant_id: UUID,
    snapshot_id: UUID,
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Any = Depends(get_db_session),
) -> PlainTextResponse:
    """Plain-text audit pack download."""
    db = _require_db(db)
    row = _fetch_snapshot(db, ctx.tenant_id, snapshot_id)
    serialized = _serialize(row)
    body = "\n".join(
        [
            "RegEngine Zero-Trust Audit Pack",
            "",
            f"Snapshot Name: {serialized['snapshot_name']}",
            f"Snapshot ID: {serialized['id']}",
            f"Tenant ID: {serialized['tenant_id']}",
            f"Captured At: {serialized['captured_at']}",
            f"Created By: {serialized['created_by']}",
            f"Content Hash: {serialized['content_hash']}",
            f"Integrity Verified: {'Yes' if serialized['integrity_verified'] else 'No'}",
            f"Compliance Status: {serialized['compliance_status_emoji']} {serialized['compliance_status']}",
            f"Active Alerts: {serialized['active_alert_count']}",
            f"Critical Alerts: {serialized['critical_alert_count']}",
            f"Reason: {serialized['snapshot_reason'] or 'Not provided'}",
        ]
    )
    # snapshot_id is a validated UUID path param — safe in the header value.
    return PlainTextResponse(
        body,
        headers={
            "Content-Disposition": f'attachment; filename="ZeroTrust-AuditPack-{snapshot_id}.txt"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{tenant_id}/{snapshot_id}/fda-response", dependencies=[Depends(require_api_key)])
def fda_response(
    tenant_id: UUID,
    snapshot_id: UUID,
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Any = Depends(get_db_session),
) -> dict[str, str]:
    """FDA response template pre-filled from the snapshot."""
    db = _require_db(db)
    row = _fetch_snapshot(db, ctx.tenant_id, snapshot_id)
    serialized = _serialize(row)
    lines = [
        "FDA Response Template",
        "",
        f"Snapshot Name: {serialized['snapshot_name']}",
        f"Snapshot ID: {serialized['id']}",
        f"Captured At: {serialized['captured_at']}",
        f"Prepared By: {serialized['created_by']}",
        f"Compliance Status: {serialized['compliance_status_emoji']} {serialized['compliance_status']}",
        f"Integrity Verified: {'Yes' if serialized['integrity_verified'] else 'No'}",
        f"Attested: {'Yes' if serialized['is_attested'] else 'No'}",
        f"Reason: {serialized['snapshot_reason'] or 'Not provided'}",
        "",
        "Summary:",
        "This compliance snapshot captures the point-in-time control state supplied for regulatory review.",
        f"Alerts recorded at capture: {serialized['active_alert_count']} active, "
        f"{serialized['critical_alert_count']} critical.",
    ]
    return {"text": "\n".join(lines)}
