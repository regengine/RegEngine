"""Unit tests for ``app.task_handlers_regulation`` — issue #1342.

The handler pulls a staged regulation file off local disk, runs it
through the :class:`RegulationLoader`, and maintains a pair of Redis
keys — ``ingest:status:{job_id}`` and ``ingest:result:{job_id}`` — that
the status-polling endpoints read. These tests stub every external
dependency (``redis``, ``httpx``, the loader, ``get_settings``,
``register_task_handler``) so each branch is pinned deterministically:

* staging-file-missing short-circuits into a ``failed: staging file not
  found`` Redis value with no temp-file side-effect.
* happy path writes ``processing`` → ``completed`` + the result JSON,
  and optionally POSTs a webhook.
* exceptions during loading emit ``failed: <error>`` and try the webhook
  before the ``finally`` cleanup.
* the ``finally`` clause always removes the temp file *and* the staging
  file even when one of them is already gone.

This is a task-queue handler that runs post-SIGTERM of the request
process, so silent failure of any branch would leave the polling
endpoint stuck in ``processing`` forever — pin it hard.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))


class _FakeRegulationLoader:
    captured: list[dict] = []

    def __init__(self, *, uri, user, password):
        self.uri = uri
        self.user = user
        self.password = password
        self.closed = False

    async def load(self, tmp_path, fmt, name):
        _FakeRegulationLoader.captured.append({
            "tmp_path": tmp_path,
            "format": fmt,
            "name": name,
            "uri": self.uri,
        })
        # Count returned is checked by the caller — make it deterministic.
        return 42

    def close(self):
        self.closed = True


# Install a stub for the submodule imported *lazily* inside the handler
# body so the real module never needs to exist on disk. The root
# conftest evicts ``app.*`` modules without a ``__file__`` attribute
# pointing into the service dir, so the stub is fully (re-)installed in
# the ``_install_loader_stub`` fixture below — installing here too just
# lets ``from app import task_handlers_regulation`` succeed at module
# load time.
_loader_mod = ModuleType("app.regulation_loader")
_loader_mod.RegulationLoader = _FakeRegulationLoader
_loader_mod.__file__ = str(service_dir / "app" / "regulation_loader.py")
sys.modules["app.regulation_loader"] = _loader_mod

import app as _app_pkg  # noqa: E402
_app_pkg.regulation_loader = _loader_mod

from app import task_handlers_regulation as thr  # noqa: E402
from app.task_handlers_regulation import (  # noqa: E402
    INGEST_STAGING_DIR,
    _handle_regulation_ingest,
    _process_regulation_from_file,
    get_staging_path,
    register_regulation_handlers,
)


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Captures ``setex`` calls."""

    def __init__(self):
        self.calls: list[tuple[str, int, str]] = []

    def setex(self, key, ttl, value):
        self.calls.append((key, ttl, value))


class _FakeAsyncClient:
    """Async context-manager stand-in for ``httpx.AsyncClient``.

    ``post`` records the call. Set ``raise_on_post`` to an exception
    instance to simulate webhook delivery failures.
    """

    instances: list["_FakeAsyncClient"] = []

    def __init__(self, *, raise_on_post: BaseException | None = None):
        self.posts: list[tuple[str, dict]] = []
        self.raise_on_post = raise_on_post
        self.entered = False
        self.exited = False
        _FakeAsyncClient.instances.append(self)

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *exc):
        self.exited = True
        return False

    async def post(self, url, json=None):
        self.posts.append((url, json))
        if self.raise_on_post:
            raise self.raise_on_post


@pytest.fixture(autouse=True)
def _reset_fakes():
    # Re-install the loader stub on every test — pytest's root conftest
    # evicts ``app.regulation_loader`` between collection and run because
    # the stub's ``__file__`` is synthetic. Restoring it here keeps the
    # lazy ``from .regulation_loader`` inside the handler resolvable.
    sys.modules["app.regulation_loader"] = _loader_mod
    import app as _app_pkg
    _app_pkg.regulation_loader = _loader_mod

    _FakeRegulationLoader.captured.clear()
    _FakeAsyncClient.instances.clear()
    yield


