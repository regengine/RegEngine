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
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from shared.database import get_db_safe
from shared.env import is_production
from shared.pagination import PaginationParams
from shared.tenant_context import tenant_scope
from shared.tenant_rate_limiting import consume_tenant_rate_limit, rate_limit_reset_epoch
from sqlalchemy import text

from .authz import IngestionPrincipal, require_permission
from .inflow_workbench import (
    CommitGateDecision,
    CommitGateRequest,
    ReadinessSummary,
    build_readiness_summary,
    decide_commit_gate,
)
from .sandbox.csv_parser import _normalize_for_rules
from .sandbox.evaluators import _evaluate_event_stateless
from .sandbox.models import EventEvaluationResponse, RuleResultResponse, SandboxResponse
from .sandbox.validation import _validate_kdes
from .shared.tenant_resolution import resolve_principal_tenant_id
from .webhook_compat import ingest_events
from .webhook_models import IngestEvent, WebhookCTEType, WebhookPayload

logger = logging.getLogger("supplier-portal")

router = APIRouter(prefix="/api/v1/portal", tags=["Supplier Portal"])

# In-memory portal link store (fallback when DB is unavailable)
_portal_links: dict[str, dict] = {}


def _allow_memory_fallback() -> bool:
    """Allow volatile portal-link fallback only outside production."""
    return not is_production()


# Issue #2508 — per-portal-link abuse controls.
#
# The public, link-authenticated portal endpoints declare no auth and were
# covered only by the coarse per-IP global middleware (preflight) and the
# victim-tenant-scoped webhook limiter (submit). Both backstops are evadable
# and neither is scoped to the portal link itself. These per-link buckets are
# keyed on ``portal:{portal_id}`` so abuse on one link cannot consume the
# owning tenant's general ``webhooks.ingest`` budget.
_PORTAL_PREFLIGHT_RATE_LIMIT_RPM = max(1, int(os.getenv("PORTAL_PREFLIGHT_RATE_LIMIT_RPM", "30")))
_PORTAL_SUBMIT_RATE_LIMIT_RPM = max(1, int(os.getenv("PORTAL_SUBMIT_RATE_LIMIT_RPM", "20")))
_PORTAL_RATE_LIMIT_WINDOW_SECS = max(1, int(os.getenv("PORTAL_RATE_LIMIT_WINDOW_SECONDS", "60")))


def _enforce_portal_rate_limit(portal_id: str, tenant_id: str, *, scope: str, limit: int) -> None:
    """Per-portal-link sliding-window limit. Raises HTTP 429 when exceeded.

    Keyed on ``portal:{portal_id}`` (not the bare tenant_id) so each link gets
    its own bucket and one abused link does not starve the owning tenant's
    other ingestion budgets.
    """
    allowed, _remaining = consume_tenant_rate_limit(
        tenant_id=tenant_id,
        bucket_suffix=f"portal:{portal_id}:{scope}",
        limit=limit,
        window=_PORTAL_RATE_LIMIT_WINDOW_SECS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(f"Portal rate limit exceeded ({limit}/{_PORTAL_RATE_LIMIT_WINDOW_SECS}s for this link)"),
            headers={
                "Retry-After": str(_PORTAL_RATE_LIMIT_WINDOW_SECS),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(rate_limit_reset_epoch(_PORTAL_RATE_LIMIT_WINDOW_SECS)),
                "X-RateLimit-Scope": f"portal:{portal_id}:{scope}",
            },
        )


