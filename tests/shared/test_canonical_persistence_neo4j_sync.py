"""
Regression tests for #1378 — Neo4j graph-sync Redis queue grows
unbounded in production.

``shared.canonical_persistence.migration.publish_graph_sync`` used
to unconditionally ``rpush`` one message per canonical event to the
``neo4j-sync`` Redis list, but the consumer
(``services/graph/scripts/fsma_sync_worker.py``) is not referenced
by any deployment manifest (railway.toml, docker-compose) — so the
queue was write-only in production and could only grow.

The fix gates the producer behind an explicit ``ENABLE_NEO4J_SYNC``
env flag (default OFF) and, when enabled, bounds the Redis list via
``LTRIM`` to ``NEO4J_SYNC_MAX_QUEUE`` entries so a briefly-stalled
consumer cannot exhaust memory.

These tests exercise the gate and the trim semantics without
touching a real Redis.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fakes — we inject ``redis.from_url`` to return a FakeRedis instance.
# ---------------------------------------------------------------------------


class FakeRedis:
    """Trivial Redis double: tracks rpush / ltrim calls."""

    def __init__(self):
        self.rpush_calls: List[tuple] = []
        self.ltrim_calls: List[tuple] = []

    def rpush(self, key: str, payload: str) -> int:
        self.rpush_calls.append((key, payload))
        return len(self.rpush_calls)

    def ltrim(self, key: str, start: int, stop: int) -> bool:
        self.ltrim_calls.append((key, start, stop))
        return True


def _make_event():
    """Minimal stand-in for a TraceabilityEvent."""
    event = MagicMock()
    event.event_id = "evt-1"
    event.tenant_id = "tenant-1"

    event_type = MagicMock(); event_type.value = "shipping"
    event.event_type = event_type

    event.traceability_lot_code = "TLC-1"
    event.product_reference = "Lettuce"
    event.quantity = 10.0
    event.unit_of_measure = "kg"

    ts = MagicMock(); ts.isoformat = MagicMock(return_value="2026-04-15T12:00:00+00:00")
    event.event_timestamp = ts

    event.from_facility_reference = "F1"
    event.to_facility_reference = "F2"
    event.from_entity_reference = None
    event.to_entity_reference = None

    ss = MagicMock(); ss.value = "webhook"
    event.source_system = ss

    event.confidence_score = 1.0
    event.schema_version = "1.0"
    event.sha256_hash = "abc"
    return event


@pytest.fixture
def fake_redis(monkeypatch):
    """Patch ``redis.from_url`` to return our FakeRedis.

    The module imports ``redis as redis_lib`` inside the function,
    so we patch the ``redis`` module's ``from_url`` rather than a
    module-level symbol in ``migration``.
    """
    fake = FakeRedis()

    class _RedisModuleStub:
        @staticmethod
        def from_url(url):  # noqa: ARG004 - matches signature
            return fake

    # Replace the ``redis`` module in sys.modules so the local
    # import inside publish_graph_sync picks up our stub.
    import sys
    monkeypatch.setitem(sys.modules, "redis", _RedisModuleStub)
    return fake


# ---------------------------------------------------------------------------
# #1378 — Gating
# ---------------------------------------------------------------------------


class TestGating_Issue1378:
    def test_producer_is_noop_by_default(self, fake_redis, monkeypatch):
        """The most important invariant: with ``ENABLE_NEO4J_SYNC``
        unset, the producer must NOT publish — no consumer is
        deployed, so any publish grows Redis unbounded."""
        monkeypatch.delenv("ENABLE_NEO4J_SYNC", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

        from shared.canonical_persistence.legacy_dual_write import publish_graph_sync

        publish_graph_sync(_make_event())
        assert fake_redis.rpush_calls == []
        assert fake_redis.ltrim_calls == []

    def test_producer_is_noop_with_false_flag(self, fake_redis, monkeypatch):
        """ENABLE_NEO4J_SYNC=false must disable the producer."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "false")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

        from shared.canonical_persistence.legacy_dual_write import publish_graph_sync

        publish_graph_sync(_make_event())
        assert fake_redis.rpush_calls == []

    def test_producer_is_noop_without_redis_url(self, fake_redis, monkeypatch):
        """Even with the flag set, no REDIS_URL means we cannot
        publish — emit a warning and return."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.delenv("REDIS_URL", raising=False)

        from shared.canonical_persistence.legacy_dual_write import publish_graph_sync

        publish_graph_sync(_make_event())
        assert fake_redis.rpush_calls == []

    def test_producer_publishes_when_explicitly_enabled(
        self, fake_redis, monkeypatch,
    ):
        """With both the flag and REDIS_URL, the producer publishes
        one rpush per canonical event."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

        from shared.canonical_persistence.legacy_dual_write import publish_graph_sync

        publish_graph_sync(_make_event())
        assert len(fake_redis.rpush_calls) == 1
        key, payload = fake_redis.rpush_calls[0]
        assert key == "neo4j-sync"
        assert "evt-1" in payload

    @pytest.mark.parametrize("truthy", ["1", "true", "True", "YES", "on"])
    def test_truthy_values_enable_producer(
        self, fake_redis, monkeypatch, truthy,
    ):
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", truthy)
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        from shared.canonical_persistence.legacy_dual_write import publish_graph_sync

        publish_graph_sync(_make_event())
        assert len(fake_redis.rpush_calls) == 1


# ---------------------------------------------------------------------------
# #1378 — LTRIM bounds the queue
# ---------------------------------------------------------------------------


class TestQueueBounding_Issue1378:
    def test_producer_trims_queue_to_default_max(
        self, fake_redis, monkeypatch,
    ):
        """When publish succeeds the producer must LTRIM the list
        so that a stalled consumer cannot grow it without bound."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.delenv("NEO4J_SYNC_MAX_QUEUE", raising=False)

        from shared.canonical_persistence.legacy_dual_write import publish_graph_sync

        publish_graph_sync(_make_event())
        assert len(fake_redis.ltrim_calls) == 1
        key, start, stop = fake_redis.ltrim_calls[0]
        assert key == "neo4j-sync"
        # Keep the newest 100k entries (default).  LTRIM semantics:
        # start=-100000, stop=-1 keeps the last 100k elements.
        assert start == -100_000
        assert stop == -1

    def test_producer_honors_max_queue_override(
        self, fake_redis, monkeypatch,
    ):
        """Operators can tune NEO4J_SYNC_MAX_QUEUE down (e.g. for a
        small Redis instance) without touching code."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("NEO4J_SYNC_MAX_QUEUE", "500")

        from shared.canonical_persistence.legacy_dual_write import publish_graph_sync

        publish_graph_sync(_make_event())
        assert fake_redis.ltrim_calls
        _, start, stop = fake_redis.ltrim_calls[0]
        assert start == -500
        assert stop == -1

    def test_invalid_max_queue_env_falls_back_to_default(
        self, fake_redis, monkeypatch,
    ):
        """Garbage in NEO4J_SYNC_MAX_QUEUE must not crash the
        producer — fall back to the 100k default."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("NEO4J_SYNC_MAX_QUEUE", "not-a-number")

        from shared.canonical_persistence.legacy_dual_write import publish_graph_sync

        publish_graph_sync(_make_event())
        assert fake_redis.ltrim_calls
        _, start, _ = fake_redis.ltrim_calls[0]
        assert start == -100_000
