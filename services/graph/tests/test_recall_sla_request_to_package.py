"""SLA flag must measure the request-to-package workflow, not compute seconds.

The audit found engine.py compared in-process drill seconds against the
24-hour limit, so a successful drill was always compliant. The engine now
measures from drill creation (the request) to the packaged result.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma_recall import MockRecallEngine, RecallType  # noqa: E402

TENANT = "sla-request-to-package-tenant"


def _engine() -> MockRecallEngine:
    async def _forward(tlc, tenant_id=None):
        return {
            "lots": [{"tlc": tlc}],
            "hop_count": 1,
            "facilities": [],
            "trace_rows": [],
        }

    return MockRecallEngine(trace_forward_fn=_forward)


@pytest.mark.asyncio
async def test_stale_request_breaches_sla_despite_fast_compute():
    """A drill requested 25h ago breaches even though execution takes ms."""
    engine = _engine()
    drill = engine.create_drill(
        tenant_id=TENANT,
        drill_type=RecallType.FORWARD_TRACE,
        target_lot="LOT-STALE",
    )
    drill.created_at = datetime.now(timezone.utc) - timedelta(hours=25)

    result = await engine.execute_drill(drill)

    assert result.total_time_seconds >= 24 * 3600
    assert result.sla_compliant is False


@pytest.mark.asyncio
async def test_fresh_request_stays_compliant_and_matches_created_at():
    """A fresh drill stays compliant and total time covers request to finish."""
    engine = _engine()
    before = datetime.now(timezone.utc)
    drill = engine.create_drill(
        tenant_id=TENANT,
        drill_type=RecallType.FORWARD_TRACE,
        target_lot="LOT-FRESH",
    )

    result = await engine.execute_drill(drill)

    assert result.sla_compliant is True
    assert result.total_time_seconds >= 0
    expected = (drill.completed_at - drill.created_at).total_seconds()
    assert result.total_time_seconds == pytest.approx(expected, abs=1.0)
    assert drill.created_at >= before
