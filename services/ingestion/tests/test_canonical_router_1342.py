"""Full-coverage tests for ``app.canonical_router`` (#1342).

Complements ``tests/test_canonical_router.py`` by exercising branches it
misses:

- ``list_records`` filter branches for ``source_system``, ``start_date``,
  and ``end_date`` (lines 103-110).
- ``get_record`` rule_evaluations + exception_cases + amendment_chain
  enrichment paths (lines 297-353). The existing file has two tests
  here but they fail with ``TypeError: get_event() got an unexpected
  keyword argument 'include_raw_payload'`` because their stub is stale;
  we use a stub that matches today's signature.
- ``_get_amendment_chain`` forward-walk loop (lines 415-421).
- ``trace_forward`` and ``trace_backward`` endpoints (lines 466-490 and
  509-532), including the empty-links branch (``total_hops=0``) and
  the non-empty branch (``max(depth)``).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

pytest.importorskip("fastapi")

from app.authz import IngestionPrincipal, get_ingestion_principal
import app.canonical_router as cr_module
from app.canonical_router import _get_db_session, router as canonical_router


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENANT_ID = "00000000-0000-0000-0000-000000000111"
EVENT_ID = "evt-abc-001"
NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fake DB — queue-based execute() so each call returns the next programmed
# result. Mirrors the pattern in the existing test file for consistency.
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, *, row: Any = None, rows: Optional[List[Any]] = None) -> None:
        self._row = row
        self._rows = rows or []

    def fetchone(self) -> Any:
        return self._row

    def fetchall(self) -> List[Any]:
        return self._rows


class _FakeSession:
    """Programmable fake session that records each ``execute`` call."""

    def __init__(self, results: Optional[List[_Result]] = None) -> None:
        self._results = list(results or [])
        self._call_index = 0
        self.calls: List[tuple] = []  # (sql, params) per execute call

    def execute(self, statement, params=None):
        # ``statement`` may be a SQLAlchemy ``TextClause``; render to str so
        # assertions can inspect the SQL without importing sqlalchemy.text.
        self.calls.append((str(statement), params))
        if self._call_index < len(self._results):
            result = self._results[self._call_index]
            self._call_index += 1
            return result
        return _Result()

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


def _make_event_row(
    *,
    event_id: str = EVENT_ID,
    event_type: str = "shipping",
    tlc: str = "TLC-2026-001",
    product_ref: str = "PROD-001",
    quantity: float = 100.0,
    uom: str = "cases",
    from_facility: str = "FAC-A",
    to_facility: str = "FAC-B",
    ts: datetime = NOW,
    source_system: str = "webhook",
    status: str = "active",
    confidence: float = 0.98,
    schema_version: str = "1.0",
    created_at: datetime = NOW,
) -> tuple:
    return (
        event_id, event_type, tlc, product_ref, quantity, uom,
        from_facility, to_facility, ts, source_system, status,
        confidence, schema_version, created_at,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def principal() -> IngestionPrincipal:
    # Wildcard scope passes both ``records.read`` permission and tenant
    # resolution for any ``tenant_id`` query param.
    return IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        tenant_id=TENANT_ID,
        auth_mode="test",
    )


def _client(principal: IngestionPrincipal, session: Optional[_FakeSession]) -> TestClient:
    app = FastAPI()
    app.include_router(canonical_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal
    app.dependency_overrides[_get_db_session] = lambda: session
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# list_records — remaining filter branches (source_system / start / end)
# ---------------------------------------------------------------------------


class TestListRecordsRemainingFilters:
    """Exercise the three filter branches the existing file skips."""

    ENDPOINT = "/api/v1/records"

    def test_source_system_filter_adds_where_fragment(
        self, principal: IngestionPrincipal
    ) -> None:
        session = _FakeSession([
            _Result(row=(1,)),
            _Result(rows=[_make_event_row(source_system="epcis")]),
        ])
        c = _client(principal, session)
        resp = c.get(
            self.ENDPOINT,
            params={"tenant_id": TENANT_ID, "source_system": "epcis"},
        )
        assert resp.status_code == 200
        # Verify the COUNT call saw ``source_system`` in its WHERE and
        # the correct param was bound.
        count_sql, count_params = session.calls[0]
        assert "source_system = :source_system" in count_sql
        assert count_params["source_system"] == "epcis"

    def test_start_date_filter_adds_where_fragment(
        self, principal: IngestionPrincipal
    ) -> None:
        session = _FakeSession([
            _Result(row=(1,)),
            _Result(rows=[_make_event_row()]),
        ])
        c = _client(principal, session)
        resp = c.get(
            self.ENDPOINT,
            params={"tenant_id": TENANT_ID, "start_date": "2026-01-01T00:00:00Z"},
        )
        assert resp.status_code == 200
        count_sql, count_params = session.calls[0]
        assert "event_timestamp >= :start_date" in count_sql
        assert count_params["start_date"] == "2026-01-01T00:00:00Z"

    def test_end_date_filter_adds_where_fragment(
        self, principal: IngestionPrincipal
    ) -> None:
        session = _FakeSession([
            _Result(row=(1,)),
            _Result(rows=[_make_event_row()]),
        ])
        c = _client(principal, session)
        resp = c.get(
            self.ENDPOINT,
            params={"tenant_id": TENANT_ID, "end_date": "2026-12-31T23:59:59Z"},
        )
        assert resp.status_code == 200
        count_sql, count_params = session.calls[0]
        assert "event_timestamp <= :end_date" in count_sql
        assert count_params["end_date"] == "2026-12-31T23:59:59Z"

    def test_all_filters_combined(self, principal: IngestionPrincipal) -> None:
        session = _FakeSession([
            _Result(row=(1,)),
            _Result(rows=[_make_event_row()]),
        ])
        c = _client(principal, session)
        resp = c.get(
            self.ENDPOINT,
            params={
                "tenant_id": TENANT_ID,
                "tlc": "TLC-1",
                "event_type": "shipping",
                "status": "active",
                "source_system": "epcis",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        )
        assert resp.status_code == 200
        count_sql, count_params = session.calls[0]
        for fragment in (
            "tenant_id = :tid",
            "traceability_lot_code = :tlc",
            "event_type = :event_type",
            "status = :status",
            "source_system = :source_system",
            "event_timestamp >= :start_date",
            "event_timestamp <= :end_date",
        ):
            assert fragment in count_sql
        # Confirm params bound correctly.
        assert count_params["tlc"] == "TLC-1"
        assert count_params["event_type"] == "shipping"
        assert count_params["source_system"] == "epcis"


# ---------------------------------------------------------------------------
# get_record — rule evaluations + exceptions + amendment_chain
# ---------------------------------------------------------------------------


class _EventStoreStub:
    """Stub matching today's ``CanonicalEventStore.get_event`` signature.

    Accepts the ``include_raw_payload`` kwarg that #1297 added and is
    patched into both the module-level and the lazy ``from shared...``
    import performed inside ``get_record``.
    """

    def __init__(self, event: Optional[Dict[str, Any]] = None) -> None:
        self._event = event

    def __call__(self, session: Any, dual_write: bool = False) -> "_EventStoreStub":
        # ``CanonicalEventStore(db_session, dual_write=False)`` → returns self.
        return self

    def get_event(
        self,
        tenant_id: str,
        event_id: str,
        *,
        include_raw_payload: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if self._event is None:
            return None
        # Return a copy so each test sees a fresh dict.
        event = dict(self._event)
        if include_raw_payload:
            event["raw_payload"] = {"included": True}
        return event


def _patch_event_store(
    monkeypatch: pytest.MonkeyPatch, event: Optional[Dict[str, Any]]
) -> _EventStoreStub:
    """Install ``stub`` in both places the router reaches for the class."""
    stub = _EventStoreStub(event)
    # Route module-level import (used by trace_forward / trace_backward).
    monkeypatch.setattr(cr_module, "CanonicalEventStore", stub)
    # Route the lazy ``from shared.canonical_persistence import ...``
    # inside ``get_record``.
    import shared.canonical_persistence as persistence_mod
    monkeypatch.setattr(persistence_mod, "CanonicalEventStore", stub)
    return stub


class TestGetRecord:
    """get_record body — covers lines 297-353."""

    def test_returns_record_with_evaluations_and_exceptions(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_event_store(
            monkeypatch,
            {
                "event_id": EVENT_ID,
                "event_type": "shipping",
                "tenant_id": TENANT_ID,
                # No supersedes → skip amendment_chain branch in this test.
                "supersedes_event_id": None,
            },
        )
        session = _FakeSession([
            # 1. rule_evaluations query
            _Result(rows=[(
                "fail", "Missing TLC", "TLC Required",
                "critical", "21 CFR 1.1315",
                "Add traceability lot code", "data_quality",
            )]),
            # 2. exception_cases query
            _Result(rows=[(
                "case-001", "high", "open", "Review record",
                "user-1", NOW,
            )]),
        ])
        c = _client(principal, session)
        resp = c.get(
            f"/api/v1/records/{EVENT_ID}",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_id"] == EVENT_ID
        # Rule evaluation enrichment landed.
        assert body["rule_evaluations"] == [{
            "result": "fail",
            "why_failed": "Missing TLC",
            "rule_title": "TLC Required",
            "severity": "critical",
            "citation_reference": "21 CFR 1.1315",
            "remediation_suggestion": "Add traceability lot code",
            "category": "data_quality",
        }]
        # Exception case enrichment landed; due_date is isoformatted.
        assert body["exception_cases"] == [{
            "case_id": "case-001",
            "severity": "high",
            "status": "open",
            "recommended_remediation": "Review record",
            "owner_user_id": "user-1",
            "due_date": NOW.isoformat(),
        }]
        # No supersedes → no amendment_chain key.
        assert "amendment_chain" not in body
        # And raw payload was requested (covers the include_raw_payload=True
        # call site at line 295).
        assert body["raw_payload"] == {"included": True}

    def test_record_not_found_returns_404(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_event_store(monkeypatch, None)
        # No DB calls happen once ``get_event`` returns None.
        session = _FakeSession([])
        c = _client(principal, session)
        resp = c.get(f"/api/v1/records/{EVENT_ID}", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Record not found"

    def test_empty_evaluations_and_exceptions(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_event_store(
            monkeypatch,
            {"event_id": EVENT_ID, "tenant_id": TENANT_ID},
        )
        session = _FakeSession([
            _Result(rows=[]),  # no evaluations
            _Result(rows=[]),  # no exception cases
        ])
        c = _client(principal, session)
        resp = c.get(f"/api/v1/records/{EVENT_ID}", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        body = resp.json()
        assert body["rule_evaluations"] == []
        assert body["exception_cases"] == []

    def test_exception_case_with_null_due_date(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Covers the ``r[5].isoformat() if r[5] else None`` ternary's None
        # branch at line 344.
        _patch_event_store(
            monkeypatch,
            {"event_id": EVENT_ID, "tenant_id": TENANT_ID},
        )
        session = _FakeSession([
            _Result(rows=[]),
            _Result(rows=[(
                "case-002", "low", "closed", "Noop", "user-2", None,
            )]),
        ])
        c = _client(principal, session)
        resp = c.get(f"/api/v1/records/{EVENT_ID}", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        assert resp.json()["exception_cases"][0]["due_date"] is None

    def test_record_with_supersedes_triggers_amendment_chain(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_event_store(
            monkeypatch,
            {
                "event_id": EVENT_ID,
                "tenant_id": TENANT_ID,
                "supersedes_event_id": "evt-prev",
            },
        )
        # Execute order:
        # 1. rule_evaluations
        # 2. exception_cases
        # 3. _get_amendment_chain backward step 1 (this event supersedes evt-prev)
        # 4. _get_amendment_chain backward step 2 (evt-prev → no further link)
        # 5. _get_amendment_chain forward step 1 (no successor)
        session = _FakeSession([
            _Result(rows=[]),
            _Result(rows=[]),
            _Result(row=(EVENT_ID, "evt-prev", "shipping", "active", NOW, None)),
            _Result(row=("evt-prev", None, "shipping", "superseded", NOW, None)),
            _Result(row=None),
        ])
        c = _client(principal, session)
        resp = c.get(f"/api/v1/records/{EVENT_ID}", params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        body = resp.json()
        assert body["amendment_chain"] == [{
            "event_id": "evt-prev",
            "superseded_by": EVENT_ID,
            "status": "superseded",
        }]


# ---------------------------------------------------------------------------
# _get_amendment_chain — forward-walk branch (lines 415-421)
# ---------------------------------------------------------------------------


class TestAmendmentChainForwardWalk:
    """``/history`` endpoint is a thin wrapper around ``_get_amendment_chain``
    — exercising it is the cleanest way to hit the forward-walk body."""

    ENDPOINT_TEMPLATE = "/api/v1/records/{event_id}/history"

    def test_forward_walk_appends_successor(
        self, principal: IngestionPrincipal
    ) -> None:
        # Backward walk: initial event has no supersedes → loop exits
        # after one probe.
        # Forward walk: initial event HAS a successor → loop appends and
        # then the second probe returns None → loop exits.
        session = _FakeSession([
            # backward step: event has no supersedes (row[1] is None).
            _Result(row=(EVENT_ID, None, "shipping", "active", NOW, None)),
            # forward step 1: successor found.
            _Result(row=("evt-new", "active", NOW)),
            # forward step 2: no further successor.
            _Result(row=None),
        ])
        c = _client(principal, session)
        resp = c.get(self.ENDPOINT_TEMPLATE.format(event_id=EVENT_ID),
                     params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        chain = resp.json()["amendment_chain"]
        # One forward-walk entry appended.
        assert chain == [{
            "event_id": "evt-new",
            "supersedes": EVENT_ID,
            "status": "active",
            "created_at": NOW.isoformat(),
        }]

    def test_forward_walk_null_created_at(
        self, principal: IngestionPrincipal
    ) -> None:
        """Covers the ``r[2].isoformat() if r[2] else None`` None branch."""
        session = _FakeSession([
            _Result(row=(EVENT_ID, None, "shipping", "active", NOW, None)),
            _Result(row=("evt-new", "active", None)),  # created_at = None
            _Result(row=None),
        ])
        c = _client(principal, session)
        resp = c.get(self.ENDPOINT_TEMPLATE.format(event_id=EVENT_ID),
                     params={"tenant_id": TENANT_ID})
        assert resp.status_code == 200
        chain = resp.json()["amendment_chain"]
        assert chain[0]["created_at"] is None


# ---------------------------------------------------------------------------
# trace_forward and trace_backward
# ---------------------------------------------------------------------------


class _TraceStoreStub:
    """Callable stub for ``CanonicalEventStore(...)`` used by trace
    endpoints. ``trace_forward`` and ``trace_backward`` return
    ``(list_of_links, truncated_bool)`` in the current store contract."""

    def __init__(
        self,
        forward_result: Optional[tuple] = None,
        backward_result: Optional[tuple] = None,
    ) -> None:
        self._forward = forward_result or ([], False)
        self._backward = backward_result or ([], False)
        self.forward_calls: List[tuple] = []
        self.backward_calls: List[tuple] = []

    def __call__(self, session: Any, dual_write: bool = False) -> "_TraceStoreStub":
        return self

    def trace_forward(
        self, tenant_id: str, tlc: str, max_depth: int = 5, max_results: int = 10000
    ) -> tuple:
        self.forward_calls.append((tenant_id, tlc, max_depth, max_results))
        return self._forward

    def trace_backward(
        self, tenant_id: str, tlc: str, max_depth: int = 5, max_results: int = 10000
    ) -> tuple:
        self.backward_calls.append((tenant_id, tlc, max_depth, max_results))
        return self._backward


def _patch_trace_store(
    monkeypatch: pytest.MonkeyPatch, stub: _TraceStoreStub
) -> None:
    monkeypatch.setattr(cr_module, "CanonicalEventStore", stub)


class TestTraceForward:
    ENDPOINT_TEMPLATE = "/api/v1/records/trace/forward/{tlc}"

    def test_db_unavailable_returns_503(self, principal: IngestionPrincipal) -> None:
        c = _client(principal, None)
        resp = c.get(self.ENDPOINT_TEMPLATE.format(tlc="TLC-1"))
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Database unavailable"

    def test_empty_links_total_hops_zero(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = _TraceStoreStub(forward_result=([], False))
        _patch_trace_store(monkeypatch, stub)
        # Also provide a session so the SET LOCAL call succeeds.
        session = _FakeSession([_Result()])
        c = _client(principal, session)
        resp = c.get(
            self.ENDPOINT_TEMPLATE.format(tlc="TLC-EMPTY"),
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tlc"] == "TLC-EMPTY"
        assert body["direction"] == "forward"
        assert body["links"] == []
        assert body["total_hops"] == 0
        assert body["truncated"] is False
        # SET LOCAL pragma was issued.
        sql, params = session.calls[0]
        assert "SET LOCAL app.tenant_id" in sql
        assert params == {"tid": TENANT_ID}
        # Store was called with the resolved tenant.
        assert stub.forward_calls == [(TENANT_ID, "TLC-EMPTY", 5, 10000)]

    def test_populated_links_compute_max_depth(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        raw_links = [
            {
                "input_tlc": "TLC-A", "output_tlc": "TLC-B",
                "transformation_event_id": "evt-1",
                "process_type": "repack",
                "depth": 1,
                "confidence_score": 0.9,
                "output_quantity": 10.0,
                "output_unit": "cases",
            },
            {
                "input_tlc": "TLC-B", "output_tlc": "TLC-C",
                "transformation_event_id": "evt-2",
                # No process_type / confidence / quantity / unit -> defaults.
                "depth": 3,
            },
        ]
        stub = _TraceStoreStub(forward_result=(raw_links, True))
        _patch_trace_store(monkeypatch, stub)
        session = _FakeSession([_Result()])
        c = _client(principal, session)
        resp = c.get(
            self.ENDPOINT_TEMPLATE.format(tlc="TLC-A"),
            params={"tenant_id": TENANT_ID, "max_depth": 10},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_hops"] == 3  # max(depth) across raw_links
        assert body["truncated"] is True
        assert len(body["links"]) == 2
        # First link keeps populated fields.
        first = body["links"][0]
        assert first["input_tlc"] == "TLC-A"
        assert first["output_tlc"] == "TLC-B"
        assert first["transformation_event_id"] == "evt-1"
        assert first["process_type"] == "repack"
        assert first["confidence_score"] == 0.9
        assert first["quantity"] == 10.0
        assert first["unit"] == "cases"
        # Second link uses defaults (process_type None, confidence 1.0).
        second = body["links"][1]
        assert second["process_type"] is None
        assert second["confidence_score"] == 1.0
        assert second["quantity"] is None
        assert second["unit"] is None
        # Store was called with the custom ``max_depth``.
        assert stub.forward_calls[0][2] == 10


class TestTraceBackward:
    ENDPOINT_TEMPLATE = "/api/v1/records/trace/backward/{tlc}"

    def test_db_unavailable_returns_503(self, principal: IngestionPrincipal) -> None:
        c = _client(principal, None)
        resp = c.get(self.ENDPOINT_TEMPLATE.format(tlc="TLC-1"))
        assert resp.status_code == 503

    def test_empty_links_total_hops_zero(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = _TraceStoreStub(backward_result=([], False))
        _patch_trace_store(monkeypatch, stub)
        session = _FakeSession([_Result()])
        c = _client(principal, session)
        resp = c.get(
            self.ENDPOINT_TEMPLATE.format(tlc="TLC-EMPTY"),
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["direction"] == "backward"
        assert body["links"] == []
        assert body["total_hops"] == 0
        assert body["truncated"] is False
        # Pragma issued.
        sql, _ = session.calls[0]
        assert "SET LOCAL app.tenant_id" in sql
        assert stub.backward_calls == [(TENANT_ID, "TLC-EMPTY", 5, 10000)]

    def test_populated_links_use_input_quantity_and_unit(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Backward trace pulls ``input_quantity`` / ``input_unit`` off each
        # raw row (vs ``output_*`` for the forward endpoint).
        raw_links = [
            {
                "input_tlc": "TLC-A", "output_tlc": "TLC-B",
                "transformation_event_id": "evt-1",
                "process_type": "blend",
                "depth": 2,
                "confidence_score": 0.75,
                "input_quantity": 5.5,
                "input_unit": "kg",
            },
        ]
        stub = _TraceStoreStub(backward_result=(raw_links, False))
        _patch_trace_store(monkeypatch, stub)
        session = _FakeSession([_Result()])
        c = _client(principal, session)
        resp = c.get(
            self.ENDPOINT_TEMPLATE.format(tlc="TLC-B"),
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_hops"] == 2
        link = body["links"][0]
        assert link["quantity"] == 5.5
        assert link["unit"] == "kg"
        assert link["process_type"] == "blend"
        assert link["confidence_score"] == 0.75

    def test_backward_link_defaults_when_fields_missing(
        self, principal: IngestionPrincipal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rows without optional fields get default ``confidence_score=1.0``
        and ``process_type=None`` (covers both ``.get(..., default)``
        fallbacks)."""
        raw_links = [
            {
                "input_tlc": "TLC-A", "output_tlc": "TLC-B",
                "transformation_event_id": "evt-1",
                "depth": 1,
                # No process_type, confidence_score, input_quantity, input_unit
            },
        ]
        stub = _TraceStoreStub(backward_result=(raw_links, False))
        _patch_trace_store(monkeypatch, stub)
        session = _FakeSession([_Result()])
        c = _client(principal, session)
        resp = c.get(
            self.ENDPOINT_TEMPLATE.format(tlc="TLC-B"),
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        link = resp.json()["links"][0]
        assert link["process_type"] is None
        assert link["confidence_score"] == 1.0
        assert link["quantity"] is None
        assert link["unit"] is None