@pytest.fixture
def fake_redis(monkeypatch):
    """Install a fake ``redis.from_url`` that returns a fresh _FakeRedis."""
    fake = _FakeRedis()

    def _from_url(url):
        fake._url = url
        return fake

    monkeypatch.setattr(thr.redis, "from_url", _from_url)
    return fake


@pytest.fixture
def fake_settings(monkeypatch):
    """Stub ``app.config.get_settings`` so the module's late import
    resolves to our deterministic Redis/Neo4j config."""
    settings = SimpleNamespace(
        redis_url="redis://fake:6379/0",
        neo4j_uri="bolt://neo4j:7687",
        neo4j_user="user",
        neo4j_password="pw",
    )

    config_mod = ModuleType("app.config")
    config_mod.get_settings = lambda: settings
    monkeypatch.setitem(sys.modules, "app.config", config_mod)
    return settings


@pytest.fixture
def fake_httpx(monkeypatch):
    """Stub the late-imported ``httpx`` module.

    Tests can override the AsyncClient factory by assigning a callable to
    the returned dict's ``factory`` key.
    """
    bag: dict[str, Any] = {"factory": lambda: _FakeAsyncClient()}

    httpx_mod = ModuleType("httpx")

    class _HTTPError(Exception):
        pass

    httpx_mod.HTTPError = _HTTPError

    def _AsyncClient(*args, **kwargs):  # signature-compatible
        return bag["factory"]()

    httpx_mod.AsyncClient = _AsyncClient
    monkeypatch.setitem(sys.modules, "httpx", httpx_mod)
    bag["module"] = httpx_mod
    return bag


@pytest.fixture
def staged_pdf(tmp_path):
    path = tmp_path / "abc-job.pdf"
    path.write_bytes(b"%PDF-1.4 fake regulation payload")
    return path


@pytest.fixture
def staged_docx(tmp_path):
    path = tmp_path / "abc-job.docx"
    path.write_bytes(b"docx bytes")
    return path


# ---------------------------------------------------------------------------
# get_staging_path
# ---------------------------------------------------------------------------


class TestGetStagingPath:
    def test_pdf_filename_yields_pdf_extension(self, tmp_path, monkeypatch):
        monkeypatch.setattr(thr, "INGEST_STAGING_DIR", str(tmp_path))
        result = get_staging_path("job-1", "regulation.pdf")
        assert result == str(tmp_path / "job-1.pdf")

    def test_docx_filename_yields_docx_extension(self, tmp_path, monkeypatch):
        monkeypatch.setattr(thr, "INGEST_STAGING_DIR", str(tmp_path))
        result = get_staging_path("job-2", "regulation.docx")
        assert result == str(tmp_path / "job-2.docx")

    def test_unknown_extension_falls_back_to_docx(self, tmp_path, monkeypatch):
        # Non-.pdf-suffixed names get the ``.docx`` extension as a safe
        # default — that matches the upload validator's accept list.
        monkeypatch.setattr(thr, "INGEST_STAGING_DIR", str(tmp_path))
        result = get_staging_path("job-3", "regulation.xyz")
        assert result.endswith("job-3.docx")

    def test_creates_staging_dir_if_missing(self, tmp_path, monkeypatch):
        target = tmp_path / "nested" / "regengine_ingest"
        assert not target.exists()
        monkeypatch.setattr(thr, "INGEST_STAGING_DIR", str(target))
        get_staging_path("job-1", "f.pdf")
        assert target.is_dir()

    def test_env_override_respected_at_import_time(self):
        # Constant defaults to /tmp/regengine_ingest; any env override
        # only takes effect if the module is re-imported. Guard the
        # default value so a rogue environment doesn't silently drift.
        assert INGEST_STAGING_DIR.endswith("regengine_ingest")


# ---------------------------------------------------------------------------
# _process_regulation_from_file — happy path
# ---------------------------------------------------------------------------


