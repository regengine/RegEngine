"""
Identity Resolution Router.

Provides API endpoints for managing the shared identity layer —
canonical entities, aliases, merges, and ambiguous match review.

Endpoints:
    GET    /api/v1/identity/entities                — List/search entities
    POST   /api/v1/identity/entities                — Register entity
    GET    /api/v1/identity/entities/{id}            — Get entity with aliases
    POST   /api/v1/identity/entities/{id}/aliases    — Add alias
    GET    /api/v1/identity/lookup                   — Find entity by alias
    GET    /api/v1/identity/match                    — Find potential matches
    POST   /api/v1/identity/merge                    — Merge entities
    POST   /api/v1/identity/split                    — Split (undo merge)
    GET    /api/v1/identity/reviews                  — Pending review queue
    PATCH  /api/v1/identity/reviews/{id}             — Resolve review
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.authz import require_permission, IngestionPrincipal
from app.tenant_validation import validate_tenant_id

logger = logging.getLogger("identity-resolution")

router = APIRouter(prefix="/api/v1/identity", tags=["Identity Resolution"])


# ---------------------------------------------------------------------------
# DB Session
# ---------------------------------------------------------------------------

def _get_db_session():
    try:
        from shared.database import SessionLocal
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.warning("database_unavailable: %s", str(e))
        yield None


def _get_service(db_session):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    from shared.identity_resolution import IdentityResolutionService
    return IdentityResolutionService(db_session)


def _resolve_tenant(tenant_id: Optional[str], principal: IngestionPrincipal) -> str:
    tid = tenant_id or principal.tenant_id
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant context required")
    validate_tenant_id(tid)
    return tid


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class RegisterEntityRequest(BaseModel):
    entity_type: str  # firm, facility, product, lot, trading_relationship
    canonical_name: str
    gln: Optional[str] = None
    gtin: Optional[str] = None
    fda_registration: Optional[str] = None
    internal_id: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "US"
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    created_by: Optional[str] = None


class AddAliasRequest(BaseModel):
    alias_type: str  # name, gln, gtin, fda_registration, internal_code, etc.
    alias_value: str
    source_system: Optional[str] = None
    created_by: Optional[str] = None


class MergeRequest(BaseModel):
    source_entity_id: str
    target_entity_id: str
    reason: Optional[str] = None
    performed_by: str


class SplitRequest(BaseModel):
    merge_id: str
    performed_by: str


class ResolveReviewRequest(BaseModel):
    status: str  # confirmed_match, confirmed_distinct, deferred
    resolved_by: str
    resolution_notes: Optional[str] = None
    auto_merge: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/entities",
    summary="List/search canonical entities",
)
async def list_entities(
    tenant_id: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("identity.read")),
    db_session=Depends(_get_db_session),
):
    tid = _resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    if search:
        entities = svc.find_potential_matches(tid, search, entity_type=entity_type)
    else:
        # List all entities of a type
        from sqlalchemy import text
        query = "SELECT entity_id, entity_type, canonical_name, gln, gtin, verification_status, confidence_score FROM fsma.canonical_entities WHERE tenant_id = :tid AND is_active = TRUE"
        params: Dict[str, Any] = {"tid": tid}
        if entity_type:
            query += " AND entity_type = :etype"
            params["etype"] = entity_type
        query += " ORDER BY canonical_name LIMIT 100"
        rows = db_session.execute(text(query), params).fetchall()
        entities = [
            {"entity_id": str(r[0]), "entity_type": r[1], "canonical_name": r[2],
             "gln": r[3], "gtin": r[4], "verification_status": r[5], "confidence_score": float(r[6]) if r[6] else 1.0}
            for r in rows
        ]
    return {"tenant_id": tid, "entities": entities, "total": len(entities)}


@router.post(
    "/entities",
    summary="Register canonical entity",
    status_code=201,
)
async def register_entity(
    body: RegisterEntityRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("identity.write")),
    db_session=Depends(_get_db_session),
):
    tid = _resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    entity_id = svc.register_entity(
        tenant_id=tid,
        entity_type=body.entity_type,
        canonical_name=body.canonical_name,
        gln=body.gln,
        gtin=body.gtin,
        fda_registration=body.fda_registration,
        internal_id=body.internal_id,
        address=body.address,
        city=body.city,
        state=body.state,
        country=body.country,
        contact_name=body.contact_name,
        contact_phone=body.contact_phone,
        contact_email=body.contact_email,
        created_by=body.created_by,
    )
    return {"entity_id": entity_id, "status": "registered"}


@router.get(
    "/entities/{entity_id}",
    summary="Get entity with all aliases",
)
async def get_entity(
    entity_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("identity.read")),
    db_session=Depends(_get_db_session),
):
    tid = _resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    entity = svc.get_entity(tid, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.post(
    "/entities/{entity_id}/aliases",
    summary="Add alias to entity",
    status_code=201,
)
async def add_alias(
    entity_id: str,
    body: AddAliasRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("identity.write")),
    db_session=Depends(_get_db_session),
):
    tid = _resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    alias_id = svc.add_alias(
        tenant_id=tid,
        entity_id=entity_id,
        alias_type=body.alias_type,
        alias_value=body.alias_value,
        source_system=body.source_system,
        created_by=body.created_by,
    )
    return {"alias_id": alias_id, "status": "added"}


@router.get(
    "/lookup",
    summary="Find entity by alias value",
)
async def lookup_by_alias(
    alias_value: str = Query(...),
    alias_type: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("identity.read")),
    db_session=Depends(_get_db_session),
):
    tid = _resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    entities = svc.find_entity_by_alias(tid, alias_value, alias_type)
    return {"tenant_id": tid, "matches": entities, "total": len(entities)}


@router.get(
    "/match",
    summary="Find potential entity matches (fuzzy)",
)
async def find_matches(
    name: str = Query(...),
    entity_type: Optional[str] = Query(None),
    min_confidence: float = Query(0.7),
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("identity.read")),
    db_session=Depends(_get_db_session),
):
    tid = _resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    matches = svc.find_potential_matches(
        tid, name, entity_type=entity_type, min_confidence=min_confidence,
    )
    return {"tenant_id": tid, "matches": matches, "total": len(matches)}


@router.post(
    "/merge",
    summary="Merge two entities into one",
)
async def merge_entities(
    body: MergeRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("identity.write")),
    db_session=Depends(_get_db_session),
):
    tid = _resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    merge_id = svc.merge_entities(
        tenant_id=tid,
        source_entity_id=body.source_entity_id,
        target_entity_id=body.target_entity_id,
        reason=body.reason,
        performed_by=body.performed_by,
    )
    return {"merge_id": merge_id, "status": "merged"}


@router.post(
    "/split",
    summary="Reverse a merge (split entities)",
)
async def split_entities(
    body: SplitRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("identity.write")),
    db_session=Depends(_get_db_session),
):
    tid = _resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    svc.split_entity(tid, body.merge_id, body.performed_by)
    return {"merge_id": body.merge_id, "status": "split"}


@router.get(
    "/reviews",
    summary="List pending identity reviews",
)
async def list_reviews(
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("identity.read")),
    db_session=Depends(_get_db_session),
):
    tid = _resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    reviews = svc.list_pending_reviews(tid)
    return {"tenant_id": tid, "reviews": reviews, "total": len(reviews)}


@router.patch(
    "/reviews/{review_id}",
    summary="Resolve identity review",
)
async def resolve_review(
    review_id: str,
    body: ResolveReviewRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("identity.write")),
    db_session=Depends(_get_db_session),
):
    tid = _resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    svc.resolve_review(
        tenant_id=tid,
        review_id=review_id,
        status=body.status,
        resolved_by=body.resolved_by,
        resolution_notes=body.resolution_notes,
        auto_merge=body.auto_merge,
    )
    return {"review_id": review_id, "status": body.status}
