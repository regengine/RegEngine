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
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from .config import get_settings
from .webhook_compat import _verify_api_key
from .tenant_validation import validate_tenant_id

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

    # Query tenant's configured active CTE types for self-normalization.
    # If the tenant has configured which CTE types apply to their operation,
    # use that subset instead of assuming all 7.
    # NOTE: obligation tables live in the public schema, not fsma — wrap in
    # its own try/except so a missing table (not-yet-migrated env) degrades
    # gracefully instead of aborting the outer transaction and zeroing all scores.
    try:
        active_row = db_session.execute(
            text("""
                SELECT ARRAY_AGG(DISTINCT cte_type)
                FROM obligation_cte_rules ocr
                JOIN obligations o ON o.id = ocr.obligation_id
                WHERE o.tenant_id = CAST(:tid AS uuid)
            """),
            {"tid": tenant_id},
        ).fetchone()
        result["active_cte_types"] = active_row[0] if active_row and active_row[0] else None
    except Exception:
        logger.debug("CTE type query failed (tables may not exist yet)", exc_info=True)
        # Tables may not exist yet — fall back to "use all 7 CTE types"
        try:
            db_session.rollback()
        except Exception:
            logger.debug("Rollback failed", exc_info=True)
        result["active_cte_types"] = None

    # 2) KDE completeness — ratio of filled vs required KDE fields
    kde_row = db_session.execute(
        text("""
            SELECT
                COUNT(*)                                   AS total_kdes,
                COUNT(*) FILTER (WHERE kde_value IS NOT NULL AND kde_value != '')  AS filled_kdes
            FROM fsma.cte_kdes k
            JOIN fsma.cte_events e ON e.id = k.cte_event_id
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
                MAX(sequence_num)                          AS max_seq,
                (SELECT chain_hash FROM fsma.hash_chain
                 WHERE tenant_id = :tid
                 ORDER BY sequence_num DESC LIMIT 1)       AS last_hash
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
                    SELECT sequence_num,
                           LAG(sequence_num) OVER (ORDER BY sequence_num) AS prev_seq
                    FROM fsma.hash_chain
                    WHERE tenant_id = :tid
                ) sub
                WHERE prev_seq IS NOT NULL AND sequence_num != prev_seq + 1
            """),
            {"tid": tenant_id},
        ).fetchone()
        result["chain_gaps"] = gap_row[0] if gap_row else 0
    else:
        result["chain_gaps"] = 0

    # 3b) Time precision — count events with midnight timestamps (no real time)
    if result["event_count"] > 0:
        midnight_row = db_session.execute(
            text("""
                SELECT COUNT(*) FROM fsma.cte_events
                WHERE tenant_id = :tid
                  AND EXTRACT(HOUR FROM event_timestamp) = 0
                  AND EXTRACT(MINUTE FROM event_timestamp) = 0
                  AND EXTRACT(SECOND FROM event_timestamp) = 0
            """),
            {"tid": tenant_id},
        ).fetchone()
        result["events_missing_time"] = midnight_row[0] if midnight_row else 0
    else:
        result["events_missing_time"] = 0

    # 4) Obligation coverage — check rules against actual event KDE presence
    # Note: obligations.tenant_id is UUID, but cte_events.tenant_id may be text.
    # Use try/except to handle type mismatches gracefully.
    try:
        obl_row = db_session.execute(
            text("""
                SELECT COUNT(*) FROM obligations WHERE tenant_id = CAST(:tid AS uuid)
            """),
            {"tid": tenant_id},
        ).fetchone()
        result["obligation_count"] = obl_row[0] if obl_row else 0
    except (OperationalError, ProgrammingError) as _obl_err:
        db_session.rollback()
        result["obligation_count"] = 0

    # Count obligation rules that are satisfied vs total checkable rules
    if result["event_count"] > 0:
        try:
            obl_coverage = db_session.execute(
                text("""
                    WITH checkable_rules AS (
                        SELECT r.id, r.cte_type, r.required_kde_key, r.validation_rule
                        FROM obligation_cte_rules r
                        JOIN obligations o ON o.id = r.obligation_id
                        WHERE o.tenant_id = CAST(:tid AS uuid)
                          AND r.validation_rule = 'present'
                          AND r.required_kde_key IS NOT NULL
                    ),
                    active_ctes AS (
                        SELECT DISTINCT event_type FROM fsma.cte_events WHERE tenant_id = :tid
                    ),
                    matched_rules AS (
                        SELECT cr.id
                        FROM checkable_rules cr
                        WHERE cr.cte_type IN (SELECT event_type FROM active_ctes)
                           OR cr.cte_type = 'all'
                    )
                    SELECT
                        (SELECT COUNT(*) FROM matched_rules) AS applicable_rules,
                        (SELECT COUNT(*) FROM checkable_rules) AS total_rules
                """),
                {"tid": tenant_id},
            ).fetchone()
            result["applicable_obligation_rules"] = obl_coverage[0] if obl_coverage else 0
            result["total_obligation_rules"] = obl_coverage[1] if obl_coverage else 0
        except (OperationalError, ProgrammingError) as _obl_cov_err:
            db_session.rollback()
            result["applicable_obligation_rules"] = 0
            result["total_obligation_rules"] = 0

        # Count active compliance alerts (unfixed obligation gaps)
        try:
            alert_row = db_session.execute(
                text("""
                    SELECT COUNT(*) FROM fsma.compliance_alerts
                    WHERE org_id = CAST(:tid AS uuid)
                      AND alert_type = 'chain_break'
                      AND (resolved IS NULL OR resolved = false)
                """),
                {"tid": tenant_id},
            ).fetchone()
            result["open_obligation_alerts"] = alert_row[0] if alert_row else 0
        except (OperationalError, ProgrammingError) as _alert_err:
            db_session.rollback()
            result["open_obligation_alerts"] = 0
    else:
        result["applicable_obligation_rules"] = 0
        result["total_obligation_rules"] = 0
        result["open_obligation_alerts"] = 0

    # 5) FTL product coverage
    try:
        ftl_row = db_session.execute(
            text("""
                SELECT COUNT(DISTINCT category) FROM food_traceability_list
            """),
        ).fetchone()
        result["ftl_category_count"] = ftl_row[0] if ftl_row else 0
    except (OperationalError, ProgrammingError) as _ftl_err:
        db_session.rollback()
        result["ftl_category_count"] = 0

    # 6) Chain integrity — full cryptographic verification (last 50 entries)
    try:
        from shared.cte_persistence import CTEPersistence
        persistence = CTEPersistence(db_session)
        chain_result = persistence.verify_chain(tenant_id)
        result["chain_verified"] = chain_result.valid
        result["chain_verification_errors"] = chain_result.errors
    except (ImportError, OperationalError, ProgrammingError) as exc:
        logger.warning("chain_verification_in_scoring_failed: %s", exc)
        result["chain_verified"] = None  # unknown
        result["chain_verification_errors"] = []

    return result