class TestProcessRegulationHappyPath:
    def _run(self, **kwargs):
        return asyncio.run(_process_regulation_from_file(**kwargs))

    def test_pdf_file_flow_writes_status_and_result(
        self, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        self._run(
            job_id="j1",
            name="FDA FSMA 204",
            filename="rule.pdf",
            tenant_id="tenant-42",
            file_path=str(staged_pdf),
            webhook=None,
        )

        # Redis writes: processing, completed, result
        keys = [c[0] for c in fake_redis.calls]
        assert keys == [
            "ingest:status:j1",
            "ingest:status:j1",
            "ingest:result:j1",
        ]
        # TTL 7200 (2 hrs) on every key so stale entries age out.
        assert all(c[1] == 7200 for c in fake_redis.calls)
        # Values for status flow
        assert fake_redis.calls[0][2] == "processing"
        assert fake_redis.calls[1][2] == "completed"
        # Result is JSON with sections + name + tenant_id
        result_body = json.loads(fake_redis.calls[2][2])
        assert result_body == {
            "sections": 42, "name": "FDA FSMA 204", "tenant_id": "tenant-42",
        }

    def test_loader_receives_settings_config(
        self, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        self._run(
            job_id="j1", name="R", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf), webhook=None,
        )
        assert len(_FakeRegulationLoader.captured) == 1
        call = _FakeRegulationLoader.captured[0]
        assert call["format"] == "pdf"
        assert call["name"] == "R"
        assert call["uri"] == "bolt://neo4j:7687"

    def test_docx_file_uses_docx_format(
        self, fake_redis, fake_settings, fake_httpx, staged_docx
    ):
        self._run(
            job_id="j2", name="Policy X", filename="policy.docx",
            tenant_id="t", file_path=str(staged_docx), webhook=None,
        )
        assert _FakeRegulationLoader.captured[0]["format"] == "docx"

    def test_tmp_file_is_removed_in_finally(
        self, fake_redis, fake_settings, fake_httpx, staged_pdf, monkeypatch
    ):
        removed_paths: list[str] = []
        real_remove = os.remove

        def _tracked_remove(path):
            removed_paths.append(path)
            real_remove(path)

        monkeypatch.setattr(thr.os, "remove", _tracked_remove)

        self._run(
            job_id="j", name="r", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf), webhook=None,
        )
        # Both the tempfile copy AND the staging file were removed.
        # Staging file last — the finally drops staging after tmp.
        assert str(staged_pdf) in removed_paths
        assert not staged_pdf.exists()

    def test_staging_file_already_gone_does_not_raise(
        self, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        # Simulate a concurrent cleanup by running the handler twice
        # against the same path — the second pass should swallow the
        # ``FileNotFoundError`` inside the ``except OSError: pass`` block.
        self._run(
            job_id="j", name="r", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf), webhook=None,
        )
        assert not staged_pdf.exists()

        # Re-stage a different job; but swap ``os.remove`` so the second
        # call on a non-existent path raises into our except block.
        self._run(
            job_id="j2", name="r2", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf),  # already gone
            webhook=None,
        )
        # Second run hits the staging-file-missing branch instead.
        # Status ends as "failed: staging file not found".
        assert fake_redis.calls[-1] == (
            "ingest:status:j2",
            7200,
            "failed: staging file not found",
        )


# ---------------------------------------------------------------------------
# Staging-file-missing branch
# ---------------------------------------------------------------------------


class TestStagingFileMissing:
    def test_missing_file_writes_failed_status_and_returns(
        self, fake_redis, fake_settings, fake_httpx, tmp_path
    ):
        missing = str(tmp_path / "does-not-exist.pdf")

        asyncio.run(_process_regulation_from_file(
            job_id="j-missing",
            name="X",
            filename="x.pdf",
            tenant_id="t",
            file_path=missing,
            webhook=None,
        ))

        # Only one Redis write — and it's the failure status — because
        # the function returns before the processing-status write.
        assert len(fake_redis.calls) == 1
        assert fake_redis.calls[0] == (
            "ingest:status:j-missing",
            7200,
            "failed: staging file not found",
        )
        # Loader was never invoked.
        assert _FakeRegulationLoader.captured == []


# ---------------------------------------------------------------------------
# Webhook integration
# ---------------------------------------------------------------------------


