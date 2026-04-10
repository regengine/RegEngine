"""
Supplier Portal Router.

Provides a lightweight, link-based submission form for suppliers to submit
shipping/receiving data without needing a RegEngine account.

A customer generates a portal link for their supplier. The supplier clicks
the link, fills in TLC + shipment details, and the data is ingested directly
into the customer's tenant as a Shipping CTE.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload
from app.webhook_compat import _verify_api_key, ingest_events
from shared.pagination import PaginationParams

logger = logging.getLogger("supplier-portal")

router = APIRouter(prefix="/api/v1/portal", tags=["Supplier Portal"])

# In-memory portal link store (fallback when DB is unavailable)
_portal_links: dict[str, dict] = {}


def _get_db():
    """Get database session. Returns None if unavailable."""
    try:
        from shared.database import SessionLocal
        return SessionLocal()
    except Exception as exc:
        logger.warning("db_unavailable error=%s", str(exc))
        return None


def _db_store_portal_link(portal_id: str, link_data: dict) -> bool:
    """Insert a portal link into the database. Returns True on success."""
    db = _get_db()
    if not db:
        return False
    try:
        db.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text("""
                INSERT INTO fsma.tenant_portal_links
                (id, tenant_id, supplier_name, link_token, status, created_at, expires_at)
                VALUES (gen_random_uuid(), :tenant_id, :supplier_name, :link_token, 'active', :created_at, :expires_at)
                ON CONFLICT (link_token) DO UPDATE SET
                    supplier_name = :supplier_name,
                    status = 'active',
                    expires_at = :expires_at
            """),
            {
                "tenant_id": link_data["tenant_id"],
                "supplier_name": link_data["supplier_name"],
                "link_token": portal_id,
                "created_at": link_data["created_at"],
                "expires_at": link_data["expires_at"],
            },
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning("db_store_portal_link_failed error=%s", str(exc))
        if db:
            db.rollback()
        return False
    finally:
        db.close()


def _db_get_portal_link(portal_id: str) -> Optional[dict]:
    """Fetch a portal link from the database by link_token. Returns dict or None."""
    db = _get_db()
    if not db:
        return None
    try:
        row = db.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text("""
                SELECT tenant_id, supplier_name, link_token, status, created_at, expires_at
                FROM fsma.tenant_portal_links
                WHERE link_token = :link_token AND status = 'active'
            """),
            {"link_token": portal_id},
        ).fetchone()
        if not row:
            return None
        return {
            "tenant_id": str(row[0]),
            "supplier_name": row[1],
            "supplier_email": None,
            "allowed_cte_types": ["shipping"],
            "expires_at": row[5].isoformat() if row[5] else None,
            "created_at": row[4].isoformat() if row[4] else None,
        }
    except Exception as exc:
        logger.warning("db_get_portal_link_failed error=%s", str(exc))
        return None
    finally:
        db.close()


def _db_update_portal_link_status(portal_id: str, status: str) -> bool:
    """Update the status of a portal link in the database."""
    db = _get_db()
    if not db:
        return False
    try:
        db.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text("UPDATE fsma.tenant_portal_links SET status = :status WHERE link_token = :link_token"),
            {"status": status, "link_token": portal_id},
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning("db_update_portal_link_status_failed error=%s", str(exc))
        if db:
            db.rollback()
        return False
    finally:
        db.close()


def _get_active_portal_link(portal_id: str) -> dict:
    # Try DB first, fall back to in-memory
    link = _db_get_portal_link(portal_id)
    if link is None:
        link = _portal_links.get(portal_id)
    if not link:
        raise HTTPException(status_code=404, detail="Portal link not found or expired")

    expires_at_raw = link.get("expires_at")
    if not expires_at_raw:
        raise HTTPException(status_code=404, detail="Portal link not found or expired")

    try:
        expires_at = datetime.fromisoformat(str(expires_at_raw).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Portal link has invalid expiry metadata")

    if expires_at <= datetime.now(timezone.utc):
        _portal_links.pop(portal_id, None)
        _db_update_portal_link_status(portal_id, "expired")
        raise HTTPException(status_code=404, detail="Portal link not found or expired")

    return link


class CreatePortalLinkRequest(BaseModel):
    """Request to create a supplier portal link."""
    tenant_id: str = Field(..., description="Customer's tenant ID")
    supplier_name: str = Field(..., description="Supplier business name")
    supplier_email: Optional[str] = Field(None, description="Supplier contact email")
    allowed_cte_types: list[str] = Field(
        default=["shipping"],
        description="CTE types the supplier can submit (default: shipping only)"
    )
    expires_days: int = Field(default=90, ge=1, le=365, description="Link expiry in days")


class PortalLinkResponse(BaseModel):
    """Response with the generated portal link."""
    portal_id: str
    portal_url: str
    supplier_name: str
    tenant_id: str
    expires_at: str
    allowed_cte_types: list[str]


class SupplierSubmission(BaseModel):
    """Data submitted by a supplier through the portal."""
    traceability_lot_code: str = Field(..., description="TLC for shipped product", min_length=3)
    product_description: str = Field(..., description="Product name/description", min_length=1)
    quantity: float = Field(..., description="Quantity shipped", gt=0)
    unit_of_measure: str = Field(..., description="Unit (cases, lbs, kg, pallets)")
    ship_date: str = Field(..., description="Ship date (YYYY-MM-DD)")
    ship_from_location: str = Field(..., description="Origin facility name")
    ship_from_gln: Optional[str] = Field(None, description="Origin GLN (optional)")
    ship_to_location: str = Field(..., description="Destination facility name")
    ship_to_gln: Optional[str] = Field(None, description="Destination GLN (optional)")
    carrier_name: Optional[str] = Field(None, description="Carrier/logistics company")
    po_number: Optional[str] = Field(None, description="Purchase order number")
    temperature_celsius: Optional[float] = Field(None, description="Temperature at shipping (°C)")
    notes: Optional[str] = Field(None, description="Additional notes")


class SubmissionResult(BaseModel):
    """Result of a supplier submission."""
    status: str  # "accepted" or "error"
    event_id: Optional[str] = None
    sha256_hash: Optional[str] = None
    message: str
    supplier_name: str
    submitted_at: str


@router.post(
    "/links",
    response_model=PortalLinkResponse,
    summary="Create a supplier portal link",
    description="Generate a unique, expiring link that a supplier can use to submit shipping data.",
)
async def create_portal_link(
    request: CreatePortalLinkRequest,
    _: None = Depends(_verify_api_key),
) -> PortalLinkResponse:
    """Create a supplier portal link."""
    portal_id = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=request.expires_days)).isoformat()

    link_data = {
        "tenant_id": request.tenant_id,
        "supplier_name": request.supplier_name,
        "supplier_email": request.supplier_email,
        "allowed_cte_types": request.allowed_cte_types,
        "expires_at": expires_at,
        "created_at": now.isoformat(),
    }

    # Try DB first, fall back to in-memory
    db_success = _db_store_portal_link(portal_id, link_data)
    if not db_success:
        logger.info("db_store_fallback using in-memory for portal_id=%s", portal_id)
    # Always store in-memory as well for supplemental fields (supplier_email, allowed_cte_types)
    _portal_links[portal_id] = link_data

    logger.info(
        "portal_link_created",
        extra={
            "portal_id": portal_id,
            "tenant_id": request.tenant_id,
            "supplier_name": request.supplier_name,
        },
    )

    return PortalLinkResponse(
        portal_id=portal_id,
        portal_url=f"https://regengine.co/portal/{portal_id}",
        supplier_name=request.supplier_name,
        tenant_id=request.tenant_id,
        expires_at=expires_at,
        allowed_cte_types=request.allowed_cte_types,
    )


@router.get(
    "/links/list",
    summary="List portal links for a tenant",
    description="Returns all portal links for the authenticated tenant.",
)
async def list_portal_links(
    tenant_id: str,
    pagination: PaginationParams = Depends(),
    _: None = Depends(_verify_api_key),
):
    """List all portal links for a tenant."""
    links: list[dict] = []

    # Try DB first
    db = _get_db()
    if db:
        try:
            rows = db.execute(
                # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
                text("""
                    SELECT id, tenant_id, supplier_name, link_token, status, created_at, expires_at
                    FROM fsma.tenant_portal_links
                    WHERE tenant_id = :tenant_id
                    ORDER BY created_at DESC
                """),
                {"tenant_id": tenant_id},
            ).fetchall()
            for row in rows:
                expires_at = row[6]
                status = row[4]
                # Auto-expire links past their expiry
                if status == "active" and expires_at and expires_at <= datetime.now(timezone.utc):
                    status = "expired"
                links.append({
                    "portal_id": row[3],
                    "portal_url": f"https://regengine.co/portal/{row[3]}",
                    "supplier_name": row[2],
                    "tenant_id": str(row[1]),
                    "status": status,
                    "created_at": row[5].isoformat() if row[5] else None,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                })
        except Exception as exc:
            logger.warning("list_portal_links_db_failed error=%s", str(exc))
        finally:
            db.close()

    # Supplement with in-memory links not in DB results
    db_tokens = {link["portal_id"] for link in links}
    for token, data in _portal_links.items():
        if data.get("tenant_id") == tenant_id and token not in db_tokens:
            expires_at_raw = data.get("expires_at")
            status = "active"
            if expires_at_raw:
                try:
                    exp = datetime.fromisoformat(str(expires_at_raw).replace("Z", "+00:00"))
                    if exp <= datetime.now(timezone.utc):
                        status = "expired"
                except ValueError:
                    pass
            links.append({
                "portal_id": token,
                "portal_url": f"https://regengine.co/portal/{token}",
                "supplier_name": data.get("supplier_name", "Unknown"),
                "tenant_id": tenant_id,
                "status": status,
                "created_at": data.get("created_at"),
                "expires_at": expires_at_raw,
            })

    total = len(links)
    links = links[pagination.skip : pagination.skip + pagination.limit]
    return {"links": links, "total": total, "skip": pagination.skip, "limit": pagination.limit}


@router.patch(
    "/links/{portal_id}/revoke",
    summary="Revoke a portal link",
    description="Deactivate a portal link so it can no longer be used for submissions.",
)
async def revoke_portal_link(
    portal_id: str,
    _: None = Depends(_verify_api_key),
):
    """Revoke a portal link."""
    # Update DB
    db_updated = _db_update_portal_link_status(portal_id, "revoked")
    # Remove from in-memory
    _portal_links.pop(portal_id, None)

    if not db_updated:
        logger.warning("revoke_portal_link portal_id=%s db_update_failed", portal_id)

    return {"status": "revoked", "portal_id": portal_id}


@router.get(
    "/{portal_id}",
    summary="Get portal link details",
    description="Retrieve portal link metadata (supplier name, allowed CTE types, etc.)",
)
async def get_portal_details(portal_id: str):
    """Get portal link details — used by the frontend to render the form."""
    link = _get_active_portal_link(portal_id)

    return {
        "portal_id": portal_id,
        "supplier_name": link["supplier_name"],
        "allowed_cte_types": link["allowed_cte_types"],
        "status": "active",
    }


@router.post(
    "/{portal_id}/submit",
    response_model=SubmissionResult,
    summary="Submit supplier data",
    description=(
        "Supplier submits shipping/receiving data through the portal. "
        "Data is validated, SHA-256 hashed, and ingested into the customer's tenant."
    ),
)
async def submit_supplier_data(
    portal_id: str,
    submission: SupplierSubmission,
) -> SubmissionResult:
    """Process a supplier submission — no auth required (link-based access)."""
    link = _get_active_portal_link(portal_id)

    # Build KDEs
    kdes: dict = {
        "ship_date": submission.ship_date,
        "ship_from_location": submission.ship_from_location,
        "ship_to_location": submission.ship_to_location,
        "supplier_name": link["supplier_name"],
        "submission_source": "supplier_portal",
        "portal_id": portal_id,
    }
    if submission.carrier_name:
        kdes["carrier_name"] = submission.carrier_name
    if submission.po_number:
        kdes["po_number"] = submission.po_number
    if submission.temperature_celsius is not None:
        kdes["temperature_celsius"] = submission.temperature_celsius
    if submission.notes:
        kdes["notes"] = submission.notes

    # Create event
    event = IngestEvent(
        cte_type=WebhookCTEType.SHIPPING,
        traceability_lot_code=submission.traceability_lot_code,
        product_description=submission.product_description,
        quantity=submission.quantity,
        unit_of_measure=submission.unit_of_measure,
        location_gln=submission.ship_from_gln,
        location_name=submission.ship_from_location,
        timestamp=f"{submission.ship_date}T00:00:00Z",
        kdes=kdes,
    )

    # Ingest into customer's tenant
    payload = WebhookPayload(
        source="supplier_portal",
        events=[event],
        tenant_id=link["tenant_id"],
    )
    result = await ingest_events(payload)

    submitted_at = datetime.now(timezone.utc).isoformat()

    if result.accepted > 0:
        event_result = result.events[0]
        logger.info(
            "supplier_submission_accepted",
            extra={
                "portal_id": portal_id,
                "tenant_id": link["tenant_id"],
                "supplier": link["supplier_name"],
                "tlc": submission.traceability_lot_code,
            },
        )
        return SubmissionResult(
            status="accepted",
            event_id=event_result.event_id,
            sha256_hash=event_result.sha256_hash,
            message=f"Shipment data received and verified. Event ID: {event_result.event_id}",
            supplier_name=link["supplier_name"],
            submitted_at=submitted_at,
        )
    else:
        errors = result.events[0].errors if result.events else ["Unknown error"]
        return SubmissionResult(
            status="error",
            message=f"Submission rejected: {'; '.join(errors)}",
            supplier_name=link["supplier_name"],
            submitted_at=submitted_at,
        )
