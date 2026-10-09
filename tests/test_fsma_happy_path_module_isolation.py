"""Guardrail: loading the FSMA happy-path app must not poison shared modules.

The ``test_client`` fixture in ``tests/test_fsma_happy_path_e2e.py`` used to
run ``del sys.modules["main"]`` (and ``del sys.modules["services.ingestion.main"]``)
to force a re-import of the ingestion app. Those shared names are also used by
other services' tests (for example
``tests/integration/test_nlp_to_compliance_handoff.py`` imports its own
``main``), so whichever module ran next silently picked up the wrong service's
app depending on collection order. The fixture now loads the ingestion
``main.py`` under a unique module name; these tests pin that behavior.
"""

from __future__ import annotations

import sys
import types

import pytest

from tests.test_fsma_happy_path_e2e import (
    _INGESTION_MAIN_MODULE_NAME,
    _load_ingestion_app,
)


def test_app_module_name_is_unique() -> None:
    """The loader must not reuse a module name owned by other test modules."""
    assert _INGESTION_MAIN_MODULE_NAME not in ("main", "services.ingestion.main")


def test_load_preserves_shared_sys_modules_entries(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Entries for other services' ``main`` and ``app`` must survive the load."""
    import tests.test_fsma_happy_path_e2e as e2e_module

    # Stand-in for services/ingestion/main.py so the test exercises the real
    # loader without booting the service (no DATABASE_URL or deps needed).
    stub_main = tmp_path / "main.py"
    stub_main.write_text("app = object()\n", encoding="utf-8")
    monkeypatch.setattr(e2e_module, "_INGESTION_DIR", tmp_path)

    # Simulate other test modules' already-imported shared entries.
    sentinel_main = types.ModuleType("main")
    sentinel_main.app = object()
    sentinel_dotted = types.ModuleType("services.ingestion.main")
    sibling_app = types.ModuleType("app")
    sibling_app.MARKER = "sibling-service"
    monkeypatch.setitem(sys.modules, "main", sentinel_main)
    monkeypatch.setitem(sys.modules, "services.ingestion.main", sentinel_dotted)
    monkeypatch.setitem(sys.modules, "app", sibling_app)

    app = _load_ingestion_app()

    try:
        assert sys.modules["main"] is sentinel_main
        assert sys.modules["services.ingestion.main"] is sentinel_dotted
        assert sys.modules["app"] is sibling_app
        assert app is sys.modules[_INGESTION_MAIN_MODULE_NAME].app
    finally:
        sys.modules.pop(_INGESTION_MAIN_MODULE_NAME, None)
