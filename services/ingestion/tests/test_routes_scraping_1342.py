"""Full-coverage tests for ``app.routes_scraping`` (#1342).

Complements ``tests/test_routes_scraping_task_queue.py`` which already
covers ``/v1/scrape/cppa`` and the happy path of
``/v1/ingest/all-regulations``. This file drives:

- ``POST /scrape/{adaptor}`` in all its branches (404, filtered source,
  empty content, pipeline success, scraper exception).
- The remaining ``ingest_all_regulations`` status branches
  (``queued_manual``, ``unchanged``, unknown/failed, exception).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
from app.scrapers.state_adaptors.base import FetchedItem, Source
import app.routes_scraping as routes_scraping
from app.routes_scraping import router as scraping_router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_key(jurisdictions: list[str] | None = None, tenant_id: str = "tenant-xyz") -> APIKey:
    key = MagicMock(spec=APIKey)
    key.tenant_id = tenant_id
    key.allowed_jurisdictions = jurisdictions or ["US-CA"]
    return key


def _client(api_key: APIKey) -> TestClient:
    app = FastAPI()
    app.include_router(scraping_router)
    app.dependency_overrides[require_api_key] = lambda: api_key
    return TestClient(app, raise_server_exceptions=True)


def _source(url: str, jurisdiction: str | None = "US-CA") -> Source:
    return Source(url=url, title="t", jurisdiction_code=jurisdiction)


def _fetched(content: bytes, content_type: str | None = "text/html", source: Source | None = None) -> FetchedItem:
    return FetchedItem(
        source=source or _source("https://example.com"),
        content_bytes=content,
        content_type=content_type,
    )


# ---------------------------------------------------------------------------
# POST /scrape/{adaptor}
# ---------------------------------------------------------------------------


class TestScrapeRegistry:
    def test_404_for_unknown_adaptor(self) -> None:
        client = _client(_make_api_key())
        response = client.post("/scrape/does-not-exist")
        assert response.status_code == 404
        assert response.json()["detail"] == "Unknown adaptor"

    def test_skips_sources_outside_allowed_jurisdictions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Scraper returns one source outside allowed jurisdictions; it
        # should be skipped before fetch is attempted.
        scraper = MagicMock()
        scraper.list_sources.return_value = [_source("https://x.test", jurisdiction="US-TX")]
        scraper.fetch = MagicMock()
        monkeypatch.setitem(routes_scraping.ADAPTORS, "tx_rss", scraper)

        client = _client(_make_api_key(jurisdictions=["US-CA"]))
        response = client.post("/scrape/tx_rss")
        assert response.status_code == 200
        body = response.json()
        assert body == {"adaptor": "tx_rss", "count": 0, "sources": []}
        # Fetch was never called because filtering kicked in first.
        scraper.fetch.assert_not_called()

    def test_includes_source_with_no_jurisdiction_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Sources with ``jurisdiction_code=None`` bypass the allow-list
        # check. ``process_content`` returns a real event, which the
        # endpoint reflects in the response.
        scraper = MagicMock()
        scraper.list_sources.return_value = [_source("https://no-juris.test", jurisdiction=None)]
        scraper.fetch.return_value = _fetched(b"<html>ok</html>")
        monkeypatch.setitem(routes_scraping.ADAPTORS, "fl_rss", scraper)
        monkeypatch.setattr(
            routes_scraping._PIPELINE,
            "process_content",
            lambda **kwargs: {"event": "ok", "url": kwargs["source_url"]},
        )

        client = _client(_make_api_key(jurisdictions=["US-CA"]))
        response = client.post("/scrape/fl_rss")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["sources"][0]["event"] == "ok"

    def test_empty_content_warning_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scraper = MagicMock()
        scraper.list_sources.return_value = [_source("https://empty.test")]
        scraper.fetch.return_value = _fetched(b"")
        monkeypatch.setitem(routes_scraping.ADAPTORS, "cppa", scraper)

        process = MagicMock()
        monkeypatch.setattr(routes_scraping._PIPELINE, "process_content", process)

        client = _client(_make_api_key(jurisdictions=["US-CA"]))
        response = client.post("/scrape/cppa")
        assert response.status_code == 200
        assert response.json()["count"] == 0
        process.assert_not_called()

    def test_pipeline_returns_no_event_is_not_appended(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scraper = MagicMock()
        scraper.list_sources.return_value = [_source("https://ok.test")]
        scraper.fetch.return_value = _fetched(b"<html>x</html>")
        monkeypatch.setitem(routes_scraping.ADAPTORS, "cppa", scraper)
        monkeypatch.setattr(
            routes_scraping._PIPELINE, "process_content", lambda **_k: None
        )

        client = _client(_make_api_key(jurisdictions=["US-CA"]))
        response = client.post("/scrape/cppa")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 0

    def test_pipeline_exception_is_swallowed_and_logged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scraper = MagicMock()
        sources = [
            _source("https://a.test"),
            _source("https://b.test"),  # second source should still be tried.
        ]
        scraper.list_sources.return_value = sources
        scraper.fetch.side_effect = [
            RuntimeError("fetch boom"),
            _fetched(b"<html>b</html>"),
        ]
        monkeypatch.setitem(routes_scraping.ADAPTORS, "cppa", scraper)
        monkeypatch.setattr(
            routes_scraping._PIPELINE,
            "process_content",
            lambda **_k: {"event": "b"},
        )

        client = _client(_make_api_key(jurisdictions=["US-CA"]))
        response = client.post("/scrape/cppa")
        assert response.status_code == 200
        body = response.json()
        # First source blew up; second succeeded.
        assert body["count"] == 1
        assert body["sources"] == [{"event": "b"}]

    def test_empty_allowed_jurisdictions_filters_everything(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ``allowed_jurisdictions=None`` → ``set(None or [])`` = empty set;
        # every non-None jurisdiction source gets skipped.
        scraper = MagicMock()
        scraper.list_sources.return_value = [
            _source("https://a.test", jurisdiction="US-CA"),
        ]
        scraper.fetch = MagicMock()
        monkeypatch.setitem(routes_scraping.ADAPTORS, "cppa", scraper)

        key = MagicMock(spec=APIKey)
        key.tenant_id = "t"
        key.allowed_jurisdictions = None
        client = _client(key)
        response = client.post("/scrape/cppa")
        assert response.status_code == 200
        assert response.json()["count"] == 0
        scraper.fetch.assert_not_called()


# ---------------------------------------------------------------------------
# POST /v1/ingest/all-regulations — remaining summary branches
# ---------------------------------------------------------------------------


class TestIngestAllRegulationsSummary:
    ENDPOINT = "/v1/ingest/all-regulations"

    def _setup_sources(self, monkeypatch: pytest.MonkeyPatch, sources) -> None:
        monkeypatch.setattr(
            "app.routes_scraping.FSMA_SOURCES",
            sources,
        )

    def _fake_source(self, idx: int = 0) -> dict:
        return {
            "name": f"S{idx}",
            "url": f"https://example.com/{idx}",
            "type": "api",
            "jurisdiction": "US",
        }

    def test_queued_manual_counted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setup_sources(monkeypatch, [self._fake_source()])
        monkeypatch.setattr(
            "app.routes_scraping.discovery.scrape",
            AsyncMock(return_value={"status": "queued_manual"}),
        )
        client = _client(_make_api_key(jurisdictions=["US"]))
        response = client.post(self.ENDPOINT)
        assert response.status_code == 200
        body = response.json()
        assert body["queued_manual"] == 1
        assert body["ingested"] == 0
        assert body["failed"] == 0
        assert body["unchanged"] == 0

    def test_unchanged_counted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setup_sources(monkeypatch, [self._fake_source()])
        monkeypatch.setattr(
            "app.routes_scraping.discovery.scrape",
            AsyncMock(return_value={"status": "unchanged"}),
        )
        client = _client(_make_api_key(jurisdictions=["US"]))
        response = client.post(self.ENDPOINT)
        assert response.status_code == 200
        assert response.json()["unchanged"] == 1

    def test_unknown_status_counted_as_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._setup_sources(monkeypatch, [self._fake_source()])
        # No ``status`` key -> falls through to ``.get("status", "failed")``
        # default, lands in ``failed`` bucket.
        monkeypatch.setattr(
            "app.routes_scraping.discovery.scrape",
            AsyncMock(return_value={}),
        )
        client = _client(_make_api_key(jurisdictions=["US"]))
        response = client.post(self.ENDPOINT)
        assert response.status_code == 200
        body = response.json()
        assert body["failed"] == 1

    def test_exception_counted_as_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setup_sources(monkeypatch, [self._fake_source()])
        monkeypatch.setattr(
            "app.routes_scraping.discovery.scrape",
            AsyncMock(side_effect=RuntimeError("boom")),
        )
        client = _client(_make_api_key(jurisdictions=["US"]))
        response = client.post(self.ENDPOINT)
        assert response.status_code == 200
        assert response.json()["failed"] == 1

    def test_mixed_summary_across_sources(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setup_sources(
            monkeypatch,
            [self._fake_source(i) for i in range(4)],
        )
        responses = [
            {"status": "ingested"},
            {"status": "queued_manual"},
            {"status": "unchanged"},
            RuntimeError("boom"),
        ]
        mock = AsyncMock(side_effect=responses)
        monkeypatch.setattr("app.routes_scraping.discovery.scrape", mock)

        client = _client(_make_api_key(jurisdictions=["US"]))
        response = client.post(self.ENDPOINT)
        assert response.status_code == 200
        body = response.json()
        assert body["sources_attempted"] == 4
        assert body["ingested"] == 1
        assert body["queued_manual"] == 1
        assert body["unchanged"] == 1
        assert body["failed"] == 1
        assert body["status"] == "complete"
