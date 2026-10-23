"""Data-free FDA export verifier fail-closed and shared-query checks."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent))

import shared.cte_persistence as shared_cte_persistence  # noqa: E402
from app.fda_export import queries, verification  # noqa: E402


class _EmptyAuditSession:
    def __init__(self) -> None:
        self.closed = False

    def execute(self, _statement, _params):
        class Result:
            def fetchone(self):
                return None

        return Result()

    def close(self) -> None:
        self.closed = True


def test_missing_export_refuses_verification_without_event_query(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _EmptyAuditSession()
    database = types.ModuleType("shared.database")
    database.SessionLocal = lambda: session
    monkeypatch.setitem(sys.modules, "shared.database", database)
    monkeypatch.setattr(shared_cte_persistence, "CTEPersistence", lambda _session: object())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(verification.verify_export_handler("", ""))
    assert exc.value.status_code == 404
    assert session.closed


def test_exporter_and_verifier_share_one_helper() -> None:
    assert verification.reconstruct_full_export_events is queries.reconstruct_full_export_events


def test_empty_reconstruction_is_deterministic() -> None:
    class EmptyPersistence:
        def query_all_events(self, **_kwargs):
            return [], 0

        def query_events_by_tlcs(self, **kwargs):
            assert kwargs["tlcs"] == []
            return []

    result = queries.reconstruct_full_export_events(
        EmptyPersistence(), tenant_id="", start_date=None, end_date=None, event_type=None
    )
    assert result == ([], 0)
