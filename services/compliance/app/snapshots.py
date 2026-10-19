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

The content hash is sha256 over the canonical JSON of the sealed payload.
The format is versioned, and the version is part of the digested payload:

* **v2** (current, #2966) covers the identity fields (tenant_id,
  snapshot_name, snapshot_reason, created_by, captured_at), the captured
  compliance posture (compliance_status, active_alert_count,
  critical_alert_count, trigger_alert_id, is_auto_created, deadline,
  regulatory_citation) and the attestation (is_attested, attested_by,
  attested_at, attestation_title). ``attest`` re-seals the row, so a
  directly-written attestation no longer verifies.
* **v1** (legacy) covered the five identity fields only. Rows frozen
  before #2966 still carry a v1 digest; ``verify`` falls back to it so no
  historical evidence is invalidated by the format change. Their digests
  are never rewritten in place — a backfill would be forging a seal over
  values that were never sealed.

``snapshot_state`` and ``degradation_reason`` are deliberately **outside**
the digest: they are record-lifecycle fields that legitimate writes mutate
after the freeze (refreeze marks the prior row SUPERSEDED), so sealing them
would break the seal on correct behaviour.

``verify`` recomputes the digest from the stored row, so any post-freeze
tampering with a sealed field flips ``hash_match`` / ``integrity_verified``
to false. Every surface that prints ``Integrity Verified`` also prints
which seal version produced it and what that version covers.

