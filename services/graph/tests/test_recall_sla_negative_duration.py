"""Data-free tests: a completed drill with completed_at before started_at.

A negative duration is corrupt timing data and must never certify 24-hour
compliance (21 CFR 1.1455(c)(1)). It fails closed as BREACHED, the existing
non-compliant status, rather than a new enum value.
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


def test_negative_duration_is_not_met():
    drill = _completed(timedelta(seconds=-1))
    assert drill.duration_seconds == -1
    assert drill.sla_status == SLAStatus.BREACHED


def test_large_negative_duration_is_breached():
    assert _completed(timedelta(hours=-48)).sla_status == SLAStatus.BREACHED


def test_zero_still_met():
    assert _completed(timedelta(0)).sla_status == SLAStatus.MET
