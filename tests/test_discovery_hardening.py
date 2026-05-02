from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from kernel import discovery as discovery_mod


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
