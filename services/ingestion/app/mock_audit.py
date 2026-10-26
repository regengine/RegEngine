"""
Mock Audit Router.

Simulates an FDA traceability records request per 21 CFR 1.1455.
The FDA can request records within 24 hours — this endpoint generates
a realistic request, starts a timer, and grades the response.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from shared.tenant_context import TenantContext

from .webhook_compat import require_tenant_context

logger = logging.getLogger("mock-audit")


def _get_real_tlc(tenant_id: str) -> str | None:
    """Return the tenant's most recently recorded TLC, or None.

    Deterministic on purpose (SEL-513): a drill targets a real lot from the
    tenant's own records, never a randomly picked or invented one.
    """
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    "SELECT traceability_lot_code FROM fsma.cte_events "
                    "WHERE tenant_id = :tid AND traceability_lot_code IS NOT NULL "
                    "ORDER BY event_timestamp DESC NULLS LAST, id DESC LIMIT 1"
                ),
                {"tid": tenant_id},
            ).fetchone()
            return row[0] if row else None
        finally:
            db.close()
    except Exception:
        logger.warning("Mock audit TLC lookup failed", exc_info=True)
        return None


def _get_product_for_tlc(tenant_id: str, tlc: str) -> str | None:
    """Return the recorded product description for a tenant's TLC, or None."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    "SELECT product_description FROM fsma.cte_events "
                    "WHERE tenant_id = :tid AND traceability_lot_code = :tlc "
                    "AND product_description IS NOT NULL "
                    "ORDER BY event_timestamp DESC NULLS LAST, id DESC LIMIT 1"
                ),
                {"tid": tenant_id, "tlc": tlc},
            ).fetchone()
            return row[0] if row else None
        finally:
            db.close()
    except Exception:
        logger.warning("Mock audit product lookup failed", exc_info=True)
        return None


def _persist_drill(drill_id: str, drill: dict) -> None:
    """Persist a self-assessment drill before acknowledging it."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        scenario = drill["scenario"]
        db = SessionLocal()
        try:
            db.execute(
                text(
                    "INSERT INTO fsma.mock_audit_drills "
                    "(drill_id, tenant_id, scenario, target_tlc, demo_mode, status, started_at, deadline) "
                    "VALUES (:drill_id, CAST(:tid AS uuid), CAST(:scenario AS jsonb), :target_tlc, "
                    ":demo_mode, :status, CAST(:started_at AS timestamptz), CAST(:deadline AS timestamptz)) "
                    "ON CONFLICT (tenant_id, drill_id) DO NOTHING"
                ),
                {
                    "drill_id": drill_id,
                    "tid": drill["tenant_id"],
                    "scenario": json.dumps(scenario),
                    "target_tlc": scenario.get("target_tlc"),
                    "demo_mode": scenario.get("demo_mode", False),
                    "status": drill["status"],
                    "started_at": drill["started_at"],
                    "deadline": drill["deadline"],
                },
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        raise HTTPException(status_code=503, detail="Drill storage is unavailable") from None


def _load_drill(drill_id: str, tenant_id: str) -> dict | None:
    """Load a drill row from fsma.mock_audit_drills as an in-memory-shaped dict.

    Scoped to the caller's tenant (drill_id is unique only per tenant).
    Returns None when the drill does not exist or the DB is unavailable.
    """
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    "SELECT tenant_id, scenario, status, grade, score, started_at, deadline "
                    "FROM fsma.mock_audit_drills "
                    "WHERE drill_id = :drill_id AND tenant_id = CAST(:tid AS uuid) LIMIT 1"
                ),
                {"drill_id": drill_id, "tid": tenant_id},
            ).fetchone()
        finally:
            db.close()
        if row is None:
            return None
        tenant_id, scenario, status, grade, score, started_at, deadline = row
        return {
            "tenant_id": str(tenant_id),
            "scenario": scenario,
            "started_at": started_at.isoformat(),
            "deadline": deadline.isoformat(),
            "status": status,
            "grade": grade,
            "score": score,
        }
    except Exception:
        logger.warning("Mock audit drill load failed", exc_info=True)
        return None


def _mark_drill_completed(drill_id: str, tenant_id: str, grade: str, score: int) -> None:
    """Save a self-reported submission before returning it as completed."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            result = db.execute(
                text(
                    "UPDATE fsma.mock_audit_drills "
                    "SET status = 'completed', grade = :grade, score = :score, "
                    "completed_at = now(), updated_at = now() "
                    "WHERE drill_id = :drill_id AND tenant_id = CAST(:tid AS uuid)"
                ),
                {"drill_id": drill_id, "tid": tenant_id, "grade": grade, "score": score},
            )
            if result.rowcount != 1:
                raise RuntimeError("Drill record was not updated")
            db.commit()
        finally:
            db.close()
    except Exception:
        raise HTTPException(status_code=503, detail="Drill result could not be saved") from None


