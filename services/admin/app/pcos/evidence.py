"""
PCOS Evidence Router — Evidence records, document uploads, risks, guidance.
"""
from __future__ import annotations
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import get_settings
from .. import s3_utils
from ._shared import get_pcos_tenant_context
from ..pcos_models import PCOSProjectModel, PCOSEvidenceModel, EvidenceCreateSchema, EvidenceResponseSchema

logger = structlog.get_logger("pcos.evidence")
router = APIRouter(tags=["PCOS Evidence"])

@router.get("/projects/{project_id}/evidence", response_model=list[EvidenceResponseSchema])
def list_project_evidence(project_id: uuid_module.UUID, evidence_type: Optional[str] = Query(None), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """List all evidence for a project."""
    db, tenant_id = ctx
    query = select(PCOSEvidenceModel).where(PCOSEvidenceModel.entity_type == "project", PCOSEvidenceModel.entity_id == project_id, PCOSEvidenceModel.tenant_id == tenant_id)
    if evidence_type:
        query = query.where(PCOSEvidenceModel.evidence_type == evidence_type)
    query = query.order_by(PCOSEvidenceModel.created_at.desc())
    return db.execute(query).scalars().all()

@router.post("/evidence", response_model=EvidenceResponseSchema, status_code=status.HTTP_201_CREATED)
def upload_evidence(evidence_data: EvidenceCreateSchema, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Create an evidence record."""
    db, tenant_id = ctx
    evidence = PCOSEvidenceModel(
        tenant_id=tenant_id, entity_type=evidence_data.entity_type, entity_id=evidence_data.entity_id,
        evidence_type=evidence_data.evidence_type.value, title=evidence_data.title, description=evidence_data.description,
        valid_from=evidence_data.valid_from, valid_until=evidence_data.valid_until,
        s3_key=f"pcos/{tenant_id}/{evidence_data.entity_type}/{evidence_data.entity_id}/{uuid_module.uuid4()}",
    )
    db.add(evidence); db.commit(); db.refresh(evidence)
    logger.info("evidence_created", evidence_id=str(evidence.id), entity_type=evidence_data.entity_type, entity_id=str(evidence_data.entity_id), evidence_type=evidence_data.evidence_type.value)
    return evidence

@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...), category: str = Form(...), project_id: Optional[str] = Form(None), entity_type: str = Form(default="project"), entity_id: Optional[str] = Form(None), title: Optional[str] = Form(None), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Upload a document file to PCOS storage. Supported: PDF, DOC, DOCX, JPG, PNG. Max 10MB."""
    db, tenant_id = ctx
    settings = get_settings()
    allowed_types = {"application/pdf": "pdf", "application/msword": "doc", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx", "image/jpeg": "jpg", "image/png": "png"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, DOC, DOCX, JPG, PNG")
    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size: {settings.max_upload_size_mb}MB")
    await file.seek(0)
    valid_categories = {"permits", "insurance", "labor", "minors", "safety", "union"}
    if category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}")
    category_to_evidence_type = {"permits": "permit_approved", "insurance": "coi", "labor": "signed_contract", "minors": "minor_work_permit", "safety": "iipp_policy", "union": "classification_memo_signed"}
    ev_type = category_to_evidence_type.get(category, "other")
    final_entity_id = entity_id or project_id
    if not final_entity_id:
        raise HTTPException(status_code=400, detail="Either project_id or entity_id must be provided")
    try:
        final_entity_id = UUID(final_entity_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entity ID format")
    file_ext = allowed_types[file.content_type]
    unique_id = uuid_module.uuid4()
    s3_key = f"pcos/{tenant_id}/{entity_type}/{final_entity_id}/{unique_id}.{file_ext}"
    s3_uri, sha256_hash, file_size = s3_utils.upload_file(bucket=settings.pcos_bucket, key=s3_key, file_data=file.file, content_type=file.content_type)
    evidence = PCOSEvidenceModel(tenant_id=tenant_id, entity_type=entity_type, entity_id=final_entity_id, evidence_type=ev_type, title=title or file.filename, file_name=file.filename, file_size_bytes=file_size, mime_type=file.content_type, s3_key=s3_key, sha256_hash=sha256_hash)
    db.add(evidence); db.commit(); db.refresh(evidence)
    logger.info("document_uploaded", evidence_id=str(evidence.id), entity_type=entity_type, entity_id=str(final_entity_id), category=category, file_name=file.filename, file_size=file_size)
    return {"id": str(evidence.id), "filename": evidence.file_name, "category": category, "evidence_type": ev_type, "status": "uploaded", "uploadedAt": evidence.created_at.isoformat() if evidence.created_at else None, "fileSize": file_size, "mimeType": file.content_type, "sha256Hash": sha256_hash}

@router.get("/documents/{document_id}/download")
def get_document_download_url(document_id: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Get a presigned URL for downloading a document. Valid for 1 hour."""
    db, tenant_id = ctx
    settings = get_settings()
    evidence = db.execute(select(PCOSEvidenceModel).where(PCOSEvidenceModel.id == document_id, PCOSEvidenceModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not evidence:
        raise HTTPException(status_code=404, detail="Document not found")
    download_url = s3_utils.generate_presigned_url(bucket=settings.pcos_bucket, key=evidence.s3_key, expires_in=3600)
    return {"downloadUrl": download_url, "filename": evidence.file_name, "mimeType": evidence.mime_type, "expiresIn": 3600}

@router.get("/projects/{project_id}/risks")
def get_project_risks(project_id: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Get aggregated risk scores by category for a project."""
    from ..pcos_fact_provider import PCOSFactProvider
    db, tenant_id = ctx
    project = db.execute(select(PCOSProjectModel).where(PCOSProjectModel.id == project_id, PCOSProjectModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    provider = PCOSFactProvider(db=db, tenant_id=tenant_id)
    risk_categories = provider.get_risk_summary(project_id)
    overall_score = sum(c.score for c in risk_categories) // len(risk_categories) if risk_categories else 0
    return {"project_id": str(project_id), "overall_risk_score": overall_score, "categories": [c.to_dict() for c in risk_categories], "evaluated_at": datetime.now(timezone.utc).isoformat()}

@router.get("/projects/{project_id}/guidance")
def get_project_guidance(project_id: uuid_module.UUID, category: Optional[str] = Query(None, description="Filter by category"), ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """Get prioritized guidance items for a project."""
    from ..pcos_fact_provider import PCOSFactProvider
    db, tenant_id = ctx
    project = db.execute(select(PCOSProjectModel).where(PCOSProjectModel.id == project_id, PCOSProjectModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    provider = PCOSFactProvider(db=db, tenant_id=tenant_id)
    guidance_items = provider.get_guidance_items(project_id)
    if category:
        guidance_items = [g for g in guidance_items if g.category == category]
    return {"project_id": str(project_id), "total_items": len(guidance_items), "items": [g.to_dict() for g in guidance_items]}

@router.get("/projects/{project_id}/documents")
def list_project_documents(project_id: uuid_module.UUID, ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context)):
    """List all documents/evidence for a project with status tracking."""
    db, tenant_id = ctx
    project = db.execute(select(PCOSProjectModel).where(PCOSProjectModel.id == project_id, PCOSProjectModel.tenant_id == tenant_id)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    evidence_list = db.execute(select(PCOSEvidenceModel).where(PCOSEvidenceModel.entity_type == "project", PCOSEvidenceModel.entity_id == project_id, PCOSEvidenceModel.tenant_id == tenant_id).order_by(PCOSEvidenceModel.created_at.desc())).scalars().all()
    documents = [{"id": str(ev.id), "name": ev.title or f"{ev.evidence_type} document", "type": ev.evidence_type, "category": _evidence_type_to_category(ev.evidence_type), "status": "verified" if ev.verified_at else "uploaded", "uploadedAt": ev.created_at.isoformat() if ev.created_at else None, "verifiedAt": ev.verified_at.isoformat() if ev.verified_at else None, "fileUrl": ev.s3_key} for ev in evidence_list]
    return {"project_id": str(project_id), "total": len(documents), "documents": documents}

def _evidence_type_to_category(evidence_type: str) -> str:
    """Map evidence type to risk category."""
    mapping = {"permit_approved": "permits", "coi": "insurance", "workers_comp_policy": "insurance", "classification_memo_signed": "labor", "minor_work_permit": "minors", "iipp_policy": "safety", "wvpp_policy": "safety", "w9": "labor", "i9": "labor", "w4": "labor"}
    return mapping.get(evidence_type, "other")
