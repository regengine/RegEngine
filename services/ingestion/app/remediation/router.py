"""Buyer-facing remediation endpoints (authenticated).

Tenant context comes only from the authenticated principal via
resolve_tenant (never from body/header for scoped principals), matching
exception_router.py conventions.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from shared.database import get_db_session
from shared.tenant_context import set_tenant_guc
from sqlalchemy import text

from ..authz import IngestionPrincipal, require_permission
from ..shared.upload_limits import MAX_CSV_FILE_SIZE_BYTES, read_upload_with_limit
from ..tenant_validation import resolve_tenant
from . import evidence, outbox, service, tokens
from .audit_utils import audit_event
from .schemas import CreateLinkRequest, CreateLinkResponse, ManifestUploadResponse, ReleaseRequest
from .state import transition

logger = logging.getLogger("remediation.router")

router = APIRouter(prefix="/api/v1/remediation", tags=["Supplier Remediation"])

_get_db_session = get_db_session  # test-override alias, mirrors exception_router


def _db(db_session):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return db_session


@router.post("/manifests", response_model=ManifestUploadResponse, summary="Upload a supplier CSV manifest")
async def upload_manifest(
    file: UploadFile = File(...),
    supplier_org: str = Form(...),
    tenant_id: Optional[str] = Form(default=None),
    principal: IngestionPrincipal = Depends(require_permission("remediation.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    db = _db(db_session)
    raw = await read_upload_with_limit(file, max_bytes=MAX_CSV_FILE_SIZE_BYTES, label="manifest CSV")
    result = service.ingest_manifest(
        db,
        tenant_id=tid,
        raw_bytes=raw,
        filename=file.filename or "manifest.csv",
        content_type=file.content_type,
        uploaded_by=principal.principal_id if hasattr(principal, "principal_id") else None,
        supplier_org=supplier_org,
    )
    return result


@router.get("/manifests", summary="List manifest submissions (buyer view)")
async def list_manifests(
    tenant_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    principal: IngestionPrincipal = Depends(require_permission("remediation.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    db = _db(db_session)
    tid = service._require_uuid_tenant(tid)
    set_tenant_guc(db, tid)
    return {"manifests": service.list_runs(db, tenant_id=tid, limit=limit)}


@router.get("/manifests/{run_id}", summary="Manifest status with per-row results")
async def get_manifest(
    run_id: str,
    tenant_id: Optional[str] = Query(default=None),
    principal: IngestionPrincipal = Depends(require_permission("remediation.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    db = _db(db_session)
    tid = service._require_uuid_tenant(tid)
    set_tenant_guc(db, tid)
    meta = service.get_run_meta(db, tenant_id=tid, run_id=run_id)
    records = service.list_run_records(db, tenant_id=tid, run_id=run_id)
    cases = service.list_run_cases(db, tenant_id=tid, run_id=run_id)
    return {
        "ingestion_run_id": run_id,
        "source_sha256": meta["sha256"],
        "original_filename": meta["filename"],
        "run_status": meta["run_status"],
        "counts": {
            "total": meta["record_count"],
            "accepted": meta["accepted_count"],
            "rejected": meta["rejected_count"],
        },
        "records": [
            {
                "record_id": r["id"],
                "row_number": r["row_number"],
                "validation_status": r["validation_status"],
                "release_status": r["release_status"],
                "released_event_id": r["released_event_id"],
                "remediation_case_id": r["remediation_case_id"],
                "case": cases.get(r["id"]),
                "failures": r["rule_failures"],
                "field_provenance": r["field_provenance"],
            }
            for r in records
        ],
    }


@router.get("/manifests/{run_id}/original", summary="Download the preserved original bytes")
async def get_original(
    run_id: str,
    tenant_id: Optional[str] = Query(default=None),
    principal: IngestionPrincipal = Depends(require_permission("remediation.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    db = _db(db_session)
    tid = service._require_uuid_tenant(tid)
    set_tenant_guc(db, tid)
    meta = service.get_run_meta(db, tenant_id=tid, run_id=run_id)
    return Response(
        content=meta["raw_bytes"],
        media_type="text/csv",
        headers={
            "X-Source-SHA256": meta["sha256"],
            "Content-Disposition": f'attachment; filename="{meta["filename"]}"',
        },
    )


@router.post("/manifests/{run_id}/release", summary="Release passing rows into the canonical store")
async def release_manifest(
    run_id: str,
    request: ReleaseRequest,
    tenant_id: Optional[str] = Query(default=None),
    principal: IngestionPrincipal = Depends(require_permission("remediation.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    db = _db(db_session)
    tid = service._require_uuid_tenant(tid)
    set_tenant_guc(db, tid)
    meta = service.get_run_meta(db, tenant_id=tid, run_id=run_id)
    records = service.list_run_records(db, tenant_id=tid, run_id=run_id)
    wanted = set(request.record_ids or [])
    released, skipped = [], []
    for record in records:
        if wanted and record["id"] not in wanted:
            continue
        if record["validation_status"] != "passed" or record["release_status"] != "staged":
            skipped.append(
                {"record_id": record["id"], "reason": f"{record['validation_status']}/{record['release_status']}"}
            )
            continue
        event_id = service.release_record(db, tenant_id=tid, record=record, source_meta=meta)
        released.append({"record_id": record["id"], "released_event_id": event_id})
    return {"released": released, "skipped": skipped}


@router.post(
    "/cases/{case_id}/link", response_model=CreateLinkResponse, summary="Issue a scoped supplier correction link"
)
async def create_link(
    case_id: str,
    request: CreateLinkRequest,
    tenant_id: Optional[str] = Query(default=None),
    principal: IngestionPrincipal = Depends(require_permission("remediation.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    db = _db(db_session)
    tid = service._require_uuid_tenant(tid)
    set_tenant_guc(db, tid)
    case = _load_case(db, tid, case_id)

    if not case["allowed_fields"]:
        # Nothing a supplier could legitimately correct (e.g. a pure
        # duplicate row). Issuing a link would invite junk corrections;
        # this case is buyer work (reject the row or escalate).
        raise HTTPException(
            status_code=409,
            detail="Case has no supplier-correctable fields; resolve it via buyer review instead of a correction link",
        )

    allowed = case["allowed_fields"]
    if request.authorized_fields:
        allowed = [f for f in allowed if f["field_path"] in set(request.authorized_fields)]
        if not allowed:
            raise HTTPException(status_code=422, detail="authorized_fields does not match any correctable field")
        db.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                UPDATE fsma.remediation_cases
                SET allowed_fields = CAST(:allowed AS jsonb), updated_at = now()
                WHERE id = CAST(:case_id AS uuid) AND tenant_id = CAST(:tenant_id AS uuid)
                """
            ),
            {"allowed": json.dumps(allowed), "case_id": case_id, "tenant_id": tid},
        )

    # Reissue semantics: revoke any live token first.
    revoked = tokens.revoke_tokens_for_case(
        db,
        tenant_id=tid,
        case_id=case_id,
        actor=str(principal.principal_id if hasattr(principal, "principal_id") else "buyer"),
    )
    minted = tokens.issue_token(
        db,
        tenant_id=tid,
        case_id=case_id,
        supplier_email=request.supplier_email,
        created_by=str(getattr(principal, "principal_id", None) or "buyer"),
        expires_hours=request.expires_hours,
        superseded_token_id=revoked[0] if revoked else None,
    )
    # Token rides in the URL FRAGMENT: browsers never send fragments to the
    # server, so the raw token cannot land in access logs anywhere.
    correction_url = f"https://regengine.co/api/v1/remediation/supplier/form#{minted['token']}"

    if case["status"] in ("supplier_action_required", "buyer_review", "escalated"):
        transition(
            db,
            tenant_id=tid,
            case_id=case_id,
            to_status="notification_ready",
            expected_from=case["status"],
            actor="buyer",
        )
        transition(
            db,
            tenant_id=tid,
            case_id=case_id,
            to_status="awaiting_supplier",
            expected_from="notification_ready",
            actor="buyer",
        )
    elif case["status"] == "awaiting_supplier":
        pass  # reissue while already awaiting supplier
    else:
        raise HTTPException(status_code=409, detail=f"Case status '{case['status']}' does not allow issuing a link")

    outbox.enqueue_preview(
        db,
        tenant_id=tid,
        case_id=case_id,
        recipient=request.supplier_email,
        subject=f"Correction needed: {case['manifest_ref']} ({case['line_ref']})",
        body=(
            f"{case['supplier_org']}: your shipment record {case['manifest_ref']} "
            f"{case['line_ref']} needs a correction. Open the secure link to fix it. "
            f"Link expires {minted['expires_at'].isoformat()}."
        ),
        # Hash-at-rest invariant: the raw token (inside correction_url) is
        # returned exactly once in the API response and never persisted —
        # the outbox row stores only a masked link + the token row id.
        payload={
            "correction_url_masked": "https://regengine.co/remediate/•••",
            "token_id": minted["token_id"],
            "case_id": case_id,
        },
    )

    return CreateLinkResponse(
        token_id=minted["token_id"],
        case_id=case_id,
        correction_url=correction_url,
        token=minted["token"],
        expires_at=minted["expires_at"].isoformat(),
        authorized_fields=allowed,
    )


