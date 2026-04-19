from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .parsers import parse_incoming_file
from .session_store import session_store
from .templates import generate_template
from .transaction_manager import build_validation_preview, execute_bulk_commit
from .validators import validate_and_normalize_payload
from ..database import get_session
from ..dependencies import get_current_user
from ..models import TenantContext
from ..supplier_cte_service import SUPPORTED_CTE_TYPES
from ..supplier_onboarding_routes import FTL_CATEGORY_LOOKUP
from ..sqlalchemy_models import UserModel


router = APIRouter()


class BulkUploadParseResponse(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "session_id": "sess_a1b2c3d4e5f6",
                "status": "parsed",
                "detected_format": "csv",
                "facilities": 3,
                "ftl_scopes": 2,
                "tlcs": 15,
                "events": 42,
                "warnings": ["Row 12: quantity field empty, defaulted to 0"],
            }
        }
    }

    session_id: str
    status: str
    detected_format: str
    facilities: int
    ftl_scopes: int
    tlcs: int
    events: int
    warnings: list[str] = Field(default_factory=list)


class BulkUploadValidationError(BaseModel):
    section: str
    row: int
    message: str
    severity: str = "error"  # "error" blocks commit, "warning" allows it


class BulkUploadValidationPreview(BaseModel):
    facilities_to_create: int
    facilities_to_update: int
    ftl_scopes_to_upsert: int
    tlcs_to_create: int
    tlcs_to_update: int
    events_to_chain: int
    errors: list[BulkUploadValidationError] = Field(default_factory=list)
    can_commit: bool


class BulkUploadValidateResponse(BaseModel):
    session_id: str
    status: str
    preview: BulkUploadValidationPreview


class BulkUploadCommitSummary(BaseModel):
    facilities_created: int = 0
    facilities_updated: int = 0
    ftl_scopes_upserted: int = 0
    tlcs_created: int = 0
    tlcs_updated: int = 0
    events_chained: int = 0
    last_merkle_hash: str | None = None
    sync_warning_count: int = 0
    sync_warnings: list[str] = Field(default_factory=list)


class BulkUploadCommitResponse(BaseModel):
    session_id: str
    status: str
    summary: BulkUploadCommitSummary


class BulkUploadStatusResponse(BaseModel):
    session_id: str
    status: str
    preview: BulkUploadValidationPreview | None = None
    summary: BulkUploadCommitSummary | None = None
    error: str | None = None


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_commit_summary(value: Any) -> BulkUploadCommitSummary:
    if isinstance(value, dict):
        return BulkUploadCommitSummary(**value)
    return BulkUploadCommitSummary()


def _coerce_validation_preview(value: Any) -> BulkUploadValidationPreview | None:
    if isinstance(value, dict):
        return BulkUploadValidationPreview(**value)
    return None


def _tenant_and_user(db: Session, current_user: UserModel) -> tuple[uuid_module.UUID, UserModel]:
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    return tenant_id, current_user


