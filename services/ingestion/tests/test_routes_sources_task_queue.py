"""Unit tests for PR-B: routes_sources.py now enqueues to task_queue.

Tests verify that:
- Each endpoint calls enqueue_task with the correct task_type and payload
- The job_id returned matches the one written to the queue
- 403 is returned for non-US tenants on all three endpoints
- SessionLocal.commit() is called after enqueue
- SessionLocal.close() is called in the finally block
- register_source_handlers wires three distinct handler keys
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.auth import APIKey, require_api_key
from app.routes_sources import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_api_key(*, us: bool) -> APIKey:
    key = MagicMock(spec=APIKey)
    key.tenant_id = "tenant-abc"
    key.allowed_jurisdictions = ["US"] if us else ["CA"]
    return key


def _build_client(api_key: APIKey) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: api_key
    return TestClient(app, raise_server_exceptions=True)


def _patch_enqueue(monkeypatch) -> tuple[MagicMock, MagicMock]:
    """Replace SessionLocal and enqueue_task; return (mock_enqueue, fake_session)."""
    fake_session = MagicMock()
    mock_enqueue = MagicMock(return_value=1)
    monkeypatch.setattr("app.routes_sources.SessionLocal", lambda: fake_session)
    monkeypatch.setattr("app.routes_sources.enqueue_task", mock_enqueue)
    return mock_enqueue, fake_session


def _enqueue_kwargs(mock_enqueue: MagicMock) -> dict:
    """Return the keyword-arg dict from the most recent enqueue_task call."""
    call = mock_enqueue.call_args
    # signature: enqueue_task(db_session, task_type=..., payload=..., tenant_id=...)
    return call.kwargs


# ---------------------------------------------------------------------------
# /v1/ingest/federal-register
# ---------------------------------------------------------------------------


class TestIngestFederalRegister:
    ENDPOINT = "/v1/ingest/federal-register"

    def test_accepted_enqueues_correct_task_type(self, monkeypatch):
        fixed = "00000000-0000-0000-0000-000000000001"
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        monkeypatch.setattr("app.routes_sources.uuid.uuid4", lambda: uuid.UUID(fixed))

        client = _build_client(_make_api_key(us=True))
        resp = client.post(self.ENDPOINT, json={"vertical": "food_safety"})

        assert resp.status_code == 202
        body = resp.json()
        assert body["job_id"] == fixed
        assert body["status"] == "accepted"

        mock_enqueue.assert_called_once()
        kw = _enqueue_kwargs(mock_enqueue)
        assert kw["task_type"] == "federal_register_ingest"
        assert kw["payload"]["job_id"] == fixed
        assert kw["payload"]["vertical"] == "food_safety"
        assert kw["payload"]["tenant_id"] == "tenant-abc"

    def test_non_us_returns_403(self, monkeypatch):
        _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=False))
        resp = client.post(self.ENDPOINT, json={"vertical": "food_safety"})
        assert resp.status_code == 403

    def test_optional_fields_propagated(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        client.post(
            self.ENDPOINT,
            json={
                "vertical": "food_safety",
                "max_documents": 50,
                "date_from": "2024-01-01",
                "agencies": ["FDA"],
            },
        )
        payload = _enqueue_kwargs(mock_enqueue)["payload"]
        assert payload["max_documents"] == 50
        assert payload["date_from"].startswith("2024-01-01")
        assert payload["agencies"] == ["FDA"]

    def test_db_commit_called(self, monkeypatch):
        _, fake_session = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        client.post(self.ENDPOINT, json={"vertical": "food_safety"})
        fake_session.commit.assert_called_once()

    def test_db_closed_on_success(self, monkeypatch):
        _, fake_session = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        client.post(self.ENDPOINT, json={"vertical": "food_safety"})
        fake_session.close.assert_called_once()

    def test_tenant_id_passed_to_enqueue(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        client.post(self.ENDPOINT, json={"vertical": "food_safety"})
        assert _enqueue_kwargs(mock_enqueue)["tenant_id"] == "tenant-abc"


# ---------------------------------------------------------------------------
# /v1/ingest/ecfr
# ---------------------------------------------------------------------------


class TestIngestECFR:
    ENDPOINT = "/v1/ingest/ecfr"

    VALID_ECFR = {"vertical": "food_safety", "cfr_title": 21, "cfr_part": 110}

    def test_accepted_enqueues_correct_task_type(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        resp = client.post(self.ENDPOINT, json=self.VALID_ECFR)
        assert resp.status_code == 202
        assert _enqueue_kwargs(mock_enqueue)["task_type"] == "ecfr_ingest"

    def test_non_us_returns_403(self, monkeypatch):
        _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=False))
        resp = client.post(self.ENDPOINT, json=self.VALID_ECFR)
        assert resp.status_code == 403

    def test_cfr_fields_propagated(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        client.post(self.ENDPOINT, json={"vertical": "food_safety", "cfr_title": 21, "cfr_part": 110})
        payload = _enqueue_kwargs(mock_enqueue)["payload"]
        assert payload["cfr_title"] == 21
        assert payload["cfr_part"] == 110

    def test_db_closed_on_success(self, monkeypatch):
        _, fake_session = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        client.post(self.ENDPOINT, json=self.VALID_ECFR)
        fake_session.close.assert_called_once()

    def test_tenant_id_passed_to_enqueue(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        client.post(self.ENDPOINT, json=self.VALID_ECFR)
        assert _enqueue_kwargs(mock_enqueue)["tenant_id"] == "tenant-abc"


# ---------------------------------------------------------------------------
# /v1/ingest/fda
# ---------------------------------------------------------------------------


class TestIngestFDA:
    ENDPOINT = "/v1/ingest/fda"

    def test_accepted_enqueues_correct_task_type(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        resp = client.post(self.ENDPOINT, json={"vertical": "food_safety"})
        assert resp.status_code == 202
        assert _enqueue_kwargs(mock_enqueue)["task_type"] == "fda_ingest"

    def test_non_us_returns_403(self, monkeypatch):
        _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=False))
        resp = client.post(self.ENDPOINT, json={"vertical": "food_safety"})
        assert resp.status_code == 403

    def test_max_documents_propagated(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        client.post(self.ENDPOINT, json={"vertical": "food_safety", "max_documents": 100})
        assert _enqueue_kwargs(mock_enqueue)["payload"]["max_documents"] == 100

    def test_db_closed_on_success(self, monkeypatch):
        _, fake_session = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        client.post(self.ENDPOINT, json={"vertical": "food_safety"})
        fake_session.close.assert_called_once()

    def test_tenant_id_passed_to_enqueue(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(us=True))
        client.post(self.ENDPOINT, json={"vertical": "food_safety"})
        assert _enqueue_kwargs(mock_enqueue)["tenant_id"] == "tenant-abc"


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


class TestRegisterSourceHandlers:
    def test_registers_all_three_task_types(self):
        from shared.task_queue import TASK_HANDLERS
        from app.task_handlers_sources import register_source_handlers

        for key in ("federal_register_ingest", "ecfr_ingest", "fda_ingest"):
            TASK_HANDLERS.pop(key, None)

        register_source_handlers()

        assert "federal_register_ingest" in TASK_HANDLERS
        assert "ecfr_ingest" in TASK_HANDLERS
        assert "fda_ingest" in TASK_HANDLERS

    def test_handlers_are_distinct_callables(self):
        from shared.task_queue import TASK_HANDLERS
        from app.task_handlers_sources import register_source_handlers

        register_source_handlers()

        handlers = [
            TASK_HANDLERS["federal_register_ingest"],
            TASK_HANDLERS["ecfr_ingest"],
            TASK_HANDLERS["fda_ingest"],
        ]
        assert len({id(h) for h in handlers}) == 3