def _portal_subscription_active(tenant_id: str) -> Optional[bool]:
    """Check the owning tenant's subscription status for a portal submission.

    Returns:
      * ``True``  — tenant has an active/trialing subscription (allow).
      * ``False`` — Redis is reachable but the tenant has no active subscription
        (block before persistence).
      * ``None``  — subscription checking is not configured for this deploy
        (no Redis) OUTSIDE production; the caller skips the gate so local/dev
        submissions are not broken.

    In production, uncertainty is never permissive: an unreachable Redis, an
    open circuit, an unexpected error, or an unset ``REDIS_URL`` raises 503
    rather than skipping the gate. This matches the documented contract for
    every other paid surface — "Redis/circuit uncertainty returns 503 because
    the service cannot confirm entitlement state" (README, Security And Tenant
    Boundaries) and ``subscription_gate.require_active_subscription``. Before
    this, a Redis incident silently downgraded the portal to ungated and
    persisted supplier evidence for tenants with no active subscription.

    Mirrors ``subscription_gate.require_active_subscription`` but is callable
    with the link's tenant_id, since the portal has no authenticated principal.
    """
    if not os.getenv("REDIS_URL"):
        if is_production():
            raise _portal_entitlement_unavailable("redis_not_configured")
        return None
    from .subscription_gate import _check_subscription_and_redis_health

    try:
        status, redis_available = _check_subscription_and_redis_health(tenant_id)
    except Exception as exc:
        # Circuit open / unexpected error — cannot confirm entitlement state.
        if is_production():
            raise _portal_entitlement_unavailable("subscription_check_failed") from exc
        return None
    if not redis_available:
        if is_production():
            raise _portal_entitlement_unavailable("redis_unavailable")
        return None
    return (status or "").lower() in {"active", "trialing"}


def _portal_entitlement_unavailable(reason: str) -> HTTPException:
    logger.error("portal_subscription_check_unavailable", extra={"reason": reason})
    return HTTPException(
        status_code=503,
        detail="Subscription status cannot be confirmed right now — submission not accepted. Please retry shortly.",
        headers={"Retry-After": "30"},
    )


def _set_tenant_context(db, tenant_id: str) -> None:
    # Phase B (#1934): delegate to the canonical tenant-GUC primitive. The
    # _if_uuid variant preserves portal behavior for non-UUID tenant slugs
    # (the GUC is skipped; fail-hard get_tenant_context() RLS still rejects
    # DB access without tenant context).
    from shared.tenant_context import set_tenant_guc_if_uuid

    set_tenant_guc_if_uuid(db, tenant_id)