@router.post("/cases/{case_id}/link/revoke", summary="Revoke all live links for a case")
async def revoke_link(
    case_id: str,
    tenant_id: Optional[str] = Query(default=None),
    principal: IngestionPrincipal = Depends(require_permission("remediation.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    db = _db(db_session)
    tid = service._require_uuid_tenant(tid)
    set_tenant_guc(db, tid)
    _load_case(db, tid, case_id)  # 404 fail-closed before revoking
    revoked = tokens.revoke_tokens_for_case(
        db, tenant_id=tid, case_id=case_id, actor=str(getattr(principal, "principal_id", None) or "buyer")
    )
    return {"revoked_token_ids": revoked}


@router.get("/manifests/{run_id}/evidence", summary="Deterministic evidence bundle (zip)")
async def get_evidence(
    run_id: str,
    tenant_id: Optional[str] = Query(default=None),
    principal: IngestionPrincipal = Depends(require_permission("remediation.export")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    db = _db(db_session)
    tid = service._require_uuid_tenant(tid)
    set_tenant_guc(db, tid)
    meta = service.get_run_meta(db, tenant_id=tid, run_id=run_id)
    records = service.list_run_records(db, tenant_id=tid, run_id=run_id)
    bundle = evidence.build_bundle(db, tenant_id=tid, run_meta=meta, records=records, run_id=run_id)
    audit_event(
        db,
        tenant_id=tid,
        event_type="remediation.export",
        action="remediation.export",
        resource_type="ingestion_run",
        resource_id=run_id,
        metadata={"bundle_bytes": len(bundle)},
    )
    return Response(
        content=bundle,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="evidence_{run_id}.zip"'},
    )


@router.get("/metrics", summary="Remediation metrics")
async def get_metrics(
    tenant_id: Optional[str] = Query(default=None),
    principal: IngestionPrincipal = Depends(require_permission("remediation.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    db = _db(db_session)
    tid = service._require_uuid_tenant(tid)
    set_tenant_guc(db, tid)
    return service.compute_metrics(db, tenant_id=tid)


@router.get("/outbox", summary="Notification previews (nothing is ever sent)")
async def get_outbox(
    tenant_id: Optional[str] = Query(default=None),
    principal: IngestionPrincipal = Depends(require_permission("remediation.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    db = _db(db_session)
    tid = service._require_uuid_tenant(tid)
    set_tenant_guc(db, tid)
    return {"notifications": outbox.list_previews(db, tenant_id=tid)}


def _load_case(db, tenant_id: str, case_id: str) -> dict:
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT id, manifest_record_id, exception_case_id, supplier_org,
                   manifest_ref, line_ref, validation_issue_ids, allowed_fields,
                   due_at, status
            FROM fsma.remediation_cases
            WHERE id = CAST(:case_id AS uuid)
              AND tenant_id = CAST(:tenant_id AS uuid)
            """
        ),
        {"case_id": case_id, "tenant_id": tenant_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return {
        "id": str(row[0]),
        "manifest_record_id": str(row[1]),
        "exception_case_id": str(row[2]) if row[2] else None,
        "supplier_org": row[3],
        "manifest_ref": row[4],
        "line_ref": row[5],
        "validation_issue_ids": row[6],
        "allowed_fields": row[7],
        "due_at": row[8].isoformat() if row[8] else None,
        "status": row[9],
    }
