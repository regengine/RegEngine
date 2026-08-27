"""Regression tests for #2921 — manual-discovery queue key namespacing.

``EthicalScraper.scrape`` queues robots-denied sources under
``manual_upload_queue:{tenant_id}`` (``app/discovery.py``), but the
approve/reject handlers in ``app/routes_discovery.py`` read the bare
``manual_upload_queue`` key that nothing writes. The result: an operator
can *see* a queued item via ``GET /v1/ingest/manual-queue`` but every
approve/reject 404s, and the bulk variants report ``count: 0`` with a 200.

These tests drive the producer and the consumers against a shared
in-memory Redis fake with real per-key list semantics (fakeredis is not
installed in this environment), so a handler that reads the wrong key
cannot pass by accident.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from unittest.mock import MagicMock

import app.routes_discovery as routes_discovery
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.ingestion.app import discovery as discovery_mod
from shared.auth import APIKey, require_api_key

_APP_DIR = Path(routes_discovery.__file__).resolve().parent


# ---------------------------------------------------------------------------
# Minimal in-memory Redis list fake (real per-key semantics)
# ---------------------------------------------------------------------------


class FakeRedisLists:
    """Implements just the list ops the discovery queue uses, keyed properly."""

    def __init__(self) -> None:
        self.lists: dict[str, list[bytes]] = {}

    @staticmethod
    def _val(value) -> bytes:
        return value.encode("utf-8") if isinstance(value, str) else value

    @staticmethod
    def _key(key) -> str:
        return key.decode("utf-8") if isinstance(key, bytes) else key

    def rpush(self, key, *values) -> int:
        bucket = self.lists.setdefault(self._key(key), [])
        bucket.extend(self._val(v) for v in values)
        return len(bucket)

    def llen(self, key) -> int:
        return len(self.lists.get(self._key(key), []))

    def lrange(self, key, start, end) -> list[bytes]:
        bucket = self.lists.get(self._key(key), [])
        if end == -1:
            return bucket[start:]
        return bucket[start : end + 1]

    def lindex(self, key, index):
        bucket = self.lists.get(self._key(key), [])
        try:
            return bucket[index]
        except IndexError:
            return None

    def lrem(self, key, count, value) -> int:
        name = self._key(key)
        bucket = self.lists.get(name, [])
        target = self._val(value)
        limit = count if count > 0 else len(bucket)
        removed = 0
        kept: list[bytes] = []
        for item in bucket:
            if item == target and removed < limit:
                removed += 1
                continue
            kept.append(item)
        self.lists[name] = kept
        return removed


def _api_key(tenant_id: str) -> APIKey:
    key = MagicMock(spec=APIKey)
    key.tenant_id = tenant_id
    key.allowed_jurisdictions = ["US"]
    return key


def _client(monkeypatch, fake_redis: FakeRedisLists, tenant_id: str) -> tuple[TestClient, MagicMock]:
    mock_enqueue = MagicMock(return_value=1)
    monkeypatch.setattr(routes_discovery.redis, "from_url", lambda *a, **kw: fake_redis)
    monkeypatch.setattr(routes_discovery, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr(routes_discovery, "enqueue_task", mock_enqueue)

    app = FastAPI()
    app.include_router(routes_discovery.router)
    app.dependency_overrides[require_api_key] = lambda: _api_key(tenant_id)
    return TestClient(app, raise_server_exceptions=True), mock_enqueue


def _queue_via_robots_denial(fake_redis: FakeRedisLists, tenant_id: str, body: str, url: str) -> dict:
    """Drive the ONLY producer of the manual queue: the robots-denied path."""
    scraper = discovery_mod.EthicalScraper(redis_url="redis://localhost:6379/0")
    scraper.redis = fake_redis
    scraper.can_fetch = lambda _url: False  # type: ignore[method-assign]
    return asyncio.run(scraper.scrape(body=body, source_url=url, tenant_id=tenant_id))


@pytest.fixture()
def seeded() -> FakeRedisLists:
    """Tenant A has one robots-denied item queued by the real producer."""
    fake = FakeRedisLists()
    result = _queue_via_robots_denial(fake, "tenant-a", "FDA Recall", "https://fda.gov/recall/1")
    assert result["status"] == "queued_manual"
    assert fake.lists == {"manual_upload_queue:tenant-a": [b"FDA Recall:https://fda.gov/recall/1"]}
    return fake


# ---------------------------------------------------------------------------
# Round trip: producer -> consumer for the SAME tenant
# ---------------------------------------------------------------------------


class TestProducerConsumerRoundTrip:
    def test_approve_drains_the_item_the_scraper_queued(self, monkeypatch, seeded):
        client, mock_enqueue = _client(monkeypatch, seeded, "tenant-a")

        resp = client.post("/v1/ingest/discovery/approve", params={"index": 0})

        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "status": "approved",
            "body": "FDA Recall",
            "url": "https://fda.gov/recall/1",
        }
        mock_enqueue.assert_called_once()
        assert mock_enqueue.call_args.kwargs["task_type"] == "discovery_scrape"
        assert mock_enqueue.call_args.kwargs["tenant_id"] == "tenant-a"
        # The item is gone from the tenant's own list, not some other key.
        assert seeded.lists["manual_upload_queue:tenant-a"] == []

    def test_reject_drains_the_item_the_scraper_queued(self, monkeypatch, seeded):
        client, _ = _client(monkeypatch, seeded, "tenant-a")

        resp = client.post("/v1/ingest/discovery/reject", params={"index": 0})

        assert resp.status_code == 200, resp.text
        assert seeded.lists["manual_upload_queue:tenant-a"] == []

    def test_bulk_approve_drains_the_item_the_scraper_queued(self, monkeypatch, seeded):
        client, mock_enqueue = _client(monkeypatch, seeded, "tenant-a")

        resp = client.post("/v1/ingest/discovery/bulk-approve", json={"indices": [0]})

        assert resp.status_code == 200, resp.text
        assert resp.json()["count"] == 1
        assert mock_enqueue.call_count == 1
        assert seeded.lists["manual_upload_queue:tenant-a"] == []

    def test_bulk_reject_drains_the_item_the_scraper_queued(self, monkeypatch, seeded):
        client, _ = _client(monkeypatch, seeded, "tenant-a")

        resp = client.post("/v1/ingest/discovery/bulk-reject", json={"indices": [0]})

        assert resp.status_code == 200, resp.text
        assert resp.json()["count"] == 1
        assert seeded.lists["manual_upload_queue:tenant-a"] == []

    def test_discovery_queue_lists_the_item_the_scraper_queued(self, monkeypatch, seeded):
        client, _ = _client(monkeypatch, seeded, "tenant-a")

        resp = client.get("/v1/ingest/discovery/queue")

        assert resp.status_code == 200, resp.text
        assert resp.json() == [{"body": "FDA Recall", "url": "https://fda.gov/recall/1", "index": 0}]


# ---------------------------------------------------------------------------
# Tenant isolation: tenant B must not see or drain tenant A's queue
# ---------------------------------------------------------------------------


class TestCrossTenantIsolation:
    def test_tenant_b_sees_empty_discovery_queue(self, monkeypatch, seeded):
        client, _ = _client(monkeypatch, seeded, "tenant-b")

        resp = client.get("/v1/ingest/discovery/queue")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_tenant_b_sees_empty_manual_queue(self, monkeypatch, seeded):
        client, _ = _client(monkeypatch, seeded, "tenant-b")

        resp = client.get("/v1/ingest/manual-queue")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    def test_tenant_b_cannot_approve_tenant_a_item(self, monkeypatch, seeded):
        client, mock_enqueue = _client(monkeypatch, seeded, "tenant-b")

        resp = client.post("/v1/ingest/discovery/approve", params={"index": 0})

        assert resp.status_code == 404
        mock_enqueue.assert_not_called()
        assert seeded.lists["manual_upload_queue:tenant-a"] == [b"FDA Recall:https://fda.gov/recall/1"]

    def test_tenant_b_cannot_reject_tenant_a_item(self, monkeypatch, seeded):
        client, _ = _client(monkeypatch, seeded, "tenant-b")

        resp = client.post("/v1/ingest/discovery/reject", params={"index": 0})

        assert resp.status_code == 404
        assert seeded.lists["manual_upload_queue:tenant-a"] == [b"FDA Recall:https://fda.gov/recall/1"]

    def test_tenant_b_bulk_approve_cannot_drain_tenant_a(self, monkeypatch, seeded):
        client, mock_enqueue = _client(monkeypatch, seeded, "tenant-b")

        resp = client.post("/v1/ingest/discovery/bulk-approve", json={"indices": [0, 1]})

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        mock_enqueue.assert_not_called()
        assert seeded.lists["manual_upload_queue:tenant-a"] == [b"FDA Recall:https://fda.gov/recall/1"]

    def test_tenant_b_bulk_reject_cannot_drain_tenant_a(self, monkeypatch, seeded):
        client, _ = _client(monkeypatch, seeded, "tenant-b")

        resp = client.post("/v1/ingest/discovery/bulk-reject", json={"indices": [0, 1]})

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert seeded.lists["manual_upload_queue:tenant-a"] == [b"FDA Recall:https://fda.gov/recall/1"]


# ---------------------------------------------------------------------------
# Bulk endpoints must not silently swallow unresolvable indices (AC #4)
# ---------------------------------------------------------------------------


class TestBulkSkippedIndices:
    def test_bulk_approve_reports_skipped_indices(self, monkeypatch, seeded):
        client, _ = _client(monkeypatch, seeded, "tenant-a")

        resp = client.post("/v1/ingest/discovery/bulk-approve", json={"indices": [0, 7]})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["count"] == 1
        assert body["skipped"] == [7]

    def test_bulk_reject_reports_skipped_indices(self, monkeypatch, seeded):
        client, _ = _client(monkeypatch, seeded, "tenant-a")

        resp = client.post("/v1/ingest/discovery/bulk-reject", json={"indices": [0, 7]})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["count"] == 1
        assert body["skipped"] == [7]


# ---------------------------------------------------------------------------
# Source guard (AC #3): no bare literal outside the single helper
# ---------------------------------------------------------------------------


def test_no_unnamespaced_manual_upload_queue_literal_in_ingestion_sources():
    """``grep -rn '"manual_upload_queue"' services/`` must find nothing.

    Every reference has to go through a helper that appends the tenant id;
    a bare literal is by definition a cross-tenant key.
    """
    offenders: list[str] = []
    bare = re.compile(r"""["']manual_upload_queue["']""")
    for path in _APP_DIR.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if bare.search(line):
                offenders.append(f"{path}:{lineno}: {line.strip()}")
    assert offenders == [], "un-namespaced manual_upload_queue key(s):\n" + "\n".join(offenders)


def test_producer_and_consumer_build_the_same_key():
    """The helper is only correct if it matches the producer byte for byte.

    ``discovery.py`` builds the key inline (importing the routes module there
    would drag httpx and the regulation loader into the producer's import
    graph), so this test — not an import — is what pins the two together.
    """
    fake = FakeRedisLists()
    _queue_via_robots_denial(fake, "tenant-xyz", "Body", "https://example.test/a")

    produced_key = next(iter(fake.lists))
    assert produced_key == routes_discovery._manual_queue_key("tenant-xyz")
