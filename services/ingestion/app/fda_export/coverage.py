"""FDA export completeness gates."""

from __future__ import annotations

import logging

from fastapi import HTTPException

logger = logging.getLogger("fda-export")

# FSMA-204 expects "adequate and reliable" traceability. Required-KDE
# coverage below this threshold requires explicit caller acknowledgement.
_KDE_COVERAGE_THRESHOLD = 0.80


def _enforce_kde_coverage_gate(
    *,
    completeness_summary: dict,
    allow_incomplete: bool,
    identity: dict,
    tenant_id: str,
    export_scope: str,
) -> None:
    """Reject low-KDE exports unless the caller acknowledges the gap."""
    kde_coverage = completeness_summary["required_kde_coverage_ratio"]
    if kde_coverage >= _KDE_COVERAGE_THRESHOLD:
        return
    if not allow_incomplete:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "kde_coverage_below_threshold",
                "kde_coverage_ratio": kde_coverage,
                "threshold": _KDE_COVERAGE_THRESHOLD,
                "events_with_missing_required_fields": completeness_summary[
                    "events_with_missing_required_fields"
                ],
                "missing_required_by_field": completeness_summary.get(
                    "missing_required_by_field", {}
                ),
                "message": (
                    f"Required-KDE coverage is {kde_coverage:.2%}, below "
                    f"the {_KDE_COVERAGE_THRESHOLD:.0%} FSMA-204 threshold. "
                    "This export would not meet 'adequate and reliable' "
                    "traceability. Fix missing KDEs, or re-submit with "
                    "allow_incomplete=true if the gap is acceptable for "
                    "this recall scope."
                ),
            },
        )
    logger.warning(
        "fda_export_coverage_gate_bypass",
        extra={
            "tenant_id": tenant_id,
            "user_id": identity["user_id"],
            "request_id": identity["request_id"],
            "export_scope": export_scope,
            "kde_coverage_ratio": kde_coverage,
            "threshold": _KDE_COVERAGE_THRESHOLD,
            "events_with_missing_required_fields": completeness_summary[
                "events_with_missing_required_fields"
            ],
        },
    )
