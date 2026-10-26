"""Data-free tests for zero-second completed drills under 21 CFR 1.1455(c)(1).

21 CFR 1.1455(c)(1) requires records within 24 hours of an FDA request.
A drill completed in 0 seconds is well inside that limit and must be MET.
The 24h (MET) and 24h + 1s (BREACHED) boundaries must not move.
Timestamps only; no records, CSV rows or EPCIS documents.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.graph.app.fsma_recall.models import (
    RecallDrill,
    RecallSeverity,
    RecallStatus,
    RecallType,
    SLAStatus,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _completed(elapsed: timedelta) -> RecallDrill:
    return RecallDrill(
        drill_id="",
        tenant_id="",
        created_at=START,
        drill_type=list(RecallType)[0],
        severity=list(RecallSeverity)[0],
        status=RecallStatus.COMPLETED,
        started_at=START,
        completed_at=START + elapsed,
    )


def test_zero_second_completion_is_met():
    """21 CFR 1.1455(c)(1): 0 s elapsed is within 24h, so MET (not BREACHED)."""
    drill = _completed(timedelta(0))
    assert drill.duration_seconds == 0
    assert drill.sla_status == SLAStatus.MET


def test_exactly_24h_still_met():
    """21 CFR 1.1455(c)(1): exactly 24h remains MET."""
    assert _completed(timedelta(hours=24)).sla_status == SLAStatus.MET


def test_24h_plus_one_second_still_breached():
    """21 CFR 1.1455(c)(1): 24h + 1s remains BREACHED."""
    assert _completed(timedelta(hours=24, seconds=1)).sla_status == SLAStatus.BREACHED


def test_completed_without_completed_at_uses_elapsed():
    """21 CFR 1.1455(c)(1): a completed drill missing completed_at falls back to elapsed time."""
    drill = _completed(timedelta(0))
    drill.completed_at = None
    drill.started_at = datetime.now(timezone.utc) - timedelta(hours=25)
    assert drill.sla_status == SLAStatus.BREACHED
