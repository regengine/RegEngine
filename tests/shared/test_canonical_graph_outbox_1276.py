"""
Regression tests for #1276 — ``publish_graph_sync`` used to run
synchronously inside ``persist_event`` BEFORE the outer transaction
committed, so a rollback after the call still left the
``canonical.created`` message on the Redis queue. The Neo4j sync
worker then applied it, producing a ghost graph node for a canonical
row that was never durable.

Fix: introduce ``shared.canonical_persistence.migration.stage_graph_sync``
which stages the event on ``session.info`` and installs SQLAlchemy
``after_commit`` / ``after_rollback`` listeners. Publish happens only
after the commit succeeds; rollback discards the staged events.

These tests exercise the transactional-outbox semantics without
hitting a real Redis or a real Postgres. We drive a real SQLAlchemy
Session bound to in-memory SQLite so the event-listener machinery
is exercised end-to-end, and inject a ``FakeRedis`` via ``sys.modules``
(the same pattern used by ``test_canonical_persistence_neo4j_sync.py``)
to observe publish calls.
"""
from __future__ import annotations

import sys
from typing import Any, List, Tuple
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def _begin_real_transaction(session: Session) -> None:
    """Force the session to have an in-flight SQL transaction.

    In production ``persist_event`` has already executed many SQL
    statements by the time it calls ``stage_graph_sync``, so the
    Session's ``after_rollback`` / ``after_commit`` events fire on
    the real transaction boundary. In these tests we don't touch
    schema, so we emit a trivial ``SELECT 1`` to start a transaction
    — otherwise ``session.rollback()`` is a no-op and the fix-under-
    test's rollback listener never fires, giving a false pass.
    """
    session.execute(text("SELECT 1"))


# ---------------------------------------------------------------------------
# Redis fake + event fixture — identical in shape to the existing #1378
# tests so the scaffolding is familiar.
# ---------------------------------------------------------------------------


class FakeRedis:
    """Counts rpush / ltrim calls; nothing else."""

    def __init__(self):
        self.rpush_calls: List[Tuple[str, str]] = []
        self.ltrim_calls: List[Tuple[str, int, int]] = []

    def rpush(self, key: str, payload: str) -> int:
        self.rpush_calls.append((key, payload))
        return len(self.rpush_calls)

    def ltrim(self, key: str, start: int, stop: int) -> bool:
        self.ltrim_calls.append((key, start, stop))
        return True


def _make_event(event_id: str = "evt-1", tenant_id: str = "tenant-1"):
    """TraceabilityEvent stand-in matching what publish_graph_sync reads."""
    event = MagicMock()
    event.event_id = event_id
    event.tenant_id = tenant_id

    event_type = MagicMock()
    event_type.value = "shipping"
    event.event_type = event_type

    event.traceability_lot_code = f"TLC-{event_id}"
    event.product_reference = "Lettuce"
    event.quantity = 10.0
    event.unit_of_measure = "kg"

    ts = MagicMock()
    ts.isoformat = MagicMock(return_value="2026-04-18T12:00:00+00:00")
    event.event_timestamp = ts

    event.from_facility_reference = "F1"
    event.to_facility_reference = "F2"
    event.from_entity_reference = None
    event.to_entity_reference = None

    ss = MagicMock()
    ss.value = "webhook"
    event.source_system = ss

    event.confidence_score = 1.0
    event.schema_version = "1.0"
    event.sha256_hash = f"hash-{event_id}"
    return event


@pytest.fixture
def fake_redis(monkeypatch):
    """Patch the ``redis`` module so ``redis.from_url`` returns our fake."""
    fake = FakeRedis()

    class _RedisModuleStub:
        @staticmethod
        def from_url(url):  # noqa: ARG004 - signature match
            return fake

    monkeypatch.setitem(sys.modules, "redis", _RedisModuleStub)
    return fake


@pytest.fixture
def sqlite_session():
    """A real SQLAlchemy Session on in-memory SQLite.

    We need a REAL session (not a MagicMock) because the #1276 fix
    relies on SQLAlchemy's ``after_commit`` / ``after_rollback`` event
    machinery firing on actual commit / rollback boundaries. SQLite is
    fine — we never touch schema; only the session lifecycle.
    """
    engine = create_engine("sqlite:///:memory:")
    session = Session(bind=engine)
    yield session
    session.close()


@pytest.fixture
def enable_sync(monkeypatch):
    """Turn the producer on for the duration of a test."""
    monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


# ---------------------------------------------------------------------------
# #1276 — ROLLBACK path: nothing reaches Redis
# ---------------------------------------------------------------------------


