"""Compliance-grade integrity scoring for recall drills.

The overall score is 0-100, composed of four equally weighted
sub-scores (each 0-25):

    trace_completeness   (0-25)  — graph coverage, gaps, orphans
    kde_completeness     (0-25)  — required KDE field presence
    temporal_integrity   (0-25)  — monotonic event ordering
    pipeline_resilience  (0-25)  — ingestion success rate, type safety
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from recall_drill.validation.fsma_validator import ValidationReport

logger = logging.getLogger(__name__)

_MAX_COMPONENT = 25


@dataclass
class IntegrityScore:
    """Final integrity score with per-component breakdown."""

    score: int  # 0-100
    trace_completeness: float  # 0-25
    kde_completeness: float  # 0-25
    temporal_integrity: float  # 0-25
    pipeline_resilience: float  # 0-25
    grade: str

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "grade": self.grade,
            "breakdown": {
                "trace_completeness": round(self.trace_completeness, 2),
                "kde_completeness": round(self.kde_completeness, 2),
                "temporal_integrity": round(self.temporal_integrity, 2),
                "pipeline_resilience": round(self.pipeline_resilience, 2),
            },
        }


def _grade(score: int) -> str:
    if score >= 95:
        return "A"
    if score >= 85:
        return "B"
    if score >= 70:
        return "C"
    if score >= 50:
        return "D"
    return "F"


class IntegrityScorer:
    """Score a recall drill based on validation results and trace data.

    Each of the four components is scored independently on a 0-25
    scale and then summed to produce the final 0-100 score.
    """

    def score(
        self,
        validation: ValidationReport,
        records: list[dict],
        trace_gaps: int = 0,
        trace_orphans: int = 0,
        injection_success_rate: float = 1.0,
    ) -> IntegrityScore:
        total = max(validation.total_records, 1)

        # ---- Trace completeness (0-25) ----
        # Gaps and orphans reduce the score; each gap costs 3 pts, each orphan 5.
        gap_penalty = min(trace_gaps * 3, _MAX_COMPONENT)
        orphan_penalty = min(trace_orphans * 5, _MAX_COMPONENT)
        cte_link_errors = sum(
            1 for e in validation.errors if e.rule == "cte_link_missing"
        )
        link_penalty = min(cte_link_errors * 2, _MAX_COMPONENT)
        trace_completeness = max(
            0.0, _MAX_COMPONENT - gap_penalty - orphan_penalty - link_penalty
        )

        # ---- KDE completeness (0-25) ----
        kde_errors = sum(
            1 for e in validation.errors if e.rule == "required_kde_missing"
        )
        supplier_errors = sum(
            1 for e in validation.errors if e.rule == "missing_supplier"
        )
        kde_error_rate = (kde_errors + supplier_errors) / total
        kde_completeness = max(0.0, _MAX_COMPONENT * (1.0 - kde_error_rate))

        # ---- Temporal integrity (0-25) ----
        temporal_errors = sum(
            1 for e in validation.errors if e.rule == "temporal_order_violation"
        )
        temporal_error_rate = temporal_errors / total
        temporal_integrity = max(0.0, _MAX_COMPONENT * (1.0 - temporal_error_rate))

        # ---- Pipeline resilience (0-25) ----
        type_errors = sum(
            1 for e in validation.errors if e.rule == "type_mismatch"
        )
        type_penalty = min(type_errors * 3, _MAX_COMPONENT)
        ingestion_score = injection_success_rate * _MAX_COMPONENT
        pipeline_resilience = max(
            0.0, (ingestion_score - type_penalty)
        )

        # ---- Composite ----
        raw_total = (
            trace_completeness
            + kde_completeness
            + temporal_integrity
            + pipeline_resilience
        )
        final = round(max(0, min(100, raw_total)))

        logger.info(
            "Integrity score: %d (trace=%.1f kde=%.1f temporal=%.1f pipeline=%.1f)",
            final,
            trace_completeness,
            kde_completeness,
            temporal_integrity,
            pipeline_resilience,
        )

        return IntegrityScore(
            score=final,
            trace_completeness=trace_completeness,
            kde_completeness=kde_completeness,
            temporal_integrity=temporal_integrity,
            pipeline_resilience=pipeline_resilience,
            grade=_grade(final),
        )
