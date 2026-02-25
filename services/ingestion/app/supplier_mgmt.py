"""
Supplier Management Router.

Dashboard API for managing supplier portal links, tracking submissions,
and monitoring supplier compliance health.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.webhook_router import _verify_api_key

logger = logging.getLogger("supplier-mgmt")

router = APIRouter(prefix="/api/v1/suppliers", tags=["Supplier Management"])


class SupplierRecord(BaseModel):
    """A managed supplier record."""
    id: str
    name: str
    contact_email: str
    portal_link_id: Optional[str] = None
    portal_status: str  # "active", "expired", "pending", "no_link"
    submissions_count: int = 0
    last_submission: Optional[str] = None
    compliance_status: str  # "compliant", "partial", "non_compliant", "unknown"
    missing_kdes: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)


class SupplierDashboard(BaseModel):
    """Supplier management dashboard data."""
    tenant_id: str
    total_suppliers: int
    active_portal_links: int
    expired_portal_links: int
    total_submissions: int
    compliance_rate: float
    suppliers: list[SupplierRecord]


class CreateSupplierRequest(BaseModel):
    """Request to create a supplier record."""
    name: str
    contact_email: str
    products: list[str] = Field(default_factory=list)


# Sample supplier data
def _generate_sample_suppliers(tenant_id: str) -> list[SupplierRecord]:
    now = datetime.now(timezone.utc)
    return [
        SupplierRecord(
            id=f"{tenant_id}-sup-001",
            name="Valley Fresh Farms",
            contact_email="ops@valleyfresh.com",
            portal_link_id="portal-vff-001",
            portal_status="active",
            submissions_count=12,
            last_submission=(now - timedelta(hours=6)).isoformat(),
            compliance_status="compliant",
            products=["Romaine Lettuce", "Roma Tomatoes"],
        ),
        SupplierRecord(
            id=f"{tenant_id}-sup-002",
            name="Pacific Seafood Inc.",
            contact_email="trace@pacseafood.com",
            portal_link_id="portal-psi-002",
            portal_status="active",
            submissions_count=8,
            last_submission=(now - timedelta(days=2)).isoformat(),
            compliance_status="compliant",
            products=["Atlantic Salmon Fillets", "Pacific Cod"],
        ),
        SupplierRecord(
            id=f"{tenant_id}-sup-003",
            name="Sunrise Produce Co.",
            contact_email="quality@sunriseproduce.com",
            portal_link_id="portal-spc-003",
            portal_status="expired",
            submissions_count=3,
            last_submission=(now - timedelta(days=35)).isoformat(),
            compliance_status="partial",
            missing_kdes=["ship_from_gln", "carrier_name"],
            products=["English Cucumbers"],
        ),
        SupplierRecord(
            id=f"{tenant_id}-sup-004",
            name="Green Valley Organics",
            contact_email="farm@greenvalley.org",
            portal_link_id=None,
            portal_status="no_link",
            submissions_count=0,
            compliance_status="non_compliant",
            missing_kdes=["all — no submissions received"],
            products=["Mixed Salad Greens"],
        ),
        SupplierRecord(
            id=f"{tenant_id}-sup-005",
            name="Cold Express Logistics",
            contact_email="dispatch@coldexpress.com",
            portal_link_id="portal-cel-005",
            portal_status="active",
            submissions_count=22,
            last_submission=(now - timedelta(hours=1)).isoformat(),
            compliance_status="compliant",
            products=["Third-party logistics (temperature monitoring)"],
        ),
    ]


_suppliers_store: dict[str, list[SupplierRecord]] = {}


@router.get(
    "/{tenant_id}",
    response_model=SupplierDashboard,
    summary="Get supplier management dashboard",
)
async def get_supplier_dashboard(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
) -> SupplierDashboard:
    """Get supplier dashboard with compliance overview."""
    if tenant_id not in _suppliers_store:
        _suppliers_store[tenant_id] = _generate_sample_suppliers(tenant_id)

    suppliers = _suppliers_store[tenant_id]
    active_links = sum(1 for s in suppliers if s.portal_status == "active")
    expired_links = sum(1 for s in suppliers if s.portal_status == "expired")
    total_subs = sum(s.submissions_count for s in suppliers)
    compliant = sum(1 for s in suppliers if s.compliance_status == "compliant")

    return SupplierDashboard(
        tenant_id=tenant_id,
        total_suppliers=len(suppliers),
        active_portal_links=active_links,
        expired_portal_links=expired_links,
        total_submissions=total_subs,
        compliance_rate=round(compliant / len(suppliers) * 100, 1) if suppliers else 0,
        suppliers=suppliers,
    )


@router.post(
    "/{tenant_id}",
    summary="Add a supplier",
)
async def add_supplier(
    tenant_id: str,
    request: CreateSupplierRequest,
    _: None = Depends(_verify_api_key),
):
    """Add a new supplier to the management dashboard."""
    if tenant_id not in _suppliers_store:
        _suppliers_store[tenant_id] = _generate_sample_suppliers(tenant_id)

    new_supplier = SupplierRecord(
        id=f"{tenant_id}-sup-{len(_suppliers_store[tenant_id]) + 1:03d}",
        name=request.name,
        contact_email=request.contact_email,
        portal_status="no_link",
        compliance_status="unknown",
        products=request.products,
    )

    _suppliers_store[tenant_id].append(new_supplier)

    return {"created": True, "supplier": new_supplier.model_dump()}


@router.post(
    "/{tenant_id}/{supplier_id}/send-link",
    summary="Send portal link to supplier",
)
async def send_portal_link(
    tenant_id: str,
    supplier_id: str,
    _: None = Depends(_verify_api_key),
):
    """Generate and send a portal link to a supplier."""
    if tenant_id not in _suppliers_store:
        raise Exception("Tenant not found")

    for supplier in _suppliers_store[tenant_id]:
        if supplier.id == supplier_id:
            supplier.portal_link_id = f"portal-{supplier_id[-3:]}-new"
            supplier.portal_status = "active"
            return {
                "sent": True,
                "supplier_id": supplier_id,
                "portal_link": f"https://regengine.co/portal/{supplier.portal_link_id}",
                "message": f"Portal link sent to {supplier.contact_email}",
            }

    return {"sent": False, "error": "Supplier not found"}


@router.get(
    "/{tenant_id}/health",
    summary="Supplier network health summary",
)
async def supplier_health(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
):
    """Get supplier network health metrics."""
    if tenant_id not in _suppliers_store:
        _suppliers_store[tenant_id] = _generate_sample_suppliers(tenant_id)

    suppliers = _suppliers_store[tenant_id]
    now = datetime.now(timezone.utc)

    active_30d = 0
    inactive_30d = 0
    for s in suppliers:
        if s.last_submission:
            last = datetime.fromisoformat(s.last_submission)
            if (now - last).days <= 30:
                active_30d += 1
            else:
                inactive_30d += 1
        else:
            inactive_30d += 1

    return {
        "tenant_id": tenant_id,
        "total_suppliers": len(suppliers),
        "active_last_30_days": active_30d,
        "inactive_30_days": inactive_30d,
        "compliance_breakdown": {
            "compliant": sum(1 for s in suppliers if s.compliance_status == "compliant"),
            "partial": sum(1 for s in suppliers if s.compliance_status == "partial"),
            "non_compliant": sum(1 for s in suppliers if s.compliance_status == "non_compliant"),
            "unknown": sum(1 for s in suppliers if s.compliance_status == "unknown"),
        },
        "total_submissions": sum(s.submissions_count for s in suppliers),
    }