class TestRollbackDoesNotPublish_Issue1276:
    """The core invariant of #1276: a rolled-back transaction must not
    produce any graph-sync message. Before the fix a publish happened
    synchronously in ``persist_event``; now publishing is deferred to
    ``after_commit``, so rollback is silent."""

    def test_stage_then_rollback_publishes_nothing(
        self, fake_redis, sqlite_session, enable_sync,
    ):
        from shared.canonical_persistence.migration import stage_graph_sync

        _begin_real_transaction(sqlite_session)
        event = _make_event("evt-rollback")
        stage_graph_sync(sqlite_session, event)

        # Simulate the outer transaction rolling back (schema violation,
        # chain-hash conflict, caller-side error — whatever).
        sqlite_session.rollback()

        assert fake_redis.rpush_calls == [], (
            "rollback must NOT publish any graph-sync message (#1276); "
            "before the fix this was the exact bug — Redis received a "
            "'canonical.created' message whose DB row never existed."
        )
        assert fake_redis.ltrim_calls == []

    def test_many_staged_events_all_dropped_on_rollback(
        self, fake_redis, sqlite_session, enable_sync,
    ):
        """A batch of N events staged in one transaction, then rolled
        back, must produce zero publishes — not even one."""
        from shared.canonical_persistence.migration import stage_graph_sync

        _begin_real_transaction(sqlite_session)
        for i in range(20):
            stage_graph_sync(sqlite_session, _make_event(f"evt-{i}"))

        sqlite_session.rollback()
        assert fake_redis.rpush_calls == []

    def test_rollback_clears_pending_so_later_commit_is_noop(
        self, fake_redis, sqlite_session, enable_sync,
    ):
        """After rollback, pending events are gone. A subsequent commit
        on the same session must not republish the dropped events —
        otherwise a rollback-then-commit sequence would still leak
        ghost messages."""
        from shared.canonical_persistence.migration import stage_graph_sync

        _begin_real_transaction(sqlite_session)
        stage_graph_sync(sqlite_session, _make_event("evt-dropped"))
        sqlite_session.rollback()
        assert fake_redis.rpush_calls == []

        # A second transaction with no new stages commits cleanly.
        _begin_real_transaction(sqlite_session)
        sqlite_session.commit()
        assert fake_redis.rpush_calls == [], (
            "post-rollback commit must not leak previously-staged events"
        )


# ---------------------------------------------------------------------------
# #1276 — COMMIT path: publish fires exactly once per staged event
# ---------------------------------------------------------------------------


class TestCommitPublishes_Issue1276:
    def test_single_stage_then_commit_publishes_once(
        self, fake_redis, sqlite_session, enable_sync,
    ):
        from shared.canonical_persistence.migration import stage_graph_sync

        _begin_real_transaction(sqlite_session)
        event = _make_event("evt-committed")
        stage_graph_sync(sqlite_session, event)

        sqlite_session.commit()

        assert len(fake_redis.rpush_calls) == 1
        key, payload = fake_redis.rpush_calls[0]
        assert key == "neo4j-sync"
        assert "evt-committed" in payload

    def test_batch_of_stages_then_commit_publishes_each_once(
        self, fake_redis, sqlite_session, enable_sync,
    ):
        """N events staged → N publishes after commit. Not 0 (dropped),
        not N² (double-install of listeners), exactly N."""
        from shared.canonical_persistence.migration import stage_graph_sync

        _begin_real_transaction(sqlite_session)
        ids = [f"evt-batch-{i}" for i in range(10)]
        for eid in ids:
            stage_graph_sync(sqlite_session, _make_event(eid))

        sqlite_session.commit()

        assert len(fake_redis.rpush_calls) == 10
        # Each event appears exactly once, order preserved.
        published_ids = []
        for _key, payload in fake_redis.rpush_calls:
            for eid in ids:
                if eid in payload:
                    published_ids.append(eid)
                    break
        assert published_ids == ids, (
            "each staged event must be published exactly once, in "
            "staging order"
        )

    def test_second_commit_on_same_session_does_not_republish(
        self, fake_redis, sqlite_session, enable_sync,
    ):
        """Session listeners persist for the session's lifetime, so a
        committed pending list must be cleared (popped) to avoid
        republishing the same events on every subsequent commit —
        which would be catastrophic for long-lived sessions."""
        from shared.canonical_persistence.migration import stage_graph_sync

        _begin_real_transaction(sqlite_session)
        stage_graph_sync(sqlite_session, _make_event("evt-first"))
        sqlite_session.commit()
        assert len(fake_redis.rpush_calls) == 1

        # Second commit with no new stages must be a no-op.
        _begin_real_transaction(sqlite_session)
        sqlite_session.commit()
        assert len(fake_redis.rpush_calls) == 1, (
            "after_commit must drain, not replay — second commit "
            "must not republish previously-committed events"
        )

    def test_second_transaction_publishes_its_own_events(
        self, fake_redis, sqlite_session, enable_sync,
    ):
        """Commit T1 → stage in T2 → commit T2. Redis should see T1's
        events on commit T1 and T2's events on commit T2, never
        mixed or duplicated."""
        from shared.canonical_persistence.migration import stage_graph_sync

        _begin_real_transaction(sqlite_session)
        stage_graph_sync(sqlite_session, _make_event("evt-t1"))
        sqlite_session.commit()
        assert len(fake_redis.rpush_calls) == 1
        assert "evt-t1" in fake_redis.rpush_calls[0][1]

        _begin_real_transaction(sqlite_session)
        stage_graph_sync(sqlite_session, _make_event("evt-t2"))
        sqlite_session.commit()
        assert len(fake_redis.rpush_calls) == 2
        assert "evt-t2" in fake_redis.rpush_calls[1][1]