The freeze reads the tenant's live alert posture and writes it explicitly
(#2931). It is fail-closed: if that read fails, the row records
``UNKNOWN`` / not-captured rather than inheriting the DDL's
``DEFAULT 'COMPLIANT'`` / ``DEFAULT 0`` clean bill of health, and every
export renders "NOT CAPTURED".
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
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

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

_STATE_EMOJI = {"VALID": "🟢", "STALE": "🟠", "INVALID": "🔴", "SUPERSEDED": "⚪"}
_STATUS_EMOJI = {"COMPLIANT": "✅", "AT_RISK": "⚠️", "NON_COMPLIANT": "🚨"}

_STATE_SUPERSEDED = "SUPERSEDED"

# #2931: stored sentinels for "the posture could not be measured". The v103
# columns are NOT NULL (DEFAULT 'COMPLIANT' / 0), so a failed read cannot be
# written as NULL — it is written as UNKNOWN / -1 instead, and every render
# path turns that into "NOT CAPTURED". What must never happen is a failed or
# absent measurement being indistinguishable from a clean bill of health.
_STATUS_UNKNOWN = "UNKNOWN"
_COUNT_NOT_CAPTURED = -1

# Rendered (never stored) status for a row whose posture is not trustworthy:
# never measured, measurement failed, or the seal that covered it is broken.
_STATUS_NOT_CAPTURED = "NOT_CAPTURED"
_NOT_CAPTURED_TEXT = "NOT CAPTURED"

_POSTURE_UNREADABLE_REASON = (
    "#2931: compliance posture could not be read at capture — recorded as NOT CAPTURED rather than assumed compliant"
)
_LEGACY_POSTURE_REASON = (
    "#2931/#2966: frozen under the v1 seal, which never captured a compliance "
    "posture — the posture columns held DDL defaults and are recorded as NOT CAPTURED"
)

# Alert severities that count as critical. Deliberately wider than the two
# values the current writers emit ('critical' / 'warning'): for an evidence
# record, over-counting critical is the safe direction.
_CRITICAL_SEVERITIES = ("critical", "fatal", "severe", "high")

# Seal format. The version is digested along with the payload, so a v1 and a
# v2 digest of the same row can never collide by construction.
_HASH_VERSION = 2

# Order is part of the wire format — json.dumps preserves insertion order.
_V2_SEALED_FIELDS = (
    "tenant_id",
    "snapshot_name",
    "snapshot_reason",
    "created_by",
    "captured_at",
    "compliance_status",
    "active_alert_count",
    "critical_alert_count",
    "trigger_alert_id",
    "is_auto_created",
    "deadline",
    "regulatory_citation",
    "is_attested",
    "attested_by",
    "attested_at",
    "attestation_title",
)

_SEAL_COVERAGE = {
    2: "identity, captured compliance posture and attestation",
    1: ("identity fields only; compliance posture and attestation are NOT sealed (legacy v1 seal)"),
}

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


def _as_int(value: Any, default: int = 0) -> int:
    return default if value is None else int(value)


def _content_hash_v1(
    tenant_id: str,
    snapshot_name: str,
    snapshot_reason: Optional[str],
    created_by: str,
    captured_at_iso: str,
) -> str:
    """LEGACY seal format — identity fields only.

    Frozen byte-for-byte: rows written before #2966 carry this digest and must
    keep verifying. Nothing computes it any more; ``_seal_version`` only falls
    back to it so historical evidence is not invalidated by the widening.
    """
    payload: dict[str, str] = {"tenant_id": tenant_id, "snapshot_name": snapshot_name}
    if snapshot_reason is not None:
        payload["snapshot_reason"] = snapshot_reason
    payload["created_by"] = created_by
    payload["captured_at"] = captured_at_iso
    canonical = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _content_hash_v2(sealed: Mapping[str, Any]) -> str:
    """#2966: canonical digest over the whole evidentiary payload.

    Key order (``_V2_SEALED_FIELDS``), None-omission and the ``hash_version``
    prefix are part of the format — verify() recomputes with the same shape.
    The version is inside the digest so a v1 and a v2 payload can never
    produce the same hash for the same row.
    """
    payload: dict[str, Any] = {"hash_version": _HASH_VERSION}
    for field in _V2_SEALED_FIELDS:
        value = sealed.get(field)
        if value is None:
            continue
        payload[field] = value
    canonical = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sealed_values(source: Mapping[str, Any]) -> dict[str, Any]:
    """Normalise a DB row (or a to-be-inserted value dict) into the sealed
    payload. Driver differences — SQLite ints for booleans, ISO text for
    timestamps — are flattened here so Postgres and SQLite digest identically.
    """
    deadline = _as_dt(source.get("deadline"))
    attested_at = _as_dt(source.get("attested_at"))
    return {
        "tenant_id": str(source["tenant_id"]),
        "snapshot_name": source["snapshot_name"],
        "snapshot_reason": source.get("snapshot_reason"),
        "created_by": source["created_by"],
        "captured_at": _iso(_as_dt(source["captured_at"])),
        "compliance_status": source.get("compliance_status"),
        "active_alert_count": _as_int(source.get("active_alert_count")),
        "critical_alert_count": _as_int(source.get("critical_alert_count")),
        "trigger_alert_id": source.get("trigger_alert_id"),
        "is_auto_created": bool(source.get("is_auto_created")),
        "deadline": _iso(deadline) if deadline else None,
        "regulatory_citation": source.get("regulatory_citation"),
        "is_attested": bool(source.get("is_attested")),
        "attested_by": source.get("attested_by"),
        "attested_at": _iso(attested_at) if attested_at else None,
        "attestation_title": source.get("attestation_title"),
    }


def _seal_version(row: Mapping[str, Any]) -> Optional[int]:
    """Which seal format the stored hash was produced under, or None if the
    row verifies under neither (i.e. it was tampered with).

    v2 is tried first; the v1 fallback is what keeps pre-#2966 rows valid.
    """
    stored = row["content_hash"]
    if _content_hash_v2(_sealed_values(row)) == stored:
        return _HASH_VERSION
    legacy = _content_hash_v1(
        tenant_id=str(row["tenant_id"]),
        snapshot_name=row["snapshot_name"],
        snapshot_reason=row["snapshot_reason"],
        created_by=row["created_by"],
        captured_at_iso=_iso(_as_dt(row["captured_at"])),
    )
    return 1 if legacy == stored else None


def _derive_status(active_count: int, critical_count: int) -> str:
    if critical_count > 0:
        return "NON_COMPLIANT"
    if active_count > 0:
        return "AT_RISK"
    return "COMPLIANT"


def _not_captured_posture(reason: str) -> dict[str, Any]:
    return {
        "compliance_status": _STATUS_UNKNOWN,
        "active_alert_count": _COUNT_NOT_CAPTURED,
        "critical_alert_count": _COUNT_NOT_CAPTURED,
        "degradation_reason": reason,
    }


def _capture_posture(db: Any, tenant_id: str) -> dict[str, Any]:
    """#2931: read the tenant's live alert posture so the freeze records what
    the posture *was*, instead of leaving the evidentiary columns to their DDL
    defaults.

    Fail-closed (same rule as compliance_score.py): a read error must never
    look like "zero alerts" — that would be the system fabricating a clean
    bill of health onto a regulator-facing document. The failed statement
    aborts the surrounding transaction on Postgres, so the rollback here is
    what lets the INSERT that follows still run.
    """
    try:
        row = (
            db.execute(
                text(
                    "SELECT COUNT(*) AS active_count, "
                    "SUM(CASE WHEN lower(severity) IN :critical THEN 1 ELSE 0 END) AS critical_count "
                    "FROM fsma.compliance_alerts "
                    "WHERE tenant_id = :tid "
                    "AND (resolved IS NULL OR resolved = false)"
                ).bindparams(bindparam("critical", expanding=True)),
                {"tid": tenant_id, "critical": list(_CRITICAL_SEVERITIES)},
            )
            .mappings()
            .first()
        )
    except SQLAlchemyError as exc:
        _logger.error("compliance_snapshot: posture read failed, freezing NOT CAPTURED: %s", exc)
        db.rollback()
        return _not_captured_posture(_POSTURE_UNREADABLE_REASON)

    active = _as_int(row["active_count"]) if row else 0
    critical = _as_int(row["critical_count"]) if row else 0
    return {
        "compliance_status": _derive_status(active, critical),
        "active_alert_count": active,
        "critical_alert_count": critical,
        "degradation_reason": None,
    }


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

    seal_version = _seal_version(row)
    snapshot_state = row["snapshot_state"]

    # #2931/#2966: the posture is only reportable as a captured fact when a v2
    # seal actually covers it. A v1 row predates posture capture (its columns
    # are DDL defaults), a broken seal means the values cannot be trusted, and
    # the UNKNOWN/-1 sentinels mean the read failed at capture time. All three
    # render as NOT CAPTURED rather than as "COMPLIANT / 0 active, 0 critical".
    active_count = _as_int(row["active_alert_count"])
    critical_count = _as_int(row["critical_alert_count"])
    posture_captured = (
        seal_version == _HASH_VERSION
        and row["compliance_status"] != _STATUS_UNKNOWN
        and active_count >= 0
        and critical_count >= 0
    )
    compliance_status = row["compliance_status"] if posture_captured else _STATUS_NOT_CAPTURED

    # #2964: an attestation dated before the capture it signs is incoherent by
    # construction. Append-only refreeze means no handler produces one; this
    # flag catches a direct write that did.
    attestation_precedes_capture = attested_at is not None and attested_at < captured

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
        "attestation_precedes_capture": attestation_precedes_capture,
        "compliance_status": compliance_status,
        "compliance_status_emoji": _STATUS_EMOJI.get(compliance_status, "❓"),
        "active_alert_count": active_count if posture_captured else None,
        "critical_alert_count": critical_count if posture_captured else None,
        "posture_captured": posture_captured,
        "content_hash": row["content_hash"],
        "integrity_verified": seal_version is not None,
        "hash_version": seal_version,
        "integrity_coverage": _SEAL_COVERAGE.get(seal_version),
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
            text("SELECT " + _COLUMNS + " FROM " + _TABLE + " WHERE tenant_id = :tid AND id = :sid"),
            {"tid": tenant_id, "sid": str(snapshot_id)},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return row


# ---------------------------------------------------------------------------
# Auditor-facing rendering (#2966: every claim states what backs it)
# ---------------------------------------------------------------------------


def _integrity_line(serialized: Mapping[str, Any]) -> str:
    """The seal flag never stands alone: it names the format it was verified
    under and what that format covers, so a reader cannot mistake it for a
    guarantee over values it does not sign."""
    if not serialized["integrity_verified"]:
        return "No"
    return f"Yes — seal v{serialized['hash_version']} covers {serialized['integrity_coverage']}"


def _status_line(serialized: Mapping[str, Any]) -> str:
    if not serialized["posture_captured"]:
        return _NOT_CAPTURED_TEXT
    return f"{serialized['compliance_status_emoji']} {serialized['compliance_status']}"


def _count_line(value: Optional[int]) -> str:
    return _NOT_CAPTURED_TEXT if value is None else str(value)


def _attestation_line(serialized: Mapping[str, Any]) -> str:
    if not serialized["is_attested"]:
        return "No"
    if serialized["attestation_precedes_capture"]:
        # #2964: refuse to present a sign-off dated before the content it signs.
        return "INVALID — attested_at precedes captured_at"
    return "Yes"


def _insert_snapshot(
    db: Any,
    *,
    snapshot_id: UUID,
    tenant_id: str,
    snapshot_name: str,
    snapshot_reason: Optional[str],
    created_by: str,
    captured_iso: str,
    posture: Mapping[str, Any],
) -> None:
    """Write one frozen evidence row, sealed over the values being written.

    The digest is computed from the same dict that is bound to the INSERT, so
    the seal can never drift from the stored row. Columns this handler does not
    write (trigger_alert_id, deadline, regulatory_citation, the attestation
    quartet) hash as their DDL defaults; the round-trip is checked immediately
    because the caller re-reads the row and re-verifies it.
    """
    values = {
        "tenant_id": tenant_id,
        "snapshot_name": snapshot_name,
        "snapshot_reason": snapshot_reason,
        "created_by": created_by,
        "captured_at": captured_iso,
        "compliance_status": posture["compliance_status"],
        "active_alert_count": posture["active_alert_count"],
        "critical_alert_count": posture["critical_alert_count"],
    }
    db.execute(
        text(
            "INSERT INTO " + _TABLE + " "
            "(id, tenant_id, snapshot_name, snapshot_reason, created_by, "
            "compliance_status, active_alert_count, critical_alert_count, "
            "degradation_reason, content_hash, captured_at) "
            "VALUES (:id, :tid, :name, :reason, :created_by, :status, "
            ":active, :critical, :degradation, :hash, :captured_at)"
        ),
        {
            "id": str(snapshot_id),
            "tid": tenant_id,
            "name": snapshot_name,
            "reason": snapshot_reason,
            "created_by": created_by,
            "status": posture["compliance_status"],
            "active": posture["active_alert_count"],
            "critical": posture["critical_alert_count"],
            "degradation": posture["degradation_reason"],
            "hash": _content_hash_v2(_sealed_values(values)),
            "captured_at": captured_iso,
        },
    )


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
            text("SELECT " + _COLUMNS + " FROM " + _TABLE + " WHERE tenant_id = :tid ORDER BY captured_at DESC"),
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
    # #2931: measure the posture BEFORE the INSERT, in the same transaction, and
    # write it explicitly. The evidentiary columns used to be left to the v103
    # DDL defaults ('COMPLIANT' / 0 / 0), so every audit pack asserted a clean
    # bill of health no tenant had earned.
    posture = _capture_posture(db, ctx.tenant_id)
    _insert_snapshot(
        db,
        snapshot_id=snapshot_id,
        tenant_id=ctx.tenant_id,
        snapshot_name=payload.snapshot_name,
        snapshot_reason=payload.snapshot_reason,
        created_by=payload.created_by,
        captured_iso=captured_iso,
        posture=posture,
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
    seal_version = _seal_version(row)
    hash_match = seal_version is not None
    # #2966: report the current-format digest. A v1 row matches on the fallback,
    # so ``computed_hash`` is only meaningful to compare against ``stored_hash``
    # when hash_version is 2 — hence hash_version travels with the verdict.
    computed = row["content_hash"] if seal_version == 1 else _content_hash_v2(_sealed_values(row))
    return {
        "is_valid": hash_match,
        "stored_hash": row["content_hash"],
        "computed_hash": computed,
        "hash_match": hash_match,
        "hash_version": seal_version,
        "hash_coverage": _SEAL_COVERAGE.get(seal_version),
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
    row = _fetch_snapshot(db, ctx.tenant_id, snapshot_id)
    if row["snapshot_state"] == _STATE_SUPERSEDED:
        # Append-only evidence (#2964): a superseded freeze is history. Its
        # seal must keep covering the content that was actually frozen, so a
        # fresh sign-off cannot be attached to it after a refreeze.
        raise HTTPException(
            status_code=409,
            detail="Snapshot has been superseded; attest its successor instead",
        )
    seal_version = _seal_version(row)
    if seal_version is None:
        # #2966: attesting re-seals the row, so signing a record that already
        # fails verification would launder the tampered values into a valid
        # seal. A human cannot vouch for content whose integrity check fails.
        raise HTTPException(
            status_code=409,
            detail="Snapshot failed integrity verification; refusing to attest",
        )

    sealed = _sealed_values(row)
    sealed.update(
        {
            "is_attested": True,
            "attested_by": payload.attested_by,
            "attested_at": _iso(_now()),
            "attestation_title": payload.attestation_title,
        }
    )
    degradation_reason = row["degradation_reason"]
    if seal_version != _HASH_VERSION:
        # #2931/#2966: a legacy v1 row was frozen before posture capture
        # existed, so its posture columns hold DDL defaults that were never
        # measured. Re-sealing them as-is would promote a default into a
        # hash-covered "captured" fact — record the honest sentinel instead.
        sealed["compliance_status"] = _STATUS_UNKNOWN
        sealed["active_alert_count"] = _COUNT_NOT_CAPTURED
        sealed["critical_alert_count"] = _COUNT_NOT_CAPTURED
        degradation_reason = _LEGACY_POSTURE_REASON

    # #2966: the attestation is inside the seal, so recording it re-seals the
    # row. That is what makes a directly-written attestation detectable — the
    # old handler wrote the four attestation columns with no hash recomputation
    # at all, leaving a forged sign-off indistinguishable from a real one.
    db.execute(
        text(
            "UPDATE " + _TABLE + " "
            "SET is_attested = :attested, "
            "attested_by = :attested_by, "
            "attestation_title = :title, "
            "attested_at = :attested_at, "
            "compliance_status = :status, "
            "active_alert_count = :active, "
            "critical_alert_count = :critical, "
            "degradation_reason = :degradation, "
            "content_hash = :hash "
            "WHERE tenant_id = :tid AND id = :sid"
        ),
        {
            "attested": True,
            "attested_by": payload.attested_by,
            "title": payload.attestation_title,
            "attested_at": sealed["attested_at"],
            "status": sealed["compliance_status"],
            "active": sealed["active_alert_count"],
            "critical": sealed["critical_alert_count"],
            "degradation": degradation_reason,
            "hash": _content_hash_v2(sealed),
            "tid": ctx.tenant_id,
            "sid": str(snapshot_id),
        },
    )
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
    """Re-capture a snapshot as a NEW evidence row, superseding the prior one.

    #2964: this used to UPDATE the existing row in place — new created_by, new
    hash, new captured_at — while leaving is_attested / attested_by /
    attested_at / attestation_title untouched. A snapshot attested on day 1
    could be re-captured on day 30 and still export as "Attested: Yes" under
    that person's name, with attested_at *earlier* than captured_at, and
    /verify reporting hash_match true because the hash was recomputed from the
    new content. The prior freeze's hash and timestamp were retained nowhere.

    Append-only fixes all of that: the attestation stays attached to the
    content it actually signed, and the original freeze remains retrievable.
    """
    db = _require_db(db)
    row = _fetch_snapshot(db, ctx.tenant_id, snapshot_id)
    if _seal_version(row) is None:
        # Same rule as attest: re-freezing copies the stored name and reason
        # into a new sealed row, so re-freezing a tampered row would launder
        # attacker text under a fresh valid hash. Refuse, fail closed.
        raise HTTPException(
            status_code=409,
            detail="Snapshot failed integrity verification; refusing to refreeze",
        )
    if row["snapshot_state"] == _STATE_SUPERSEDED:
        raise HTTPException(
            status_code=409,
            detail="Snapshot has already been superseded; re-freeze its successor instead",
        )

    created_by = (payload.created_by if payload else None) or row["created_by"]
    captured_iso = _iso(_now())
    new_id = uuid4()
    posture = _capture_posture(db, ctx.tenant_id)
    _insert_snapshot(
        db,
        snapshot_id=new_id,
        tenant_id=ctx.tenant_id,
        snapshot_name=row["snapshot_name"],
        snapshot_reason=row["snapshot_reason"],
        created_by=created_by,
        captured_iso=captured_iso,
        posture=posture,
    )
    # Forward pointer on the superseded row. snapshot_state and
    # degradation_reason sit outside the digest precisely so this legitimate
    # write cannot break the prior freeze's seal.
    db.execute(
        text(
            "UPDATE " + _TABLE + " "
            "SET snapshot_state = :state, degradation_reason = :reason "
            "WHERE tenant_id = :tid AND id = :sid"
        ),
        {
            "state": _STATE_SUPERSEDED,
            "reason": f"Superseded by snapshot {new_id} re-captured at {captured_iso}",
            "tid": ctx.tenant_id,
            "sid": str(snapshot_id),
        },
    )
    _audit_logger.info(
        "compliance_snapshot_refrozen",
        extra={
            "tenant_id": ctx.tenant_id,
            "snapshot_id": str(new_id),
            "superseded_snapshot_id": str(snapshot_id),
            "actor": created_by,
        },
    )
    return {
        **_serialize(_fetch_snapshot(db, ctx.tenant_id, new_id)),
        "supersedes_snapshot_id": str(snapshot_id),
    }


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
        # #2966: the consumer renders a PDF from this — it needs to know which
        # seal produced the flag and what that seal covers, not just Yes/No.
        "hash_version": serialized["hash_version"],
        "integrity_coverage": serialized["integrity_coverage"],
        "compliance_status": serialized["compliance_status"],
        "compliance_status_emoji": serialized["compliance_status_emoji"],
        "active_alert_count": serialized["active_alert_count"],
        "critical_alert_count": serialized["critical_alert_count"],
        "posture_captured": serialized["posture_captured"],
        "snapshot_state": serialized["snapshot_state"],
        "state_emoji": serialized["state_emoji"],
        "is_attested": serialized["is_attested"],
        "attested_by": serialized["attested_by"],
        "attested_at": serialized["attested_at"],
        "attestation_title": serialized["attestation_title"],
        "attestation_precedes_capture": serialized["attestation_precedes_capture"],
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
            f"Integrity Verified: {_integrity_line(serialized)}",
            f"Compliance Status: {_status_line(serialized)}",
            f"Active Alerts: {_count_line(serialized['active_alert_count'])}",
            f"Critical Alerts: {_count_line(serialized['critical_alert_count'])}",
            f"Attested: {_attestation_line(serialized)}",
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
        f"Compliance Status: {_status_line(serialized)}",
        f"Integrity Verified: {_integrity_line(serialized)}",
        f"Attested: {_attestation_line(serialized)}",
        f"Reason: {serialized['snapshot_reason'] or 'Not provided'}",
        "",
        "Summary:",
        "This compliance snapshot captures the point-in-time control state supplied for regulatory review.",
    ]
    # #2931: never assert "0 active, 0 critical" for a posture that was never
    # measured — say so instead.
    if serialized["posture_captured"]:
        lines.append(
            f"Alerts recorded at capture: {serialized['active_alert_count']} active, "
            f"{serialized['critical_alert_count']} critical."
        )
    else:
        lines.append(f"Alerts recorded at capture: {_NOT_CAPTURED_TEXT}.")
    return {"text": "\n".join(lines)}