def _db_store_portal_link(portal_id: str, link_data: dict) -> bool:
    """Insert a portal link into the database. Returns True on success."""
    db = get_db_safe()
    if not db:
        return False
    try:
        _set_tenant_context(db, link_data["tenant_id"])
        try:
            db.execute(
                # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
                text("""
                    INSERT INTO fsma.tenant_portal_links
                    (id, tenant_id, supplier_name, supplier_email, allowed_cte_types,
                     integration_profile_id, link_token, status, created_at, expires_at)
                    VALUES (gen_random_uuid(), :tenant_id, :supplier_name, :supplier_email,
                            :allowed_cte_types, :integration_profile_id, :link_token,
                            'active', :created_at, :expires_at)
                    ON CONFLICT (link_token) DO UPDATE SET
                        supplier_name = :supplier_name,
                        supplier_email = :supplier_email,
                        allowed_cte_types = :allowed_cte_types,
                        integration_profile_id = :integration_profile_id,
                        status = 'active',
                        expires_at = :expires_at
                """),
                {
                    "tenant_id": link_data["tenant_id"],
                    "supplier_name": link_data["supplier_name"],
                    "supplier_email": link_data.get("supplier_email"),
                    "allowed_cte_types": link_data.get("allowed_cte_types") or ["shipping"],
                    "integration_profile_id": link_data.get("integration_profile_id"),
                    "link_token": portal_id,
                    "created_at": link_data["created_at"],
                    "expires_at": link_data["expires_at"],
                },
            )
        except Exception as exc:
            if (
                "supplier_email" not in str(exc)
                and "allowed_cte_types" not in str(exc)
                and "integration_profile_id" not in str(exc)
            ):
                raise
            db.rollback()
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
    db = get_db_safe()
    if not db:
        return None
    try:
        try:
            row = db.execute(
                # nosemgrep: avoid-sqlalchemy-text — SECURITY DEFINER function, parameterized token
                text("""
                    SELECT tenant_id, supplier_name, supplier_email, allowed_cte_types,
                           integration_profile_id, link_token, status, created_at, expires_at
                    FROM fsma.get_active_portal_link_by_token(:link_token)
                """),
                {"link_token": portal_id},
            ).fetchone()
            if row and len(row) >= 9:
                return {
                    "tenant_id": str(row[0]),
                    "supplier_name": row[1],
                    "supplier_email": row[2],
                    "allowed_cte_types": list(row[3] or ["shipping"]),
                    "integration_profile_id": row[4],
                    "expires_at": row[8].isoformat() if row[8] else None,
                    "created_at": row[7].isoformat() if row[7] else None,
                }
        except Exception as exc:
            logger.debug("portal_link_function_lookup_unavailable error=%s", str(exc))
            db.rollback()

        try:
            row = db.execute(
                # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
                text("""
                    SELECT tenant_id, supplier_name, supplier_email, allowed_cte_types,
                           integration_profile_id, link_token, status, created_at, expires_at
                    FROM fsma.tenant_portal_links
                    WHERE link_token = :link_token AND status = 'active'
                """),
                {"link_token": portal_id},
            ).fetchone()
            if not row:
                return None
            if len(row) < 9:
                return {
                    "tenant_id": str(row[0]),
                    "supplier_name": row[1],
                    "supplier_email": None,
                    "allowed_cte_types": ["shipping"],
                    "integration_profile_id": None,
                    "expires_at": row[5].isoformat() if row[5] else None,
                    "created_at": row[4].isoformat() if row[4] else None,
                }
            return {
                "tenant_id": str(row[0]),
                "supplier_name": row[1],
                "supplier_email": row[2],
                "allowed_cte_types": list(row[3] or ["shipping"]),
                "integration_profile_id": row[4],
                "expires_at": row[8].isoformat() if row[8] else None,
                "created_at": row[7].isoformat() if row[7] else None,
            }
        except Exception as exc:
            if (
                "supplier_email" not in str(exc)
                and "allowed_cte_types" not in str(exc)
                and "integration_profile_id" not in str(exc)
            ):
                raise
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
            "integration_profile_id": None,
            "expires_at": row[5].isoformat() if row[5] else None,
            "created_at": row[4].isoformat() if row[4] else None,
        }
    except Exception as exc:
        logger.warning("db_get_portal_link_failed error=%s", str(exc))
        return None
    finally:
        db.close()


def _db_update_portal_link_status(portal_id: str, status: str, tenant_id: Optional[str] = None) -> bool:
    """Update the status of a portal link in the database."""
    db = get_db_safe()
    if not db:
        return False
    try:
        if tenant_id:
            _set_tenant_context(db, tenant_id)
            db.execute(
                # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
                text(
                    "UPDATE fsma.tenant_portal_links SET status = :status "
                    "WHERE link_token = :link_token AND tenant_id = CAST(:tenant_id AS uuid)"
                ),
                {"status": status, "link_token": portal_id, "tenant_id": tenant_id},
            )
        else:
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
    if link is None and _allow_memory_fallback():
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
        _db_update_portal_link_status(portal_id, "expired", link["tenant_id"])
        raise HTTPException(status_code=404, detail="Portal link not found or expired")

    return link


def _db_get_integration_profile_summary(tenant_id: str, profile_id: Optional[str]) -> Optional[dict]:
    """Return non-secret profile metadata safe to show to a supplier."""
    if not profile_id:
        return None
    db = get_db_safe()
    if db:
        try:
            _set_tenant_context(db, tenant_id)
            row = db.execute(
                # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
                text("""
                    SELECT profile_id, display_name, source_type, default_cte_type, status,
                           confidence, supplier_name
                    FROM fsma.supplier_integration_profiles
                    WHERE tenant_id = CAST(:tenant_id AS uuid)
                      AND profile_id = :profile_id
                """),
                {"tenant_id": tenant_id, "profile_id": profile_id},
            ).fetchone()
            if row:
                return {
                    "profile_id": row[0],
                    "display_name": row[1],
                    "source_type": row[2],
                    "default_cte_type": row[3],
                    "status": row[4],
                    "confidence": float(row[5] or 0),
                    "supplier_name": row[6],
                }
        except Exception as exc:
            logger.warning("portal_profile_summary_failed portal_profile=%s error=%s", profile_id, str(exc))
        finally:
            db.close()

    if not _allow_memory_fallback():
        return None

    try:
        from .integration_router import _memory_get_profile

        profile = _memory_get_profile(tenant_id, profile_id)
        if not profile:
            return None
        return {
            "profile_id": profile.profile_id,
            "display_name": profile.display_name,
            "source_type": profile.source_type,
            "default_cte_type": profile.default_cte_type,
            "status": profile.status,
            "confidence": float(profile.confidence or 0),
            "supplier_name": profile.supplier_name,
        }
    except Exception as exc:
        logger.warning("portal_profile_summary_memory_failed portal_profile=%s error=%s", profile_id, str(exc))
        return None


