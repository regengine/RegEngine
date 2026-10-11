"""Adversarial checks for the FSMA plugin catalog.

The nightly ingest treats plugins/fsma/sources.py as the manifest of what
may be fetched. A malformed entry, a path-like name, an off-scope URL, or
an extra scope claim must be refused before any scrape starts.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock

import app.routes_scraping as routes_scraping
import pytest

from plugins.fsma.sources import FSMA_SOURCES, PluginManifestError, load_fsma_sources


def _valid(**overrides) -> dict:
    entry = {
        "name": "21CFR-Part1",
        "url": "https://www.fda.gov/food/example",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "Example FDA source",
    }
    entry.update(overrides)
    return entry


def test_shipped_catalog_loads_and_stays_fda_scoped() -> None:
    loaded = load_fsma_sources()
    assert [item["name"] for item in loaded] == [item["name"] for item in FSMA_SOURCES]
    assert len(loaded) == 8
    assert {item["jurisdiction"] for item in loaded} == {"FDA"}
    assert {item["type"] for item in loaded} <= {"html", "pdf"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "../../etc/passwd"},
        {"name": "/etc/passwd"},
        {"name": "ok..hidden"},
        {"name": "name:with-colon"},
        {"name": "has\nnewline"},
        {"name": "has\x00null"},
        {"name": ""},
        {"name": "A" * 129},
        {"url": "file:///etc/passwd"},
        {"url": "/etc/passwd"},
        {"url": "../secrets.env"},
        {"url": "http://www.fda.gov/food"},
        {"url": "https://evil.example/plugin"},
        {"url": "https://fda.gov.evil.com/food"},
        {"url": "https://evilfda.gov/food"},
        {"url": "https://notecfr.gov/"},
        {"url": "https://user:pass@www.fda.gov/food"},
        {"url": "https://www.fda.gov@evil.com/food"},
        {"url": "https://www.fda.gov/a/../../etc/passwd"},
        {"url": "https://www.fda.gov/%2e%2e/etc/passwd"},
        {"url": "https://127.0.0.1/latest"},
        {"type": "url"},
        {"type": "../../../tmp/pwned"},
        {"jurisdiction": "US-CA"},
        {"jurisdiction": "*"},
        {"description": ""},
        {"description": "line\nbreak"},
        {"scopes": ["admin"]},
        {"tenant_id": "victim"},
    ],
)
def test_malformed_or_overscoped_entry_is_rejected(overrides: dict) -> None:
    with pytest.raises(PluginManifestError):
        load_fsma_sources([_valid(**overrides)])


def test_missing_fields_non_dicts_and_duplicates_are_rejected() -> None:
    with pytest.raises(PluginManifestError):
        load_fsma_sources([{"name": "Only-Name"}])
    with pytest.raises(PluginManifestError):
        load_fsma_sources(["not-a-mapping"])
    with pytest.raises(PluginManifestError):
        load_fsma_sources([])
    with pytest.raises(PluginManifestError):
        load_fsma_sources("https://www.fda.gov/food")
    first = _valid(name="Same-Name")
    second = _valid(name="same-name", url="https://www.ecfr.gov/food")
    with pytest.raises(PluginManifestError):
        load_fsma_sources([first, second])


def test_hostile_catalog_is_not_scraped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Path escape, file URL, and an extra scope must not reach the fetcher."""
    hostile = {
        "name": "../../etc/passwd",
        "url": "file:///etc/passwd",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "escape",
        "scopes": ["admin"],
    }
    monkeypatch.setattr(routes_scraping, "FSMA_SOURCES", [hostile])
    scrape = AsyncMock(return_value={"status": "ingested"})
    monkeypatch.setattr(routes_scraping.discovery, "scrape", scrape)

    with pytest.raises(PluginManifestError):
        asyncio.run(routes_scraping.run_all_regulations_ingest())

    scrape.assert_not_called()


def test_parallel_loads_return_the_same_catalog() -> None:
    """Concurrent readers share no mutable loader state."""
    results: list[tuple[str, ...]] = []
    lock = threading.Lock()

    def _run() -> None:
        loaded = tuple(item["name"] for item in load_fsma_sources())
        with lock:
            results.append(loaded)

    threads = [threading.Thread(target=_run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 8
    assert len(set(results)) == 1
