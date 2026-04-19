"""Unit tests for PR-D: routes_discovery.py BackgroundTasks → task_queue.

Coverage:
- /approve: removes from Redis queue, enqueues discovery_scrape task
- /approve: 404 when item not found in Redis
- /bulk-approve: enqueues one task per approved item in a single transaction
- /bulk-approve: empty indices → 0 tasks enqueued
- reject/bulk-reject: unmodified (no BackgroundTasks), still return correct shape
- register_discovery_handlers wires discovery_scrape key
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.auth import APIKey, require_api_key
from app.routes_discovery import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_key() -> APIKey:
    key = MagicMock(spec=APIKey)
    key.tenant_id = "tenant-disco"
    key.allowed_jurisdictions = ["US"]
    return key


def _build_client(monkeypatch) -> tuple[TestClient, MagicMock, MagicMock, MagicMock]:
    """Return (client, mock_redis, mock_enqueue, fake_session)."""
    fake_redis = MagicMock()
    fake_session = MagicMock()
    mock_enqueue = MagicMock(return_value=1)

    monkeypatch.setattr("app.routes_discovery.redis.from_url", lambda *a, **kw: fake_redis)
    monkeypatch.setattr("app.routes_discovery.SessionLocal", lambda: fake_session)
    monkeypatch.setattr("app.routes_discovery.enqueue_task", mock_enqueue)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: _make_api_key()

    return TestClient(app, raise_server_exceptions=True), fake_redis, mock_enqueue, fake_session


# ---------------------------------------------------------------------------
# /v1/ingest/discovery/approve
# ---------------------------------------------------------------------------


class TestApproveDiscovery:
    ENDPOINT = "/v1/ingest/discovery/approve"

    def test_enqueues_discovery_scrape(self, monkeypatch):
        client, fake_redis, mock_enqueue, _ = _build_client(monkeypatch)
        fake_redis.lindex.return_value = b"CPPA Warning:https://cppa.ca.gov/item/1"

        resp = client.post(self.ENDPOINT, params={"index": 0})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["body"] == "CPPA Warning"
        assert body["url"] == "https://cppa.ca.gov/item/1"

        mock_enqueue.assert_called_once()
        kw = mock_enqueue.call_args.kwargs
        assert kw["task_type"] == "discovery_scrape"
        assert kw["payload"] == {"body": "CPPA Warning", "url": "https://cppa.ca.gov/item/1"}
        assert kw["tenant_id"] == "tenant-disco"

    def test_item_removed_from_redis(self, monkeypatch):
        client, fake_redis, _, _ = _build_client(monkeypatch)
        raw = b"CPPA Warning:https://cppa.ca.gov/item/1"
        fake_redis.lindex.return_value = raw

        client.post(self.ENDPOINT, params={"index": 0})

        fake_redis.lrem.assert_called_once_with("manual_upload_queue", 1, raw)

    def test_404_when_item_missing(self, monkeypatch):
        client, fake_redis, _, _ = _build_client(monkeypatch)
        fake_redis.lindex.return_value = None

        resp = client.post(self.ENDPOINT, params={"index": 99})
        assert resp.status_code == 404

    def test_db_commit_called(self, monkeypatch):
        client, fake_redis, _, fake_session = _build_client(monkeypatch)
        fake_redis.lindex.return_value = b"Body:https://example.com"

        client.post(self.ENDPOINT, params={"index": 0})
        fake_session.commit.assert_called_once()

    def test_db_closed(self, monkeypatch):
        client, fake_redis, _, fake_session = _build_client(monkeypatch)
        fake_redis.lindex.return_value = b"Body:https://example.com"

        client.post(self.ENDPOINT, params={"index": 0})
        fake_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# /v1/ingest/discovery/bulk-approve
# ---------------------------------------------------------------------------


class TestBulkApproveDiscovery:
    ENDPOINT = "/v1/ingest/discovery/bulk-approve"

    def _redis_with_items(self, fake_redis, items: list[bytes | None]) -> None:
        fake_redis.lindex.side_effect = items

    def test_enqueues_one_task_per_item(self, monkeypatch):
        client, fake_redis, mock_enqueue, _ = _build_client(monkeypatch)
        self._redis_with_items(fake_redis, [
            b"Reg A:https://example.com/a",
            b"Reg B:https://example.com/b",
        ])

        resp = client.post(self.ENDPOINT, json={"indices": [0, 1]})

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert mock_enqueue.call_count == 2

        payloads = [c.kwargs["payload"] for c in mock_enqueue.call_args_list]
        assert {"body": "Reg A", "url": "https://example.com/a"} in payloads
        assert {"body": "Reg B", "url": "https://example.com/b"} in payloads

    def test_single_commit_for_all_items(self, monkeypatch):
        client, fake_redis, _, fake_session = _build_client(monkeypatch)
        self._redis_with_items(fake_redis, [b"X:https://x.com", b"Y:https://y.com"])

        client.post(self.ENDPOINT, json={"indices": [0, 1]})
        fake_session.commit.assert_called_once()

    def test_db_closed_after_bulk(self, monkeypatch):
        client, fake_redis, _, fake_session = _build_client(monkeypatch)
        self._redis_with_items(fake_redis, [b"X:https://x.com"])

        client.post(self.ENDPOINT, json={"indices": [0]})
        fake_session.close.assert_called_once()

    def test_empty_indices_enqueues_nothing(self, monkeypatch):
        client, fake_redis, mock_enqueue, fake_session = _build_client(monkeypatch)

        resp = client.post(self.ENDPOINT, json={"indices": []})

        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        mock_enqueue.assert_not_called()
        fake_session.commit.assert_called_once()

    def test_missing_items_skipped(self, monkeypatch):
        client, fake_redis, mock_enqueue, _ = _build_client(monkeypatch)
        # index 0 exists, index 1 is missing
        self._redis_with_items(fake_redis, [b"Reg A:https://example.com/a", None])

        resp = client.post(self.ENDPOINT, json={"indices": [0, 1]})

        assert resp.json()["count"] == 1
        assert mock_enqueue.call_count == 1


# ---------------------------------------------------------------------------
# /reject and /bulk-reject — unchanged, just smoke-test shape
# ---------------------------------------------------------------------------


class TestRejectRoutes:
    def test_reject_returns_rejected_status(self, monkeypatch):
        client, fake_redis, _, _ = _build_client(monkeypatch)
        fake_redis.lindex.return_value = b"Body:https://example.com"

        resp = client.post("/v1/ingest/discovery/reject", params={"index": 0})
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_reject_404_when_missing(self, monkeypatch):
        client, fake_redis, _, _ = _build_client(monkeypatch)
        fake_redis.lindex.return_value = None

        resp = client.post("/v1/ingest/discovery/reject", params={"index": 5})
        assert resp.status_code == 404

    def test_bulk_reject_returns_count(self, monkeypatch):
        client, fake_redis, _, _ = _build_client(monkeypatch)
        fake_redis.lindex.side_effect = [b"A:https://a.com", b"B:https://b.com"]

        resp = client.post("/v1/ingest/discovery/bulk-reject", json={"indices": [0, 1]})
        assert resp.status_code == 200
        assert resp.json()["count"] == 2


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


class TestRegisterDiscoveryHandlers:
    def test_registers_discovery_scrape(self):
        from shared.task_queue import TASK_HANDLERS
        from app.task_handlers_discovery import register_discovery_handlers

        TASK_HANDLERS.pop("discovery_scrape", None)
        register_discovery_handlers()
        assert "discovery_scrape" in TASK_HANDLERS