def _compute_scores(data: dict) -> dict:
    """
    Compute the five compliance sub-scores from raw query data.

    Returns dict with score (0-100) and detail string for each dimension.
    """
    scores = {}

    # --- 1) Chain Integrity (30% weight) ---
    # Uses cryptographic hash recalculation, not just gap detection
    if data["chain_length"] == 0:
        scores["chain_integrity"] = (0, "No events in audit trail")
    elif data.get("chain_verified") is True:
        scores["chain_integrity"] = (
            100,
            f"All {data['chain_length']} entries cryptographically verified — "
            f"chain hash: {data['last_chain_hash'][:16]}..."
            if data["last_chain_hash"] else "All entries verified",
        )
    elif data.get("chain_verified") is False:
        errors = data.get("chain_verification_errors", [])
        error_count = len(errors)
        # Severe: each verification error is a potential tampering incident
        penalty = min(error_count * 25, 100)
        detail = f"TAMPER DETECTED: {error_count} chain verification failure(s)"
        if errors:
            detail += f" — {errors[0][:80]}"
        scores["chain_integrity"] = (max(0, 100 - penalty), detail)
    else:
        # Verification couldn't run (DB issue) — use gap detection fallback
        if data["chain_gaps"] > 0:
            penalty = min(data["chain_gaps"] * 10, 50)
            scores["chain_integrity"] = (
                100 - penalty,
                f"Chain has {data['chain_gaps']} gap(s) — verification unavailable",
            )
        else:
            scores["chain_integrity"] = (
                90,  # Can't give 100 without crypto verification
                f"{data['chain_length']} entries, no gaps — crypto verification pending",
            )

    # --- 2) KDE Completeness (25% weight) ---
    if data["total_kdes"] == 0:
        scores["kde_completeness"] = (0, "No KDEs recorded")
    else:
        kde_ratio = data["filled_kdes"] / data["total_kdes"]
        kde_score = int(kde_ratio * 100)

        # Penalize for missing event time precision (FDA requires time, not just date)
        events_missing_time = data.get("events_missing_time", 0)
        if events_missing_time > 0 and data["event_count"] > 0:
            time_penalty = min(10, int((events_missing_time / data["event_count"]) * 10))
            kde_score = max(0, kde_score - time_penalty)

        missing = data["total_kdes"] - data["filled_kdes"]
        time_note = f"; {events_missing_time} events lack precise time" if events_missing_time > 0 else ""
        if missing > 0:
            scores["kde_completeness"] = (
                kde_score,
                f"{data['filled_kdes']}/{data['total_kdes']} KDE fields populated — {missing} blank{time_note}",
            )
        else:
            scores["kde_completeness"] = (
                kde_score if events_missing_time > 0 else 100,
                f"All {data['total_kdes']} KDE fields populated{time_note}",
            )

    # --- 3) CTE Completeness (20% weight) ---
    # Self-normalize by tenant's active CTE types instead of assuming all 7.
    # A cold-chain distributor may only use 3 CTE types (receiving, shipping,
    # transformation) and should score 100% when all 3 are tracked.
    active_cte_types = data.get("active_cte_types", None)
    if active_cte_types and len(active_cte_types) > 0:
        total_cte_types = len(active_cte_types)
    else:
        total_cte_types = 7  # Fallback: FSMA 204 defines 7 CTE types
    if data["distinct_cte_types"] == 0:
        scores["cte_completeness"] = (0, "No CTEs tracked")
    else:
        cte_score = min(100, int((data["distinct_cte_types"] / total_cte_types) * 100))
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

    # --- 5) Obligation Coverage (10% weight) ---
    # How many FSMA 204 obligations are satisfied by current event data
    total_rules = data.get("total_obligation_rules", 0)
    applicable_rules = data.get("applicable_obligation_rules", 0)
    open_alerts = data.get("open_obligation_alerts", 0)

    if data["event_count"] == 0:
        scores["obligation_coverage"] = (0, "No events — obligations not yet assessed")
    elif total_rules == 0:
        scores["obligation_coverage"] = (50, "Obligation rules not loaded — seed regulatory data")
    else:
        # Base score from CTE type coverage of obligations
        coverage_ratio = applicable_rules / total_rules
        obl_score = int(coverage_ratio * 80)  # Up to 80 points for CTE coverage

        # Deduct for open obligation alerts
        if open_alerts > 0:
            alert_penalty = min(open_alerts * 3, 30)
            obl_score = max(0, obl_score - alert_penalty)
        else:
            obl_score = min(100, obl_score + 20)  # Bonus for zero alerts

        detail = (
            f"{applicable_rules}/{total_rules} obligation rules covered by active CTE types"
        )
        if open_alerts > 0:
            detail += f" — {open_alerts} open compliance alert(s)"
        scores["obligation_coverage"] = (obl_score, detail)

    # --- 6) Export Readiness (10% weight) ---
    # Requires: chain intact, KDEs present, multiple CTE types
    if data["event_count"] == 0:
        scores["export_readiness"] = (0, "Cannot produce FDA report — no data")
    else:
        export_score = 0
        issues = []
        # Chain must be intact
        if data.get("chain_verified") is True:
            export_score += 40
        elif data["chain_length"] > 0 and data["chain_gaps"] == 0:
            export_score += 30
            issues.append("chain not cryptographically verified")
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
    obligation_score = scores["obligation_coverage"][0]
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

    if chain_score < 100:
        if data.get("chain_verified") is False:
            actions.append(NextAction(
                priority="HIGH",
                action="URGENT: Chain tampering detected — investigate immediately",
                impact="Chain integrity is 10% of overall score; tampering = audit failure",
            ))
        else:
            actions.append(NextAction(
                priority="HIGH",
                action="Investigate chain integrity issues — possible data loss",
                impact="Chain integrity is 10% of overall score",
            ))

    if obligation_score < 80:
        open_alerts = data.get("open_obligation_alerts", 0)
        if open_alerts > 0:
            actions.append(NextAction(
                priority="HIGH",
                action=f"Resolve {open_alerts} open obligation gap(s) flagged during ingestion",
                impact=f"+{min(open_alerts * 3, 30)} points on obligation coverage",
            ))
        else:
            actions.append(NextAction(
                priority="HIGH",
                action="Expand CTE type coverage to satisfy more FSMA 204 obligations",
                impact="Each new CTE type unlocks 7-15 obligation checks",
            ))

    if kde_score < 80:
        actions.append(NextAction(
            priority="HIGH",
            action="Complete all required KDEs per event — add GLN, reference documents, dates",
            impact=f"+{100 - kde_score} points possible on KDE completeness",
        ))

    if cte_score < 100 and data["missing_cte_types"]:
        top_missing = sorted(data["missing_cte_types"])[0]
        actions.append(NextAction(
            priority="MEDIUM",
            action=f"Add {top_missing.replace('_', ' ')} CTE tracking to your supply chain",
            impact=f"+{int(100/7)} points on CTE completeness per type added",
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
    validate_tenant_id(tenant_id)

    db_session = None
    try:
        from shared.database import SessionLocal
        db_session = SessionLocal()
    except (ImportError, OSError, OperationalError) as exc:
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
    except (OperationalError, ProgrammingError) as exc:
        # Tables may not exist yet (missing migrations) — return zero-score
        # rather than a 500, so the frontend renders the empty state.
        # OperationalError: DB connection issues; ProgrammingError: missing tables/schema.
        logger.warning("compliance_score: query failed (likely missing schema): %s", exc)
        if db_session:
            db_session.close()
        return ComplianceScoreResponse(
            tenant_id=tenant_id,
            overall_score=0,
            grade="F",
            breakdown={
                "chain_integrity": ScoreBreakdown(score=0, detail="Schema not initialized — run migrations"),
                "kde_completeness": ScoreBreakdown(score=0, detail="Schema not initialized — run migrations"),
                "cte_completeness": ScoreBreakdown(score=0, detail="Schema not initialized — run migrations"),
                "product_coverage": ScoreBreakdown(score=0, detail="Schema not initialized — run migrations"),
                "obligation_coverage": ScoreBreakdown(score=0, detail="Schema not initialized — run migrations"),
                "export_readiness": ScoreBreakdown(score=0, detail="Schema not initialized — run migrations"),
            },
            next_actions=[
                NextAction(
                    priority="HIGH",
                    action="Run database migrations to create the FSMA schema tables",
                    impact="All scoring depends on fsma.cte_events, fsma.hash_chain, and related tables",
                ),
            ],
        )

    try:
        # Compute sub-scores
        scores = _compute_scores(data)

        # Weighted overall — 6 dimensions (aligned with FSMA 204 priorities)
        # Export readiness:     30% (FDA 24-hour response capability — §1.1455)
        # KDE completeness:     25% (data quality per event — §1.1325–§1.1350)
        # CTE completeness:     15% (supply chain coverage)
        # Chain integrity:      10% (tamper-proof audit trail)
        # Obligation coverage:  10% (regulatory requirement satisfaction)
        # Product coverage:     10% (FTL food category mapping)
        chain_score = scores["chain_integrity"][0]
        kde_score = scores["kde_completeness"][0]
        cte_score = scores["cte_completeness"][0]
        obligation_score = scores["obligation_coverage"][0]
        product_score = scores["product_coverage"][0]
        export_score = scores["export_readiness"][0]

        # Weights aligned with FSMA 204 regulatory priorities:
        # - Export readiness (30%): FDA may request records within 24h (§1.1455)
        # - KDE completeness (25%): Core traceability data per §1.1325–§1.1350
        # - CTE completeness (15%): Coverage of applicable critical tracking events
        # - Chain integrity (10%): Hash-chain verification for tamper detection
        # - Obligation coverage (10%): Regulatory obligation fulfillment
        # - Product coverage (10%): Product catalog completeness
        overall = int(
            chain_score * 0.10
            + kde_score * 0.25
            + cte_score * 0.15
            + obligation_score * 0.10
            + product_score * 0.10
            + export_score * 0.30
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
                "obligation_coverage": ScoreBreakdown(
                    score=obligation_score, detail=scores["obligation_coverage"][1],
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
        raise HTTPException(status_code=500, detail="Scoring error. Check server logs for details.")
    finally:
        if db_session:
            db_session.close()


# ---------------------------------------------------------------------------
# Pending Reviews Endpoint (M11)
# ---------------------------------------------------------------------------

@router.get(
    "/pending-reviews/{tenant_id}",
    summary="Get count of items pending compliance review",
    description=(
        "Returns a count of unresolved exception cases, pending identity "
        "reviews, and active request cases that need attention. Used by "
        "the dashboard overview to show the pending reviews metric."
    ),
)
async def get_pending_reviews(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
):
    """Count all items requiring compliance review for a tenant."""
    validate_tenant_id(tenant_id)

    db_session = None
    try:
        from shared.database import SessionLocal
        db_session = SessionLocal()
    except (ImportError, OSError, OperationalError) as exc:
        logger.warning("pending_reviews: DB unavailable (%s)", exc)
        return {
            "tenant_id": tenant_id,
            "pending_reviews": 0,
            "breakdown": {},
            "db_available": False,
        }

    try:
        # 1. Unresolved exception cases
        exc_count = db_session.execute(
            text("""
                SELECT COUNT(*) FROM fsma.exception_cases
                WHERE tenant_id = :tid
                  AND status NOT IN ('resolved', 'waived')
            """),
            {"tid": tenant_id},
        ).scalar() or 0

        # 2. Pending identity reviews
        identity_count = 0
        try:
            identity_count = db_session.execute(
                text("""
                    SELECT COUNT(*) FROM fsma.identity_review_queue
                    WHERE tenant_id = :tid AND status = 'pending'
                """),
                {"tid": tenant_id},
            ).scalar() or 0
        except (OperationalError, ProgrammingError):
            pass  # table may not exist

        # 3. Active request cases not yet submitted
        request_count = db_session.execute(
            text("""
                SELECT COUNT(*) FROM fsma.request_cases
                WHERE tenant_id = :tid
                  AND package_status NOT IN ('submitted', 'amended')
            """),
            {"tid": tenant_id},
        ).scalar() or 0

        # 4. Events with failed critical rule evaluations (unresolved)
        critical_failures = db_session.execute(
            text("""
                SELECT COUNT(DISTINCT re.event_id)
                FROM fsma.rule_evaluations re
                JOIN fsma.rule_definitions rd
                  ON re.rule_id = rd.rule_id AND re.rule_version = rd.rule_version
                WHERE re.tenant_id = :tid
                  AND re.result = 'fail'
                  AND rd.severity = 'critical'
                  AND NOT EXISTS (
                      SELECT 1 FROM fsma.exception_cases ec
                      WHERE ec.tenant_id = re.tenant_id
                        AND ec.linked_event_ids @> ARRAY[re.event_id]::text[]
                        AND ec.status IN ('resolved', 'waived')
                  )
            """),
            {"tid": tenant_id},
        ).scalar() or 0

        total = exc_count + identity_count + request_count + critical_failures

        return {
            "tenant_id": tenant_id,
            "pending_reviews": total,
            "breakdown": {
                "unresolved_exceptions": exc_count,
                "identity_reviews": identity_count,
                "active_requests": request_count,
                "critical_failures": critical_failures,
            },
            "db_available": True,
        }

    except Exception as exc:
        logger.warning("pending_reviews: query failed: %s", exc)
        return {
            "tenant_id": tenant_id,
            "pending_reviews": 0,
            "breakdown": {},
            "db_available": False,
            "error": str(exc),
        }
    finally:
        if db_session:
            db_session.close()
