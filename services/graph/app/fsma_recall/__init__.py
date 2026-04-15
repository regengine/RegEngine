# ============================================================
# FSMA 204 Mock Recall Automation Engine — subpackage init.
#
# Backward-compatible re-export layer: all public symbols that
# were previously importable from ``app.fsma_recall`` remain
# importable from the same path.
#
# Split from monolithic fsma_recall.py — zero logic changes.
# ============================================================
"""
FSMA 204 Mock Recall Automation Engine.

Sprint 8: Programmatic recall drill execution, tracking, and FDA compliance.

Per FSMA 204 requirements:
- Organizations must be able to produce traceability records within 24 hours of FDA request
- Regular mock recalls validate recall readiness
- All drill results must be auditable

This module provides:
- MockRecallEngine: Orchestrates recall drill execution
- RecallDrill: Represents a single mock recall exercise
- RecallResult: Captures drill outcomes with SLA metrics
- RecallSchedule: Manages periodic recall drill scheduling
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# --- Re-exports: models ------------------------------------------------
from .models import (  # noqa: F401
    RecallStatus,
    RecallType,
    RecallSeverity,
    SLAStatus,
    AffectedFacility,
    RecallDrill,
    RecallResult,
    ScheduledDrill,
)

# --- Re-exports: engine -------------------------------------------------
from .engine import MockRecallEngine  # noqa: F401

# --- Re-exports: persistence (internal helpers, but previously importable)
from .persistence import (  # noqa: F401
    _get_db_engine,
    _upsert_drill_row,
    _update_drill_row,
    _load_drills_from_db,
    _load_drill_by_id_from_db,
    _dict_to_recall_drill,
)


# ============================================================================
# GLOBAL INSTANCE & CONVENIENCE FUNCTIONS
# ============================================================================

_recall_engine: Optional[MockRecallEngine] = None


def get_recall_engine() -> MockRecallEngine:
    """Get or create the global MockRecallEngine instance."""
    global _recall_engine
    if _recall_engine is None:
        _recall_engine = MockRecallEngine()
    return _recall_engine


def reset_recall_engine() -> None:
    """Reset the global engine (for testing)."""
    global _recall_engine
    _recall_engine = None


async def create_mock_recall(
    tenant_id: str,
    drill_type: str = "full_trace",
    severity: str = "class_ii",
    target_lot: Optional[str] = None,
    initiated_by: str = "api",
) -> Dict[str, Any]:
    """
    Convenience function to create and execute a mock recall drill.

    Args:
        tenant_id: Tenant identifier
        drill_type: Type of recall (forward_trace, backward_trace, full_trace)
        severity: FDA classification (class_i, class_ii, class_iii)
        target_lot: Optional starting lot code
        initiated_by: User/system identifier

    Returns:
        Dict with drill_id, status, and result summary
    """
    engine = get_recall_engine()

    drill = engine.create_drill(
        tenant_id=tenant_id,
        drill_type=RecallType(drill_type),
        severity=RecallSeverity(severity),
        target_lot=target_lot,
        initiated_by=initiated_by,
        reason="api_request",
    )

    result = await engine.execute_drill(drill)

    return {
        "drill_id": drill.drill_id,
        "status": drill.status.value,
        "sla_status": drill.sla_status.value,
        "result": result.get_summary(),
    }


def get_recall_history(
    tenant_id: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Get recent recall drill history."""
    engine = get_recall_engine()
    drills = engine.get_drill_history(tenant_id, limit=limit)
    return [d.to_dict() for d in drills]


def get_recall_readiness(tenant_id: str) -> Dict[str, Any]:
    """Get recall readiness report for tenant."""
    engine = get_recall_engine()
    return engine.get_readiness_report(tenant_id)
