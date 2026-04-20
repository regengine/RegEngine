"""Unit tests for ``app.task_handlers_scraping`` — issue #1342.

Pins the worker contract for the two scraper task types:
``state_scrape`` (named-adaptor + ``run_state_scrape_job``) and
``generic_scrape`` (fallback + ``run_generic_scrape_job``).

The state-scrape handler does a *lazy* import of ``ADAPTORS`` from
``app.routes_scraping`` inside the function body — the module-level
import would create a cycle. This means the stub for
``app.routes_scraping`` only needs to be in place at *call* time, but
must survive the root conftest's ``app.*`` eviction sweep.

Critical contracts pinned:
  - Unknown adaptor name raises ``ValueError`` with the offending name
    (otherwise the worker would silently swallow the bad payload).
  - Adaptor instance is fetched from the live ``ADAPTORS`` dict and
    forwarded by reference — no copy, no rewrap.
  - ``tenant_id`` defaults to ``None`` for both handlers (multi-tenant
    fan-out is opt-in, not implicit).
  - ``**_`` sink absorbs unknown payload fields so a future enqueuer
    field can't crash an in-flight worker.
  - ``register_scraping_handlers`` registers exactly two task types in
    a stable order.
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
# Stub app.scraper_job — the handlers import the two run_* coroutines
# at module-load time, so this stub must be in place before
# ``app.task_handlers_scraping`` is imported.
# ---------------------------------------------------------------------------


_state_calls: list[dict[str, Any]] = []
_generic_calls: list[dict[str, Any]] = []


async def _stub_run_state_scrape_job(**kwargs):
    _state_calls.append(kwargs)
    return None


async def _stub_run_generic_scrape_job(**kwargs):
    _generic_calls.append(kwargs)
    return None


_scraper_job_stub = ModuleType("app.scraper_job")
_scraper_job_stub.run_state_scrape_job = _stub_run_state_scrape_job
_scraper_job_stub.run_generic_scrape_job = _stub_run_generic_scrape_job
_scraper_job_stub.__file__ = str(service_dir / "app" / "scraper_job.py")
sys.modules["app.scraper_job"] = _scraper_job_stub

import app as _app_pkg  # noqa: E402
_app_pkg.scraper_job = _scraper_job_stub


# ---------------------------------------------------------------------------
# Stub app.routes_scraping — only the ADAPTORS dict is consumed, and only
# inside _handle_state_scrape (lazy import). Keep the stub minimal so we
# don't have to drag in the full FastAPI router.
# ---------------------------------------------------------------------------


class _RecordedAdaptor:
    """Marker spy — the handler should pass us through unmodified."""

    def __init__(self, name: str):
        self.name = name


_FAKE_ADAPTORS: dict[str, _RecordedAdaptor] = {
    "ca_doh": _RecordedAdaptor("ca_doh"),
    "ny_aghealth": _RecordedAdaptor("ny_aghealth"),
}

_routes_scraping_stub = ModuleType("app.routes_scraping")
_routes_scraping_stub.ADAPTORS = _FAKE_ADAPTORS
_routes_scraping_stub.__file__ = str(service_dir / "app" / "routes_scraping.py")
sys.modules["app.routes_scraping"] = _routes_scraping_stub
_app_pkg.routes_scraping = _routes_scraping_stub


from app import task_handlers_scraping as ths  # noqa: E402
from app.task_handlers_scraping import (  # noqa: E402
    _handle_generic_scrape,
    _handle_state_scrape,
    register_scraping_handlers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Re-install stubs evicted by the root conftest and clear capture state."""
    sys.modules["app.scraper_job"] = _scraper_job_stub
    sys.modules["app.routes_scraping"] = _routes_scraping_stub

    # Re-pin into ths in case the module was reloaded against fresh source.
    monkeypatch.setattr(
        ths, "run_state_scrape_job", _stub_run_state_scrape_job, raising=False
    )
    monkeypatch.setattr(
        ths, "run_generic_scrape_job", _stub_run_generic_scrape_job, raising=False
    )

    _state_calls.clear()
    _generic_calls.clear()
    yield


# ---------------------------------------------------------------------------
# _handle_state_scrape
# ---------------------------------------------------------------------------


