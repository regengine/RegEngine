"""Unit tests for ``app.task_handlers_sources`` — issue #1342.

Stubs the federal-source adapters and the shared ``_run_adapter_ingest``
coroutine so each handler's wiring is pinned: the right adapter type is
constructed, the right ``source_system`` string is forwarded to the
ingest coroutine, optional kwargs (``max_documents``, ``date_from``,
``agencies``, ``cfr_title``, ``cfr_part``) flow through verbatim, and
unknown kwargs are absorbed by the ``**_`` sink so a future payload
field can't crash an in-flight worker.

The handlers run inside a task-queue worker after the original request
context has been torn down, so silent kwarg drift would corrupt the
ingest pipeline. These tests pin the contract.
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
# Stub the regengine_ingestion.sources adapters so the import succeeds
# without pulling in the full ingestion library.
# ---------------------------------------------------------------------------


class _RecordedAdapter:
    """Base class for spy adapters — records constructor kwargs."""

    instances: list["_RecordedAdapter"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        type(self).instances.append(self)


class _FederalRegisterAdapter(_RecordedAdapter):
    instances: list["_FederalRegisterAdapter"] = []


class _ECFRAdapter(_RecordedAdapter):
    instances: list["_ECFRAdapter"] = []


class _FDAAdapter(_RecordedAdapter):
    instances: list["_FDAAdapter"] = []


# Build a package-shaped stub for ``regengine_ingestion`` and the only
# submodule the handler actually exercises (``sources``).
_sources_pkg = ModuleType("regengine_ingestion")
_sources_pkg.__path__ = []  # type: ignore[attr-defined]
_sources_pkg.__file__ = str(service_dir / "regengine_ingestion_pkg.py")

_sources_mod = ModuleType("regengine_ingestion.sources")
_sources_mod.FederalRegisterAdapter = _FederalRegisterAdapter
_sources_mod.ECFRAdapter = _ECFRAdapter
_sources_mod.FDAAdapter = _FDAAdapter
_sources_mod.__file__ = str(service_dir / "regengine_ingestion_sources.py")

_sources_pkg.sources = _sources_mod
sys.modules["regengine_ingestion"] = _sources_pkg
sys.modules["regengine_ingestion.sources"] = _sources_mod

# ``app.routes`` is heavy (full FastAPI router + many shared imports).
# The handler only consumes ``_run_adapter_ingest`` from it, so stub
# the whole module.
_routes_stub = ModuleType("app.routes")


async def _stub_run_adapter_ingest(**_kwargs):
    return None


_routes_stub._run_adapter_ingest = _stub_run_adapter_ingest
_routes_stub.__file__ = str(service_dir / "app" / "routes.py")
sys.modules["app.routes"] = _routes_stub

import app as _app_pkg  # noqa: E402
_app_pkg.routes = _routes_stub

from app import task_handlers_sources as ths  # noqa: E402
from app.task_handlers_sources import (  # noqa: E402
    _handle_ecfr,
    _handle_fda,
    _handle_federal_register,
    register_source_handlers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Re-install stubs evicted by the root conftest and clear capture state."""
    sys.modules["regengine_ingestion"] = _sources_pkg
    sys.modules["regengine_ingestion.sources"] = _sources_mod
    sys.modules["app.routes"] = _routes_stub

    # Make sure the names imported into ``ths`` at module-load time
    # still point at our spies (root conftest may have purged the
    # module and reloaded against fresh source).
    monkeypatch.setattr(ths, "FederalRegisterAdapter",
                        _FederalRegisterAdapter, raising=False)
    monkeypatch.setattr(ths, "ECFRAdapter", _ECFRAdapter, raising=False)
    monkeypatch.setattr(ths, "FDAAdapter", _FDAAdapter, raising=False)

    _FederalRegisterAdapter.instances.clear()
    _ECFRAdapter.instances.clear()
    _FDAAdapter.instances.clear()
    yield


