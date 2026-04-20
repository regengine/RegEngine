"""Full-coverage tests for ``app.routes_discovery`` (#1342).

Complements ``tests/test_routes_discovery_task_queue.py`` by driving
the two read-only endpoints that helper file skips:

- ``GET /v1/ingest/discovery/queue``
- ``GET /v1/ingest/manual-queue``

Together they cover the previously-missing lines 29-43 and 53-80.
"""

from __future__ import annotations

import sys
from pathlib import Path
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

from shared.auth import APIKey, require_api_key
from app.routes_discovery import router as discovery_router


def _api_key(tenant_id: str = "tenant-disco") -> APIKey:
    key = MagicMock(spec=APIKey)
    key.tenant_id = tenant_id
    key.allowed_jurisdictions = ["US"]
    return key


def _build(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, MagicMock]:
    fake_redis = MagicMock()
    monkeypatch.setattr(
        "app.routes_discovery.redis.from_url", lambda *a, **kw: fake_redis
    )
    app = FastAPI()
    app.include_router(discovery_router)
    app.dependency_overrides[require_api_key] = lambda: _api_key()
    return TestClient(app, raise_server_exceptions=True), fake_redis


# ---------------------------------------------------------------------------
# GET /v1/ingest/discovery/queue
# ---------------------------------------------------------------------------


class TestGetDiscoveryQueue:
    ENDPOINT = "/v1/ingest/discovery/queue"

    def test_returns_parsed_items(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, fake_redis = _build(monkeypatch)
        fake_redis.lrange.return_value = [
            b"CPPA Warning:https://cppa.ca.gov/item/1",
            b"FDA Rec:https://fda.gov/rec/2",
        ]
        response = client.get(self.ENDPOINT)
        assert response.status_code == 200
        items = response.json()
        assert len(items) == 2
        assert items[0] == {
            "body": "CPPA Warning",
            "url": "https://cppa.ca.gov/item/1",
            "index": 0,
        }
        assert items[1]["url"] == "https://fda.gov/rec/2"
        fake_redis.lrange.assert_called_once_with("manual_upload_queue", 0, -1)

    def test_skips_items_without_colon_separator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, fake_redis = _build(monkeypatch)
        fake_redis.lrange.return_value = [
            b"no-colon-item",
            b"good:https://ok.test",
        ]
        response = client.get(self.ENDPOINT)
        assert response.status_code == 200
        items = response.json()
        # Only the well-formed item survives; its index reflects original
        # position (1), not post-filter position (0).
        assert len(items) == 1
        assert items[0]["index"] == 1
        assert items[0]["body"] == "good"

    def test_catches_decode_errors_and_continues(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, fake_redis = _build(monkeypatch)

        bad = MagicMock()
        bad.decode.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "bad")
        good = b"ok:https://ok.test"
        fake_redis.lrange.return_value = [bad, good]

        response = client.get(self.ENDPOINT)
        assert response.status_code == 200
        items = response.json()
        # Bad entry swallowed, good entry returned with its ORIGINAL index.
        assert len(items) == 1
        assert items[0]["index"] == 1
        assert items[0]["url"] == "https://ok.test"

    def test_empty_queue_returns_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, fake_redis = _build(monkeypatch)
        fake_redis.lrange.return_value = []
        response = client.get(self.ENDPOINT)
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# GET /v1/ingest/manual-queue
# ---------------------------------------------------------------------------


class TestGetManualQueue:
    ENDPOINT = "/v1/ingest/manual-queue"

    def test_returns_scoped_queue_with_default_pagination(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, fake_redis = _build(monkeypatch)
        fake_redis.llen.return_value = 2
        fake_redis.lrange.return_value = [
            b"Body A:https://a.test",
            b"Body B:https://b.test",
        ]
        response = client.get(self.ENDPOINT)
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == "tenant-disco"
        assert body["total"] == 2
        assert body["skip"] == 0
        assert body["limit"] == 100
        assert [it["body"] for it in body["items"]] == ["Body A", "Body B"]
        # Queue key is tenant-scoped.
        fake_redis.llen.assert_called_once_with("manual_upload_queue:tenant-disco")
        fake_redis.lrange.assert_called_once_with(
            "manual_upload_queue:tenant-disco", 0, 99
        )

    def test_url_is_none_when_no_colon(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, fake_redis = _build(monkeypatch)
        fake_redis.llen.return_value = 1
        fake_redis.lrange.return_value = [b"body-only-no-colon"]
        response = client.get(self.ENDPOINT)
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item == {"index": 0, "body": "body-only-no-colon", "url": None}

    def test_skip_offsets_index(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, fake_redis = _build(monkeypatch)
        fake_redis.llen.return_value = 10
        fake_redis.lrange.return_value = [b"x:https://x.test"]
        response = client.get(self.ENDPOINT, params={"skip": 5, "limit": 1})
        assert response.status_code == 200
        body = response.json()
        assert body["skip"] == 5
        assert body["limit"] == 1
        assert body["items"][0]["index"] == 5
        fake_redis.lrange.assert_called_once_with(
            "manual_upload_queue:tenant-disco", 5, 5
        )

    def test_decode_error_is_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, fake_redis = _build(monkeypatch)
        fake_redis.llen.return_value = 2
        bad = MagicMock()
        bad.decode.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "bad")
        fake_redis.lrange.return_value = [bad, b"ok:https://ok.test"]
        response = client.get(self.ENDPOINT)
        assert response.status_code == 200
        body = response.json()
        # Bad entry dropped; surviving entry keeps its original offset.
        assert len(body["items"]) == 1
        assert body["items"][0]["index"] == 1
        assert body["items"][0]["url"] == "https://ok.test"

    def test_rejects_invalid_skip_and_limit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, _ = _build(monkeypatch)
        # skip cannot be negative.
        response = client.get(self.ENDPOINT, params={"skip": -1})
        assert response.status_code == 422
        # limit cannot exceed 500.
        response = client.get(self.ENDPOINT, params={"limit": 1000})
        assert response.status_code == 422
