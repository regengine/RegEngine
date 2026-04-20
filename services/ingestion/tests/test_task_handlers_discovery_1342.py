"""Unit tests for ``app.task_handlers_discovery`` — issue #1342.

Pins the contract for the ``discovery_scrape`` task handler that
replaces the BackgroundTasks-based path in
``/v1/ingest/discovery/approve`` and ``.../bulk-approve``.

Critical contracts pinned:
  - ``_handle_discovery_scrape`` calls ``kernel.discovery.scrape(body, url)``
    with positional args in that exact order — the underlying
    ``discovery.scrape`` signature is positional, so any kwarg drift
    here would break in production with a confusing TypeError.
  - The handler is sync (returns ``None``) and wraps the async
    ``scrape`` coroutine via ``asyncio.run`` — this is what allows the
    sync ``TaskWorker`` thread pool to invoke it.
  - ``**_`` sink absorbs unknown payload fields so future
    ``/discovery/approve`` schema additions can't crash in-flight workers.
  - ``register_discovery_handlers`` registers exactly one task type
    (``discovery_scrape``) and binds it to ``_handle_discovery_scrape``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


# ---------------------------------------------------------------------------
# Stub kernel.discovery.discovery — only ``scrape`` is consumed.
#
# kernel/ is a top-level package with heavy transitive deps (Vertex AI,
# Neo4j drivers, etc.). Stub the leaf module the handler actually uses,
# build the package shape, and pin __file__ so the root conftest's
# eviction sweep (which keys off __file__) leaves us alone.
# ---------------------------------------------------------------------------


_scrape_calls: list[tuple] = []


class _FakeDiscovery:
    """Spy that records (body, url) positional args."""

    @staticmethod
    async def scrape(body, url):
        _scrape_calls.append((body, url))
        return None


_kernel_pkg = ModuleType("kernel")
_kernel_pkg.__path__ = []  # type: ignore[attr-defined]
_kernel_pkg.__file__ = str(service_dir / "kernel_pkg.py")

_discovery_pkg = ModuleType("kernel.discovery")
_discovery_pkg.__path__ = []  # type: ignore[attr-defined]
_discovery_pkg.__file__ = str(service_dir / "kernel_discovery_pkg.py")
_discovery_pkg.discovery = _FakeDiscovery

_kernel_pkg.discovery = _discovery_pkg
sys.modules["kernel"] = _kernel_pkg
sys.modules["kernel.discovery"] = _discovery_pkg


from app import task_handlers_discovery as thd  # noqa: E402
from app.task_handlers_discovery import (  # noqa: E402
    _handle_discovery_scrape,
    register_discovery_handlers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Re-install the kernel.discovery stub and clear capture state."""
    sys.modules["kernel"] = _kernel_pkg
    sys.modules["kernel.discovery"] = _discovery_pkg

    # The handler imports ``discovery`` at module load:
    #     from kernel.discovery import discovery
    # Re-pin onto the handler module in case a reload swapped it.
    monkeypatch.setattr(thd, "discovery", _FakeDiscovery, raising=False)

    _scrape_calls.clear()
    yield


# ---------------------------------------------------------------------------
# _handle_discovery_scrape
# ---------------------------------------------------------------------------


class TestHandleDiscoveryScrape:
    def test_calls_discovery_scrape_with_body_then_url(self):
        # discovery.scrape(body, url) — positional order matters.
        # Swapping body/url would still type-check as str/str but
        # would scrape the wrong target with the wrong content.
        _handle_discovery_scrape(
            body="<html>FDA notice...</html>",
            url="https://example.gov/notice/42",
        )
        assert len(_scrape_calls) == 1
        body, url = _scrape_calls[0]
        assert body == "<html>FDA notice...</html>"
        assert url == "https://example.gov/notice/42"

    def test_returns_none(self):
        # Sync handler, returns None — TaskWorker contract.
        result = _handle_discovery_scrape(
            body="x",
            url="https://example.com",
        )
        assert result is None

    def test_unknown_kwargs_absorbed_by_sink(self):
        # Forward-compat: future /discovery/approve payload fields
        # must not crash in-flight workers.
        _handle_discovery_scrape(
            body="x",
            url="https://example.com",
            future_field="ignored",
            another_extra={"k": "v"},
            tenant_id="t-1",  # not part of the documented signature
        )
        assert len(_scrape_calls) == 1

    def test_propagates_scrape_errors(self):
        # If the underlying scrape raises, the handler must propagate
        # so the task queue can mark the job failed and retry.
        async def _raising(body, url):
            raise RuntimeError("scrape failed")

        original = _FakeDiscovery.scrape
        _FakeDiscovery.scrape = staticmethod(_raising)  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="scrape failed"):
                _handle_discovery_scrape(body="x", url="https://example.com")
        finally:
            _FakeDiscovery.scrape = original  # type: ignore[assignment]

    def test_kwargs_only_signature(self):
        # The handler is keyword-only (``*,`` in signature). Calling
        # positionally must raise TypeError — this protects against
        # accidental positional dispatch from the task queue.
        with pytest.raises(TypeError):
            _handle_discovery_scrape("body", "https://example.com")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# register_discovery_handlers
# ---------------------------------------------------------------------------


class TestRegisterDiscoveryHandlers:
    def test_registers_single_discovery_scrape_task(self, monkeypatch):
        captured: list[tuple[str, Any]] = []
        monkeypatch.setattr(
            thd, "register_task_handler",
            lambda t, h: captured.append((t, h)),
        )
        register_discovery_handlers()
        assert captured == [("discovery_scrape", _handle_discovery_scrape)]

    def test_handler_reference_is_the_module_function(self, monkeypatch):
        # The registered handler must be the actual function object,
        # not a wrapper or partial — task queue introspection relies
        # on identity for hot-reload and de-registration.
        captured: list[Any] = []
        monkeypatch.setattr(
            thd, "register_task_handler",
            lambda t, h: captured.append(h),
        )
        register_discovery_handlers()
        assert captured[0] is _handle_discovery_scrape