@pytest.fixture
def captured_ingest(monkeypatch):
    """Capture ``_run_adapter_ingest`` calls without actually running anything."""
    calls: list[dict] = []

    async def _capturing(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(ths, "_run_adapter_ingest", _capturing)
    return calls


# ---------------------------------------------------------------------------
# _handle_federal_register
# ---------------------------------------------------------------------------


class TestHandleFederalRegister:
    def test_constructs_adapter_with_user_agent(self, captured_ingest):
        _handle_federal_register(
            vertical="food_safety",
            tenant_id="t-42",
            job_id="j-1",
        )
        assert len(_FederalRegisterAdapter.instances) == 1
        assert _FederalRegisterAdapter.instances[0].kwargs == {
            "user_agent": "RegEngine/1.0",
        }

    def test_forwards_required_kwargs_to_ingest(self, captured_ingest):
        _handle_federal_register(
            vertical="food_safety",
            tenant_id="t-42",
            job_id="j-1",
        )
        assert len(captured_ingest) == 1
        call = captured_ingest[0]
        assert call["vertical"] == "food_safety"
        assert call["tenant_id"] == "t-42"
        assert call["job_id"] == "j-1"
        assert call["source_system"] == "federal_register_api"
        # Optional kwargs default to None / pass-through
        assert call["max_documents"] is None
        assert call["date_from"] is None
        assert call["agencies"] is None
        # Adapter was forwarded
        assert isinstance(call["adapter"], _FederalRegisterAdapter)

    def test_optional_kwargs_pass_through(self, captured_ingest):
        _handle_federal_register(
            vertical="food_safety",
            tenant_id="t-42",
            job_id="j-1",
            max_documents=50,
            date_from="2026-01-01",
            agencies=["FDA", "USDA"],
        )
        call = captured_ingest[0]
        assert call["max_documents"] == 50
        assert call["date_from"] == "2026-01-01"
        assert call["agencies"] == ["FDA", "USDA"]

    def test_unknown_kwargs_absorbed_by_sink(self, captured_ingest):
        # The ``**_: Any`` sink must absorb forward-compatible payload
        # fields without raising — this is what lets the task queue
        # roll out new payload schemas without bricking in-flight workers.
        _handle_federal_register(
            vertical="v",
            tenant_id="t",
            job_id="j",
            future_field="ignored",
            another_extra=42,
        )
        assert len(captured_ingest) == 1
        # Only the documented kwargs are forwarded — unknowns dropped.
        assert "future_field" not in captured_ingest[0]


# ---------------------------------------------------------------------------
# _handle_ecfr
# ---------------------------------------------------------------------------


class TestHandleECFR:
    def test_constructs_ecfr_adapter(self, captured_ingest):
        _handle_ecfr(vertical="v", tenant_id="t", job_id="j")
        assert len(_ECFRAdapter.instances) == 1
        assert _ECFRAdapter.instances[0].kwargs == {"user_agent": "RegEngine/1.0"}

    def test_source_system_is_ecfr_api(self, captured_ingest):
        _handle_ecfr(vertical="v", tenant_id="t", job_id="j")
        assert captured_ingest[0]["source_system"] == "ecfr_api"

    def test_cfr_title_and_part_pass_through(self, captured_ingest):
        _handle_ecfr(
            vertical="v",
            tenant_id="t",
            job_id="j",
            cfr_title=21,
            cfr_part="1.110",
        )
        call = captured_ingest[0]
        assert call["cfr_title"] == 21
        assert call["cfr_part"] == "1.110"

    def test_optional_args_default_to_none(self, captured_ingest):
        _handle_ecfr(vertical="v", tenant_id="t", job_id="j")
        call = captured_ingest[0]
        assert call["cfr_title"] is None
        assert call["cfr_part"] is None

    def test_unknown_kwargs_absorbed(self, captured_ingest):
        _handle_ecfr(vertical="v", tenant_id="t", job_id="j",
                     future_thing="ok")
        assert "future_thing" not in captured_ingest[0]


# ---------------------------------------------------------------------------
# _handle_fda
# ---------------------------------------------------------------------------


class TestHandleFDA:
    def test_constructs_fda_adapter_with_no_api_key(self, captured_ingest):
        _handle_fda(vertical="v", tenant_id="t", job_id="j")
        assert len(_FDAAdapter.instances) == 1
        # FDA adapter is constructed unauthenticated by default; rate
        # limits are stricter but the module-level constant is None,
        # not an env-derived secret.
        assert _FDAAdapter.instances[0].kwargs == {
            "api_key": None,
            "user_agent": "RegEngine/1.0",
        }

    def test_source_system_is_openfda_api(self, captured_ingest):
        _handle_fda(vertical="v", tenant_id="t", job_id="j")
        assert captured_ingest[0]["source_system"] == "openfda_api"

    def test_max_documents_pass_through(self, captured_ingest):
        _handle_fda(vertical="v", tenant_id="t", job_id="j",
                    max_documents=200)
        assert captured_ingest[0]["max_documents"] == 200

    def test_max_documents_defaults_to_none(self, captured_ingest):
        _handle_fda(vertical="v", tenant_id="t", job_id="j")
        assert captured_ingest[0]["max_documents"] is None

    def test_unknown_kwargs_absorbed(self, captured_ingest):
        _handle_fda(vertical="v", tenant_id="t", job_id="j",
                    future_field="x")
        assert "future_field" not in captured_ingest[0]


# ---------------------------------------------------------------------------
# register_source_handlers
# ---------------------------------------------------------------------------


class TestRegisterSourceHandlers:
    def test_registers_three_task_types(self, monkeypatch):
        captured: list[tuple[str, Any]] = []

        def _fake_register(task_type, handler):
            captured.append((task_type, handler))

        monkeypatch.setattr(ths, "register_task_handler", _fake_register)

        register_source_handlers()

        assert len(captured) == 3
        registered = dict(captured)
        assert registered["federal_register_ingest"] is _handle_federal_register
        assert registered["ecfr_ingest"] is _handle_ecfr
        assert registered["fda_ingest"] is _handle_fda

    def test_registration_order_is_stable(self, monkeypatch):
        # Stable order matters for any task-queue introspection that
        # relies on registration sequence (admin dashboards etc.).
        order: list[str] = []
        monkeypatch.setattr(
            ths, "register_task_handler",
            lambda t, h: order.append(t)
        )
        register_source_handlers()
        assert order == ["federal_register_ingest", "ecfr_ingest", "fda_ingest"]
