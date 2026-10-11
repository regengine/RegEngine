"""Adversarial checks for disaster recovery and the chain verification job.

Corrupt chain rows, a missing hash or KDE blob, and a chain that was
truncated while events remain. These tests use scripted sessions only.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app import chain_verification_job as cvj, disaster_recovery as dr
from app.chain_verification_job import _run_verification, _verification_jobs
from app.disaster_recovery import router
from app.webhook_compat import _verify_api_key
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.canonical_persistence.verification import CanonicalChainVerificationMixin
from shared.cte_persistence import CTEPersistence, compute_chain_hash
from sqlalchemy.exc import SQLAlchemyError

from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []
        self.closed = False

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), dict(params or {})))
        rows = self.steps.pop(0) if self.steps else []
        return _Result(rows)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        self.closed = True


def _linked(length, *, break_seq=None, sequences=None):
    """Chain rows (seq, event_hash, previous, chain_hash) with real link hashes."""
    rows = []
    previous = None
    seqs = list(sequences or range(1, length + 1))
    for seq in seqs:
        event_hash = f"event-{seq}"
        chain_hash = compute_chain_hash(event_hash, previous)
        stored_prev = None if break_seq == seq else previous
        rows.append((seq, event_hash, stored_prev, chain_hash))
        previous = chain_hash
    return rows


def _legacy_row(seq, event_hash, previous, chain_hash, event_id="evt-1"):
    return (seq, event_hash, previous, chain_hash, event_id, event_id)


def _canonical_row(seq, event_hash, previous, chain_hash, kdes, event_id="evt-1"):
    return (
        seq,
        event_hash,
        previous,
        chain_hash,
        event_id,
        event_id,
        "receiving",
        "TLC-1",
        None,
        1,
        "kg",
        None,
        None,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        kdes,
        event_id,
        None,
        "ab" * 32,
    )


class _Store(CanonicalChainVerificationMixin):
    def __init__(self, session):
        self.session = session


@pytest.fixture(autouse=True)
def _clear_jobs():
    with cvj._verification_lock:
        _verification_jobs.clear()
    yield
    with cvj._verification_lock:
        _verification_jobs.clear()


def test_null_previous_hash_is_reported_invalid_not_raised():
    """A later row with a missing previous hash is a chain break.

    The error text used to slice that missing value and raise TypeError,
    so the verification job recorded a crash instead of an invalid chain.
    """
    first = compute_chain_hash("event-1", None)
    rows = [
        _legacy_row(1, "event-1", None, first, "evt-1"),
        _legacy_row(2, "event-2", None, compute_chain_hash("event-2", first), "evt-2"),
    ]
    session = _Session([rows, [(2,)]])

    result = CTEPersistence(session).verify_chain("tenant-1")

    assert result.valid is False
    assert any("Chain break at seq=2" in error for error in result.errors)
    assert all("missing" in error or "Chain break" in error or "Tamper" in error for error in result.errors)


def test_null_chain_hash_blob_is_reported_invalid_not_raised():
    """A missing chain hash is tamper evidence, not a formatting crash."""
    session = _Session(
        [
            [_legacy_row(1, "event-1", None, None)],
            [(1,)],
        ]
    )

    result = CTEPersistence(session).verify_chain("tenant-1")

    assert result.valid is False
    assert any("Tamper detected at seq=1" in error for error in result.errors)


@pytest.mark.parametrize("kdes", ["{", [1, 2], 5])
def test_unreadable_kde_blob_is_invalid_not_raised(kdes):
    """A truncated or non-object KDE blob must not abort verification."""
    chain = compute_chain_hash("event-1", None)
    session = _Session(
        [
            [_canonical_row(1, "event-1", None, chain, kdes)],
            [(1,)],
        ]
    )

    result = _Store(session).verify_chain_canonical("tenant-1")

    assert result.valid is False
    assert any("Unreadable KDE blob at seq=1" in error for error in result.errors)


def test_verification_job_completes_invalid_when_previous_hash_is_missing(monkeypatch):
    """The job must finish with chain_valid false, not status failed."""
    first = compute_chain_hash("event-1", None)
    second = compute_chain_hash("event-2", first)
    legacy_rows = [
        _legacy_row(1, "event-1", None, first, "evt-1"),
        _legacy_row(2, "event-2", None, second, "evt-2"),
    ]
    canonical_rows = [
        _canonical_row(1, "event-1", None, first, {}, "evt-1"),
        _canonical_row(2, "event-2", None, second, {}, "evt-2"),
    ]

    class _JobSession:
        def __init__(self):
            self.closed = False

        def execute(self, stmt, params=None):
            sql = str(stmt)
            if "chain_verification_log" in sql:
                return _Result([])
            if "traceability_events" in sql and "COUNT(*)" in sql:
                return _Result([(2,)])
            if "traceability_events" in sql:
                return _Result(canonical_rows)
            if "validation_status" in sql:
                return _Result([(2,)])
            if "hc.id IS NULL" in sql:
                return _Result([])
            return _Result(legacy_rows)

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            self.closed = True

    import shared.database as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", _JobSession)
    monkeypatch.setattr(cvj, "_log_verification_audit", lambda *args, **kwargs: None)
    _verification_jobs["job-1"] = {
        "job_id": "job-1",
        "tenant_id": "tenant-1",
        "status": "running",
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": None,
        "chain_valid": None,
        "chain_length": None,
        "errors": [],
        "message": None,
    }

    _run_verification("job-1", "tenant-1")

    entry = _verification_jobs["job-1"]
    assert entry["status"] == "completed"
    assert entry["chain_valid"] is False
    assert any("Chain break" in error for error in entry["errors"])


def test_sequence_hole_after_truncate_fails_the_dr_check(monkeypatch):
    """Deleting a middle row leaves later hashes filled in. That is still a gap."""
    first = compute_chain_hash("event-1", None)
    third = compute_chain_hash("event-3", first)
    rows = [
        (1, "event-1", None, first),
        (3, "event-3", first, third),
    ]
    session = _Session([rows])
    monkeypatch.setattr(dr, "get_db_safe", lambda: session)

    check = dr._check_hash_chain_integrity("tenant-1")

    assert check.status == "fail", check.details
    assert "1 gap" in check.details
    assert session.closed is True


def test_corrupt_chain_hash_fails_the_dr_check(monkeypatch):
    session = _Session([[(1, "event-1", None, "f" * 64)]])
    monkeypatch.setattr(dr, "get_db_safe", lambda: session)

    check = dr._check_hash_chain_integrity("tenant-1")

    assert check.status == "fail", check.details


def test_chain_statement_walks_row_hashes(monkeypatch):
    """The check used to count only null previous hashes past sequence 1."""
    session = _Session([[]])
    monkeypatch.setattr(dr, "get_db_safe", lambda: session)

    dr._check_hash_chain_integrity("tenant-1")

    sql = session.calls[0][0]
    assert "chain_hash" in sql
    assert "ORDER BY sequence_num" in sql
    assert "previous_chain_hash IS NULL AND sequence_num > 1" not in sql


def test_truncated_chain_with_events_fails(monkeypatch):
    """Zero chain rows while events remain is a failed check, not a warning."""
    session = _Session([[], [(3,)]])
    monkeypatch.setattr(dr, "get_db_safe", lambda: session)

    check = dr._check_hash_chain_integrity("tenant-1")

    assert check.status == "fail", check.details
    assert "3 event" in check.details
    assert "traceability_events" in session.calls[1][0]
    assert "status != 'rejected'" in session.calls[1][0]
    assert session.calls[1][1] == {"tid": "tenant-1"}
    assert session.closed is True


def test_empty_chain_without_events_stays_a_warning(monkeypatch):
    session = _Session([[], [(0,)]])
    monkeypatch.setattr(dr, "get_db_safe", lambda: session)

    check = dr._check_hash_chain_integrity("tenant-1")

    assert check.status == "warn"
    assert check.details == "No hash chain records found for tenant"


def test_unreadable_chain_does_not_claim_rebuild_is_possible(monkeypatch):
    """A database error while reading the chain must not say rebuild will work."""
    steps = {"n": 0}

    def _db():
        steps["n"] += 1
        if steps["n"] == 1:
            return _Session([[(4, 1, 1.0)]])
        if steps["n"] == 2:
            session = _Session([])
            session.execute = lambda *args, **kwargs: (_ for _ in ()).throw(SQLAlchemyError("chain boom"))
            return session
        return _Session([[], []])

    monkeypatch.setattr(dr, "get_db_safe", _db)
    monkeypatch.setattr(
        dr,
        "_query_required_kde_coverage",
        lambda db, tenant_id: {
            "required_kde_checks_total": 4,
            "required_kde_checks_passed": 4,
            "events_unchecked_type": 0,
        },
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app)

    response = TestClient(app).post("/api/v1/dr/tenant-1/test-recovery")

    assert response.status_code == 200
    checks = {item["name"]: item for item in response.json()["checks"]}
    assert checks["hash_chain_integrity"]["status"] == "warn"
    assert checks["chain_rebuild_feasibility"]["status"] == "warn"
    assert "could not be read" in checks["chain_rebuild_feasibility"]["details"]


def test_truncated_chain_recovery_is_not_ready(monkeypatch):
    """Events with no chain fail readiness, and the report still says a rebuild can use those events."""
    steps = {"n": 0}

    def _db():
        steps["n"] += 1
        if steps["n"] == 1:
            return _Session([[(4, 1, 1.0)]])
        if steps["n"] == 2:
            return _Session([[], [(4,)]])
        return _Session([[], []])

    monkeypatch.setattr(dr, "get_db_safe", _db)
    monkeypatch.setattr(
        dr,
        "_query_required_kde_coverage",
        lambda db, tenant_id: {
            "required_kde_checks_total": 4,
            "required_kde_checks_passed": 4,
            "events_unchecked_type": 0,
        },
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app)

    response = TestClient(app).post("/api/v1/dr/tenant-1/test-recovery")

    assert response.status_code == 200
    body = response.json()
    checks = {item["name"]: item for item in body["checks"]}
    assert checks["hash_chain_integrity"]["status"] == "fail"
    assert "missing while" in checks["hash_chain_integrity"]["details"]
    assert checks["chain_rebuild_feasibility"]["status"] == "pass"
    assert body["overall_status"] != "ready"