router = APIRouter(prefix="/api/v1/audit", tags=["Mock Audit"])

# In-process cache of drills created by this process. PostgreSQL
# (fsma.mock_audit_drills) is the durable store — reads fall back to it so
# drills survive restarts and build a longitudinal dataset.
_active_drills: dict[str, dict] = {}

# Simulated FDA request scenarios
# Request templates only. The target lot and product always come from the
# tenant's own CTE records (SEL-513); there are no placeholder lots.
_FDA_REQUEST_TEMPLATES = [
    {
        "scenario": "Outbreak Investigation",
        "request_text": (
            "The FDA has identified a potential link between a multi-state foodborne illness outbreak "
            "and a product you handled. Under 21 CFR 1.1455, you are required to provide all "
            "traceability records for the following lot within 24 hours."
        ),
        "cfr_citation": "21 CFR 1.1455(a)",
    },
    {
        "scenario": "Routine Compliance Check",
        "request_text": (
            "As part of a routine compliance assessment under FSMA 204, the FDA requests "
            "traceability records demonstrating your ability to trace the following product "
            "from receipt through distribution. Records must be provided within 24 hours."
        ),
        "cfr_citation": "21 CFR 1.1455(a)",
    },
    {
        "scenario": "Retailer-Initiated Trace",
        "request_text": (
            "A retailer has flagged a potential safety issue affecting the following product. "
            "The FDA is requesting full chain-of-custody records for this lot."
        ),
        "cfr_citation": "21 CFR 1.1455(a)",
    },
]

# Alias for backward compat
FDA_SCENARIOS = _FDA_REQUEST_TEMPLATES


class StartDrillRequest(BaseModel):
    """Request to start a mock audit drill."""

    tenant_id: str = Field(..., description="Tenant ID to audit")
    scenario_index: Optional[int] = Field(None, description="Specific scenario (0-2); defaults to 0")


class DrillStatus(BaseModel):
    """Current status of an active drill."""

    drill_id: str
    scenario: str
    request_text: str
    target_product: str
    target_tlc: str
    cfr_citation: str
    started_at: str
    deadline: str
    time_remaining_seconds: int
    time_remaining_display: str
    status: str  # "active", "completed", "expired"
    grade: Optional[str] = None
    score: Optional[int] = None
    feedback: list[str] = Field(default_factory=list)
    assessment_basis: str = "self_reported"
    verified: bool = False
    disclaimer: str = "Practice drill based on client assertions; supporting evidence has not been verified."
    demo_mode: bool = Field(
        default=False,
        description="Always False: drills only run against real tenant data (SEL-513).",
    )


class DrillResponse(BaseModel):
    """Submitted drill response for grading."""

    drill_id: str
    has_lot_genealogy: bool = Field(..., description="Can trace lot from farm to current location")
    has_electronic_records: bool = Field(..., description="Records in electronic sortable format")
    has_all_ctes: bool = Field(..., description="All CTEs present (ship, receive, transform)")
    has_all_kdes: bool = Field(..., description="All required KDEs present per CTE")
    has_chain_verification: bool = Field(..., description="SHA-256 chain integrity verified")
    has_epcis_export: bool = Field(..., description="Can export in GS1 EPCIS 2.0 format")
    response_time_minutes: Optional[int] = Field(None, description="How long it took to compile (self-reported)")


class DrillGrade(BaseModel):
    """Grading result for a completed drill."""

    drill_id: str
    grade: str  # A, B, C, D, F
    score: int  # 0-100
    time_to_respond: str
    passed: Optional[bool]
    assessment_basis: str = "self_reported"
    verified: bool = False
    disclaimer: str = (
        "Self-reported practice assessment; no server-side evidence verification or compliance determination."
    )
    feedback: list[str]
    breakdown: dict[str, dict]