class CreatePortalLinkRequest(BaseModel):
    """Request to create a supplier portal link."""

    tenant_id: str = Field(..., description="Customer's tenant ID")
    supplier_name: str = Field(..., description="Supplier business name")
    supplier_email: Optional[str] = Field(None, description="Supplier contact email")
    allowed_cte_types: list[str] = Field(
        default=["shipping"], description="CTE types the supplier can submit (default: shipping only)"
    )
    integration_profile_id: Optional[str] = Field(
        default=None,
        description="Optional saved integration profile to attach to this supplier link",
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
    integration_profile_id: Optional[str] = None


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


class SupplierPreflightResult(BaseModel):
    """Validate supplier-submitted data before committing it."""

    status: str
    message: str
    supplier_name: str
    result: SandboxResponse
    readiness: ReadinessSummary
    commit_gate: CommitGateDecision


def _submission_event_dict(portal_id: str, link: dict, submission: SupplierSubmission) -> dict:
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
    kdes["reference_document"] = submission.po_number or f"supplier-portal:{portal_id}"
    kdes["tlc_source_reference"] = link["supplier_name"]
    kdes["ftl_covered"] = True
    if submission.temperature_celsius is not None:
        kdes["temperature_celsius"] = submission.temperature_celsius
    if submission.notes:
        kdes["notes"] = submission.notes

    return {
        "cte_type": "shipping",
        "traceability_lot_code": submission.traceability_lot_code,
        "product_description": submission.product_description,
        "quantity": submission.quantity,
        "unit_of_measure": submission.unit_of_measure,
        "location_gln": submission.ship_from_gln,
        "location_name": submission.ship_from_location,
        "ship_from_location": submission.ship_from_location,
        "ship_to_location": submission.ship_to_location,
        "reference_document": kdes["reference_document"],
        "tlc_source_reference": kdes["tlc_source_reference"],
        "timestamp": f"{submission.ship_date}T00:00:00Z",
        "kdes": kdes,
    }


def _build_supplier_preflight(portal_id: str, link: dict, submission: SupplierSubmission) -> SupplierPreflightResult:
    raw_event = _submission_event_dict(portal_id, link, submission)
    canonical = _normalize_for_rules(raw_event)
    kde_errors = _validate_kdes(raw_event)
    summary = _evaluate_event_stateless(canonical, include_custom=False)

    blocking: list[RuleResultResponse] = []
    blocking_reasons: list[str] = []
    for rule in summary.results:
        if rule.result == "fail" and rule.severity == "critical":
            reason = rule.why_failed or rule.rule_title
            blocking_reasons.append(f"Event 1 (shipping): {reason}")
            blocking.append(
                RuleResultResponse(
                    rule_title=rule.rule_title,
                    severity=rule.severity,
                    result=rule.result,
                    why_failed=rule.why_failed,
                    citation=rule.citation_reference,
                    remediation=rule.remediation_suggestion,
                    category=rule.category,
                    evidence=rule.evidence_fields_inspected or None,
                )
            )

    blocking_reasons.extend(f"Event 1 (shipping): {error}" for error in kde_errors)
    compliant = not kde_errors and summary.compliant
    sandbox_result = SandboxResponse(
        total_events=1,
        compliant_events=1 if compliant else 0,
        non_compliant_events=0 if compliant else 1,
        total_kde_errors=len(kde_errors),
        total_rule_failures=summary.failed,
        submission_blocked=bool(kde_errors or blocking),
        blocking_reasons=list(dict.fromkeys(blocking_reasons)),
        duplicate_warnings=[],
        entity_warnings=[],
        normalizations=[],
        events=[
            EventEvaluationResponse(
                event_index=0,
                cte_type="shipping",
                traceability_lot_code=submission.traceability_lot_code,
                product_description=submission.product_description,
                kde_errors=kde_errors,
                rules_evaluated=summary.total_rules,
                rules_passed=summary.passed,
                rules_failed=summary.failed,
                rules_warned=summary.warned,
                compliant=compliant,
                blocking_defects=blocking,
                all_results=[
                    RuleResultResponse(
                        rule_title=rule.rule_title,
                        severity=rule.severity,
                        result=rule.result,
                        why_failed=rule.why_failed,
                        citation=rule.citation_reference,
                        remediation=rule.remediation_suggestion,
                        category=rule.category,
                        evidence=rule.evidence_fields_inspected or None,
                    )
                    for rule in summary.results
                ],
            )
        ],
    )
    readiness = build_readiness_summary(sandbox_result)
    commit_gate = decide_commit_gate(
        CommitGateRequest(
            mode="preflight",
            tenant_id=link["tenant_id"],
            result=sandbox_result,
            authenticated=True,
            persisted=False,
            provenance_attached=True,
        )
    )
    status = "ready" if not sandbox_result.submission_blocked else "blocked"
    message = (
        "Supplier record passed preflight and can be submitted."
        if status == "ready"
        else "Supplier record is blocked. Correct the listed KDE/rule issues before submission."
    )
    return SupplierPreflightResult(
        status=status,
        message=message,
        supplier_name=link["supplier_name"],
        result=sandbox_result,
        readiness=readiness,
        commit_gate=commit_gate,
    )


@router.post(
    "/links",
    response_model=PortalLinkResponse,
    summary="Create a supplier portal link",
    description="Generate a unique, expiring link that a supplier can use to submit shipping data.",
)
async def create_portal_link(
    request: CreatePortalLinkRequest,
    principal: IngestionPrincipal = Depends(require_permission("webhooks.ingest")),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> PortalLinkResponse:
    """Create a supplier portal link."""
    tenant_id = resolve_principal_tenant_id(request.tenant_id, x_tenant_id, principal.tenant_id)
    portal_id = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=request.expires_days)).isoformat()

    link_data = {
        "tenant_id": tenant_id,
        "supplier_name": request.supplier_name,
        "supplier_email": request.supplier_email,
        "allowed_cte_types": request.allowed_cte_types,
        "integration_profile_id": request.integration_profile_id,
        "expires_at": expires_at,
        "created_at": now.isoformat(),
    }

    # Try DB first, fall back to in-memory
    db_success = _db_store_portal_link(portal_id, link_data)
    if not db_success:
        if not _allow_memory_fallback():
            raise HTTPException(status_code=503, detail="Portal link persistence unavailable")
        logger.info("db_store_fallback using in-memory for portal_id=%s", portal_id)
    # Always store in-memory as well for supplemental fields (supplier_email, allowed_cte_types)
    _portal_links[portal_id] = link_data

    logger.info(
        "portal_link_created",
        extra={
            "portal_id": portal_id,
            "tenant_id": tenant_id,
            "supplier_name": request.supplier_name,
        },
    )

    return PortalLinkResponse(
        portal_id=portal_id,
        portal_url=f"https://regengine.co/portal/{portal_id}",
        supplier_name=request.supplier_name,
        tenant_id=tenant_id,
        expires_at=expires_at,
        allowed_cte_types=request.allowed_cte_types,
        integration_profile_id=request.integration_profile_id,
    )