class TestHandleStateScrape:
    def test_forwards_named_adaptor_and_metadata(self):
        _handle_state_scrape(
            adaptor_name="ca_doh",
            url="https://example.gov/regs",
            jurisdiction_code="CA",
            tenant_id="tenant-7",
        )
        assert len(_state_calls) == 1
        call = _state_calls[0]
        assert call["adaptor_name"] == "ca_doh"
        assert call["url"] == "https://example.gov/regs"
        assert call["jurisdiction_code"] == "CA"
        assert call["tenant_id"] == "tenant-7"

    def test_forwards_adaptor_instance_by_reference(self):
        # The ADAPTORS dict holds long-lived instances (each adaptor wraps
        # session state, rate limiters, etc.). The handler must pass the
        # *same* instance through, not a copy or re-wrap.
        expected_instance = _FAKE_ADAPTORS["ca_doh"]
        _handle_state_scrape(
            adaptor_name="ca_doh",
            url="https://example.gov",
            jurisdiction_code="CA",
        )
        call = _state_calls[0]
        assert call["adaptor_instance"] is expected_instance

    def test_tenant_id_defaults_to_none(self):
        _handle_state_scrape(
            adaptor_name="ny_aghealth",
            url="https://example.gov",
            jurisdiction_code="NY",
        )
        assert _state_calls[0]["tenant_id"] is None

    def test_unknown_adaptor_raises_value_error_with_name(self):
        # Critical safety: an unknown adaptor name must surface as a
        # hard error so the task queue can mark the job failed and
        # retry/dead-letter. Silently no-op'ing would lose the work.
        with pytest.raises(ValueError) as excinfo:
            _handle_state_scrape(
                adaptor_name="nonexistent_state",
                url="https://example.gov",
                jurisdiction_code="ZZ",
            )
        # The error message should include the bad name (in repr quotes)
        # so operators can grep logs for the offending payload.
        assert "nonexistent_state" in str(excinfo.value)
        # And the run coroutine must not have been called.
        assert _state_calls == []

    def test_unknown_kwargs_absorbed_by_sink(self):
        _handle_state_scrape(
            adaptor_name="ca_doh",
            url="https://example.gov",
            jurisdiction_code="CA",
            future_field="ignored",
            another_extra={"x": 1},
        )
        # The handler accepted the call (no TypeError) and forwarded
        # only the documented kwargs.
        assert len(_state_calls) == 1
        assert "future_field" not in _state_calls[0]
        assert "another_extra" not in _state_calls[0]

    def test_uses_live_adaptors_dict_at_call_time(self, monkeypatch):
        # Lazy import means swapping ADAPTORS at runtime should be
        # picked up — this protects the hot-reload pattern used by
        # tests and admin tools that register new adaptors at runtime.
        new_adaptor = _RecordedAdaptor("hot_loaded")
        monkeypatch.setitem(_routes_scraping_stub.ADAPTORS, "hot_loaded", new_adaptor)
        _handle_state_scrape(
            adaptor_name="hot_loaded",
            url="https://example.gov",
            jurisdiction_code="WA",
        )
        assert _state_calls[0]["adaptor_instance"] is new_adaptor


# ---------------------------------------------------------------------------
# _handle_generic_scrape
# ---------------------------------------------------------------------------


class TestHandleGenericScrape:
    def test_forwards_url_and_jurisdiction(self):
        _handle_generic_scrape(
            url="https://example.com/page",
            jurisdiction_code="TX",
            tenant_id="tenant-3",
        )
        assert len(_generic_calls) == 1
        call = _generic_calls[0]
        assert call["url"] == "https://example.com/page"
        assert call["jurisdiction_code"] == "TX"
        assert call["tenant_id"] == "tenant-3"

    def test_tenant_id_defaults_to_none(self):
        _handle_generic_scrape(
            url="https://example.com",
            jurisdiction_code="OR",
        )
        assert _generic_calls[0]["tenant_id"] is None

    def test_no_adaptor_lookup_required(self):
        # The generic handler is the fallback when no named adaptor
        # matches a target — it must NOT consult ADAPTORS at all.
        # We verify by confirming the call goes through cleanly with
        # an empty ADAPTORS dict.
        original = dict(_routes_scraping_stub.ADAPTORS)
        _routes_scraping_stub.ADAPTORS.clear()
        try:
            _handle_generic_scrape(
                url="https://example.com",
                jurisdiction_code="CA",
            )
            assert len(_generic_calls) == 1
        finally:
            _routes_scraping_stub.ADAPTORS.update(original)

    def test_unknown_kwargs_absorbed_by_sink(self):
        _handle_generic_scrape(
            url="https://example.com",
            jurisdiction_code="CA",
            adaptor_name="if_present_should_be_ignored",
            future_field=42,
        )
        # Generic handler doesn't accept adaptor_name — it's swallowed.
        assert len(_generic_calls) == 1
        assert "adaptor_name" not in _generic_calls[0]
        assert "future_field" not in _generic_calls[0]


# ---------------------------------------------------------------------------
# register_scraping_handlers
# ---------------------------------------------------------------------------


class TestRegisterScrapingHandlers:
    def test_registers_both_task_types(self, monkeypatch):
        captured: list[tuple[str, Any]] = []

        def _fake_register(task_type, handler):
            captured.append((task_type, handler))

        monkeypatch.setattr(ths, "register_task_handler", _fake_register)
        register_scraping_handlers()

        assert len(captured) == 2
        registered = dict(captured)
        assert registered["state_scrape"] is _handle_state_scrape
        assert registered["generic_scrape"] is _handle_generic_scrape

    def test_registration_order_state_before_generic(self, monkeypatch):
        # Stable order matters for any task-queue introspection that
        # relies on registration sequence — and conceptually state
        # scrapers are the primary path, generic the fallback, so
        # state should come first.
        order: list[str] = []
        monkeypatch.setattr(
            ths, "register_task_handler",
            lambda t, h: order.append(t),
        )
        register_scraping_handlers()
        assert order == ["state_scrape", "generic_scrape"]
