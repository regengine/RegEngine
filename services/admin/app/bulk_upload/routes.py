from __future__ import annotations

import uuid as uuid_module
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.bulk_upload.parsers import parse_incoming_file
from app.bulk_upload.session_store import session_store
from app.bulk_upload.templates import generate_template
from app.bulk_upload.transaction_manager import build_validation_preview, execute_bulk_commit
from app.bulk_upload.validators import validate_and_normalize_payload
from app.database import get_session
from app.dependencies import get_current_user
from app.models import TenantContext
from app.supplier_cte_service import SUPPORTED_CTE_TYPES
from app.supplier_onboarding_routes import FTL_CATEGORY_LOOKUP
from app.sqlalchemy_models import UserModel


router = APIRouter()


class BulkUploadParseResponse(BaseModel):
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


class BulkUploadCommitResponse(BaseModel):
    session_id: str
    status: str
    summary: dict[str, Any]


class BulkUploadStatusResponse(BaseModel):
    session_id: str
    status: str
    preview: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    can_commit = bool(preview.get("can_commit"))
    session_data["status"] = "validated" if can_commit else "parsed"
    session_data["normalized_data"] = normalized
    session_data["validation_preview"] = preview
    session_data["error"] = None
    session_data["updated_at"] = _iso_utc_now()
    await session_store.update_session(str(tenant_id), str(user.id), session_id, session_data)

    return BulkUploadValidateResponse(
        session_id=session_id,
        status=session_data["status"],
        preview=BulkUploadValidationPreview(**preview),
    )


@router.post("/commit", response_model=BulkUploadCommitResponse)
async def commit_bulk_upload(
    session_id: str = Query(min_length=8),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> BulkUploadCommitResponse:
    tenant_id, user = _tenant_and_user(db, current_user)
    session_data = await session_store.get_session(str(tenant_id), str(user.id), session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session expired or not found")

    current_status = str(session_data.get("status") or "")
    if current_status == "completed":
        return BulkUploadCommitResponse(
            session_id=session_id,
            status="completed",
            summary=session_data.get("commit_summary") or {},
        )
    if current_status == "processing":
        raise HTTPException(status_code=409, detail="Commit already in progress")
    if current_status != "validated":
        raise HTTPException(status_code=400, detail="Session must be validated before commit")

    session_data["status"] = "processing"
    session_data["error"] = None
    session_data["updated_at"] = _iso_utc_now()
    await session_store.update_session(str(tenant_id), str(user.id), session_id, session_data)

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
        await session_store.update_session(str(tenant_id), str(user.id), session_id, session_data)
        raise HTTPException(status_code=400, detail=f"Bulk commit failed: {exc}") from exc

    session_data["status"] = "completed"
    session_data["commit_summary"] = summary
    session_data["updated_at"] = _iso_utc_now()
    await session_store.update_session(str(tenant_id), str(user.id), session_id, session_data)

    return BulkUploadCommitResponse(
        session_id=session_id,
        status="completed",
        summary=summary,
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
        preview=session_data.get("validation_preview"),
        summary=session_data.get("commit_summary"),
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