@router.post(
    "/drill/start",
    response_model=DrillStatus,
    summary="Start a mock FDA audit drill",
    description="Simulates an FDA 24-hour traceability records request. Starts a countdown timer.",
)
async def start_drill(
    request: StartDrillRequest,
    ctx: TenantContext = Depends(require_tenant_context),
) -> DrillStatus:
    """Start a mock audit drill."""
    tenant_id = ctx.tenant_id
    # Pick scenario (deterministic; no random selection)
    idx = request.scenario_index if request.scenario_index is not None else 0
    scenario = FDA_SCENARIOS[idx % len(FDA_SCENARIOS)].copy()

    # Drills only target the tenant's real records (SEL-513).
    real_tlc = _get_real_tlc(tenant_id)
    if not real_tlc:
        raise HTTPException(
            status_code=409,
            detail=(
                "No traceability records found for this tenant. Ingest CTE events before starting a mock audit drill."
            ),
        )
    scenario["target_tlc"] = real_tlc
    scenario["target_product"] = _get_product_for_tlc(tenant_id, real_tlc) or "Not recorded"
    scenario["demo_mode"] = False

    drill_id = str(uuid4())[:12]
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=24)

    drill = {
        "tenant_id": tenant_id,
        "scenario": scenario,
        "started_at": now.isoformat(),
        "deadline": deadline.isoformat(),
        "status": "active",
        "grade": None,
    }
    _persist_drill(drill_id, drill)
    _active_drills[drill_id] = drill

    logger.info("drill_started", extra={"drill_id": drill_id, "scenario": scenario["scenario"]})

    remaining = int((deadline - now).total_seconds())
    hours, remainder = divmod(remaining, 3600)
    minutes, _ = divmod(remainder, 60)

    return DrillStatus(
        drill_id=drill_id,
        scenario=scenario["scenario"],
        request_text=scenario["request_text"],
        target_product=scenario["target_product"],
        target_tlc=scenario["target_tlc"],
        cfr_citation=scenario["cfr_citation"],
        started_at=now.isoformat(),
        deadline=deadline.isoformat(),
        time_remaining_seconds=remaining,
        time_remaining_display=f"{hours}h {minutes}m",
        status="active",
        demo_mode=scenario.get("demo_mode", False),
    )


@router.get(
    "/drill/{drill_id}",
    response_model=DrillStatus,
    summary="Check drill status",
)
async def get_drill_status(drill_id: str, ctx: TenantContext = Depends(require_tenant_context)) -> DrillStatus:
    """Get current status of an active drill."""
    drill = _active_drills.get(drill_id) or _load_drill(drill_id, ctx.tenant_id)
    if not drill or drill.get("tenant_id") != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Drill not found")

    scenario = drill["scenario"]
    deadline = datetime.fromisoformat(drill["deadline"])
    now = datetime.now(timezone.utc)
    remaining = max(0, int((deadline - now).total_seconds()))

    status = drill["status"]
    if remaining <= 0 and status == "active":
        status = "expired"

    hours, remainder = divmod(remaining, 3600)
    minutes, _ = divmod(remainder, 60)

    return DrillStatus(
        drill_id=drill_id,
        scenario=scenario["scenario"],
        request_text=scenario["request_text"],
        target_product=scenario["target_product"],
        target_tlc=scenario["target_tlc"],
        cfr_citation=scenario["cfr_citation"],
        started_at=drill["started_at"],
        deadline=drill["deadline"],
        time_remaining_seconds=remaining,
        time_remaining_display=f"{hours}h {minutes}m",
        status=status,
        grade=drill.get("grade"),
        score=drill.get("score"),
        demo_mode=scenario.get("demo_mode", False),
    )


