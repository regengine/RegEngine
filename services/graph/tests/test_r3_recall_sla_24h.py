"""Data-free tests for the 24-hour recall SLA under 21 CFR 1.1455(c)(1).

21 CFR 1.1455(c)(1) requires traceability records to be provided to FDA
within 24 hours of a request. ``RecallDrill.sla_status`` encodes that limit
as ``sla_limit = 24 * 3600``. These tests use timestamps only; no records,
CSV rows or EPCIS documents are involved.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import datetime, timedelta, timezone

from services.graph.app.fsma_recall import models
from services.graph.app.fsma_recall.models import (
    RecallDrill,
    RecallSeverity,
    RecallStatus,
    RecallType,
    SLAStatus,
)

LIMIT = timedelta(hours=24)


def _drill(**kwargs) -> RecallDrill:
    return RecallDrill(
        drill_id="",
        tenant_id="",
        created_at=datetime.now(timezone.utc),
        drill_type=list(RecallType)[0],
        severity=list(RecallSeverity)[0],
        **kwargs,
    )


def test_sla_limit_is_24_hours_in_source():
    """21 CFR 1.1455(c)(1): the limit literal is ``24 * 3600`` seconds."""
    src = textwrap.dedent(inspect.getsource(RecallDrill.sla_status.fget))
    assigns = {
        n.targets[0].id: n.value
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
    }
    assert "sla_limit" in assigns
    assert eval(compile(ast.Expression(assigns["sla_limit"]), "<sla>", "eval")) == 24 * 3600


def test_sla_status_enum_values():
    """21 CFR 1.1455(c)(1): MET / AT_RISK / BREACHED states exist."""
    assert {s.value for s in SLAStatus} >= {"met", "at_risk", "breached"}
    assert models.SLAStatus is SLAStatus


def test_not_started_is_met():
    """21 CFR 1.1455(c)(1): the clock has not started without started_at."""
    assert _drill().sla_status == SLAStatus.MET


def test_completed_exactly_24h_is_met():
    """21 CFR 1.1455(c)(1): completing at exactly 24h meets the limit."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d = _drill(status=RecallStatus.COMPLETED, started_at=start, completed_at=start + LIMIT)
    assert d.sla_status == SLAStatus.MET


def test_completed_one_second_over_24h_is_breached():
    """21 CFR 1.1455(c)(1): one second past 24h breaches the limit."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d = _drill(
        status=RecallStatus.COMPLETED,
        started_at=start,
        completed_at=start + LIMIT + timedelta(seconds=1),
    )
    assert d.sla_status == SLAStatus.BREACHED


def test_in_progress_thresholds():
    """21 CFR 1.1455(c)(1): in-progress drills go MET -> AT_RISK (>75%) -> BREACHED (>24h)."""
    now = datetime.now(timezone.utc)
    cases = [
        (timedelta(hours=1), SLAStatus.MET),
        (timedelta(hours=19), SLAStatus.AT_RISK),
        (LIMIT + timedelta(hours=1), SLAStatus.BREACHED),
    ]
    for elapsed, expected in cases:
        d = _drill(status=RecallStatus.IN_PROGRESS, started_at=now - elapsed)
        assert d.sla_status == expected, elapsed
