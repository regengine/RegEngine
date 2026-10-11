"""QA: tenant isolation and robustness for the discovery approve flow.

Covers two findings in ``app.routes_discovery`` / ``app.task_handlers_discovery``:

1. The ``discovery_scrape`` task payload carries no tenant, so the handler
   re-scrapes with the default ``tenant_id="system"``. A robots-denied
   re-scrape is then re-queued to ``manual_upload_queue:system`` instead of
   the owning tenant's queue (item lost to the tenant, queue polluted).
2. Queue entries that do not contain ``":"`` crash approve/bulk-approve
   with an unhandled ``ValueError`` (HTTP 500). The manual-queue reader
   explicitly allows such entries (``url=None``), so approve must handle
   them: single approve rejects with 400, bulk-approve counts them skipped.

Fast and deterministic: Redis, DB and enqueue are mocked, no network.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import app.routes_discovery as routes_discovery
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.auth import APIKey, require_api_key


def _make_api_key() -> APIKey:
    key = MagicMock(spec=APIKey)
    key.tenant_id = "tenant-qa"
    key.allowed_jurisdictions = ["US"]
    return key


def _build_client(monkeypatch) -> tuple[TestClient, MagicMock, MagicMock, MagicMock]:
    fake_redis = MagicMock()
    fake_session = MagicMock()
    mock_enqueue = MagicMock(return_value=1)

    monkeypatch.setattr(routes_discovery.redis, "from_url", lambda *a, **kw: fake_redis)
    monkeypatch.setattr(routes_discovery, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(routes_discovery, "enqueue_task", mock_enqueue)

    app = FastAPI()
    app.include_router(routes_discovery.router)
    app.dependency_overrides[require_api_key] = lambda: _make_api_key()

    return TestClient(app, raise_server_exceptions=True), fake_redis, mock_enqueue, fake_session


class TestApproveCarriesTenant:
    ENDPOINT = "/v1/ingest/discovery/approve"

    def test_payload_includes_tenant_id(self, monkeypatch):
        client, fake_redis, mock_enqueue, _ = _build_client(monkeypatch)
        fake_redis.lindex.return_value = b"FDA Warning:https://example.gov/w/1"

        resp = client.post(self.ENDPOINT, params={"index": 0})

        assert resp.status_code == 200
        payload = mock_enqueue.call_args.kwargs["payload"]
        assert payload == {
            "body": "FDA Warning",
            "url": "https://example.gov/w/1",
            "tenant_id": "tenant-qa",
        }

    def test_malformed_entry_without_colon_returns_400(self, monkeypatch):
        client, fake_redis, mock_enqueue, _ = _build_client(monkeypatch)
        fake_redis.lindex.return_value = b"no-separator-here"

        resp = client.post(self.ENDPOINT, params={"index": 0})

        assert resp.status_code == 400
        mock_enqueue.assert_not_called()

    def test_malformed_entry_is_not_removed(self, monkeypatch):
        # The operator can still reject it by index; approve must not drop it.
        client, fake_redis, _, _ = _build_client(monkeypatch)
        fake_redis.lindex.return_value = b"no-separator-here"

        client.post(self.ENDPOINT, params={"index": 0})

        fake_redis.lrem.assert_not_called()


class TestBulkApproveCarriesTenant:
    ENDPOINT = "/v1/ingest/discovery/bulk-approve"

    def _queue(self, fake_redis, *entries: bytes):
        fake_redis.lindex.side_effect = lambda _key, i: entries[i] if i < len(entries) else None

    def test_payloads_include_tenant_id(self, monkeypatch):
        client, fake_redis, mock_enqueue, _ = _build_client(monkeypatch)
        self._queue(fake_redis, b"Reg A:https://example.com/a", b"Reg B:https://example.com/b")

        resp = client.post(self.ENDPOINT, json={"indices": [0, 1]})

        assert resp.status_code == 200
        payloads = [c.kwargs["payload"] for c in mock_enqueue.call_args_list]
        assert {
            "body": "Reg A",
            "url": "https://example.com/a",
            "tenant_id": "tenant-qa",
        } in payloads
        assert {
            "body": "Reg B",
            "url": "https://example.com/b",
            "tenant_id": "tenant-qa",
        } in payloads

    def test_malformed_entry_counted_skipped_not_500(self, monkeypatch):
        client, fake_redis, mock_enqueue, _ = _build_client(monkeypatch)
        self._queue(fake_redis, b"Reg A:https://example.com/a", b"no-separator-here")

        resp = client.post(self.ENDPOINT, json={"indices": [0, 1]})

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["skipped"] == [1]
        assert mock_enqueue.call_count == 1


class TestHandlerForwardsTenant:
    def test_tenant_id_forwarded_to_scrape(self, monkeypatch):
        from app import task_handlers_discovery as thd

        calls: list[dict] = []

        class _FakeDiscovery:
            @staticmethod
            async def scrape(body, url, tenant_id="system"):
                calls.append({"body": body, "url": url, "tenant_id": tenant_id})

        monkeypatch.setattr(thd, "discovery", _FakeDiscovery)

        thd._handle_discovery_scrape(
            body="FDA Warning",
            url="https://example.gov/w/1",
            tenant_id="tenant-qa",
        )

        assert calls == [
            {"body": "FDA Warning", "url": "https://example.gov/w/1", "tenant_id": "tenant-qa"}
        ]

    def test_tenant_id_defaults_to_system(self, monkeypatch):
        from app import task_handlers_discovery as thd

        calls: list[dict] = []

        class _FakeDiscovery:
            @staticmethod
            async def scrape(body, url, tenant_id="system"):
                calls.append({"body": body, "url": url, "tenant_id": tenant_id})

        monkeypatch.setattr(thd, "discovery", _FakeDiscovery)

        thd._handle_discovery_scrape(body="x", url="https://example.com")

        assert calls == [{"body": "x", "url": "https://example.com", "tenant_id": "system"}]