@router.get(
    "/links/list",
    summary="List portal links for a tenant",
    description="Returns all portal links for the authenticated tenant.",
)
async def list_portal_links(
    tenant_id: Optional[str] = None,
    pagination: PaginationParams = Depends(),
    principal: IngestionPrincipal = Depends(require_permission("webhooks.ingest")),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
):
    """List all portal links for a tenant."""
    tenant_id = resolve_principal_tenant_id(tenant_id, x_tenant_id, principal.tenant_id)
    links: list[dict] = []

    # Try DB first
    db = get_db_safe()
    if db:
        try:
            _set_tenant_context(db, tenant_id)
            try:
                rows = db.execute(
                    # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
                    text("""
                        SELECT id, tenant_id, supplier_name, link_token, status, created_at, expires_at,
                               integration_profile_id
                        FROM fsma.tenant_portal_links
                        WHERE tenant_id = :tenant_id
                        ORDER BY created_at DESC
                    """),
                    {"tenant_id": tenant_id},
                ).fetchall()
            except Exception as exc:
                if "integration_profile_id" not in str(exc):
                    raise
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
                integration_profile_id = row[7] if len(row) > 7 else None
                # Auto-expire links past their expiry
                if status == "active" and expires_at and expires_at <= datetime.now(timezone.utc):
                    status = "expired"
                links.append(
                    {
                        "portal_id": row[3],
                        "portal_url": f"https://regengine.co/portal/{row[3]}",
                        "supplier_name": row[2],
                        "tenant_id": str(row[1]),
                        "status": status,
                        "created_at": row[5].isoformat() if row[5] else None,
                        "expires_at": expires_at.isoformat() if expires_at else None,
                        "integration_profile_id": str(integration_profile_id) if integration_profile_id else None,
                    }
                )
        except Exception as exc:
            logger.warning("list_portal_links_db_failed error=%s", str(exc))
        finally:
            db.close()

    # Supplement with in-memory links not in DB results
    db_tokens = {link["portal_id"] for link in links}
    if _allow_memory_fallback():
        for token, entry in _portal_links.items():
            # Filter the in-memory cache to entries owned by the authoritative
            # tenant_id argument — we are NOT trusting tenant_id from a request
            # body, just scoping the in-memory store like a WHERE clause would.
            if entry.get("tenant_id") != tenant_id or token in db_tokens:
                continue
            expires_at_raw = entry.get("expires_at")
            status = "active"
            if expires_at_raw:
                try:
                    exp = datetime.fromisoformat(str(expires_at_raw).replace("Z", "+00:00"))
                    if exp <= datetime.now(timezone.utc):
                        status = "expired"
                except ValueError:
                    pass
            links.append(
                {
                    "portal_id": token,
                    "portal_url": f"https://regengine.co/portal/{token}",
                    "supplier_name": entry.get("supplier_name", "Unknown"),
                    "tenant_id": tenant_id,
                    "status": status,
                    "created_at": entry.get("created_at"),
                    "expires_at": expires_at_raw,
                    "integration_profile_id": entry.get("integration_profile_id"),
                }
            )

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
    principal: IngestionPrincipal = Depends(require_permission("webhooks.ingest")),
):
    """Revoke a portal link."""
    link = _db_get_portal_link(portal_id)
    if link is None and _allow_memory_fallback():
        link = _portal_links.get(portal_id)
    if link is None:
        # #2461: refuse instead of issuing a tenantless UPDATE —
        # _db_update_portal_link_status(tenant_id=None) can never
        # succeed under RLS and silently reported failure before.
        raise HTTPException(status_code=404, detail="Portal link not found or expired")
    if principal.tenant_id and link.get("tenant_id") != principal.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Tenant mismatch: your API key does not have access to this tenant.",
        )
    # Update DB
    db_updated = _db_update_portal_link_status(
        portal_id,
        "revoked",
        link.get("tenant_id"),
    )
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
    # #2461: public unauthenticated route — the tenant is unknown until
    # the portal-link row is read (via the SECURITY DEFINER
    # fsma.get_active_portal_link_by_token). Scope the remainder of the
    # handler to the link's tenant so the begin-hook covers all queries.
    with tenant_scope(link["tenant_id"]):
        profile = _db_get_integration_profile_summary(link["tenant_id"], link.get("integration_profile_id"))

    return {
        "portal_id": portal_id,
        "supplier_name": link["supplier_name"],
        "allowed_cte_types": link["allowed_cte_types"],
        "integration_profile_id": link.get("integration_profile_id"),
        "integration_profile": profile,
        "status": "active",
    }


