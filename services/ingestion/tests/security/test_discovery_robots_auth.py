"""Robots 401/403 regressions for ``app.discovery.EthicalScraper``.

``can_fetch`` must return False when robots.txt answers 401/403 instead
of falling through to the generic unreachable->True fallback. Scraping
must then take the queued-manual path without fetching the source URL.

All HTTP is faked; Redis is faked. No network.
"""

from __future__ import annotations

import httpx
import pytest


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.lists: dict[str, list] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value) -> None:
        self.store[key] = value.encode() if isinstance(value, str) else value

    def rpush(self, key: str, value) -> None:
        self.lists.setdefault(key, []).append(value)


def _make_scraper(monkeypatch):
    from app import discovery as discovery_module

    monkeypatch.setattr(discovery_module.Redis, "from_url", lambda *a, **k: _FakeRedis())
    scraper = discovery_module.EthicalScraper()
    assert isinstance(scraper.redis, _FakeRedis)
    return discovery_module, scraper


def _resp(status: int, url: str = "https://example.com/robots.txt") -> httpx.Response:
    req = httpx.Request("GET", url)
    return httpx.Response(status, content=b"User-agent: *\nDisallow: /", request=req)


def test_can_fetch_returns_false_on_401(monkeypatch):
    discovery_module, scraper = _make_scraper(monkeypatch)
    monkeypatch.setattr(discovery_module, "safe_httpx_get_sync", lambda *a, **k: _resp(401))
    assert scraper.can_fetch("https://example.com/page") is False


def test_can_fetch_returns_false_on_403(monkeypatch):
    discovery_module, scraper = _make_scraper(monkeypatch)
    monkeypatch.setattr(discovery_module, "safe_httpx_get_sync", lambda *a, **k: _resp(403))
    assert scraper.can_fetch("https://example.com/page") is False


async def test_scrape_with_forbidden_robots_queues_manual_without_source_fetch(monkeypatch):
    discovery_module, scraper = _make_scraper(monkeypatch)
    calls: list[str] = []

    def fake_get(url, **kwargs):
        calls.append(url)
        assert url.endswith("/robots.txt"), "source URL must not be fetched when robots forbids"
        return _resp(403, url)

    monkeypatch.setattr(discovery_module, "safe_httpx_get_sync", fake_get)
    result = await scraper.scrape("FDA", "https://example.com/rules")
    assert result["status"] == "queued_manual"
    assert calls == ["https://example.com/robots.txt"]
    assert scraper.redis.lists.get("manual_upload_queue:system") == ["FDA:https://example.com/rules"]


@pytest.mark.parametrize("status", [200, 401, 403])
async def test_oversized_robots_response_denies_and_queues_manual(monkeypatch, status):
    from shared import safe_http

    discovery_module, scraper = _make_scraper(monkeypatch)
    calls = []

    class RobotsTransport(httpx.BaseTransport):
        def handle_request(self, request):
            calls.append(str(request.url))
            assert request.url.path == "/robots.txt", "source must never be fetched"
            return httpx.Response(
                status,
                stream=httpx.ByteStream(b"x" * (discovery_module.ROBOTS_TXT_MAX_BYTES + 1)),
                request=request,
            )

    monkeypatch.setattr(safe_http, "_IPPinnedSyncTransport", lambda **kwargs: RobotsTransport())
    monkeypatch.setattr(safe_http, "_validate_and_pin", lambda url: ("93.184.216.34", "example.com"))
    monkeypatch.setattr(
        discovery_module,
        "safe_httpx_get_sync",
        lambda url, **kwargs: safe_http.safe_httpx_get_sync(url, validator=lambda value: value, **kwargs),
    )

    assert scraper.can_fetch("https://example.com/rules") is False
    result = await scraper.scrape("FDA", "https://example.com/rules")
    assert result["status"] == "queued_manual"
    assert calls == ["https://example.com/robots.txt"] * 2
    assert scraper.redis.lists["manual_upload_queue:system"] == ["FDA:https://example.com/rules"]