class TestWebhookOnSuccess:
    def test_completed_webhook_includes_sections(
        self, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        asyncio.run(_process_regulation_from_file(
            job_id="j", name="FSMA 204", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf),
            webhook="https://cb.example.com/hook",
        ))

        # Exactly one webhook POST was made with completed payload.
        assert len(_FakeAsyncClient.instances) == 1
        client = _FakeAsyncClient.instances[0]
        assert len(client.posts) == 1
        url, body = client.posts[0]
        assert url == "https://cb.example.com/hook"
        assert body == {
            "job_id": "j",
            "status": "completed",
            "regulation": "FSMA 204",
            "sections": 42,
        }

    def test_webhook_post_failure_swallowed_via_except(
        self, fake_redis, fake_settings, fake_httpx, staged_pdf, caplog
    ):
        import httpx

        fake_httpx["factory"] = lambda: _FakeAsyncClient(
            raise_on_post=httpx.HTTPError("boom")
        )

        # Must NOT raise — webhook failure is logged but not re-raised.
        asyncio.run(_process_regulation_from_file(
            job_id="j", name="r", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf),
            webhook="https://cb.example.com",
        ))

        # Core status keys still flowed to completion — webhook is a
        # side channel, not a gate.
        statuses = [c[2] for c in fake_redis.calls
                    if c[0] == "ingest:status:j"]
        assert "completed" in statuses

    def test_webhook_post_oserror_swallowed(
        self, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        fake_httpx["factory"] = lambda: _FakeAsyncClient(
            raise_on_post=OSError("connection refused")
        )

        asyncio.run(_process_regulation_from_file(
            job_id="j", name="r", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf),
            webhook="https://cb.example.com",
        ))

        # Completion status still written despite webhook OSError.
        assert any(c[2] == "completed" for c in fake_redis.calls)


# ---------------------------------------------------------------------------
# Loader failure branches
# ---------------------------------------------------------------------------


class TestLoaderFailure:
    def test_loader_oserror_produces_failed_status(
        self, monkeypatch, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        # Patch the loader class to raise during load().
        class _BadLoader:
            def __init__(self, **_):
                pass

            async def load(self, *args, **kwargs):
                raise OSError("disk gone")

            def close(self):
                pass

        monkeypatch.setattr(
            sys.modules["app.regulation_loader"], "RegulationLoader", _BadLoader
        )

        asyncio.run(_process_regulation_from_file(
            job_id="j-err", name="r", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf), webhook=None,
        ))

        # Status ends in ``failed: disk gone``.
        failure_status = [c for c in fake_redis.calls
                          if c[0] == "ingest:status:j-err"][-1]
        assert failure_status[2].startswith("failed: ")
        assert "disk gone" in failure_status[2]

    def test_loader_value_error_also_reported(
        self, monkeypatch, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        class _BadLoader:
            def __init__(self, **_):
                pass

            async def load(self, *args, **kwargs):
                raise ValueError("bad format")

            def close(self):
                pass

        monkeypatch.setattr(
            sys.modules["app.regulation_loader"], "RegulationLoader", _BadLoader
        )

        asyncio.run(_process_regulation_from_file(
            job_id="j-v", name="r", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf), webhook=None,
        ))
        failure = [c for c in fake_redis.calls
                   if c[0] == "ingest:status:j-v"][-1]
        assert "bad format" in failure[2]

    def test_loader_failure_posts_webhook_with_failed_status(
        self, monkeypatch, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        class _BadLoader:
            def __init__(self, **_):
                pass

            async def load(self, *args, **kwargs):
                raise ValueError("bad format")

            def close(self):
                pass

        monkeypatch.setattr(
            sys.modules["app.regulation_loader"], "RegulationLoader", _BadLoader
        )

        asyncio.run(_process_regulation_from_file(
            job_id="j", name="r", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf),
            webhook="https://cb.example.com",
        ))

        assert len(_FakeAsyncClient.instances) == 1
        url, body = _FakeAsyncClient.instances[0].posts[0]
        assert url == "https://cb.example.com"
        assert body["status"] == "failed"
        assert "bad format" in body["error"]

    def test_loader_failure_webhook_also_fails_is_swallowed(
        self, monkeypatch, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        class _BadLoader:
            def __init__(self, **_):
                pass

            async def load(self, *args, **kwargs):
                raise ValueError("bad")

            def close(self):
                pass

        monkeypatch.setattr(
            sys.modules["app.regulation_loader"], "RegulationLoader", _BadLoader
        )

        import httpx
        fake_httpx["factory"] = lambda: _FakeAsyncClient(
            raise_on_post=httpx.HTTPError("webhook down")
        )

        # Must not raise despite both loader AND webhook failing.
        asyncio.run(_process_regulation_from_file(
            job_id="j", name="r", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf),
            webhook="https://cb.example.com",
        ))

    def test_loader_failure_webhook_oserror_swallowed(
        self, monkeypatch, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        class _BadLoader:
            def __init__(self, **_):
                pass

            async def load(self, *args, **kwargs):
                raise ValueError("bad")

            def close(self):
                pass

        monkeypatch.setattr(
            sys.modules["app.regulation_loader"], "RegulationLoader", _BadLoader
        )

        fake_httpx["factory"] = lambda: _FakeAsyncClient(
            raise_on_post=OSError("connection refused")
        )

        asyncio.run(_process_regulation_from_file(
            job_id="j", name="r", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf),
            webhook="https://cb.example.com",
        ))


