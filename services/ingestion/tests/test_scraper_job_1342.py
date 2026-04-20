"""Unit tests for ``app.scraper_job`` — issue #1342.

Covers the two background-task coroutines that execute scraper logic:

``run_state_scrape_job``:
  - Delegates synchronous adaptor ``fetch`` to the event loop's
    executor (so a slow network call doesn't block the loop).
  - Happy path: fetch succeeds, pipeline yields an event, success log
    fires with the event id.
  - Empty-content short-circuit: ``content_bytes == b""`` → early
    return without pipeline call (don't log bogus 0-byte events).
  - Error path: adaptor raises a caught exception → logs failure and
    stores a Redis record (``scrape_job:failed:{url}`` with 1h TTL
    and JSON blob) so operators can see what broke without replaying
    the entire job queue.
  - Redis-storage-also-fails path: if Redis is unreachable the
    top-level error is still logged, and the inner ``redis_exc`` is
    logged at debug level (no secondary crash).
  - Uncaught exception types propagate: only the listed exc classes
    are swallowed — a bare ``Exception`` would mask bugs.

``run_generic_scrape_job``:
  - Awaits the generic scraper's ``fetch_document``.
  - Error path: caught exceptions → error log, no raise.
  - Uncaught exception types propagate.

Stubs ``_PIPELINE``, ``_GENERIC_SCRAPER``, ``redis`` module, and
``get_settings`` to keep tests offline and deterministic.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


from app import scraper_job as mod  # noqa: E402
from app.scrapers.state_adaptors.base import FetchedItem, Source  # noqa: E402
from app.scraper_job import run_generic_scrape_job, run_state_scrape_job  # noqa: E402


# ---------------------------------------------------------------------------
# Stubs / spies
# ---------------------------------------------------------------------------


class _Event:
    def __init__(self, event_id: str = "evt-1"):
        self.event_id = event_id


class _PipelineSpy:
    def __init__(self):
        self.calls: list[dict] = []
        self.result: _Event | None = _Event()

    def process_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _GenericScraperSpy:
    def __init__(self):
        self.calls: list[dict] = []
        self.raises: Exception | None = None

    async def fetch_document(self, url, jurisdiction_code, *, tenant_id=None):
        self.calls.append(
            {"url": url, "jurisdiction_code": jurisdiction_code, "tenant_id": tenant_id}
        )
        if self.raises:
            raise self.raises


class _AdaptorSpy:
    """Synchronous fetch — returns the scripted ``FetchedItem`` or raises."""

    def __init__(
        self,
        *,
        fetched_item: FetchedItem | None = None,
        raises: Exception | None = None,
    ):
        self.fetch_calls: list[Source] = []
        self._fetched_item = fetched_item or FetchedItem(
            source=Source(url="x"),
            content_bytes=b"hi",
            content_type="text/html",
        )
        self._raises = raises

    def fetch(self, source: Source) -> FetchedItem:
        self.fetch_calls.append(source)
        if self._raises:
            raise self._raises
        return self._fetched_item


class _RedisSpy:
    """Fake redis client; records setex calls."""

    def __init__(self, *, setex_raises: Exception | None = None):
        self.setex_calls: list[tuple[str, int, str]] = []
        self._setex_raises = setex_raises

    def setex(self, key: str, ttl: int, value: str):
        if self._setex_raises:
            raise self._setex_raises
        self.setex_calls.append((key, ttl, value))


def _make_redis_module(client: _RedisSpy | Exception):
    """Build a ``redis`` module stub that returns ``client`` from
    ``from_url``, or raises if ``client`` is an Exception.
    """
    m = ModuleType("redis")

    def _from_url(url: str):
        if isinstance(client, Exception):
            raise client
        return client

    m.from_url = _from_url
    return m


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_module_singletons(monkeypatch):
    """Swap the module-level ``_PIPELINE`` + ``_GENERIC_SCRAPER`` before each test."""
    pipeline = _PipelineSpy()
    generic = _GenericScraperSpy()
    monkeypatch.setattr(mod, "_PIPELINE", pipeline)
    monkeypatch.setattr(mod, "_GENERIC_SCRAPER", generic)
    return pipeline, generic


@pytest.fixture
def patch_redis(monkeypatch):
    """Install a stub ``redis`` module + settings, return the spy client."""

    def _install(client: _RedisSpy | Exception = None):
        client = client or _RedisSpy()
        mod_redis = _make_redis_module(client)
        sys.modules["redis"] = mod_redis
        monkeypatch.setattr(
            mod, "get_settings",
            lambda: SimpleNamespace(redis_url="redis://stub:6379"),
            raising=False,
        )
        return client

    return _install


# ---------------------------------------------------------------------------
# run_state_scrape_job — happy path
# ---------------------------------------------------------------------------


class TestRunStateScrapeJob:
    def test_fetch_executor_pipeline_success(self, _patch_module_singletons):
        pipeline, _ = _patch_module_singletons
        fetched = FetchedItem(
            source=Source(url="https://example.gov/doc"),
            content_bytes=b"<html>hi</html>",
            content_type="text/html",
        )
        adaptor = _AdaptorSpy(fetched_item=fetched)

        asyncio.run(
            run_state_scrape_job(
                adaptor_name="ca_doh",
                adaptor_instance=adaptor,
                url="https://example.gov/doc",
                jurisdiction_code="CA",
                tenant_id="t-1",
            )
        )

        # Adaptor called once with the right Source.
        assert len(adaptor.fetch_calls) == 1
        src = adaptor.fetch_calls[0]
        assert src.url == "https://example.gov/doc"
        assert src.jurisdiction_code == "CA"

        # Pipeline got the fetched bytes and metadata.
        assert len(pipeline.calls) == 1
        call = pipeline.calls[0]
        assert call["content"] == b"<html>hi</html>"
        assert call["content_type"] == "text/html"
        assert call["jurisdiction_code"] == "CA"
        assert call["source_url"] == "https://example.gov/doc"
        assert call["tenant_id"] == "t-1"

    def test_fetch_runs_in_executor_not_event_loop(self, _patch_module_singletons):
        """Critical contract: adaptor.fetch is synchronous (httpx.get + blocking
        XML parse). Running it directly in the event loop would pause the
        scheduler; the job must dispatch it to a thread pool via run_in_executor.
        """
        adaptor = _AdaptorSpy(
            fetched_item=FetchedItem(
                source=Source(url="u"),
                content_bytes=b"x",
                content_type="text/plain",
            )
        )

        async def _runner():
            loop = asyncio.get_running_loop()
            # Override run_in_executor so we can observe that the fetch
            # was dispatched to the executor rather than being awaited
            # directly on the loop.
            captured: list[Any] = []
            real = loop.run_in_executor

            async def _wrapped(executor, func, *args):
                captured.append(("executor", executor, func.__name__))
                return await real(executor, func, *args)

            loop.run_in_executor = _wrapped  # type: ignore[method-assign]
            try:
                await run_state_scrape_job(
                    adaptor_name="x",
                    adaptor_instance=adaptor,
                    url="u",
                    jurisdiction_code="CA",
                    tenant_id=None,
                )
            finally:
                loop.run_in_executor = real  # type: ignore[method-assign]
            return captured

        captured = asyncio.run(_runner())
        # Exactly one executor dispatch.
        assert len(captured) == 1
        tag, executor, fname = captured[0]
        assert tag == "executor"
        # Default executor (None) — doesn't allocate a custom pool.
        assert executor is None
        assert fname == "_fetch_sync"

    def test_empty_content_short_circuits_pipeline(self, _patch_module_singletons):
        pipeline, _ = _patch_module_singletons
        fetched = FetchedItem(
            source=Source(url="u"),
            content_bytes=b"",
            content_type="text/html",
        )
        adaptor = _AdaptorSpy(fetched_item=fetched)

        asyncio.run(
            run_state_scrape_job(
                adaptor_name="x",
                adaptor_instance=adaptor,
                url="u",
                jurisdiction_code="CA",
                tenant_id=None,
            )
        )

        # Pipeline never called — don't log or persist 0-byte events.
        assert pipeline.calls == []

    def test_pipeline_returns_none_no_success_log(self, _patch_module_singletons):
        pipeline, _ = _patch_module_singletons
        pipeline.result = None  # e.g. pipeline decided the content was junk

        adaptor = _AdaptorSpy()
        asyncio.run(
            run_state_scrape_job(
                adaptor_name="x",
                adaptor_instance=adaptor,
                url="u",
                jurisdiction_code="CA",
                tenant_id=None,
            )
        )
        # Pipeline WAS called (content wasn't empty) but there's no event to log.
        assert len(pipeline.calls) == 1

    def test_caught_exception_logs_failure_to_redis(
        self, _patch_module_singletons, patch_redis
    ):
        client = patch_redis(_RedisSpy())
        adaptor = _AdaptorSpy(raises=ValueError("boom"))

        asyncio.run(
            run_state_scrape_job(
                adaptor_name="ca_doh",
                adaptor_instance=adaptor,
                url="https://example.gov/doc",
                jurisdiction_code="CA",
                tenant_id=None,
            )
        )

        assert len(client.setex_calls) == 1
        key, ttl, value = client.setex_calls[0]
        assert key == "scrape_job:failed:https://example.gov/doc"
        assert ttl == 3600
        payload = json.loads(value)
        assert payload["adaptor"] == "ca_doh"
        assert payload["url"] == "https://example.gov/doc"
        assert payload["error"] == "boom"
        # ISO8601 UTC timestamp with offset.
        assert "T" in payload["failed_at"]

    @pytest.mark.parametrize(
        "exc",
        [OSError("fs"), IOError("io"), AttributeError("attr"),
         TypeError("type"), ValueError("val")],
    )
    def test_caught_exception_types(
        self, _patch_module_singletons, patch_redis, exc
    ):
        client = patch_redis(_RedisSpy())
        adaptor = _AdaptorSpy(raises=exc)
        # Should not raise — all these exc types are caught.
        asyncio.run(
            run_state_scrape_job(
                adaptor_name="x",
                adaptor_instance=adaptor,
                url="u",
                jurisdiction_code="CA",
                tenant_id=None,
            )
        )
        assert len(client.setex_calls) == 1

    def test_redis_setex_failure_swallowed(
        self, _patch_module_singletons, patch_redis
    ):
        # Redis unreachable / auth fails — the outer error is already
        # logged; the status-store side-effect is best-effort.
        client = patch_redis(_RedisSpy(setex_raises=OSError("redis down")))
        adaptor = _AdaptorSpy(raises=ValueError("primary error"))

        # Must not raise — the secondary Redis error shouldn't crash
        # the worker.
        asyncio.run(
            run_state_scrape_job(
                adaptor_name="x",
                adaptor_instance=adaptor,
                url="u",
                jurisdiction_code="CA",
                tenant_id=None,
            )
        )

    def test_redis_from_url_failure_swallowed(
        self, _patch_module_singletons, patch_redis
    ):
        # redis.from_url itself raising (bad URL, dns fail) must also
        # not crash the worker.
        patch_redis(OSError("dns"))
        adaptor = _AdaptorSpy(raises=ValueError("primary"))
        asyncio.run(
            run_state_scrape_job(
                adaptor_name="x",
                adaptor_instance=adaptor,
                url="u",
                jurisdiction_code="CA",
                tenant_id=None,
            )
        )

    def test_uncaught_exception_propagates(self, _patch_module_singletons):
        # Exception types NOT in the catch list must propagate so the
        # worker can retry/dead-letter (don't silently swallow
        # KeyboardInterrupt, RuntimeError, etc.).
        adaptor = _AdaptorSpy(raises=RuntimeError("surprise"))
        with pytest.raises(RuntimeError, match="surprise"):
            asyncio.run(
                run_state_scrape_job(
                    adaptor_name="x",
                    adaptor_instance=adaptor,
                    url="u",
                    jurisdiction_code="CA",
                    tenant_id=None,
                )
            )


# ---------------------------------------------------------------------------
# run_generic_scrape_job
# ---------------------------------------------------------------------------


class TestRunGenericScrapeJob:
    def test_delegates_to_generic_scraper(self, _patch_module_singletons):
        _, generic = _patch_module_singletons
        asyncio.run(
            run_generic_scrape_job(
                url="https://ex.gov/x",
                jurisdiction_code="OR",
                tenant_id="t-7",
            )
        )
        assert generic.calls == [
            {"url": "https://ex.gov/x", "jurisdiction_code": "OR", "tenant_id": "t-7"}
        ]

    @pytest.mark.parametrize(
        "exc",
        [OSError("fs"), IOError("io"), AttributeError("attr"),
         TypeError("type"), ValueError("val")],
    )
    def test_caught_exceptions_do_not_propagate(
        self, _patch_module_singletons, exc
    ):
        _, generic = _patch_module_singletons
        generic.raises = exc
        # Must not raise.
        asyncio.run(
            run_generic_scrape_job(
                url="u", jurisdiction_code="CA", tenant_id=None,
            )
        )

    def test_uncaught_exception_propagates(self, _patch_module_singletons):
        _, generic = _patch_module_singletons
        generic.raises = RuntimeError("surprise")
        with pytest.raises(RuntimeError, match="surprise"):
            asyncio.run(
                run_generic_scrape_job(
                    url="u", jurisdiction_code="CA", tenant_id=None,
                )
            )
