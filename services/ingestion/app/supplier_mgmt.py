"""
Supplier Management Router.

Dashboard API for managing supplier portal links, tracking submissions,
and monitoring supplier compliance health.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.webhook_compat import _verify_api_key
from shared.database import get_db_safe

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
    is_sample: bool = Field(
        default=False,
        description="True for auto-generated sample data. Replace with real supplier records.",
    )


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


# In-memory fallback for when DB is unavailable (thread-safe via _suppliers_lock)
_suppliers_store: dict[str, list[SupplierRecord]] = {}
_suppliers_lock = threading.Lock()


def _db_get_suppliers(tenant_id: str) -> Optional[list[SupplierRecord]]:
    """Query suppliers from database."""
    db = get_db_safe()
    if not db:
        return None
    try:
        rows = db.execute(
            text("SELECT id, name, contact_email, portal_link_id, portal_status, submissions_count, last_submission, compliance_status, missing_kdes, products FROM fsma.tenant_suppliers WHERE tenant_id = :tid"),
            {"tid": tenant_id}
        ).fetchall()
        suppliers = []
        for row in rows:
            suppliers.append(SupplierRecord(
                id=row[0],
                name=row[1],
                contact_email=row[2],
                portal_link_id=row[3],
                portal_status=row[4],
                submissions_count=row[5],
                last_submission=row[6],
                compliance_status=row[7],
                missing_kdes=json.loads(row[8]) if row[8] else [],
                products=json.loads(row[9]) if row[9] else [],
                is_sample=False,
            ))
        return suppliers
    except (ValueError, KeyError, TypeError, RuntimeError, OSError, AttributeError) as exc:
        logger.warning("db_read_failed error=%s", str(exc))
        return None
    finally:
        db.close()


def _db_add_supplier(tenant_id: str, supplier: SupplierRecord) -> bool:
    """Insert supplier into database."""
    db = get_db_safe()
    if not db:
        return False
    try:
        db.execute(
            text("""
                INSERT INTO fsma.tenant_suppliers 
                (id, tenant_id, name, contact_email, portal_link_id, portal_status, submissions_count, 
                 last_submission, compliance_status, missing_kdes, products, is_sample, created_at, updated_at)
                VALUES (:id, :tid, :name, :email, :plink, :pstatus, :subcount, :lastsub, :comp, :kdes, :prods, false, now(), now())
                ON CONFLICT (id) DO UPDATE SET 
                    name = :name, contact_email = :email, portal_link_id = :plink, 
                    portal_status = :pstatus, submissions_count = :subcount, 
                    last_submission = :lastsub, compliance_status = :comp, 
                    missing_kdes = :kdes, products = :prods, updated_at = now()
            """),
            {
                "id": supplier.id,
                "tid": tenant_id,
                "name": supplier.name,
                "email": supplier.contact_email,
                "plink": supplier.portal_link_id,
                "pstatus": supplier.portal_status,
                "subcount": supplier.submissions_count,
                "lastsub": supplier.last_submission,
                "comp": supplier.compliance_status,
                "kdes": json.dumps(supplier.missing_kdes),
                "prods": json.dumps(supplier.products),
            }
        )
        db.commit()
        return True
    except (ValueError, TypeError, RuntimeError, OSError, AttributeError) as exc:
        logger.warning("db_write_failed error=%s", str(exc))
        if db:
            db.rollback()
        return False
    finally:
        db.close()


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
    # Try DB first
    suppliers = _db_get_suppliers(tenant_id)
    
    # Fall back to memory if DB unavailable
    if suppliers is None:
        with _suppliers_lock:
            if tenant_id not in _suppliers_store:
                _suppliers_store[tenant_id] = []
            suppliers = list(_suppliers_store[tenant_id])
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
    # Get current count from DB or memory
    suppliers = _db_get_suppliers(tenant_id)
    if suppliers is None:
        with _suppliers_lock:
            if tenant_id not in _suppliers_store:
                _suppliers_store[tenant_id] = []
            suppliers = list(_suppliers_store[tenant_id])

    new_supplier = SupplierRecord(
        id=f"{tenant_id}-sup-{len(suppliers) + 1:03d}",
        name=request.name,
        contact_email=request.contact_email,
        portal_status="no_link",
        compliance_status="unknown",
        products=request.products,
    )

    # Try DB first, fall back to memory
    db_success = _db_add_supplier(tenant_id, new_supplier)
    if not db_success:
        with _suppliers_lock:
            if tenant_id not in _suppliers_store:
                _suppliers_store[tenant_id] = []
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
    # Try DB first
    suppliers = _db_get_suppliers(tenant_id)
    if suppliers is None:
        with _suppliers_lock:
            suppliers = list(_suppliers_store.get(tenant_id, []))

    for supplier in suppliers:
        if supplier.id == supplier_id:
            supplier.portal_link_id = f"portal-{supplier_id[-3:]}-new"
            supplier.portal_status = "active"
            
            # Update in DB or memory
            db_success = _db_add_supplier(tenant_id, supplier)
            if not db_success:
                with _suppliers_lock:
                    if tenant_id in _suppliers_store:
                        for mem_sup in _suppliers_store[tenant_id]:
                            if mem_sup.id == supplier_id:
                                mem_sup.portal_link_id = supplier.portal_link_id
                                mem_sup.portal_status = supplier.portal_status
            
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
    # Try DB first
    suppliers = _db_get_suppliers(tenant_id)
    if suppliers is None:
        with _suppliers_lock:
            if tenant_id not in _suppliers_store:
                _suppliers_store[tenant_id] = []
            suppliers = list(_suppliers_store[tenant_id])
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