# ---------------------------------------------------------------------------
# #1276 — Gating: staging respects the ENABLE_NEO4J_SYNC env flag.
# ---------------------------------------------------------------------------


class TestStagingRespectsGating_Issue1276:
    def test_staging_is_noop_when_sync_disabled(
        self, fake_redis, sqlite_session, monkeypatch,
    ):
        """When the producer is off (the production default), staging
        must be a zero-cost no-op — not even the session.info dict
        should grow, so long-lived ingestion sessions cannot leak
        memory via a forgotten pending list."""
        monkeypatch.delenv("ENABLE_NEO4J_SYNC", raising=False)
        from shared.canonical_persistence.migration import (
            _SESSION_PENDING_KEY,
            stage_graph_sync,
        )

        _begin_real_transaction(sqlite_session)
        stage_graph_sync(sqlite_session, _make_event("evt-gated-off"))

        # No staging, no publish.
        assert _SESSION_PENDING_KEY not in sqlite_session.info
        sqlite_session.commit()
        assert fake_redis.rpush_calls == []

    def test_staging_honours_runtime_env_toggle(
        self, fake_redis, sqlite_session, monkeypatch,
    ):
        """If the operator flips ``ENABLE_NEO4J_SYNC`` true mid-process
        a subsequent stage call must start staging; the feature is
        evaluated at call time, not at import time."""
        monkeypatch.delenv("ENABLE_NEO4J_SYNC", raising=False)
        from shared.canonical_persistence.migration import stage_graph_sync

        _begin_real_transaction(sqlite_session)
        stage_graph_sync(sqlite_session, _make_event("evt-before"))
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        stage_graph_sync(sqlite_session, _make_event("evt-after"))

        sqlite_session.commit()

        # Only the post-toggle event should publish — the pre-toggle
        # call was a no-op and never made it into pending.
        assert len(fake_redis.rpush_calls) == 1
        assert "evt-after" in fake_redis.rpush_calls[0][1]


# ---------------------------------------------------------------------------
# #1276 — Listener installation is idempotent (defense against N²).
# ---------------------------------------------------------------------------


class TestListenerInstallation_Issue1276:
    def test_listeners_installed_at_most_once_per_session(
        self, fake_redis, sqlite_session, enable_sync,
    ):
        """A batch of 100 stage_graph_sync calls must not register 100
        after_commit listeners — that would fire the drain callback
        100 times per commit and produce 100× publishes. The flag
        guard in ``stage_graph_sync`` prevents the quadratic blowup."""
        from shared.canonical_persistence.migration import stage_graph_sync

        _begin_real_transaction(sqlite_session)
        for i in range(100):
            stage_graph_sync(sqlite_session, _make_event(f"evt-{i}"))

        sqlite_session.commit()

        # 100 events, 100 publishes, not 100 * 100.
        assert len(fake_redis.rpush_calls) == 100


# ---------------------------------------------------------------------------
# #1276 — Integration proxy: a persist_event-shaped caller pattern.
# ---------------------------------------------------------------------------


class TestPersistEventIntegrationShape_Issue1276:
    """Shallow integration test: exercise the exact call shape
    ``CanonicalEventStore.persist_event`` uses — stage right before
    returning, then the caller commits or rolls back."""

    def test_caller_rollback_does_not_publish(
        self, fake_redis, sqlite_session, enable_sync,
    ):
        from shared.canonical_persistence.migration import stage_graph_sync

        def persist_like(session, event):
            # Simulate the persist_event flow: do some DB work, stage
            # the publish, then let the caller commit.
            session.execute(text("SELECT 1"))
            stage_graph_sync(session, event)

        persist_like(sqlite_session, _make_event("evt-persist-rollback"))
        # Caller hit a downstream error and rolls back.
        sqlite_session.rollback()

        assert fake_redis.rpush_calls == [], (
            "caller rollback after persist-like call must not leak a "
            "graph-sync message (#1276)"
        )

    def test_caller_commit_does_publish(
        self, fake_redis, sqlite_session, enable_sync,
    ):
        from shared.canonical_persistence.migration import stage_graph_sync

        def persist_like(session, event):
            session.execute(text("SELECT 1"))
            stage_graph_sync(session, event)

        persist_like(sqlite_session, _make_event("evt-persist-commit"))
        sqlite_session.commit()

        assert len(fake_redis.rpush_calls) == 1
        assert "evt-persist-commit" in fake_redis.rpush_calls[0][1]
