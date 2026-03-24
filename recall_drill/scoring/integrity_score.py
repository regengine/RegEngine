"""Compliance-grade integrity scoring for recall drills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from recall_drill.validation.fsma_validator import ValidationReport


@dataclass
class IntegrityScore:
    score: int  # 0-100
    trace_completeness: float
    kde_completeness: float
    temporal_integrity: float
    pipeline_resilience: float
    supplier_linkage: float
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
                "supplier_linkage": round(self.supplier_linkage, 2),
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
    """Score a recall drill based on validation results and trace data."""

    # Weights must sum to 1.0
    WEIGHTS = {
        "trace_completeness": 0.30,
        "kde_completeness": 0.25,
        "temporal_integrity": 0.20,
        "pipeline_resilience": 0.15,
        "supplier_linkage": 0.10,
    }

    def score(
        self,
        validation: ValidationReport,
        records: list[dict],
        trace_gaps: int = 0,
        trace_orphans: int = 0,
        injection_success_rate: float = 1.0,
    ) -> IntegrityScore:
        total = max(validation.total_records, 1)

        # --- Trace completeness (30%) ---
        gap_penalty = min(trace_gaps * 10, 100)
        orphan_penalty = min(trace_orphans * 15, 100)
        trace_completeness = max(0, 100 - gap_penalty - orphan_penalty)

        # --- KDE completeness (25%) ---
        kde_errors = sum(
            1 for e in validation.errors if e.rule == "required_kde_missing"
        )
        kde_completeness = max(0, 100 - (kde_errors / total) * 100)

        # --- Temporal integrity (20%) ---
        temporal_errors = sum(
            1 for e in validation.errors if e.rule == "temporal_order_violation"
        )
        temporal_integrity = max(0, 100 - (temporal_errors / total) * 100)

        # --- Pipeline resilience (15%) ---
        pipeline_resilience = injection_success_rate * 100

        # --- Supplier linkage (10%) ---
        supplier_errors = sum(
            1 for e in validation.errors if e.rule == "missing_supplier"
        )
        supplier_linkage = max(0, 100 - (supplier_errors / total) * 100)

        components = {
            "trace_completeness": trace_completeness,
            "kde_completeness": kde_completeness,
            "temporal_integrity": temporal_integrity,
            "pipeline_resilience": pipeline_resilience,
            "supplier_linkage": supplier_linkage,
        }

        weighted = sum(
            components[k] * self.WEIGHTS[k] for k in self.WEIGHTS
        )
        final = round(max(0, min(100, weighted)))

        return IntegrityScore(
            score=final,
            grade=_grade(final),
            **components,
        )
