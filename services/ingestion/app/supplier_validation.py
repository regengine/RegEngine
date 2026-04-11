"""
Supplier Validation Router.

Runs compliance validation checks against tenant suppliers and produces
scored reports indicating readiness for FSMA 204 audits.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.webhook_compat import _verify_api_key
from shared.database import get_db_safe
from shared.tenant_settings import get_tenant_data, set_tenant_data

logger = logging.getLogger("supplier-validation")


router = APIRouter(
    prefix="/api/v1/suppliers/validation",
    tags=["Supplier Validation"],
)

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class ValidationCheck(BaseModel):
    """A single validation check result."""
    name: str
    passed: bool
    details: str
    severity: str = Field(..., description="critical | warning | info")


class SupplierValidationResult(BaseModel):
    """Validation result for a single supplier."""
    supplier_id: str
    supplier_name: str
    status: str = Field(..., description="compliant | partial | non_compliant")
    checks: list[ValidationCheck] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    last_validated: str
    score: int = Field(..., ge=0, le=100)


class TenantSupplierReport(BaseModel):
    """Aggregate validation report for all tenant suppliers."""
    tenant_id: str
    total_suppliers: int
    compliant_count: int
    partial_count: int
    non_compliant_count: int
    overall_compliance_pct: float
    suppliers: list[SupplierValidationResult] = Field(default_factory=list)
    generated_at: str


# ---------------------------------------------------------------------------
# In-memory cache for latest reports (thread-safe)
# ---------------------------------------------------------------------------

_reports_store: dict[str, TenantSupplierReport] = {}
_reports_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Required CTE types per product category (simplified mapping)
_REQUIRED_CTE_TYPES: dict[str, list[str]] = {
    "produce": ["growing", "receiving", "shipping"],
    "seafood": ["harvesting", "receiving", "shipping"],
    "dairy": ["receiving", "transformation", "shipping"],
    "default": ["receiving", "shipping"],
}


def _fetch_suppliers(tenant_id: str) -> Optional[list[dict]]:
    """Fetch supplier rows from DB. Returns None if DB unavailable."""
    db = get_db_safe()
    if not db:
        return None
    try:
        import json
        rows = db.execute(
            text(
                "SELECT id, name, contact_email, portal_link_id, portal_status, "
                "submissions_count, last_submission, compliance_status, missing_kdes, "
                "products FROM fsma.tenant_suppliers WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        ).fetchall()
        suppliers = []
        for row in rows:
            suppliers.append({
                "id": row[0],
                "name": row[1],
                "contact_email": row[2],
                "portal_link_id": row[3],
                "portal_status": row[4],
                "submissions_count": row[5],
                "last_submission": row[6],
                "compliance_status": row[7],
                "missing_kdes": json.loads(row[8]) if row[8] else [],
                "products": json.loads(row[9]) if row[9] else [],
            })
        return suppliers
    except Exception as exc:
        logger.warning("db_read_failed error=%s", str(exc))
        return None
    finally:
        db.close()


def _fetch_supplier_submissions(tenant_id: str, supplier_id: str) -> Optional[list[dict]]:
    """Fetch recent submissions for a supplier. Returns None if DB unavailable."""
    db = get_db_safe()
    if not db:
        return None
    try:
        rows = db.execute(
            text(
                "SELECT cte_type, kde_completeness, gln FROM fsma.supplier_submissions "
                "WHERE tenant_id = :tid AND supplier_id = :sid "
                "ORDER BY submitted_at DESC LIMIT 100"
            ),
            {"tid": tenant_id, "sid": supplier_id},
        ).fetchall()
        return [{"cte_type": r[0], "kde_completeness": r[1], "gln": r[2]} for r in rows]
    except Exception as exc:
        logger.debug("supplier_submissions_query_failed error=%s", str(exc))
        return None
    finally:
        db.close()


def _validate_supplier(supplier: dict, tenant_id: str) -> SupplierValidationResult:
    """Run all validation checks on a single supplier."""
    now = datetime.now(timezone.utc)
    checks: list[ValidationCheck] = []
    missing: list[str] = []

    # 1. Recent submission check (critical)
    has_recent_submission = False
    if supplier.get("last_submission"):
        try:
            last = datetime.fromisoformat(str(supplier["last_submission"]).replace("Z", "+00:00"))
            if not last.tzinfo:
                last = last.replace(tzinfo=timezone.utc)
            has_recent_submission = (now - last).days <= 30
        except (ValueError, TypeError):
            pass

    checks.append(ValidationCheck(
        name="recent_submission",
        passed=has_recent_submission,
        details="Submitted within last 30 days" if has_recent_submission else "No submission in 30+ days",
        severity="critical",
    ))
    if not has_recent_submission:
        missing.append("Submission within last 30 days required")

    # 2. Portal status check (critical)
    portal_active = supplier.get("portal_status") == "active"
    checks.append(ValidationCheck(
        name="portal_status",
        passed=portal_active,
        details=f"Portal status: {supplier.get('portal_status', 'unknown')}",
        severity="critical",
    ))
    if not portal_active:
        missing.append("Active portal link required")

    # 3. Valid contact email (warning)
    email = supplier.get("contact_email", "")
    email_valid = bool(email and _EMAIL_RE.match(email))
    checks.append(ValidationCheck(
        name="valid_contact_email",
        passed=email_valid,
        details=f"Email: {email}" if email_valid else "Missing or invalid contact email",
        severity="warning",
    ))
    if not email_valid:
        missing.append("Valid contact email required")

    # 4. CTE type coverage (warning)
    products = supplier.get("products", [])
    submissions = _fetch_supplier_submissions(tenant_id, supplier["id"])
    submitted_cte_types: set[str] = set()
    kde_scores: list[float] = []
    has_gln = False

    if submissions:
        for sub in submissions:
            if sub.get("cte_type"):
                submitted_cte_types.add(sub["cte_type"].lower())
            if sub.get("kde_completeness") is not None:
                try:
                    kde_scores.append(float(sub["kde_completeness"]))
                except (ValueError, TypeError):
                    pass
            if sub.get("gln"):
                has_gln = True

    required_ctes: set[str] = set()
    for product in products:
        category = product.lower() if product.lower() in _REQUIRED_CTE_TYPES else "default"
        required_ctes.update(_REQUIRED_CTE_TYPES[category])

    if not required_ctes:
        required_ctes = set(_REQUIRED_CTE_TYPES["default"])

    cte_coverage = required_ctes.issubset(submitted_cte_types) if submitted_cte_types else False
    checks.append(ValidationCheck(
        name="cte_type_coverage",
        passed=cte_coverage,
        details=(
            f"Covers all required CTEs: {sorted(required_ctes)}"
            if cte_coverage
            else f"Missing CTE types: {sorted(required_ctes - submitted_cte_types)}"
        ),
        severity="warning",
    ))
    if not cte_coverage:
        missing_ctes = sorted(required_ctes - submitted_cte_types)
        missing.append(f"CTE type submissions needed: {', '.join(missing_ctes)}")

    # 5. KDE completeness (warning)
    avg_kde = (sum(kde_scores) / len(kde_scores)) if kde_scores else 0.0
    kde_ok = avg_kde >= 80.0
    checks.append(ValidationCheck(
        name="kde_completeness",
        passed=kde_ok,
        details=f"Average KDE completeness: {avg_kde:.1f}%" if kde_scores else "No KDE data available",
        severity="warning",
    ))
    if not kde_ok:
        missing.append("KDE completeness must be >= 80%")

    # 6. Valid GLN on file (info)
    checks.append(ValidationCheck(
        name="valid_gln",
        passed=has_gln,
        details="GLN on file" if has_gln else "No GLN associated with submissions",
        severity="info",
    ))
    if not has_gln:
        missing.append("GLN (Global Location Number) recommended")

    # Score calculation: start at 100, deduct per failed check
    score = 100
    for check in checks:
        if not check.passed:
            if check.severity == "critical":
                score -= 30
            elif check.severity == "warning":
                score -= 10
            elif check.severity == "info":
                score -= 5
    score = max(0, score)

    # Status based on score
    if score >= 80:
        status = "compliant"
    elif score >= 50:
        status = "partial"
    else:
        status = "non_compliant"

    return SupplierValidationResult(
        supplier_id=supplier["id"],
        supplier_name=supplier["name"],
        status=status,
        checks=checks,
        missing_requirements=missing,
        last_validated=now.isoformat(),
        score=score,
    )


def _build_report(tenant_id: str, results: list[SupplierValidationResult]) -> TenantSupplierReport:
    """Build aggregate report from individual results."""
    compliant = sum(1 for r in results if r.status == "compliant")
    partial = sum(1 for r in results if r.status == "partial")
    non_compliant = sum(1 for r in results if r.status == "non_compliant")
    total = len(results)

    report = TenantSupplierReport(
        tenant_id=tenant_id,
        total_suppliers=total,
        compliant_count=compliant,
        partial_count=partial,
        non_compliant_count=non_compliant,
        overall_compliance_pct=round(compliant / total * 100, 1) if total else 0.0,
        suppliers=results,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    with _reports_lock:
        _reports_store[tenant_id] = report

    # Write-through to DB for persistence across restarts
    try:
        report_data = report.model_dump() if hasattr(report, 'model_dump') else report.__dict__
        set_tenant_data(tenant_id, "supplier_reports", tenant_id, report_data)
    except Exception as exc:
        logger.warning("supplier_report_db_write_failed tenant=%s error=%s", tenant_id, str(exc))

    return report


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{tenant_id}/validate",
    response_model=TenantSupplierReport,
    summary="Validate all suppliers for a tenant",
)
async def validate_all_suppliers(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
) -> TenantSupplierReport:
    """Run validation checks against every supplier for the tenant."""
    suppliers = _fetch_suppliers(tenant_id)

    if suppliers is None:
        logger.info("db_unavailable, returning empty report for tenant=%s", tenant_id)
        suppliers = []

    results = [_validate_supplier(s, tenant_id) for s in suppliers]
    report = _build_report(tenant_id, results)
    logger.info(
        "validation_complete tenant=%s total=%d compliant=%d",
        tenant_id, report.total_suppliers, report.compliant_count,
    )
    return report


@router.post(
    "/{tenant_id}/{supplier_id}/validate",
    response_model=SupplierValidationResult,
    summary="Validate a single supplier",
)
async def validate_single_supplier(
    tenant_id: str,
    supplier_id: str,
    _: None = Depends(_verify_api_key),
) -> SupplierValidationResult:
    """Run validation checks against a single supplier."""
    suppliers = _fetch_suppliers(tenant_id)

    if suppliers is None:
        logger.info("db_unavailable, returning empty result for supplier=%s", supplier_id)
        suppliers = []

    for s in suppliers:
        if s["id"] == supplier_id:
            result = _validate_supplier(s, tenant_id)
            logger.info(
                "single_validation_complete supplier=%s score=%d status=%s",
                supplier_id, result.score, result.status,
            )
            return result

    # Supplier not found — return a non-compliant placeholder
    now = datetime.now(timezone.utc)
    return SupplierValidationResult(
        supplier_id=supplier_id,
        supplier_name="Unknown",
        status="non_compliant",
        checks=[
            ValidationCheck(
                name="supplier_exists",
                passed=False,
                details="Supplier not found in tenant records",
                severity="critical",
            ),
        ],
        missing_requirements=["Supplier must be registered"],
        last_validated=now.isoformat(),
        score=0,
    )


@router.get(
    "/{tenant_id}/report",
    response_model=TenantSupplierReport,
    summary="Get latest validation report",
)
async def get_validation_report(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
) -> TenantSupplierReport:
    """Return the most recently generated validation report for a tenant."""
    with _reports_lock:
        report = _reports_store.get(tenant_id)

    if not report:
        # Fall back to DB lookup
        try:
            db_data = get_tenant_data(tenant_id, "supplier_reports", tenant_id)
            if db_data:
                report = TenantSupplierReport(**db_data)
                # Re-populate in-memory cache
                with _reports_lock:
                    _reports_store[tenant_id] = report
        except Exception as exc:
            logger.warning("supplier_report_db_read_failed tenant=%s error=%s", tenant_id, str(exc))

    if report:
        return report

    # No cached report — generate a fresh one
    suppliers = _fetch_suppliers(tenant_id)
    if suppliers is None:
        suppliers = []

    results = [_validate_supplier(s, tenant_id) for s in suppliers]
    return _build_report(tenant_id, results)
