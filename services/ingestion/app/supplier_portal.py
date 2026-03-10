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

from app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload
from app.webhook_compat import _verify_api_key, ingest_events

logger = logging.getLogger("supplier-portal")

router = APIRouter(prefix="/api/v1/portal", tags=["Supplier Portal"])

# In-memory portal link store (in production: database)
_portal_links: dict[str, dict] = {}


def _get_active_portal_link(portal_id: str) -> dict:
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
    expires_at = (datetime.now(timezone.utc) + timedelta(days=request.expires_days)).isoformat()

    _portal_links[portal_id] = {
        "tenant_id": request.tenant_id,
        "supplier_name": request.supplier_name,
        "supplier_email": request.supplier_email,
        "allowed_cte_types": request.allowed_cte_types,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

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
