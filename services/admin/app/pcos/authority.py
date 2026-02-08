"""
PCOS Authority & Fact Lineage Router — Authority documents, facts, and verdicts.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_pcos_session
from ..models import TenantContext
from ._shared import get_pcos_tenant_context

router = APIRouter(tags=["PCOS Authority & Lineage"])


# =============================================================================
# AUTHORITY & FACT LINEAGE ENDPOINTS
# =============================================================================

@router.post("/authorities")
def register_authority_document(
    document_code: str,
    document_name: str,
    document_type: str,
    issuer_name: str,
    effective_date: date,
    issuer_type: Optional[str] = None,
    expiration_date: Optional[date] = None,
    file_path: Optional[str] = None,
    extraction_method: str = "manual",
    extraction_notes: Optional[str] = None,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Register a new authority document (CBA, statute, regulation).
    
    Creates a record for source documents that contain authoritative facts.
    If a file path is provided, the document will be hashed for integrity.
    """
    from ..authority_lineage_service import AuthorityLineageService

    tenant_id = UUID(x_tenant_id)
    user_id = UUID(x_user_id) if x_user_id else None
    TenantContext.set_tenant_context(session, tenant_id)

    service = AuthorityLineageService(session, tenant_id)
    result = service.register_authority_document(
        document_code=document_code,
        document_name=document_name,
        document_type=document_type,
        issuer_name=issuer_name,
        effective_date=effective_date,
        issuer_type=issuer_type,
        expiration_date=expiration_date,
        file_path=file_path,
        extraction_method=extraction_method,
        extraction_notes=extraction_notes,
        ingested_by=user_id
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/authorities")
def list_authority_documents(
    document_type: Optional[str] = None,
    issuer: Optional[str] = None,
    status: str = "active",
    include_expired: bool = False,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    List authority documents with optional filtering.
    
    Filter by document type (cba, statute, regulation, municipal_code),
    issuer name, or status (active, superseded, expired).
    """
    from ..authority_lineage_service import AuthorityLineageService

    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)

    service = AuthorityLineageService(session, tenant_id)
    return service.list_authority_documents(
        document_type=document_type,
        issuer=issuer,
        status=status,
        include_expired=include_expired
    )


@router.get("/authorities/{code}/export")
def export_authority_lineage(
    code: str,
    ctx: tuple[Session, UUID] = Depends(get_pcos_tenant_context),
):
    """
    Export full audit lineage for an authority document family.
    Returns cryptographic proofs for all facts and history.
    """
    db, tenant_id = ctx
    from ..authority_lineage_service import AuthorityLineageService

    service = AuthorityLineageService(db, tenant_id)
    result = service.export_authority_history(code)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.post("/authorities/{authority_id}/facts")
def extract_fact_from_authority(
    authority_id: UUID,
    fact_key: str,
    fact_name: str,
    fact_category: str,
    fact_value: str,
    fact_value_type: str,
    validity_conditions: Optional[str] = None,
    fact_unit: Optional[str] = None,
    fact_description: Optional[str] = None,
    source_page: Optional[int] = None,
    source_section: Optional[str] = None,
    source_quote: Optional[str] = None,
    extraction_confidence: Optional[float] = None,
    extraction_method: str = "manual",
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Extract a fact from an authority document.
    
    Creates a versioned, citable fact linked to the source document.
    If a fact with the same key exists, creates a new version.
    """
    from ..authority_lineage_service import AuthorityLineageService

    tenant_id = UUID(x_tenant_id)
    user_id = UUID(x_user_id) if x_user_id else None
    TenantContext.set_tenant_context(session, tenant_id)

    # Parse validity conditions if provided
    conditions = None
    if validity_conditions:
        try:
            conditions = json.loads(validity_conditions)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in validity_conditions")

    # Convert fact value based on type
    parsed_value = fact_value
    if fact_value_type == "decimal":
        parsed_value = float(fact_value)
    elif fact_value_type == "integer":
        parsed_value = int(fact_value)
    elif fact_value_type == "boolean":
        parsed_value = fact_value.lower() in ("true", "1", "yes")
    elif fact_value_type == "json":
        parsed_value = json.loads(fact_value)

    service = AuthorityLineageService(session, tenant_id)
    result = service.extract_fact(
        authority_document_id=authority_id,
        fact_key=fact_key,
        fact_name=fact_name,
        fact_category=fact_category,
        fact_value=parsed_value,
        fact_value_type=fact_value_type,
        validity_conditions=conditions,
        fact_unit=fact_unit,
        fact_description=fact_description,
        source_page=source_page,
        source_section=source_section,
        source_quote=source_quote,
        extraction_confidence=extraction_confidence,
        extraction_method=extraction_method,
        extracted_by=user_id
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/authorities/{authority_id}/facts")
def list_authority_facts(
    authority_id: UUID,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    List all extracted facts for a specific authority document.
    """
    from ..authority_lineage_service import AuthorityLineageService

    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)

    service = AuthorityLineageService(session, tenant_id)
    return service.list_authority_facts(authority_id)


@router.get("/facts/{fact_key}/resolve")
def resolve_fact(
    fact_key: str,
    budget: Optional[float] = None,
    project_type: Optional[str] = None,
    union: Optional[str] = None,
    as_of_date: Optional[date] = None,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Resolve a fact for a given production context.
    
    Finds the applicable fact based on validity conditions like
    budget tier, date range, project type, and union affiliation.
    Returns the fact value with full provenance back to source document.
    """
    from ..authority_lineage_service import AuthorityLineageService

    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)

    context = {}
    if budget is not None:
        context["budget"] = budget
    if project_type:
        context["project_type"] = project_type
    if union:
        context["union"] = union

    service = AuthorityLineageService(session, tenant_id)
    result = service.resolve_fact(
        fact_key=fact_key,
        context=context,
        as_of_date=as_of_date
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Fact '{fact_key}' not found or not applicable for given context"
        )

    return result


@router.get("/verdicts/{entity_type}/{entity_id}/lineage")
def get_verdict_lineage(
    entity_type: str,
    entity_id: UUID,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    Get the full lineage for a verdict or rule evaluation.
    
    Returns all facts cited by this entity with complete provenance
    back to the source authority documents, including document hashes.
    """
    from ..authority_lineage_service import AuthorityLineageService

    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)

    service = AuthorityLineageService(session, tenant_id)
    return service.get_verdict_lineage(
        citing_entity_type=entity_type,
        citing_entity_id=entity_id
    )


@router.get("/facts")
def list_facts(
    fact_category: Optional[str] = None,
    authority_code: Optional[str] = None,
    current_only: bool = True,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    session: Session = Depends(get_pcos_session),
):
    """
    List extracted facts with optional filtering.
    
    Filter by fact category (rate, threshold, deadline, requirement)
    or source authority document code.
    """
    from ..pcos_models import PCOSExtractedFactModel, PCOSAuthorityDocumentModel

    tenant_id = UUID(x_tenant_id)
    TenantContext.set_tenant_context(session, tenant_id)

    query = (
        select(PCOSExtractedFactModel)
        .where(PCOSExtractedFactModel.tenant_id == tenant_id)
    )

    if current_only:
        query = query.where(PCOSExtractedFactModel.is_current == True)

    if fact_category:
        query = query.where(PCOSExtractedFactModel.fact_category == fact_category)

    if authority_code:
        query = (
            query.join(PCOSAuthorityDocumentModel)
            .where(PCOSAuthorityDocumentModel.document_code == authority_code)
        )

    query = query.order_by(PCOSExtractedFactModel.fact_key)

    facts = session.execute(query).scalars().all()

    return [
        {
            "id": str(f.id),
            "fact_key": f.fact_key,
            "fact_name": f.fact_name,
            "fact_category": f.fact_category,
            "value_type": f.fact_value_type,
            "value": float(f.fact_value_decimal) if f.fact_value_decimal else (
                f.fact_value_integer or f.fact_value_string or f.fact_value_boolean
            ),
            "unit": f.fact_unit,
            "version": f.version,
            "is_current": f.is_current,
            "validity_conditions": f.validity_conditions,
            "authority_id": str(f.authority_document_id),
            "extraction_confidence": float(f.extraction_confidence) if f.extraction_confidence else None,
            "created_at": f.created_at.isoformat()
        }
        for f in facts
    ]
