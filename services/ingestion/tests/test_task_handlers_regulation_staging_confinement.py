"""Staging-path confinement tests for ``app.task_handlers_regulation``.

The ``regulation_ingest`` queue payload carries a ``file_path`` that the
handler opens and later deletes. That path must resolve inside
``INGEST_STAGING_DIR`` (after resolving ``..`` segments and symlinks):
an outside path must be rejected before any open or delete, and the
outside file must be left untouched.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


class _FakeRegulationLoader:
    captured: list[dict] = []

    def __init__(self, *, uri, user, password):
        pass

    async def load(self, tmp_path, fmt, name):
        _FakeRegulationLoader.captured.append({"tmp_path": tmp_path, "format": fmt, "name": name})
        return 7

    def close(self):
        pass


_loader_mod = ModuleType("app.regulation_loader")
_loader_mod.RegulationLoader = _FakeRegulationLoader
_loader_mod.__file__ = str(service_dir / "app" / "regulation_loader.py")
_REAL_APP_REGULATION_LOADER = sys.modules.get("app.regulation_loader")
sys.modules["app.regulation_loader"] = _loader_mod

import app as _app_pkg  # noqa: E402

_REAL_APP_REGULATION_LOADER_ATTR = getattr(_app_pkg, "regulation_loader", None)
_app_pkg.regulation_loader = _loader_mod


@pytest.fixture(scope="module", autouse=True)
def _restore_modules_on_module_teardown():
    yield
    if _REAL_APP_REGULATION_LOADER is not None:
        sys.modules["app.regulation_loader"] = _REAL_APP_REGULATION_LOADER
    else:
        sys.modules.pop("app.regulation_loader", None)
    if _REAL_APP_REGULATION_LOADER_ATTR is not None:
        _app_pkg.regulation_loader = _REAL_APP_REGULATION_LOADER_ATTR
    elif hasattr(_app_pkg, "regulation_loader"):
        delattr(_app_pkg, "regulation_loader")


from app import task_handlers_regulation as thr  # noqa: E402
from app.task_handlers_regulation import (  # noqa: E402
    _process_regulation_from_file,
    _remove_staging_file_quietly,
    _resolve_staging_path,
    get_staging_path,
)


class _FakeRedis:
    def __init__(self):
        self.calls: list[tuple[str, int, str]] = []

    def setex(self, key, ttl, value):
        self.calls.append((key, ttl, value))


@pytest.fixture(autouse=True)
def _reset_fakes(monkeypatch):
    sys.modules["app.regulation_loader"] = _loader_mod
    import app as _app_pkg2

    _app_pkg2.regulation_loader = _loader_mod
    _FakeRegulationLoader.captured.clear()

    fake = _FakeRedis()
    monkeypatch.setattr(thr.redis, "from_url", lambda url: fake)

    settings = SimpleNamespace(
        redis_url="redis://fake:6379/0",
        neo4j_uri="bolt://neo4j:7687",
        neo4j_user="user",
        neo4j_password="pw",
    )
    config_mod = ModuleType("app.config")
    config_mod.get_settings = lambda: settings
    monkeypatch.setitem(sys.modules, "app.config", config_mod)
    return fake


@pytest.fixture
def staging(tmp_path, monkeypatch):
    """A fresh staging dir the handler is confined to."""
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    monkeypatch.setattr(thr, "INGEST_STAGING_DIR", str(staging_dir))
    return staging_dir


def _statuses(fake):
    return [c for c in fake.calls if c[0].startswith("ingest:status:")]


def _run(**kwargs):
    return asyncio.run(_process_regulation_from_file(**kwargs))


class TestResolveStagingPath:
    def test_inside_path_resolves(self, staging):
        target = staging / "job-1.pdf"
        target.write_bytes(b"%PDF-1.4 x")
        assert _resolve_staging_path(str(target)) == str(target)

    def test_absolute_outside_path_raises(self, staging, tmp_path):
        with pytest.raises(ValueError):
            _resolve_staging_path(str(tmp_path / "victim.pdf"))

    def test_dotdot_traversal_raises(self, staging, tmp_path):
        victim = tmp_path / "victim.pdf"
        victim.write_bytes(b"victim")
        with pytest.raises(ValueError):
            _resolve_staging_path(str(staging / ".." / "victim.pdf"))

    def test_symlink_inside_pointing_outside_raises(self, staging, tmp_path):
        victim = tmp_path / "victim.pdf"
        victim.write_bytes(b"victim")
        link = staging / "link.pdf"
        link.symlink_to(victim)
        with pytest.raises(ValueError):
            _resolve_staging_path(str(link))

    def test_empty_path_raises(self, staging):
        with pytest.raises(ValueError):
            _resolve_staging_path("")

    def test_get_staging_path_round_trips(self, staging):
        staged = get_staging_path("job-9", "regulation.pdf")
        assert _resolve_staging_path(staged) == staged


class TestHandlerRejectsOutsidePaths:
    def test_absolute_outside_path_not_opened_or_deleted(self, _reset_fakes, staging, tmp_path):
        fake = _reset_fakes
        victim = tmp_path / "victim.pdf"
        victim.write_bytes(b"victim bytes")

        _run(
            job_id="j-out",
            name="R",
            filename="r.pdf",
            tenant_id="t",
            file_path=str(victim),
            webhook=None,
        )

        assert victim.exists()
        assert victim.read_bytes() == b"victim bytes"
        assert _FakeRegulationLoader.captured == []
        assert _statuses(fake)[-1] == ("ingest:status:j-out", 7200, "failed: invalid staging path")

    def test_dotdot_traversal_not_opened_or_deleted(self, _reset_fakes, staging, tmp_path):
        fake = _reset_fakes
        victim = tmp_path / "victim.pdf"
        victim.write_bytes(b"victim bytes")

        _run(
            job_id="j-trav",
            name="R",
            filename="r.pdf",
            tenant_id="t",
            file_path=str(staging / ".." / "victim.pdf"),
            webhook=None,
        )

        assert victim.exists()
        assert _FakeRegulationLoader.captured == []
        assert _statuses(fake)[-1] == ("ingest:status:j-trav", 7200, "failed: invalid staging path")

    def test_symlink_escape_not_opened_or_deleted(self, _reset_fakes, staging, tmp_path):
        fake = _reset_fakes
        victim = tmp_path / "victim.pdf"
        victim.write_bytes(b"victim bytes")
        link = staging / "evil.pdf"
        link.symlink_to(victim)

        _run(
            job_id="j-link",
            name="R",
            filename="r.pdf",
            tenant_id="t",
            file_path=str(link),
            webhook=None,
        )

        assert victim.exists()
        assert victim.read_bytes() == b"victim bytes"
        assert link.is_symlink()
        assert _FakeRegulationLoader.captured == []
        assert _statuses(fake)[-1] == ("ingest:status:j-link", 7200, "failed: invalid staging path")


class TestHandlerAcceptsInsidePaths:
    def test_inside_path_processed_and_cleaned_up(self, _reset_fakes, staging):
        fake = _reset_fakes
        staged = staging / "job-ok.pdf"
        staged.write_bytes(b"%PDF-1.4 fake regulation payload")

        _run(
            job_id="j-ok",
            name="FDA FSMA 204",
            filename="rule.pdf",
            tenant_id="t",
            file_path=str(staged),
            webhook=None,
        )

        assert _statuses(fake)[-1] == ("ingest:status:j-ok", 7200, "completed")
        assert len(_FakeRegulationLoader.captured) == 1
        assert not staged.exists()


class TestRemoveStagingFileQuietly:
    def test_outside_path_never_deleted(self, staging, tmp_path):
        victim = tmp_path / "victim.pdf"
        victim.write_bytes(b"victim bytes")
        _remove_staging_file_quietly(str(victim))
        assert victim.exists()

    def test_symlink_escape_never_deleted(self, staging, tmp_path):
        victim = tmp_path / "victim.pdf"
        victim.write_bytes(b"victim bytes")
        link = staging / "evil.pdf"
        link.symlink_to(victim)
        _remove_staging_file_quietly(str(link))
        assert victim.exists()
        assert link.is_symlink()

    def test_inside_path_deleted(self, staging):
        staged = staging / "job-gone.pdf"
        staged.write_bytes(b"x")
        _remove_staging_file_quietly(str(staged))
        assert not staged.exists()

    def test_missing_inside_path_does_not_raise(self, staging):
        _remove_staging_file_quietly(str(staging / "does-not-exist.pdf"))
