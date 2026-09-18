"""Regression tests for FDA-export performance hardening (#2515, #2516).

#2515 — ``/export/all`` previously looped ``query_events_by_tlc`` once per
        distinct traceability lot code, fanning out into O(distinct_TLCs)
        recursive-CTE + unbounded-SELECT round-trips on a single pooled
        connection. It now expands all seed TLCs in one recursive CTE and
        fetches their events with one bounded set-based query
        (``query_events_by_tlcs``).

#2516 — the four FDA-export handlers that open a synchronous ``SessionLocal()``
        were ``async def``, running blocking psycopg I/O directly on the shared
        event loop. They are now plain ``def`` so FastAPI runs them in its
        threadpool and a slow export no longer stalls every other tenant.
"""

from __future__ import annotations

import inspect
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import shared.cte_persistence as shared_cte_persistence
from services.ingestion.app.authz import IngestionPrincipal
from services.ingestion.app.fda_export.router import router as fda_router

# The ``app.fda_export`` package re-exports the ``router`` APIRouter, which
# shadows the ``router`` *submodule* as a package attribute. Pull the actual
# module object out of ``sys.modules`` so we can introspect handler functions.
fda_router_module = sys.modules["services.ingestion.app.fda_export.router"]

from services.ingestion.tests.authz_overrides import (
    install_active_subscription_override,
    install_ingestion_principal_override,
)

TENANT = "00000000-0000-0000-0000-000000000111"


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class _FakeChainVerification:
    valid = True
    chain_length = 3
    errors: list[str] = []
    checked_at = "2026-03-10T10:00:00+00:00"


class _FakeSession:
    def execute(self, *_args, **_kwargs):
        class _R:
            def fetchone(self):
                return None

            def fetchall(self):
                return []

        return _R()

    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


def _event(idx: int, tlc: str) -> dict:
    return {
        "id": f"evt-{idx}",
        "event_type": "shipping",
        "traceability_lot_code": tlc,
        "product_description": "Romaine Hearts",
        "quantity": 1.0,
        "unit_of_measure": "cases",
        "location_gln": "0614141000005",
        "location_name": "Valley Fresh Farms",
        "event_timestamp": "2026-03-10T09:00:00+00:00",
        "sha256_hash": "a" * 64,
        "chain_hash": "b" * 64,
        "source": "webhook",
        "kdes": {
            "ship_date": "2026-03-10",
            "ship_from_location": "Valley Fresh Farms",
            "ship_to_location": "Metro DC",
        },
    }


def _install_fake_dependencies(monkeypatch, persistence_cls) -> None:
    fake_db = types.ModuleType("shared.database")
    fake_db.SessionLocal = lambda: _FakeSession()
    monkeypatch.setitem(sys.modules, "shared.database", fake_db)
    monkeypatch.setattr(shared_cte_persistence, "CTEPersistence", persistence_cls)


def _make_client(monkeypatch, persistence_cls) -> TestClient:
    app = FastAPI()
    app.include_router(fda_router)
    install_ingestion_principal_override(
        app,
        IngestionPrincipal(key_id="test-key", scopes=["*"], auth_mode="test"),
    )
    install_active_subscription_override(app)
    _install_fake_dependencies(monkeypatch, persistence_cls)
    return TestClient(app)


# ---------------------------------------------------------------------------
# #2515 — bounded round-trips on /export/all
# ---------------------------------------------------------------------------


def test_export_all_uses_single_batch_call_regardless_of_tlc_count(monkeypatch):
    """``/export/all`` must call the batch query exactly once and never call
    the per-TLC ``query_events_by_tlc`` in a loop, no matter how many distinct
    lot codes are in the window (#2515)."""

    N_TLCS = 250  # large fan-out: the old loop would issue ~250 query calls

    class _CountingPersistence:
        per_tlc_calls = 0
        batch_calls = 0

        def __init__(self, _session):
            pass

        def query_all_events(self, **_kwargs):
            tlcs = [f"TLC-{i:04d}" for i in range(N_TLCS)]
            return ([{"traceability_lot_code": t} for t in tlcs], N_TLCS)

        def query_events_by_tlc(self, **_kwargs):  # pragma: no cover - must not run
            type(self).per_tlc_calls += 1
            return []

        def query_events_by_tlcs(self, tenant_id, tlcs, **_kwargs):
            type(self).batch_calls += 1
            return [_event(i, t) for i, t in enumerate(tlcs)]

        def verify_chain(self, **_kwargs):
            return _FakeChainVerification()

        def log_export(self, **_kwargs):
            return "log-id"

    client = _make_client(monkeypatch, _CountingPersistence)
    with client:
        r = client.get(
            "/api/v1/fda/export/all",
            params={
                "tenant_id": TENANT,
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "allow_incomplete": "true",
            },
        )

    assert r.status_code == 200, r.text
    # Constant fan-out: one batch call, zero per-TLC calls — regardless of the
    # 250 distinct lot codes.
    assert _CountingPersistence.batch_calls == 1
    assert _CountingPersistence.per_tlc_calls == 0


# ---------------------------------------------------------------------------
# #2515 — query_events_by_tlcs issues a bounded number of DB statements
# ---------------------------------------------------------------------------


