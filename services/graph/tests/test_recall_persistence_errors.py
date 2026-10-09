"""Recall persistence helpers must surface DB failures (audit re-services).

Regression tests: every helper in
``services.graph.app.fsma_recall.persistence`` used to catch all
exceptions, log a warning, and return a success-shaped default (None /
[]), so a database outage was reported to callers as "no drills" and
drill history was silently lost. These tests require failures to
propagate instead.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma_recall.models import (  # noqa: E402
    RecallDrill,
    RecallSeverity,
    RecallStatus,
    RecallType,
)
from services.graph.app.fsma_recall.persistence import (  # noqa: E402
    _get_db_engine,
    _load_drill_by_id_from_db,
    _load_drills_from_db,
    _select_random_target_lot,
    _update_drill_row,
    _upsert_drill_row,
)


def _make_drill() -> RecallDrill:
    return RecallDrill(
        drill_id="drill_persist_err_0001",
        tenant_id="tenant_1",
        created_at=datetime.now(timezone.utc),
        drill_type=RecallType.FORWARD_TRACE,
        severity=RecallSeverity.CLASS_II,
        status=RecallStatus.PENDING,
    )


def _broken_engine() -> MagicMock:
    engine = MagicMock()
    engine.connect.side_effect = RuntimeError("db down")
    return engine


def test_upsert_surfaces_db_error():
    """A failed drill insert must raise, not vanish into a warning."""
    with pytest.raises(RuntimeError, match="db down"):
        _upsert_drill_row(_broken_engine(), _make_drill())


def test_update_surfaces_db_error():
    """A failed drill update must raise, not vanish into a warning."""
    with pytest.raises(RuntimeError, match="db down"):
        _update_drill_row(_broken_engine(), _make_drill())


def test_load_drills_surfaces_db_error():
    """A failed history read must raise, not pose as an empty history."""
    with pytest.raises(RuntimeError, match="db down"):
        _load_drills_from_db(_broken_engine(), "tenant_1")


def test_load_drill_by_id_surfaces_db_error():
    """A failed drill lookup must raise, not pose as 'not found'."""
    with pytest.raises(RuntimeError, match="db down"):
        _load_drill_by_id_from_db(_broken_engine(), "tenant_1", "drill_x")


def test_select_random_target_lot_surfaces_db_error():
    """A failed target-lot query must raise, not pose as 'no lots'."""
    with pytest.raises(RuntimeError, match="db down"):
        _select_random_target_lot(_broken_engine(), "tenant_1")


def test_get_db_engine_returns_none_when_unset(monkeypatch):
    """No DATABASE_URL still means 'no database', not an error."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _get_db_engine() is None


def test_create_drill_surfaces_persist_failure():
    """End to end: create_drill must not report success when history is lost."""
    from services.graph.app.fsma_recall.engine import MockRecallEngine

    engine = MockRecallEngine()
    engine._db_engine = _broken_engine()
    with pytest.raises(RuntimeError, match="db down"):
        engine.create_drill(
            tenant_id="tenant_1",
            drill_type=RecallType.FORWARD_TRACE,
        )
