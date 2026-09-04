"""
Recall Readiness Report Router.

Generates an exportable recall readiness assessment for a tenant.
Evaluates 6 dimensions, produces a letter grade, and provides
an actionable improvement plan — ready for board presentations
and FDA inspectors.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from shared.tenant_context import TenantContext

from .disclaimers import DEMO_DATA_DISCLAIMER
from .webhook_compat import require_tenant_context

logger = logging.getLogger("recall-report")


def _query_scoring_data(tenant_id: str) -> dict | None:
    """Query actual tenant data for recall readiness scoring."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Count events from the canonical store of record (#2506). The
            # legacy ``fsma.cte_events`` table is a dual-write copy being
            # retired; the hash-chain verifier now anchors on
            # ``fsma.traceability_events``, so these scoring readers read the
            # same source of truth. Columns ``traceability_lot_code`` and
            # ``event_type`` are identical on both tables, and no status
            # filter is applied here (matching the prior legacy behavior,
            # which counted every row regardless of validation status).
            cte_count = (
                db.execute(
                    text("SELECT COUNT(*) FROM fsma.traceability_events WHERE tenant_id = :tid"), {"tid": tenant_id}
                ).scalar()
                or 0
            )

            # Count distinct TLCs
            tlc_count = (
                db.execute(
                    text(
                        "SELECT COUNT(DISTINCT traceability_lot_code) "
                        "FROM fsma.traceability_events WHERE tenant_id = :tid"
                    ),
                    {"tid": tenant_id},
                ).scalar()
                or 0
            )

            # Count CTE types covered
            cte_types = (
                db.execute(
                    text("SELECT COUNT(DISTINCT event_type) FROM fsma.traceability_events WHERE tenant_id = :tid"),
                    {"tid": tenant_id},
                ).scalar()
                or 0
            )

            # Check FDA export capability
            has_export = (
                db.execute(
                    text("SELECT COUNT(*) FROM fsma.fda_export_log WHERE tenant_id = :tid"), {"tid": tenant_id}
                ).scalar()
                or 0
            )

            # Count suppliers
            supplier_count = (
                db.execute(
                    text("SELECT COUNT(*) FROM fsma.tenant_suppliers WHERE tenant_id = :tid"), {"tid": tenant_id}
                ).scalar()
                or 0
            )

            # Chain integrity: count chain entries and detect sequence gaps
            chain_length = (
                db.execute(
                    text("SELECT COUNT(*) FROM fsma.hash_chain WHERE tenant_id = :tid"), {"tid": tenant_id}
                ).scalar()
                or 0
            )

            chain_gap_count = 0
            if chain_length > 0:
                max_seq = (
                    db.execute(
                        text("SELECT MAX(sequence_num) FROM fsma.hash_chain WHERE tenant_id = :tid"), {"tid": tenant_id}
                    ).scalar()
                    or 0
                )
                # Gaps = expected entries minus actual entries
                chain_gap_count = max(0, max_seq - chain_length)

            return {
                "cte_count": cte_count,
                "tlc_count": tlc_count,
                "cte_types": cte_types,
                "has_export": has_export > 0,
                "supplier_count": supplier_count,
                "chain_length": chain_length,
                "chain_gap_count": chain_gap_count,
            }
        finally:
            db.close()
    except (RuntimeError, OSError, AttributeError, TypeError, ValueError) as exc:
        logger.warning("recall_scoring_query_failed error=%s", str(exc))
        return None


router = APIRouter(prefix="/api/v1/recall", tags=["Recall Readiness"])


class RecallDimension(BaseModel):
    """A single dimension of recall readiness."""

    id: str
    name: str
    score: int  # 0-100
    max_score: int = 100
    grade: str
    status: str  # "excellent", "good", "needs_improvement", "critical"
    findings: list[str]
    recommendations: list[str]


