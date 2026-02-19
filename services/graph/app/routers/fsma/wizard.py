"""
FSMA 204 V2 Applicability & Exemption Wizard API.

Public endpoints (no auth required) that power the FTL Coverage Checker wizard.
These endpoints are intentionally unauthenticated — they serve as a free,
lead-generation tool and mirror the client-side logic in ftl-checker/page.tsx.

Routes:
  GET  /v1/fsma/wizard/ftl-categories   — All 23 FTL categories with CTE/KDE metadata
  POST /v1/fsma/wizard/applicability    — Evaluate if selected categories are on the FTL
  POST /v1/fsma/wizard/exemptions       — Evaluate exemption status from wizard answers
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

# Import the engine from the kernel (portable path resolution)
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from kernel.reporting.fsma_engine import FSMAApplicabilityEngine

router = APIRouter(prefix="/wizard", tags=["FSMA 204 Wizard"])
logger = structlog.get_logger("fsma-wizard")

# Singleton engine instance (stateless, safe to share)
_engine = FSMAApplicabilityEngine()


# ============================================================================
# REQUEST / RESPONSE MODELS
# ============================================================================


class ApplicabilityRequest(BaseModel):
    """Request body for the applicability check endpoint."""

    selections: List[str] = Field(
        ...,
        description="List of FTL category IDs to evaluate (e.g. ['leafy-greens-fresh', 'eggs'])",
        min_length=0,
    )


class ExemptionRequest(BaseModel):
    """
    Request body for the exemption check endpoint.

    Each key is an exemption ID; the value is the user's yes/no answer.
    Omitted keys are treated as unanswered (null).

    Valid exemption IDs:
      - small-producer
      - kill-step
      - direct-to-consumer
      - small-retail
      - rarely-consumed-raw
      - usda-jurisdiction
    """

    answers: Dict[str, bool] = Field(
        default_factory=dict,
        description="Map of exemption ID → boolean answer (True = Yes, False = No)",
    )


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("/ftl-categories")
def get_ftl_categories():
    """
    Return all 23 FDA Food Traceability List (FTL) categories.

    Each category includes:
    - id, name, examples, exclusions
    - covered (bool) — whether the category is on the FTL
    - outbreak_frequency (HIGH | MODERATE)
    - ctes — required Critical Tracking Events
    - cfr_sections — applicable 21 CFR sections
    - kdes — required Key Data Elements

    No authentication required — public tool.
    """
    categories = _engine.get_ftl_categories()
    exemptions = _engine.get_exemption_definitions()

    logger.info("ftl_categories_requested", count=len(categories))

    return {
        "categories": categories,
        "total": len(categories),
        "covered_count": sum(1 for c in categories if c.get("covered")),
        "exemption_definitions": exemptions,
        "regulatory_reference": "21 CFR Part 1 Subpart S",
        "compliance_deadline": "2028-07-20",
        "enforcement_note": "FDA not enforcing before July 20, 2028 (Congressional directive)",
    }


@router.post("/applicability")
def check_applicability(request: ApplicabilityRequest):
    """
    Evaluate whether selected product categories are subject to FSMA 204.

    Accepts a list of FTL category IDs and returns:
    - is_applicable — True if any selected category is on the FTL
    - covered_categories — matched FTL category objects with full CTE/KDE detail
    - not_covered_categories — any submitted IDs not recognised by the engine
    - high_outbreak_count — number of HIGH outbreak-frequency categories selected
    - reason — human-readable summary

    No authentication required — public tool.
    """
    result = _engine.evaluate_applicability(request.selections)

    logger.info(
        "applicability_checked",
        selections=request.selections,
        is_applicable=result["is_applicable"],
        covered_count=len(result["covered_categories"]),
    )

    return result


@router.post("/exemptions")
def check_exemptions(request: ExemptionRequest):
    """
    Evaluate FSMA 204 exemption status based on wizard yes/no answers.

    Accepts a map of exemption IDs to boolean answers and returns:
    - status — "EXEMPT" or "NOT_EXEMPT"
    - is_exempt — True if any exemption qualifies
    - active_exemptions — list of qualifying exemption objects (with citation)
    - unanswered_count — number of exemption questions not yet answered

    Valid exemption IDs (per 21 CFR §1.1305):
      small-producer, kill-step, direct-to-consumer,
      small-retail, rarely-consumed-raw, usda-jurisdiction

    No authentication required — public tool.
    """
    result = _engine.evaluate_exemptions(request.answers)

    logger.info(
        "exemptions_checked",
        answers=request.answers,
        status=result["status"],
        active_count=len(result["active_exemptions"]),
    )

    return result