@router.post(
    "/{portal_id}/preflight",
    response_model=SupplierPreflightResult,
    summary="Preflight supplier data",
    description="Validate supplier-submitted shipment data before creating a persisted event.",
)
async def preflight_supplier_data(
    portal_id: str,
    submission: SupplierSubmission,
) -> SupplierPreflightResult:
    """Run the supplier submission through the Workbench validation gate."""
    link = _get_active_portal_link(portal_id)
    # #2461: public route — scope to the link's tenant (see get_portal_details).
    with tenant_scope(link["tenant_id"]):
        # Issue #2508 — per-link throttle for CPU-heavy sandbox validation, scoped
        # to the portal link so it cannot be driven at the full per-IP ceiling.
        _enforce_portal_rate_limit(
            portal_id,
            link["tenant_id"],
            scope="preflight",
            limit=_PORTAL_PREFLIGHT_RATE_LIMIT_RPM,
        )
        return _build_supplier_preflight(portal_id, link, submission)


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

    # #2461: public route — the portal-link row binds the token to exactly
    # one tenant; scope the remainder of the handler (including the
    # awaited ingest_events persistence) to it so the Engine begin-hook
    # applies app.tenant_id on every transaction.
    with tenant_scope(link["tenant_id"]):
        return await _submit_supplier_data_inner(portal_id, link, submission)