class RecallReport(BaseModel):
    """Complete recall readiness report."""

    tenant_id: str
    generated_at: str
    report_title: str
    overall_score: int
    overall_grade: str
    overall_status: str
    time_to_respond_estimate: str
    dimensions: list[RecallDimension]
    executive_summary: str
    action_items: list[dict]
    regulatory_citations: list[str]
    demo_mode: bool = Field(
        default=False,
        description="True when scores are illustrative (not derived from tenant data).",
    )
    demo_disclaimer: str | None = Field(
        default=None,
        description="Disclaimer shown when report uses demo/sample data.",
    )


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _status(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "good"
    if score >= 70:
        return "needs_improvement"
    return "critical"


def _derive_action_items(dimensions: list["RecallDimension"]) -> list[dict]:
    """Build the improvement plan from the tenant's actual gaps (#3042).

    Every item traces to a dimension scoring below 80 and reuses that
    dimension's own recommendations. Impact is stated as the dimension
    and its current score — no invented point estimates. A tenant with
    no gaps gets an empty plan, which is the honest answer.
    """
    items: list[dict] = []
    for dim in sorted(dimensions, key=lambda d: d.score):
        if dim.score >= 80:
            continue
        priority = "HIGH" if dim.status == "critical" else "MEDIUM"
        for rec in dim.recommendations[:2]:
            items.append(
                {
                    "priority": priority,
                    "action": rec,
                    "impact": f"Improves {dim.name} (currently {dim.score}/100)",
                    "effort": "Not estimated",
                }
            )
    return items[:6]


@router.get(
    "/{tenant_id}/report",
    response_model=RecallReport,
    summary="Generate recall readiness report",
    description=(
        "Generates a comprehensive recall readiness assessment evaluating "
        "6 dimensions of traceability preparedness. Suitable for board "
        "presentations and regulatory inspections."
    ),
)
async def generate_report(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
) -> RecallReport:
    """Generate recall readiness report."""
    tenant_id = ctx.tenant_id
    now = datetime.now(timezone.utc)

    # Try to query real data
    scoring_data = _query_scoring_data(tenant_id)
    use_demo_mode = scoring_data is None or scoring_data.get("cte_count", 0) == 0

    if not use_demo_mode:
        # Compute real scores based on actual data
        cte_count = scoring_data.get("cte_count", 0)
        cte_types = scoring_data.get("cte_types", 0)
        has_export = scoring_data.get("has_export", False)
        supplier_count = scoring_data.get("supplier_count", 0)

        # Scoring logic:
        # Traceability depth: based on CTE types (max 7 types) out of 100
        trace_depth_score = min(100, int((cte_types / 7) * 100))

        # Data completeness: scale with supplier count, can reach 0
        data_completeness_score = min(100, supplier_count * 10) if supplier_count > 0 else 0

        # Response time: based on export readiness
        response_time_score = 90 if has_export else 65

        # Supply chain: proportional to supplier count (20+ suppliers = 100%)
        supply_chain_score = min(100, (supplier_count / max(supplier_count, 20)) * 100) if supplier_count > 0 else 0

        # Team readiness: scale with event volume, can reach 0
        team_readiness_score = min(100, cte_count // 10) if cte_count > 0 else 0

        # Chain integrity: compute from actual hash chain data
        chain_length = scoring_data.get("chain_length", 0)
        chain_gap_count = scoring_data.get("chain_gap_count", 0)
        if chain_length == 0:
            chain_integrity_score = 50  # No chain data yet
        else:
            chain_integrity_score = max(0, min(100, 100 - (25 * chain_gap_count)))

        dimensions = [
            RecallDimension(
                id="trace_speed",
                name="Trace Speed",
                score=response_time_score,
                grade=_grade(response_time_score),
                status=_status(response_time_score),
                findings=[
                    f"CTE events recorded: {cte_count}",
                    f"Distinct TLCs tracked: {scoring_data.get('tlc_count', 0)}",
                    f"Export capability: {'enabled' if has_export else 'not yet enabled'}",
                ],
                recommendations=[
                    "Enable FDA export if not already active",
                    "Reduce CTE entry delay with real-time API integration",
                ]
                if not has_export
                else ["Maintain current export practices"],
            ),
            RecallDimension(
                id="data_completeness",
                name="Data Completeness",
                score=data_completeness_score,
                grade=_grade(data_completeness_score),
                status=_status(data_completeness_score),
                findings=[
                    f"Active suppliers: {supplier_count}",
                    f"CTE event types: {cte_types} / 7",
                    f"Total event volume: {cte_count} events",
                ],
                recommendations=[
                    "Onboard additional suppliers to improve traceability visibility",
                    "Ensure all CTE event types are represented",
                ]
                if supplier_count < 5
                else ["Continue current data collection practices"],
            ),
            RecallDimension(
                id="chain_integrity",
                name="Chain Integrity",
                score=chain_integrity_score,
                grade=_grade(chain_integrity_score),
                status=_status(chain_integrity_score),
                # #3042: findings state only what was queried — no
                # unverified capability claims in real mode.
                findings=[
                    f"SHA-256 hash chain length: {chain_length} entries",
                    f"Sequence gaps detected: {chain_gap_count}"
                    if chain_gap_count > 0
                    else "No gaps in event sequence",
                ]
                if chain_length > 0
                else [
                    "No hash chain entries recorded yet",
                    "Chain verification will activate after first event ingestion",
                ],
                recommendations=[
                    "Maintain current integrity practices",
                    "Consider adding independent third-party verification",
                ]
                if chain_gap_count == 0
                else [
                    f"Investigate {chain_gap_count} sequence gap(s) in the hash chain",
                    "Run chain verification via /api/v1/fda/export/verify",
                    "Consider re-ingesting events to fill gaps",
                ],
            ),
            RecallDimension(
                id="supplier_coverage",
                name="Supplier Coverage",
                score=supply_chain_score,
                grade=_grade(supply_chain_score),
                status=_status(supply_chain_score),
                findings=[
                    f"Suppliers in system: {supplier_count}",
                    f"CTE event types represented: {cte_types} / 7",
                ],
                recommendations=[
                    "Expand supplier network to key trading partners",
                    "Send portal activation reminders to inactive suppliers",
                ]
                if supplier_count < 10
                else ["Supply chain coverage is strong"],
            ),
            RecallDimension(
                id="export_readiness",
                name="Export Readiness",
                score=90 if has_export else 50,
                grade=_grade(90 if has_export else 50),
                status=_status(90 if has_export else 50),
                findings=[
                    "FDA sortable export: functional",
                    "Exports include SHA-256 verification hashes",
                ]
                if has_export
                else [
                    "FDA sortable export: not yet enabled",
                ],
                recommendations=[
                    "Enable FDA export capability",
                    "Test with retailer portals",
                ]
                if not has_export
                else ["Test with additional retailer portals"],
            ),
            RecallDimension(
                id="team_readiness",
                name="Team Readiness",
                score=team_readiness_score,
                grade=_grade(team_readiness_score),
                status=_status(team_readiness_score),
                findings=[
                    f"Data maturity indicators: {cte_count} events in system",
                    "Training and drill history are not tracked by this report",
                ],
                recommendations=[
                    "Generate SOP via /api/v1/sop/generate",
                    "Schedule monthly mock audit drills",
                    "Complete FSMA 204 training for team members",
                ],
            ),
        ]
    else:
        # Use hardcoded demo scenarios
        dimensions = [
            RecallDimension(
                id="trace_speed",
                name="Trace Speed",
                score=78,
                grade="C",
                status="needs_improvement",
                findings=[
                    "Average trace-back time: 4.2 hours",
                    "3 lots required manual lookups (non-electronic records)",
                    "Receiving CTEs averaged 3.1 hour entry delay",
                ],
                recommendations=[
                    "Reduce CTE entry delay to under 2 hours",
                    "Digitize remaining manual records via CSV upload or API",
                    "Run monthly mock audit drills to improve response time",
                ],
            ),
            RecallDimension(
                id="data_completeness",
                name="Data Completeness",
                score=85,
                grade="B",
                status="good",
                findings=[
                    "92% of CTEs have all required KDEs",
                    "GLN coverage: 78% (missing for 3 supplier locations)",
                    "TLC format consistency: 95%",
                ],
                recommendations=[
                    "Collect missing GLNs from 3 supplier locations",
                    "Standardize TLC format across all facilities",
                    "Enable automated KDE validation rules",
                ],
            ),
            RecallDimension(
                id="chain_integrity",
                name="Chain Integrity",
                score=95,
                grade="A",
                status="excellent",
                findings=[
                    "SHA-256 hash chain: 100% verified",
                    "No gaps in event sequence",
                    "All immutability triggers active",
                ],
                recommendations=[
                    "Maintain current integrity practices",
                    "Consider adding independent third-party verification",
                ],
            ),
            RecallDimension(
                id="supplier_coverage",
                name="Supplier Coverage",
                score=65,
                grade="D",
                status="critical",
                findings=[
                    "Only 60% of suppliers actively using portal",
                    "2 suppliers have not submitted in 30+ days",
                    "1 supplier still using paper-based records",
                ],
                recommendations=[
                    "Send portal link reminders to inactive suppliers",
                    "Offer supplier training sessions",
                    "Consider switching non-compliant suppliers",
                ],
            ),
            RecallDimension(
                id="export_readiness",
                name="Export Readiness",
                score=88,
                grade="B",
                status="good",
                findings=[
                    "FDA sortable spreadsheet export: functional",
                    "EPCIS 2.0 JSON-LD export: functional",
                    "Export includes SHA-256 verification hashes",
                ],
                recommendations=[
                    "Test export with target retailer portals (Walmart, Kroger)",
                    "Validate EPCIS schema compliance with GS1 validator",
                ],
            ),
            RecallDimension(
                id="team_readiness",
                name="Team Readiness",
                score=72,
                grade="C",
                status="needs_improvement",
                findings=[
                    "Last mock drill: 2 weeks ago (score: C)",
                    "2 of 5 team members completed FSMA training",
                    "No documented recall SOP on file",
                ],
                recommendations=[
                    "Generate SOP via /api/v1/sop/generate",
                    "Schedule monthly mock audit drills",
                    "Complete FSMA 204 training for remaining 3 team members",
                ],
            ),
        ]

    overall = int(sum(d.score for d in dimensions) / len(dimensions))

    # Build executive summary from computed dimension scores
    _dim_scores = {d.id: d.score for d in dimensions}
    _chain_score = _dim_scores.get("chain_integrity", overall)
    _supplier_score = _dim_scores.get("supplier_coverage", overall)
    _team_score = _dim_scores.get("team_readiness", overall)
    executive_summary = (
        f"This recall readiness assessment evaluates {tenant_id}'s preparedness "
        f"to respond to an FDA traceability records request under 21 CFR 1.1455. "
        f"The overall readiness score is {overall}/100 (Grade {_grade(overall)}). "
        f"Chain integrity score: {_chain_score}/100. "
        f"Supplier coverage score: {_supplier_score}/100. "
        f"Team readiness score: {_team_score}/100. "
        f"Addressing any gaps below 80 would raise the overall grade to B or above."
    )

    # #3042: the improvement plan must come from the tenant's actual
    # computed gaps. Only the demo scenario ships the canned narrative
    # (its dimension findings are equally illustrative).
    if use_demo_mode:
        action_items = [
            {
                "priority": "HIGH",
                "action": "Collect missing GLNs from 3 supplier locations",
                "impact": "+5 to Data Completeness",
                "effort": "Low",
            },
            {
                "priority": "HIGH",
                "action": "Re-engage 2 inactive suppliers via portal reminders",
                "impact": "+10 to Supplier Coverage",
                "effort": "Low",
            },
            {
                "priority": "MEDIUM",
                "action": "Generate and distribute FSMA 204 SOP",
                "impact": "+8 to Team Readiness",
                "effort": "Low",
            },
            {
                "priority": "MEDIUM",
                "action": "Complete FSMA training for 3 remaining team members",
                "impact": "+10 to Team Readiness",
                "effort": "Medium",
            },
            {
                "priority": "MEDIUM",
                "action": "Reduce CTE entry delay to under 2 hours",
                "impact": "+7 to Trace Speed",
                "effort": "Medium",
            },
            {
                "priority": "LOW",
                "action": "Test EPCIS exports with retailer portals",
                "impact": "+5 to Export Readiness",
                "effort": "Low",
            },
        ]
    else:
        action_items = _derive_action_items(dimensions)

    return RecallReport(
        tenant_id=tenant_id,
        generated_at=now.isoformat(),
        report_title=f"Recall Readiness Report — {tenant_id}",
        overall_score=overall,
        overall_grade=_grade(overall),
        overall_status=_status(overall),
        # #3042: the previous real-mode value (overall/100*24 hours) was a
        # score formula formatted as a latency measurement. Response time
        # is not measured anywhere in this service, so say so.
        time_to_respond_estimate="4.2 hours (target: < 24 hours)"
        if use_demo_mode
        else "Not yet measured — run a recall drill to establish a baseline (target: < 24 hours per 21 CFR 1.1455(c))",
        dimensions=dimensions,
        executive_summary=executive_summary,
        action_items=action_items,
        regulatory_citations=[
            "21 CFR Part 1, Subpart S — Additional Traceability Records",
            "21 CFR 1.1455 — Records Request (24-hour mandate)",
            "21 CFR 1.1325-1.1350 — CTE/KDE Requirements",
            "FSMA Section 204 — Food Traceability Rule",
        ],
        demo_mode=use_demo_mode,
        demo_disclaimer=DEMO_DATA_DISCLAIMER if use_demo_mode else None,
    )