# ---------------------------------------------------------------------------
# finally cleanup — staging file already gone
# ---------------------------------------------------------------------------


class TestFinallyCleanup:
    def test_staging_cleanup_oserror_swallowed(
        self, fake_redis, fake_settings, fake_httpx, staged_pdf, monkeypatch
    ):
        real_remove = os.remove
        removed: list[str] = []

        def _fickle_remove(path):
            removed.append(path)
            if path == str(staged_pdf):
                # Simulate a concurrent race where the staging file was
                # already removed by another actor.
                raise OSError("already gone")
            real_remove(path)

        monkeypatch.setattr(thr.os, "remove", _fickle_remove)

        # Must NOT raise.
        asyncio.run(_process_regulation_from_file(
            job_id="j", name="r", filename="r.pdf",
            tenant_id="t", file_path=str(staged_pdf), webhook=None,
        ))

        # The handler attempted the staging cleanup despite the race.
        assert str(staged_pdf) in removed


# ---------------------------------------------------------------------------
# _handle_regulation_ingest (sync wrapper)
# ---------------------------------------------------------------------------


class TestHandleRegulationIngestSyncWrapper:
    def test_forwards_kwargs_to_async_processor(
        self, monkeypatch, fake_redis, fake_settings, fake_httpx, staged_pdf
    ):
        captured = {}

        async def _capturing_process(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(
            thr, "_process_regulation_from_file", _capturing_process
        )

        _handle_regulation_ingest(
            job_id="j1",
            name="FSMA 204",
            filename="r.pdf",
            tenant_id="t",
            file_path=str(staged_pdf),
            webhook="https://cb.example.com",
            extra_ignored_kwarg="should_not_crash",
        )

        assert captured == {
            "job_id": "j1",
            "name": "FSMA 204",
            "filename": "r.pdf",
            "tenant_id": "t",
            "file_path": str(staged_pdf),
            "webhook": "https://cb.example.com",
        }

    def test_webhook_defaults_to_none_when_omitted(self, monkeypatch):
        captured = {}

        async def _capturing_process(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(
            thr, "_process_regulation_from_file", _capturing_process
        )

        _handle_regulation_ingest(
            job_id="j",
            name="n",
            filename="f.pdf",
            tenant_id="t",
            file_path="/tmp/foo",
        )
        assert captured["webhook"] is None


# ---------------------------------------------------------------------------
# register_regulation_handlers
# ---------------------------------------------------------------------------


class TestRegisterRegulationHandlers:
    def test_registers_regulation_ingest_with_task_queue(self, monkeypatch):
        captured: list[tuple[str, Any]] = []

        def _fake_register(task_type, handler):
            captured.append((task_type, handler))

        monkeypatch.setattr(thr, "register_task_handler", _fake_register)

        register_regulation_handlers()

        assert captured == [("regulation_ingest", thr._handle_regulation_ingest)]