@router.post(
    "/drill/{drill_id}/submit",
    response_model=DrillGrade,
    summary="Submit drill response for grading",
    description="Grade a mock audit response based on completeness, accuracy, and response time.",
)
async def submit_drill_response(
    drill_id: str,
    response: DrillResponse,
    ctx: TenantContext = Depends(require_tenant_context),
) -> DrillGrade:
    """Grade a drill response."""
    drill = _active_drills.get(drill_id) or _load_drill(drill_id, ctx.tenant_id)
    if not drill:
        raise HTTPException(status_code=404, detail="Drill not found")
    if drill.get("tenant_id") != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Drill not found")

    # Scoring (each category out of ~17 points, total 100)
    breakdown = {}
    total = 0
    feedback = []

    # 1. Lot Genealogy (20 pts)
    if response.has_lot_genealogy:
        breakdown["lot_genealogy"] = {"score": 20, "max": 20, "status": "PASS"}
        total += 20
    else:
        breakdown["lot_genealogy"] = {"score": 0, "max": 20, "status": "FAIL"}
        feedback.append("CRITICAL: Cannot trace lot genealogy. FDA requires full farm-to-fork tracing.")

    # 2. Electronic Records (20 pts)
    if response.has_electronic_records:
        breakdown["electronic_records"] = {"score": 20, "max": 20, "status": "PASS"}
        total += 20
    else:
        breakdown["electronic_records"] = {"score": 0, "max": 20, "status": "FAIL"}
        feedback.append("CRITICAL: Records must be in electronic, sortable format per §1.1455.")

    # 3. CTE Completeness (15 pts)
    if response.has_all_ctes:
        breakdown["cte_completeness"] = {"score": 15, "max": 15, "status": "PASS"}
        total += 15
    else:
        breakdown["cte_completeness"] = {"score": 5, "max": 15, "status": "PARTIAL"}
        total += 5
        feedback.append("Some CTEs missing. Review Shipping, Receiving, and Transformation events.")

    # 4. KDE Completeness (15 pts)
    if response.has_all_kdes:
        breakdown["kde_completeness"] = {"score": 15, "max": 15, "status": "PASS"}
        total += 15
    else:
        breakdown["kde_completeness"] = {"score": 5, "max": 15, "status": "PARTIAL"}
        total += 5
        feedback.append("Missing required KDEs. Check GLN, TLC source, and timestamps.")

    # 5. Chain Integrity (15 pts)
    if response.has_chain_verification:
        breakdown["chain_integrity"] = {"score": 15, "max": 15, "status": "PASS"}
        total += 15
    else:
        breakdown["chain_integrity"] = {"score": 0, "max": 15, "status": "FAIL"}
        feedback.append("No cryptographic verification. Run verify_chain.py to prove data integrity.")

    # 6. EPCIS Export (15 pts)
    if response.has_epcis_export:
        breakdown["epcis_export"] = {"score": 15, "max": 15, "status": "PASS"}
        total += 15
    else:
        breakdown["epcis_export"] = {"score": 5, "max": 15, "status": "PARTIAL"}
        total += 5
        feedback.append("EPCIS 2.0 export not available. Consider enabling GS1 JSON-LD export.")

    # Time bonus/penalty
    deadline = datetime.fromisoformat(drill["deadline"])
    started = datetime.fromisoformat(drill["started_at"])
    now = datetime.now(timezone.utc)
    elapsed = now - started
    elapsed_hours = elapsed.total_seconds() / 3600

    time_display = f"{int(elapsed_hours)}h {int((elapsed.total_seconds() % 3600) / 60)}m"

    if elapsed_hours <= 4:
        feedback.insert(0, f"✅ Excellent response time: {time_display}. Well within 24-hour mandate.")
    elif elapsed_hours <= 12:
        feedback.insert(0, f"✅ Good response time: {time_display}. Within 24-hour mandate.")
    elif elapsed_hours <= 24:
        feedback.insert(0, f"⚠️ Response time: {time_display}. Cutting it close to the 24-hour deadline.")
    else:
        total = max(0, total - 20)  # Penalty for late
        feedback.insert(0, f"❌ Response time: {time_display}. EXCEEDED 24-hour mandate.")

    # Grade
    if total >= 90:
        grade = "A"
    elif total >= 80:
        grade = "B"
    elif total >= 70:
        grade = "C"
    elif total >= 60:
        grade = "D"
    else:
        grade = "F"

    passed = None  # Client assertions cannot establish an audit pass.
    for entry in breakdown.values():
        entry["status"] = "SELF_REPORTED_" + entry["status"]
    feedback.insert(0, "Self-reported practice score only; supporting evidence has not been verified.")

    # Update drill state (drill may have been loaded from DB after a restart)
    _mark_drill_completed(drill_id, ctx.tenant_id, grade, total)
    drill["status"] = "completed"
    drill["grade"] = grade
    drill["score"] = total
    _active_drills[drill_id] = drill

    if not feedback:
        feedback.append("Perfect score. You're audit-ready.")

    logger.info("drill_completed", extra={"drill_id": drill_id, "grade": grade, "score": total})

    return DrillGrade(
        drill_id=drill_id,
        grade=grade,
        score=total,
        time_to_respond=time_display,
        passed=passed,
        feedback=feedback,
        breakdown=breakdown,
    )
