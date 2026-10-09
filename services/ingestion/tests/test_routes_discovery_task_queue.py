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

import hashlib
import json
from unittest.mock import MagicMock

import app.routes_discovery as routes_discovery
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.auth import APIKey, require_api_key

router = routes_discovery.router


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

    monkeypatch.setattr(routes_discovery.redis, "from_url", lambda *a, **kw: fake_redis)
    monkeypatch.setattr(routes_discovery, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(routes_discovery, "enqueue_task", mock_enqueue)

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
        expected_hash = hashlib.sha256("CPPA Warninghttps://cppa.ca.gov/item/1".encode("utf-8")).hexdigest()
        assert kw["idempotency_key"] == f"discovery_scrape:tenant-disco:{expected_hash}"

    def test_item_removed_from_redis(self, monkeypatch):
        client, fake_redis, _, _ = _build_client(monkeypatch)
        raw = b"CPPA Warning:https://cppa.ca.gov/item/1"
        fake_redis.lindex.return_value = raw

        client.post(self.ENDPOINT, params={"index": 0})

        # #2921: approve must remove from the tenant-namespaced key the
        # scraper actually writes, not the bare one.
        fake_redis.lrem.assert_called_once_with("manual_upload_queue:tenant-disco", 1, raw)

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
        self._redis_with_items(
            fake_redis,
            [
                b"Reg A:https://example.com/a",
                b"Reg B:https://example.com/b",
            ],
        )

        resp = client.post(self.ENDPOINT, json={"indices": [0, 1]})

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert mock_enqueue.call_count == 2

        payloads = [c.kwargs["payload"] for c in mock_enqueue.call_args_list]
        assert {"body": "Reg A", "url": "https://example.com/a"} in payloads
        assert {"body": "Reg B", "url": "https://example.com/b"} in payloads
        keys = {c.kwargs["idempotency_key"] for c in mock_enqueue.call_args_list}
        expected_a = hashlib.sha256("Reg Ahttps://example.com/a".encode("utf-8")).hexdigest()
        expected_b = hashlib.sha256("Reg Bhttps://example.com/b".encode("utf-8")).hexdigest()
        assert keys == {
            f"discovery_scrape:tenant-disco:{expected_a}",
            f"discovery_scrape:tenant-disco:{expected_b}",
        }

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
        from app.task_handlers_discovery import register_discovery_handlers
        from shared.task_queue import TASK_HANDLERS

        TASK_HANDLERS.pop("discovery_scrape", None)
        register_discovery_handlers()
        assert "discovery_scrape" in TASK_HANDLERS


# ---------------------------------------------------------------------------
# Queue entry codec: JSON entries round-trip, legacy colon entries still read
# ---------------------------------------------------------------------------


def _json_entry(body: str, url: str) -> bytes:
    return json.dumps({"body": body, "url": url}).encode("utf-8")


class TestDecodeQueueEntry:
    decode = routes_discovery._decode_queue_entry

    def test_json_entry_decodes(self):
        assert self.decode(_json_entry("FDA Recall", "https://fda.gov/recall/1")) == (
            "FDA Recall",
            "https://fda.gov/recall/1",
        )

    def test_json_entry_with_colons_in_body_round_trips(self):
        """The old f"{body}:{url}" split mangled bodies containing colons."""
        body = "FDA Recall: June update: enforcement reports"
        assert self.decode(_json_entry(body, "https://fda.gov/recall/2")) == (
            body,
            "https://fda.gov/recall/2",
        )

    def test_legacy_colon_entry_still_decodes(self):
        assert self.decode(b"CPPA Warning:https://cppa.ca.gov/item/1") == (
            "CPPA Warning",
            "https://cppa.ca.gov/item/1",
        )

    def test_legacy_entry_without_colon_has_no_url(self):
        assert self.decode(b"just-a-body") == ("just-a-body", None)

    def test_undecodable_bytes_return_none(self):
        assert self.decode(b"\xff\xfe\x00bad") is None


class TestApproveWithNewCodec:
    ENDPOINT = "/v1/ingest/discovery/approve"

    def test_approve_json_entry_with_colon_body(self, monkeypatch):
        client, fake_redis, mock_enqueue, _ = _build_client(monkeypatch)
        body = "FDA Recall: June update"
        fake_redis.lindex.return_value = _json_entry(body, "https://fda.gov/recall/2")

        resp = client.post(self.ENDPOINT, params={"index": 0})

        assert resp.status_code == 200
        assert resp.json() == {"status": "approved", "body": body, "url": "https://fda.gov/recall/2"}
        kw = mock_enqueue.call_args.kwargs
        assert kw["payload"] == {"body": body, "url": "https://fda.gov/recall/2"}

    def test_approve_malformed_entry_returns_422_not_500(self, monkeypatch):
        client, fake_redis, mock_enqueue, _ = _build_client(monkeypatch)
        fake_redis.lindex.return_value = b"not-a-queue-entry"

        resp = client.post(self.ENDPOINT, params={"index": 0})

        assert resp.status_code == 422
        mock_enqueue.assert_not_called()

    def test_bulk_approve_skips_malformed_entry(self, monkeypatch):
        client, fake_redis, mock_enqueue, _ = _build_client(monkeypatch)
        fake_redis.lindex.side_effect = [
            _json_entry("Reg A", "https://example.com/a"),
            b"not-a-queue-entry",
        ]

        resp = client.post("/v1/ingest/discovery/bulk-approve", json={"indices": [0, 1]})

        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert mock_enqueue.call_count == 1
        payloads = [c.kwargs["payload"] for c in mock_enqueue.call_args_list]
        assert payloads == [{"body": "Reg A", "url": "https://example.com/a"}]
