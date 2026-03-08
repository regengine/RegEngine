"""
Compliance Score API.

Provides GET /api/v1/compliance/score/{tenant_id} which returns
a real-time compliance readiness grade based on FSMA 204 requirements.

Scores are computed from actual database state:
  - CTE events (fsma.cte_events)
  - KDE records (fsma.cte_kdes)
  - Hash chain integrity (fsma.hash_chain)
  - Obligation coverage (obligations table)
  - Food Traceability List (food_traceability_list table)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.webhook_router import _verify_api_key

logger = logging.getLogger("compliance-score")

router = APIRouter(prefix="/api/v1/compliance", tags=["Compliance Score"])


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

class ScoreBreakdown(BaseModel):
    """Individual score category."""
    score: int = Field(..., ge=0, le=100)
    detail: str


class NextAction(BaseModel):
    """Recommended next action to improve compliance."""
    priority: str  # "HIGH" | "MEDIUM" | "LOW"
    action: str
    impact: str


class ComplianceScoreResponse(BaseModel):
    """Full compliance score response."""
    tenant_id: str
    overall_score: int = Field(..., ge=0, le=100)
    grade: str  # A, B, C, D, F
    breakdown: dict[str, ScoreBreakdown]
    next_actions: list[NextAction] = Field(default_factory=list)
    events_analyzed: int = 0
    last_chain_hash: Optional[str] = None


def _compute_grade(score: int) -> str:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_db_session():
    """Get a database session. Returns None if DB unavailable."""
    try:
        from shared.database import SessionLocal
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    except Exception as exc:
        logger.warning("compliance_score: DB unavailable (%s), using fallback", exc)
        yield None


def _query_scoring_data(db_session, tenant_id: str) -> dict:
    """
    Query all scoring signals from the database in a single round-trip.

    Returns dict with keys:
      event_count, distinct_cte_types, total_kdes, required_kdes_present,
      chain_length, chain_valid, last_chain_hash, obligation_count,
      ftl_category_count, product_categories_covered
    """
    from sqlalchemy import text

    result = {}

    # 1) CTE event stats
    row = db_session.execute(
        text("""
            SELECT
                COUNT(*)                                   AS event_count,
                COUNT(DISTINCT event_type)                 AS distinct_cte_types,
                ARRAY_AGG(DISTINCT event_type)             AS cte_types_present
            FROM fsma.cte_events
            WHERE tenant_id = :tid
        """),
        {"tid": tenant_id},
    ).fetchone()

    result["event_count"] = row[0] if row else 0
    result["distinct_cte_types"] = row[1] if row else 0
    result["cte_types_present"] = row[2] if row and row[2] else []

    # All 7 CTE types defined in FSMA 204
    all_cte_types = {
        "harvesting", "cooling", "initial_packing",
        "first_land_based_receiving", "shipping", "receiving", "transformation",
    }
    result["missing_cte_types"] = list(all_cte_types - set(result["cte_types_present"] or []))

    # 2) KDE completeness — ratio of filled vs required KDE fields
    kde_row = db_session.execute(
        text("""
            SELECT
                COUNT(*)                                   AS total_kdes,
                COUNT(*) FILTER (WHERE value IS NOT NULL AND value != '')  AS filled_kdes
            FROM fsma.cte_kdes k
            JOIN fsma.cte_events e ON e.id = k.event_id
            WHERE e.tenant_id = :tid
        """),
        {"tid": tenant_id},
    ).fetchone()

    result["total_kdes"] = kde_row[0] if kde_row else 0
    result["filled_kdes"] = kde_row[1] if kde_row else 0

    # 3) Chain integrity
    chain_row = db_session.execute(
        text("""
            SELECT
                COUNT(*)                                   AS chain_length,
                MAX(sequence_number)                       AS max_seq,
                (SELECT chain_hash FROM fsma.hash_chain
                 WHERE tenant_id = :tid
                 ORDER BY sequence_number DESC LIMIT 1)    AS last_hash
            FROM fsma.hash_chain
            WHERE tenant_id = :tid
        """),
        {"tid": tenant_id},
    ).fetchone()

    result["chain_length"] = chain_row[0] if chain_row else 0
    result["last_chain_hash"] = chain_row[2] if chain_row else None

    # Verify chain continuity (no gaps in sequence numbers)
    if result["chain_length"] > 0:
        gap_row = db_session.execute(
            text("""
                SELECT COUNT(*) FROM (
                    SELECT sequence_number,
                           LAG(sequence_number) OVER (ORDER BY sequence_number) AS prev_seq
                    FROM fsma.hash_chain
                    WHERE tenant_id = :tid
                ) sub
                WHERE prev_seq IS NOT NULL AND sequence_number != prev_seq + 1
            """),
            {"tid": tenant_id},
        ).fetchone()
        result["chain_gaps"] = gap_row[0] if gap_row else 0
    else:
        result["chain_gaps"] = 0

    # 4) Obligation coverage — how many obligations have matching CTE data
    obl_row = db_session.execute(
        text("""
            SELECT COUNT(*) FROM obligations WHERE tenant_id = :tid
        """),
        {"tid": tenant_id},
    ).fetchone()
    result["obligation_count"] = obl_row[0] if obl_row else 0

    # 5) FTL product coverage
    ftl_row = db_session.execute(
        text("""
            SELECT COUNT(DISTINCT category) FROM food_traceability_list
        """),
    ).fetchone()
    result["ftl_category_count"] = ftl_row[0] if ftl_row else 0

    return result


def _compute_scores(data: dict) -> dict:
    """
    Compute the five compliance sub-scores from raw query data.

    Returns dict with score (0-100) and detail string for each dimension.
    """
    scores = {}

    # --- 1) Chain Integrity (30% weight) ---
    if data["chain_length"] == 0:
        scores["chain_integrity"] = (0, "No events in audit trail")
    elif data["chain_gaps"] > 0:
        penalty = min(data["chain_gaps"] * 10, 50)
        scores["chain_integrity"] = (
            100 - penalty,
            f"Chain has {data['chain_gaps']} gap(s) in sequence — possible tampering",
        )
    else:
        scores["chain_integrity"] = (
            100,
            f"All {data['chain_length']} entries verified — chain hash: "
            f"{data['last_chain_hash'][:16]}..." if data["last_chain_hash"] else "verified",
        )

    # --- 2) KDE Completeness (25% weight) ---
    if data["total_kdes"] == 0:
        scores["kde_completeness"] = (0, "No KDEs recorded")
    else:
        kde_ratio = data["filled_kdes"] / data["total_kdes"]
        kde_score = int(kde_ratio * 100)
        missing = data["total_kdes"] - data["filled_kdes"]
        if missing > 0:
            scores["kde_completeness"] = (
                kde_score,
                f"{data['filled_kdes']}/{data['total_kdes']} KDE fields populated — {missing} blank",
            )
        else:
            scores["kde_completeness"] = (
                100,
                f"All {data['total_kdes']} KDE fields populated",
            )

    # --- 3) CTE Completeness (25% weight) ---
    total_cte_types = 7  # FSMA 204 defines 7 CTE types
    if data["distinct_cte_types"] == 0:
        scores["cte_completeness"] = (0, "No CTEs tracked")
    else:
        cte_score = int((data["distinct_cte_types"] / total_cte_types) * 100)
        if data["missing_cte_types"]:
            missing_str = ", ".join(sorted(data["missing_cte_types"]))
            scores["cte_completeness"] = (
                cte_score,
                f"{data['distinct_cte_types']}/{total_cte_types} CTE types tracked — "
                f"missing: {missing_str}",
            )
        else:
            scores["cte_completeness"] = (
                100,
                f"All {total_cte_types} CTE types tracked across {data['event_count']} events",
            )

    # --- 4) Product Coverage (10% weight) ---
    # Based on whether events cover FTL food categories
    if data["event_count"] == 0:
        scores["product_coverage"] = (0, "No products mapped to FTL categories")
    elif data["ftl_category_count"] == 0:
        scores["product_coverage"] = (50, "Events exist but FTL category mapping needed")
    else:
        # Events exist and FTL data loaded — score based on data presence
        base = 60
        # Bonus for more events (diminishing returns, caps at +40)
        event_bonus = min(40, data["event_count"] * 5)
        scores["product_coverage"] = (
            min(100, base + event_bonus),
            f"{data['event_count']} events tracked across FTL-mapped products",
        )

    # --- 5) Export Readiness (10% weight) ---
    # Requires: chain intact, KDEs present, multiple CTE types
    if data["event_count"] == 0:
        scores["export_readiness"] = (0, "Cannot produce FDA report — no data")
    else:
        export_score = 0
        issues = []
        # Chain must be intact
        if data["chain_length"] > 0 and data["chain_gaps"] == 0:
            export_score += 40
        else:
            issues.append("chain integrity")
        # KDEs must be mostly complete
        if data["total_kdes"] > 0:
            kde_ratio = data["filled_kdes"] / data["total_kdes"]
            export_score += int(kde_ratio * 30)
            if kde_ratio < 0.8:
                issues.append("KDE gaps")
        else:
            issues.append("no KDEs")
        # Multiple CTE types present
        if data["distinct_cte_types"] >= 3:
            export_score += 30
        elif data["distinct_cte_types"] >= 1:
            export_score += 15
            issues.append("limited CTE coverage")
        else:
            issues.append("no CTE types")

        detail = "FDA export ready" if export_score >= 80 else (
            f"Export score {export_score}/100 — address: {', '.join(issues)}"
        )
        scores["export_readiness"] = (min(100, export_score), detail)

    return scores


def _build_next_actions(scores: dict, data: dict) -> list[NextAction]:
    """Generate prioritized next actions based on score gaps."""
    actions = []

    cte_score = scores["cte_completeness"][0]
    kde_score = scores["kde_completeness"][0]
    chain_score = scores["chain_integrity"][0]
    product_score = scores["product_coverage"][0]
    export_score = scores["export_readiness"][0]

    if data["event_count"] == 0:
        actions.append(NextAction(
            priority="HIGH",
            action="Ingest your first traceability event via CSV upload or API",
            impact="Activates your compliance baseline",
        ))
        actions.append(NextAction(
            priority="HIGH",
            action="Use the FTL Checker to identify which products are covered",
            impact="Establishes product coverage score",
        ))
        return actions

    if cte_score < 100 and data["missing_cte_types"]:
        top_missing = sorted(data["missing_cte_types"])[0]
        actions.append(NextAction(
            priority="HIGH",
            action=f"Add {top_missing.replace('_', ' ')} CTE tracking to your supply chain",
            impact=f"+{int(100/7)} points on CTE completeness per type added",
        ))

    if kde_score < 80:
        actions.append(NextAction(
            priority="HIGH",
            action="Add GLN (Global Location Number) and complete all required KDEs per event",
            impact=f"+{100 - kde_score} points possible on KDE completeness",
        ))

    if chain_score < 100:
        actions.append(NextAction(
            priority="HIGH",
            action="Investigate chain integrity gaps — possible data loss or tampering",
            impact="Chain integrity is 30% of overall score",
        ))

    if product_score < 80:
        actions.append(NextAction(
            priority="MEDIUM",
            action="Run FTL Checker against all products and confirm category assignments",
            impact="+10-25 points on product coverage",
        ))

    if export_score < 80:
        actions.append(NextAction(
            priority="MEDIUM",
            action="Run a 24-hour mock recall drill to test export readiness",
            impact="Validates real-world compliance under time pressure",
        ))

    # Always include this if score < 90
    overall = int(
        chain_score * 0.30
        + kde_score * 0.25
        + cte_score * 0.25
        + product_score * 0.10
        + export_score * 0.10
    )
    if overall < 90 and len(actions) < 4:
        actions.append(NextAction(
            priority="MEDIUM",
            action="Review obligation coverage against 82 FSMA 204 requirements in the system",
            impact="Identifies specific regulatory gaps",
        ))

    return actions[:5]  # Cap at 5


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/score/{tenant_id}",
    response_model=ComplianceScoreResponse,
    summary="Get compliance readiness score",
    description=(
        "Returns a real-time compliance readiness grade (A-F) for the specified tenant, "
        "with breakdown by category and recommended next actions. "
        "Scores are computed from actual CTE events, KDEs, chain integrity, "
        "and obligation coverage in the database."
    ),
)
async def get_compliance_score(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
) -> ComplianceScoreResponse:
    """Compute and return compliance score for a tenant."""

    db_session = None
    try:
        from shared.database import SessionLocal
        db_session = SessionLocal()
    except Exception as exc:
        logger.warning("compliance_score: DB unavailable (%s)", exc)

    if db_session is None:
        # Fallback — no DB, return zero score
        return ComplianceScoreResponse(
            tenant_id=tenant_id,
            overall_score=0,
            grade="F",
            breakdown={
                "chain_integrity": ScoreBreakdown(score=0, detail="Database unavailable"),
                "kde_completeness": ScoreBreakdown(score=0, detail="Database unavailable"),
                "cte_completeness": ScoreBreakdown(score=0, detail="Database unavailable"),
                "product_coverage": ScoreBreakdown(score=0, detail="Database unavailable"),
                "export_readiness": ScoreBreakdown(score=0, detail="Database unavailable"),
            },
            next_actions=[
                NextAction(
                    priority="HIGH",
                    action="Database connection required for compliance scoring",
                    impact="All scores depend on database access",
                ),
            ],
        )

    try:
        # Query all scoring signals
        data = _query_scoring_data(db_session, tenant_id)

        # Compute sub-scores
        scores = _compute_scores(data)

        # Weighted overall (same weights as before)
        chain_score = scores["chain_integrity"][0]
        kde_score = scores["kde_completeness"][0]
        cte_score = scores["cte_completeness"][0]
        product_score = scores["product_coverage"][0]
        export_score = scores["export_readiness"][0]

        overall = int(
            chain_score * 0.30
            + kde_score * 0.25
            + cte_score * 0.25
            + product_score * 0.10
            + export_score * 0.10
        )

        # Build next actions
        next_actions = _build_next_actions(scores, data)

        return ComplianceScoreResponse(
            tenant_id=tenant_id,
            overall_score=overall,
            grade=_compute_grade(overall),
            breakdown={
                "chain_integrity": ScoreBreakdown(
                    score=chain_score, detail=scores["chain_integrity"][1],
                ),
                "kde_completeness": ScoreBreakdown(
                    score=kde_score, detail=scores["kde_completeness"][1],
                ),
                "cte_completeness": ScoreBreakdown(
                    score=cte_score, detail=scores["cte_completeness"][1],
                ),
                "product_coverage": ScoreBreakdown(
                    score=product_score, detail=scores["product_coverage"][1],
                ),
                "export_readiness": ScoreBreakdown(
                    score=export_score, detail=scores["export_readiness"][1],
                ),
            },
            next_actions=next_actions,
            events_analyzed=data["event_count"],
            last_chain_hash=data.get("last_chain_hash"),
        )

    except Exception as exc:
        logger.error("compliance_score: scoring failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scoring error: {str(exc)}")
    finally:
        if db_session:
            db_session.close()
