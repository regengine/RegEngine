"""
Mock Audit Router.

Simulates an FDA traceability records request per 21 CFR 1.1455.
The FDA can request records within 24 hours — this endpoint generates
a realistic request, starts a timer, and grades the response.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("mock-audit")

router = APIRouter(prefix="/api/v1/audit", tags=["Mock Audit"])

# In-memory drill store
_active_drills: dict[str, dict] = {}

# Simulated FDA request scenarios
# NOTE: TLCs below are demo placeholders. In production, the start_drill endpoint
# queries the tenant's actual CTE events to select a real TLC for the drill.
_DEMO_FDA_SCENARIOS = [
    {
        "scenario": "Outbreak Investigation — Romaine Lettuce",
        "request_text": (
            "The FDA has identified a potential link between a multi-state Salmonella outbreak "
            "and romaine lettuce distributed in the western United States. Under 21 CFR 1.1455, "
            "you are required to provide all traceability records for the following lot within 24 hours."
        ),
        "target_product": "Romaine Lettuce",
        "target_tlc": "ROM-0226-A1-001",
        "cfr_citation": "21 CFR 1.1455(a)",
        "demo_mode": True,
    },
    {
        "scenario": "Routine Compliance Check — Fresh Tomatoes",
        "request_text": (
            "As part of a routine compliance assessment under FSMA 204, the FDA requests "
            "traceability records demonstrating your ability to trace the following product "
            "from receipt through distribution. Records must be provided within 24 hours."
        ),
        "target_product": "Roma Tomatoes",
        "target_tlc": "TOM-0226-F3-001",
        "cfr_citation": "21 CFR 1.1455(a)",
        "demo_mode": True,
    },
    {
        "scenario": "Retailer-Initiated Trace — Atlantic Salmon",
        "request_text": (
            "A major retailer has flagged a potential temperature excursion affecting imported "
            "seafood products. The FDA is requesting full chain-of-custody records for the following "
            "product as part of a First Land-Based Receiving investigation."
        ),
        "target_product": "Atlantic Salmon Fillets",
        "target_tlc": "SAL-0226-B1-007",
        "cfr_citation": "21 CFR 1.1455(a), 21 CFR 1.1325(c)",
        "demo_mode": True,
    },
]

# Alias for backward compat
FDA_SCENARIOS = _DEMO_FDA_SCENARIOS


class StartDrillRequest(BaseModel):
    """Request to start a mock audit drill."""
    tenant_id: str = Field(..., description="Tenant ID to audit")
    scenario_index: Optional[int] = Field(None, description="Specific scenario (0-2), or random if null")


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
    demo_mode: bool = Field(
        default=False,
        description="True when drill uses demo TLCs instead of real tenant data.",
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
    passed: bool
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
    _: None = Depends(_verify_api_key),
) -> DrillStatus:
    """Start a mock audit drill."""
    # Pick scenario
    idx = request.scenario_index if request.scenario_index is not None else random.randint(0, len(FDA_SCENARIOS) - 1)
    scenario = FDA_SCENARIOS[idx % len(FDA_SCENARIOS)]

    drill_id = str(uuid4())[:12]
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=24)

    _active_drills[drill_id] = {
        "tenant_id": request.tenant_id,
        "scenario": scenario,
        "started_at": now.isoformat(),
        "deadline": deadline.isoformat(),
        "status": "active",
        "grade": None,
    }

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
async def get_drill_status(drill_id: str) -> DrillStatus:
    """Get current status of an active drill."""
    drill = _active_drills.get(drill_id)
    if not drill:
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
    _: None = Depends(_verify_api_key),
) -> DrillGrade:
    """Grade a drill response."""
    drill = _active_drills.get(drill_id)
    if not drill:
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

    passed = total >= 70

    # Update drill state
    _active_drills[drill_id]["status"] = "completed"
    _active_drills[drill_id]["grade"] = grade
    _active_drills[drill_id]["score"] = total

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
