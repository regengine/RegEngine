"""Guard: the live RLS suite fails closed instead of skipping when gated.

``test_rls_enforcement_live.py`` is the end-to-end proof that an unset
``app.tenant_id`` fails closed rather than returning zero rows. It skips
without ``DATABASE_URL``, which keeps local runs friendly but once let the
whole #2461 build-out merge without ever executing. Backend CI backstops this
with a skip-grep; this guard pins the in-test contract so the suite itself
fails (instead of skipping) whenever ``REGENGINE_REQUIRE_DB=1`` declares the
gate must run.

Every test here runs offline: no database is contacted. The live module is
loaded by file path because the repo-root conftest remaps ``sys.path`` per
service, so sibling test modules are not importable by bare name.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_LIVE_PATH = Path(__file__).with_name("test_rls_enforcement_live.py")


def _load_live():
    spec = importlib.util.spec_from_file_location("test_rls_enforcement_live", _LIVE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skip_helper_skips_without_require_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/probe")
    monkeypatch.delenv("REGENGINE_REQUIRE_DB", raising=False)
    live = _load_live()
    with pytest.raises(pytest.skip.Exception):
        live._skip_or_fail("probe reason")


def test_skip_helper_fails_with_require_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/probe")
    monkeypatch.setenv("REGENGINE_REQUIRE_DB", "1")
    live = _load_live()
    with pytest.raises(pytest.fail.Exception):
        live._skip_or_fail("probe reason")


def test_missing_database_url_fails_load_under_require_db(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_REQUIRE_DB", "1")
    with pytest.raises(pytest.fail.Exception):
        _load_live()


def test_missing_database_url_still_skips_locally(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REGENGINE_REQUIRE_DB", raising=False)
    live = _load_live()
    assert live.DATABASE_URL is None