@router.post("/parse", response_model=BulkUploadParseResponse)
async def parse_bulk_upload(
    file: UploadFile = File(...),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> BulkUploadParseResponse:
    tenant_id, user = _tenant_and_user(db, current_user)
    parsed_data = await parse_incoming_file(file)

    payload = {
        "status": "parsed",
        "filename": file.filename,
        "detected_format": parsed_data.get("detected_format"),
        "parsed_data": {
            "facilities": parsed_data.get("facilities") or [],
            "ftl_scopes": parsed_data.get("ftl_scopes") or [],
            "tlcs": parsed_data.get("tlcs") or [],
            "events": parsed_data.get("events") or [],
            "warnings": parsed_data.get("warnings") or [],
        },
        "normalized_data": None,
        "validation_preview": None,
        "commit_summary": None,
        "error": None,
        "updated_at": _iso_utc_now(),
    }

    session_id = await session_store.create_session(str(tenant_id), str(user.id), payload)
    parsed_payload = payload["parsed_data"]

    return BulkUploadParseResponse(
        session_id=session_id,
        status="parsed",
        detected_format=str(parsed_data.get("detected_format") or "unknown"),
        facilities=len(parsed_payload.get("facilities") or []),
        ftl_scopes=len(parsed_payload.get("ftl_scopes") or []),
        tlcs=len(parsed_payload.get("tlcs") or []),
        events=len(parsed_payload.get("events") or []),
        warnings=parsed_payload.get("warnings") or [],
    )


@router.post("/validate", response_model=BulkUploadValidateResponse)
async def validate_bulk_upload(
    session_id: str = Query(min_length=8),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> BulkUploadValidateResponse:
    tenant_id, user = _tenant_and_user(db, current_user)
    session_data = await session_store.get_session(str(tenant_id), str(user.id), session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session expired or not found")

    parsed_data = session_data.get("parsed_data") or {}
    normalized, errors = validate_and_normalize_payload(
        parsed_data,
        supported_cte_types=SUPPORTED_CTE_TYPES,
        valid_ftl_category_ids=set(FTL_CATEGORY_LOOKUP.keys()),
    )
    preview = build_validation_preview(
        db,
        tenant_id=tenant_id,
        supplier_user_id=user.id,
        normalized_payload=normalized,
        validation_errors=errors,
    )

    preview_model = BulkUploadValidationPreview(**preview)
    can_commit = preview_model.can_commit
    session_data["status"] = "validated" if can_commit else "parsed"
    session_data["normalized_data"] = normalized
    session_data["validation_preview"] = preview_model.model_dump()
    session_data["error"] = None
    session_data["updated_at"] = _iso_utc_now()
    await session_store.update_session(str(tenant_id), str(user.id), session_id, session_data)

    return BulkUploadValidateResponse(
        session_id=session_id,
        status=session_data["status"],
        preview=preview_model,
    )


@router.post("/commit", response_model=BulkUploadCommitResponse)
async def commit_bulk_upload(
    session_id: str = Query(min_length=8),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> BulkUploadCommitResponse:
    tenant_id, user = _tenant_and_user(db, current_user)
    tenant_key = str(tenant_id)
    user_key = str(user.id)

    # Fast idempotency: a commit that already ran returns its cached
    # summary without taking the commit lock. This MUST stay outside
    # ``try_claim_commit`` — the CAS enforces ``status==validated`` and
    # we want ``status==completed`` to short-circuit cheaply.
    existing = await session_store.get_session(tenant_key, user_key, session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Session expired or not found")
    existing_status = str(existing.get("status") or "")
    if existing_status == "completed":
        return BulkUploadCommitResponse(
            session_id=session_id,
            status="completed",
            summary=_coerce_commit_summary(existing.get("commit_summary")),
        )

    # Atomic check-and-transition: claim the commit lock by flipping
    # ``status`` from ``validated`` to ``processing`` in a single CAS
    # operation. Without this, two concurrent commit requests both
    # observe ``status=validated``, both pass the guard, and both call
    # ``execute_bulk_commit`` — producing duplicate FSMA rows and
    # Merkle-hash divergence in the audit chain (issue #1074).
    #
    # On failure ``try_claim_commit`` returns ``None``; we look at the
    # *current* persisted status to decide what HTTP error to surface.
    session_data = await session_store.try_claim_commit(
        tenant_key,
        user_key,
        session_id,
        from_status="validated",
        to_status="processing",
        mutations={"error": None, "updated_at": _iso_utc_now()},
    )
    if session_data is None:
        # Re-read to build a precise error. Another request may have
        # raced ahead and the session could now be in any state.
        refreshed = await session_store.get_session(tenant_key, user_key, session_id)
        if refreshed is None:
            raise HTTPException(status_code=404, detail="Session expired or not found")
        refreshed_status = str(refreshed.get("status") or "")
        if refreshed_status == "completed":
            # A concurrent commit finished between our idempotency check
            # and the CAS — return its summary.
            return BulkUploadCommitResponse(
                session_id=session_id,
                status="completed",
                summary=_coerce_commit_summary(refreshed.get("commit_summary")),
            )
        if refreshed_status == "processing":
            raise HTTPException(
                status_code=409,
                detail="Commit already in progress",
            )
        raise HTTPException(
            status_code=400,
            detail="Session must be validated before commit",
        )

    try:
        summary = execute_bulk_commit(
            db,
            tenant_id=tenant_id,
            current_user=user,
            normalized_payload=session_data.get("normalized_data") or {},
        )
    except Exception as exc:
        session_data["status"] = "failed"
        session_data["error"] = str(exc)
        session_data["updated_at"] = _iso_utc_now()
        await session_store.update_session(tenant_key, user_key, session_id, session_data)
        raise HTTPException(status_code=400, detail=f"Bulk commit failed: {exc}") from exc

    summary_payload = _coerce_commit_summary(summary).model_dump()
    session_data["status"] = "completed"
    session_data["commit_summary"] = summary_payload
    session_data["updated_at"] = _iso_utc_now()
    await session_store.update_session(tenant_key, user_key, session_id, session_data)

    return BulkUploadCommitResponse(
        session_id=session_id,
        status="completed",
        summary=_coerce_commit_summary(summary_payload),
    )


@router.get("/status/{session_id}", response_model=BulkUploadStatusResponse)
async def get_bulk_upload_status(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> BulkUploadStatusResponse:
    tenant_id, user = _tenant_and_user(db, current_user)
    session_data = await session_store.get_session(str(tenant_id), str(user.id), session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session expired or not found")

    return BulkUploadStatusResponse(
        session_id=session_id,
        status=str(session_data.get("status") or "unknown"),
        preview=_coerce_validation_preview(session_data.get("validation_preview")),
        summary=(
            _coerce_commit_summary(session_data.get("commit_summary"))
            if session_data.get("commit_summary") is not None
            else None
        ),
        error=session_data.get("error"),
    )


@router.get("/template")
async def download_bulk_template(
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
    _current_user: UserModel = Depends(get_current_user),
    _db: Session = Depends(get_session),
) -> StreamingResponse:
    payload, media_type, filename = generate_template(format)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([payload]), media_type=media_type, headers=headers)