class _StmtCountingSession:
    """Records every executed SQL statement so a test can assert the round-trip
    count is bounded (not proportional to the seed-TLC count)."""

    def __init__(self, *, event_rows, tlc_rows):
        self.statements: list[str] = []
        self._event_rows = event_rows
        self._tlc_rows = tlc_rows

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)

        class _R:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

            def fetchone(self):
                return self._rows[0] if self._rows else None

        if "RECURSIVE" in sql:
            return _R(self._tlc_rows)
        if "fsma.cte_events" in sql:
            return _R(self._event_rows)
        if "fsma.cte_kdes" in sql:
            return _R([])
        # set_tenant_guc / SELECT 1 etc.
        return _R([])


def test_query_events_by_tlcs_bounded_round_trips(monkeypatch):
    """``query_events_by_tlcs`` must issue a constant number of DB round-trips:
    one transformation-link expansion + one events SELECT + chunked KDE fetch,
    regardless of how many seed TLCs are passed (#2515)."""

    from datetime import datetime, timezone

    from shared.cte_persistence import CTEPersistence

    ts = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)
    # One event row in the cte_events SELECT shape (15 columns).
    event_rows = [
        (
            "evt-1",
            "shipping",
            "TLC-0001",
            "Romaine",
            1.0,
            "cases",
            "0614141000005",
            "Valley Fresh",
            ts,
            "a" * 64,
            "b" * 64,
            "webhook",
            "validated",
            ts,
            ts,
        )
    ]
    tlc_rows = [("TLC-0001",), ("TLC-0002",)]

    session = _StmtCountingSession(event_rows=event_rows, tlc_rows=tlc_rows)
    persistence = CTEPersistence(session)
    # Skip the RLS GUC set (requires real Postgres / UUID validation path).
    monkeypatch.setattr(persistence, "set_tenant_context", lambda *_a, **_k: None)

    seeds = [f"TLC-{i:04d}" for i in range(100)]
    events = persistence.query_events_by_tlcs(TENANT, seeds)

    assert len(events) == 1
    recursive = [s for s in session.statements if "RECURSIVE" in s]
    event_selects = [s for s in session.statements if "fsma.cte_events" in s]
    # Exactly one recursive expansion and one events SELECT for 100 seeds —
    # the old per-TLC loop would have produced 100 of each.
    assert len(recursive) == 1
    assert len(event_selects) == 1


def test_query_events_by_tlcs_empty_input_no_db(monkeypatch):
    """Empty seed list short-circuits before touching the DB."""
    from shared.cte_persistence import CTEPersistence

    session = _StmtCountingSession(event_rows=[], tlc_rows=[])
    persistence = CTEPersistence(session)
    monkeypatch.setattr(persistence, "set_tenant_context", lambda *_a, **_k: None)

    assert persistence.query_events_by_tlcs(TENANT, []) == []
    assert session.statements == []


# ---------------------------------------------------------------------------
# #2516 — handlers no longer block the event loop
# ---------------------------------------------------------------------------

_OFFLOADED_HANDLERS = [
    "export_fda_spreadsheet",
    "export_all_events",
    "export_fda_spreadsheet_v2",
    "trace_transformation_graph",
]


@pytest.mark.parametrize("handler_name", _OFFLOADED_HANDLERS)
def test_blocking_handlers_are_sync_def(handler_name):
    """Guard (#2516): the FDA-export handlers that open a synchronous
    ``SessionLocal()`` must be plain ``def`` so FastAPI runs them in its
    threadpool. An ``async def`` here would run blocking psycopg I/O directly
    on the shared event loop and stall every other tenant's request."""
    handler = getattr(fda_router_module, handler_name)
    assert not inspect.iscoroutinefunction(handler), (
        f"{handler_name} is async def but performs blocking sync DB I/O; "
        "it must be plain def (or offload via run_in_threadpool) — see #2516."
    )


def test_export_handler_runs_off_the_event_loop(monkeypatch):
    """The blocking DB work must execute in a worker thread, not on the event
    loop (#2516).

    Because the handler is plain ``def``, Starlette dispatches it through
    ``run_in_threadpool``: the synchronous body runs in a thread that is *not*
    the event-loop (main) thread. If the handler were ``async def``, the body
    — including the blocking psycopg call captured here — would run on the
    main/event-loop thread instead. We capture the executing thread inside the
    persistence layer and assert it is not the main thread."""

    main_thread = threading.main_thread()
    captured: dict[str, Any] = {}

    class _ThreadCapturingPersistence:
        def __init__(self, _session):
            pass

        def query_all_events(self, **_kwargs):
            return ([{"traceability_lot_code": "TLC-0001"}], 1)

        def query_events_by_tlcs(self, **_kwargs):
            captured["thread"] = threading.current_thread()
            # Sleep to make the point that this would freeze the loop if it
            # ran there; kept short so the suite stays fast.
            time.sleep(0.05)
            return [_event(1, "TLC-0001")]

        def verify_chain(self, **_kwargs):
            return _FakeChainVerification()

        def log_export(self, **_kwargs):
            return "log-id"

    client = _make_client(monkeypatch, _ThreadCapturingPersistence)
    with client:
        r = client.get(
            "/api/v1/fda/export/all",
            params={
                "tenant_id": TENANT,
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "allow_incomplete": "true",
            },
        )

    assert r.status_code == 200, r.text
    assert "thread" in captured, "persistence layer was never reached"
    assert captured["thread"] is not main_thread, (
        "blocking DB work ran on the event-loop (main) thread — the handler "
        "is not being offloaded to the threadpool (#2516)."
    )