async def _submit_supplier_data_inner(
    portal_id: str,
    link: dict,
    submission: SupplierSubmission,
) -> SubmissionResult:
    """Body of submit_supplier_data — runs inside tenant_scope(link tenant)."""
    # Issue #2508 — per-link submission cap. Scoped to the portal link, not the
    # victim tenant's general ingest budget, and enforced BEFORE any persisted
    # write so abuse past the cap never reaches ``ingest_events``.
    _enforce_portal_rate_limit(
        portal_id,
        link["tenant_id"],
        scope="submit",
        limit=_PORTAL_SUBMIT_RATE_LIMIT_RPM,
    )

    # Issue #2508 — gate persisted writes on the owning tenant's subscription.
    # The portal has no authenticated principal, so we check the link's tenant
    # directly. ``None`` means subscription checking is not configured for this
    # deploy (no Redis) and the gate is skipped.
    if _portal_subscription_active(link["tenant_id"]) is False:
        return SubmissionResult(
            status="error",
            message="Submission rejected: the receiving organization does not have an active subscription.",
            supplier_name=link["supplier_name"],
            submitted_at=datetime.now(timezone.utc).isoformat(),
        )

    preflight = _build_supplier_preflight(portal_id, link, submission)
    if preflight.status == "blocked":
        return SubmissionResult(
            status="error",
            message=f"Submission blocked by preflight: {'; '.join(preflight.result.blocking_reasons)}",
            supplier_name=link["supplier_name"],
            submitted_at=datetime.now(timezone.utc).isoformat(),
        )

    # Build KDEs
    event_data = _submission_event_dict(portal_id, link, submission)
    kdes: dict = event_data["kdes"]

    # Create event
    event = IngestEvent(
        cte_type=WebhookCTEType.SHIPPING,
        traceability_lot_code=submission.traceability_lot_code,
        product_description=submission.product_description,
        quantity=submission.quantity,
        unit_of_measure=submission.unit_of_measure,
        location_gln=submission.ship_from_gln,
        location_name=submission.ship_from_location,
        timestamp=event_data["timestamp"],
        kdes=kdes,
    )

    # Ingest into customer's tenant. The portal link record IS the
    # authenticated context here — the supplier's identity is verified
    # via the portal token, and the link binds that token to exactly
    # one customer tenant. Passing link["tenant_id"] as principal makes
    # the symmetric verification trivially pass while keeping the
    # contract enforceable for any future caller.
    payload = WebhookPayload(
        source="supplier_portal",
        events=[event],
        tenant_id=link["tenant_id"],
    )
    result = await ingest_events(payload, principal_tenant_id=link["tenant_id"])

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
