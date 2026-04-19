"""Unit tests for PR-C: routes_scraping.py BackgroundTasks → task_queue.

Coverage:
- /v1/scrape/cppa routes to state_scrape when CPPA adaptor is present
- /v1/scrape/cppa routes to generic_scrape when CPPA adaptor is absent
- 403 returned for non-CA tenants on /v1/scrape/cppa
- /v1/ingest/all-regulations no longer accepts a BackgroundTasks param
- register_scraping_handlers wires two distinct handler keys
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.auth import APIKey, require_api_key
from app.routes_scraping import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_key(*, jurisdictions: list[str]) -> APIKey:
    key = MagicMock(spec=APIKey)
    key.tenant_id = "tenant-xyz"
    key.allowed_jurisdictions = jurisdictions
    return key


def _build_client(api_key: APIKey) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: api_key
    return TestClient(app, raise_server_exceptions=True)


def _patch_enqueue(monkeypatch) -> tuple[MagicMock, MagicMock]:
    fake_session = MagicMock()
    mock_enqueue = MagicMock(return_value=1)
    monkeypatch.setattr("app.routes_scraping.SessionLocal", lambda: fake_session)
    monkeypatch.setattr("app.routes_scraping.enqueue_task", mock_enqueue)
    return mock_enqueue, fake_session


def _enqueue_kwargs(mock_enqueue: MagicMock) -> dict:
    return mock_enqueue.call_args.kwargs


# ---------------------------------------------------------------------------
# /v1/scrape/cppa — state_scrape path
# ---------------------------------------------------------------------------


class TestScrapeCppa:
    ENDPOINT = "/v1/scrape/cppa"
    CA_KEY = None  # set per-test

    def test_cppa_adaptor_enqueues_state_scrape(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(jurisdictions=["US-CA"]))
        resp = client.post(self.ENDPOINT, params={"url": "https://cppa.ca.gov/rss"})
        assert resp.status_code == 202
        kw = _enqueue_kwargs(mock_enqueue)
        assert kw["task_type"] == "state_scrape"
        assert kw["payload"]["adaptor_name"] == "cppa"
        assert kw["payload"]["url"] == "https://cppa.ca.gov/rss"
        assert kw["payload"]["jurisdiction_code"] == "US-CA"
        assert kw["payload"]["tenant_id"] == "tenant-xyz"

    def test_cppa_adaptor_missing_enqueues_generic_scrape(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        # Remove cppa from ADAPTORS for this test
        monkeypatch.setattr("app.routes_scraping.ADAPTORS", {})
        client = _build_client(_make_api_key(jurisdictions=["US-CA"]))
        resp = client.post(self.ENDPOINT, params={"url": "https://example.com/feed"})
        assert resp.status_code == 202
        kw = _enqueue_kwargs(mock_enqueue)
        assert kw["task_type"] == "generic_scrape"
        assert kw["payload"]["url"] == "https://example.com/feed"
        assert kw["payload"]["jurisdiction_code"] == "US-CA"

    def test_non_ca_tenant_returns_403(self, monkeypatch):
        _patch_enqueue(monkeypatch)
        # US-only key has no "US-CA" entitlement → verify_jurisdiction_access raises 403
        client = _build_client(_make_api_key(jurisdictions=["US"]))
        resp = client.post(self.ENDPOINT, params={"url": "https://cppa.ca.gov/rss"})
        assert resp.status_code == 403

    def test_db_commit_called_on_state_scrape(self, monkeypatch):
        _, fake_session = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(jurisdictions=["US-CA"]))
        client.post(self.ENDPOINT, params={"url": "https://cppa.ca.gov/rss"})
        fake_session.commit.assert_called_once()

    def test_db_closed_after_state_scrape(self, monkeypatch):
        _, fake_session = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(jurisdictions=["US-CA"]))
        client.post(self.ENDPOINT, params={"url": "https://cppa.ca.gov/rss"})
        fake_session.close.assert_called_once()

    def test_tenant_id_in_enqueue(self, monkeypatch):
        mock_enqueue, _ = _patch_enqueue(monkeypatch)
        client = _build_client(_make_api_key(jurisdictions=["US-CA"]))
        client.post(self.ENDPOINT, params={"url": "https://cppa.ca.gov/rss"})
        assert _enqueue_kwargs(mock_enqueue)["tenant_id"] == "tenant-xyz"


# ---------------------------------------------------------------------------
# /v1/ingest/all-regulations — BackgroundTasks param removed
# ---------------------------------------------------------------------------


class TestIngestAllRegulations:
    ENDPOINT = "/v1/ingest/all-regulations"

    def test_endpoint_does_not_accept_background_tasks_param(self):
        """Signature must not list BackgroundTasks — confirms the dead param was removed."""
        import inspect
        from fastapi import BackgroundTasks
        from app.routes_scraping import ingest_all_regulations

        sig = inspect.signature(ingest_all_regulations)
        for param in sig.parameters.values():
            assert param.annotation is not BackgroundTasks, (
                "ingest_all_regulations should no longer accept BackgroundTasks"
            )

    def test_returns_job_id_and_summary(self, monkeypatch):
        fixed = "00000000-0000-0000-0000-000000000002"
        monkeypatch.setattr("app.routes_scraping.uuid.uuid4", lambda: uuid.UUID(fixed))

        async_result = {"status": "ingested"}
        monkeypatch.setattr(
            "app.routes_scraping.discovery.scrape",
            AsyncMock(return_value=async_result),
        )
        # Patch FSMA_SOURCES to a minimal list to keep test fast
        monkeypatch.setattr(
            "app.routes_scraping.FSMA_SOURCES",
            [{"name": "Test", "url": "https://example.com", "type": "api", "jurisdiction": "US"}],
        )

        client = _build_client(_make_api_key(jurisdictions=["US"]))
        resp = client.post(self.ENDPOINT)
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == fixed
        assert body["status"] == "complete"
        assert body["ingested"] == 1
        assert body["failed"] == 0


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


class TestRegisterScrapingHandlers:
    def test_registers_both_task_types(self):
        from shared.task_queue import TASK_HANDLERS
        from app.task_handlers_scraping import register_scraping_handlers

        for key in ("state_scrape", "generic_scrape"):
            TASK_HANDLERS.pop(key, None)

        register_scraping_handlers()

        assert "state_scrape" in TASK_HANDLERS
        assert "generic_scrape" in TASK_HANDLERS

    def test_handlers_are_distinct(self):
        from shared.task_queue import TASK_HANDLERS
        from app.task_handlers_scraping import register_scraping_handlers

        register_scraping_handlers()

        assert id(TASK_HANDLERS["state_scrape"]) != id(TASK_HANDLERS["generic_scrape"])
