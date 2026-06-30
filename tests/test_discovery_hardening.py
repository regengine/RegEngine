from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.ingestion.app import discovery as discovery_mod

# ─── #2505: EthicalScraper must read REDIS_URL like every other consumer ─────


def _resolved_redis_host(scraper) -> str:
    """The host the redis client is actually pointed at."""
    return scraper.redis.connection_pool.connection_kwargs.get("host")


def test_redis_url_from_env_is_used_when_set(monkeypatch):
    """On Railway the Redis host is not ``redis``; the scraper must resolve it
    from REDIS_URL (the var the readiness probe and shared stores use) instead
    of the hardcoded docker-compose default (#2505)."""
    monkeypatch.setenv("REDIS_URL", "redis://prod-redis.internal:6380/2")

    scraper = discovery_mod.EthicalScraper()

    assert _resolved_redis_host(scraper) == "prod-redis.internal"


def test_redis_url_tls_scheme_is_inherited(monkeypatch):
    """Production Redis may be rediss:// (TLS); reading the env var inherits the
    scheme automatically (#2505)."""
    monkeypatch.setenv("REDIS_URL", "rediss://secure-redis.internal:6379/0")

    scraper = discovery_mod.EthicalScraper()

    assert scraper.redis.connection_pool.connection_kwargs.get("host") == "secure-redis.internal"
    # redis-py records TLS via the SSL connection class.
    conn_class = scraper.redis.connection_pool.connection_class
    assert "SSL" in conn_class.__name__


def test_explicit_redis_url_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://env-host:6379/0")

    scraper = discovery_mod.EthicalScraper(redis_url="redis://explicit-host:6379/1")

    assert _resolved_redis_host(scraper) == "explicit-host"


def test_falls_back_to_docker_default_only_when_env_unset(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    scraper = discovery_mod.EthicalScraper()

    assert _resolved_redis_host(scraper) == "redis"


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.queue = []

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def rpush(self, key, value):
        self.queue.append((key, value))


class FakeResponse:
    status_code = 200
    content = b"<html><body>Section 1. A firm shall keep records.</body></html>"
    headers = {"Content-Type": "text/html; charset=utf-8"}

    def raise_for_status(self):
        return None


@pytest.mark.asyncio
async def test_discovery_uses_safe_tempfile_without_changing_parser_loader_flow(
    monkeypatch,
):
    scraper = discovery_mod.EthicalScraper(redis_url="redis://unused")
    scraper.redis = FakeRedis()
    scraper.session = MagicMock()
    scraper.session.get.return_value = FakeResponse()
    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)
    monkeypatch.setattr(discovery_mod.asyncio, "sleep", AsyncMock())

    loader = MagicMock()

    async def parse_artifact(path, source_type):
        assert Path(path).exists()
        assert Path(path).read_bytes() == FakeResponse.content
        return [{"section_id": "1"}]

    async def load_artifact(path, source_type, body):
        assert Path(path).exists()
        assert Path(path).read_bytes() == FakeResponse.content
        return 1

    parser = MagicMock()
    parser.parse = AsyncMock(side_effect=parse_artifact)
    loader.load = AsyncMock(side_effect=load_artifact)

    monkeypatch.setattr(
        discovery_mod,
        "RegulationParser",
        MagicMock(return_value=parser),
    )
    monkeypatch.setattr(
        discovery_mod,
        "RegulationLoader",
        MagicMock(return_value=loader),
    )

    result = await scraper.scrape(
        body="../FDA unsafe body",
        source_url="https://example.test/regulation",
        source_type="html",
        jurisdiction="FDA",
    )

    parser_path, parser_source_type = parser.parse.call_args.args
    loader_path, loader_source_type, loader_body = loader.load.call_args.args

    assert result["status"] == "ingested"
    assert parser_source_type == "html"
    assert loader_source_type == "html"
    assert loader_body == "../FDA unsafe body"
    assert parser_path == loader_path

    artifact_path = Path(parser_path)
    assert artifact_path.suffix == ".html"
    assert artifact_path.name.startswith("regengine-discovery-")
    assert "FDA unsafe body" not in artifact_path.name
    assert not artifact_path.exists()


@pytest.mark.asyncio
async def test_discovery_removes_tempfile_and_closes_loader_on_load_failure(
    monkeypatch,
):
    scraper = discovery_mod.EthicalScraper(redis_url="redis://unused")
    scraper.redis = FakeRedis()
    scraper.session = MagicMock()
    scraper.session.get.return_value = FakeResponse()
    monkeypatch.setattr(scraper, "can_fetch", lambda url: True)
    monkeypatch.setattr(discovery_mod.asyncio, "sleep", AsyncMock())

    parser = MagicMock()
    parser.parse = AsyncMock(return_value=[{"section_id": "1"}])

    loader = MagicMock()
    loader.load = AsyncMock(side_effect=RuntimeError("load failed"))

    monkeypatch.setattr(
        discovery_mod,
        "RegulationParser",
        MagicMock(return_value=parser),
    )
    monkeypatch.setattr(
        discovery_mod,
        "RegulationLoader",
        MagicMock(return_value=loader),
    )

    result = await scraper.scrape(
        body="FDA",
        source_url="https://example.test/regulation",
        source_type="html",
        jurisdiction="FDA",
    )

    artifact_path = Path(parser.parse.call_args.args[0])

    assert result["status"] == "failed"
    assert result["error"] == "load failed"
    loader.close.assert_called_once()
    assert not artifact_path.exists()
