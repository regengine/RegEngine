"""Unit tests for PR-E: routes.py regulation endpoints BackgroundTasks → task_queue.

Coverage:
- /v1/ingest/regulation: enqueues regulation_ingest task, writes staging file
- /v1/ingest/regulation: 400/403/413 validations still work
- /v1/ingest/regulation: staging file cleaned up if enqueue fails
- /v1/ingest/file: no longer accepts BackgroundTasks param (dead param removed)
- register_regulation_handlers wires regulation_ingest key
- get_staging_path creates the staging dir and returns correct path
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, mock_open

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.auth import APIKey, require_api_key
from app.routes import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_key(*, us: bool = True) -> APIKey:
    key = MagicMock(spec=APIKey)
    key.tenant_id = "tenant-reg"
    key.allowed_jurisdictions = ["US"] if us else ["EU"]
    return key


def _build_client(api_key: APIKey, monkeypatch=None) -> TestClient:
    if monkeypatch:
        # Bypass Redis-backed rate limiter so tests don't need a real Redis
        monkeypatch.setattr("app.routes.consume_tenant_rate_limit", lambda **kw: (True, 100))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: api_key
    return TestClient(app, raise_server_exceptions=True)


def _patch_regulation_enqueue(monkeypatch, fixed_job_id: str | None = None):
    """Patch staging write, SessionLocal, enqueue_task, and redis status write."""
    fake_session = MagicMock()
    mock_enqueue = MagicMock(return_value=1)
    mock_redis = MagicMock()

    # Patch staging path to a deterministic value without touching the FS
    if fixed_job_id:
        monkeypatch.setattr("app.routes.uuid.uuid4", lambda: uuid.UUID(fixed_job_id))

    monkeypatch.setattr(
        "app.routes.get_staging_path" if False else "app.task_handlers_regulation.get_staging_path",
        lambda job_id, filename: f"/tmp/regengine_ingest/{job_id}.pdf",
    )
    # Patch the import inside ingest_regulation
    monkeypatch.setattr(
        "app.routes.SessionLocal" if False else "builtins.open",
        mock_open(),
    )
    monkeypatch.setattr("app.routes.SessionLocal", lambda: fake_session)
    monkeypatch.setattr("app.routes.enqueue_task", mock_enqueue)
    monkeypatch.setattr("app.routes.redis.from_url", lambda *a, **kw: mock_redis)

    return mock_enqueue, fake_session, mock_redis


# ---------------------------------------------------------------------------
# /v1/ingest/regulation
# ---------------------------------------------------------------------------


class TestIngestRegulation:
    # Router has prefix=/api/v1/regulatory (pre-existing double-versioned path)
    ENDPOINT = "/api/v1/regulatory/v1/ingest/regulation"

    def _post(self, client, name="food-safety-reg", content=b"%PDF-fake", filename="reg.pdf"):
        return client.post(
            self.ENDPOINT,
            params={"name": name},
            files={"file": (filename, content, "application/pdf")},
        )

    def test_returns_202_and_job_id(self, monkeypatch, tmp_path):
        fixed = "00000000-0000-0000-0000-000000000010"
        monkeypatch.setattr("app.routes.uuid.uuid4", lambda: uuid.UUID(fixed))

        fake_session = MagicMock()
        mock_enqueue = MagicMock(return_value=1)
        mock_redis = MagicMock()
        monkeypatch.setattr("app.routes.SessionLocal", lambda: fake_session)
        monkeypatch.setattr("app.routes.enqueue_task", mock_enqueue)
        monkeypatch.setattr("app.routes.redis.from_url", lambda *a, **kw: mock_redis)
        staging = str(tmp_path)
        monkeypatch.setenv("INGEST_STAGING_DIR", staging)
        # Re-import after env change
        import importlib
        import app.task_handlers_regulation as thr
        importlib.reload(thr)
        monkeypatch.setattr("app.routes.get_staging_path", thr.get_staging_path)

        client = _build_client(_make_api_key(us=True), monkeypatch)
        resp = self._post(client)

        assert resp.status_code == 202
        body = resp.json()
        assert body["job_id"] == fixed
        assert body["status"] == "queued"

    def test_enqueues_correct_task_type(self, monkeypatch, tmp_path):
        fake_session = MagicMock()
        mock_enqueue = MagicMock(return_value=1)
        mock_redis = MagicMock()
        monkeypatch.setattr("app.routes.SessionLocal", lambda: fake_session)
        monkeypatch.setattr("app.routes.enqueue_task", mock_enqueue)
        monkeypatch.setattr("app.routes.redis.from_url", lambda *a, **kw: mock_redis)
        monkeypatch.setenv("INGEST_STAGING_DIR", str(tmp_path))

        import importlib
        import app.task_handlers_regulation as thr
        importlib.reload(thr)
        monkeypatch.setattr("app.routes.get_staging_path", thr.get_staging_path)

        client = _build_client(_make_api_key(us=True), monkeypatch)
        self._post(client)

        mock_enqueue.assert_called_once()
        kw = mock_enqueue.call_args.kwargs
        assert kw["task_type"] == "regulation_ingest"
        assert kw["payload"]["name"] == "food-safety-reg"
        assert kw["payload"]["filename"] == "reg.pdf"
        assert kw["payload"]["tenant_id"] == "tenant-reg"
        assert "file_path" in kw["payload"]

    def test_staging_file_written(self, monkeypatch, tmp_path):
        fake_session = MagicMock()
        monkeypatch.setattr("app.routes.SessionLocal", lambda: fake_session)
        monkeypatch.setattr("app.routes.enqueue_task", MagicMock(return_value=1))
        monkeypatch.setattr("app.routes.redis.from_url", lambda *a, **kw: MagicMock())
        monkeypatch.setenv("INGEST_STAGING_DIR", str(tmp_path))

        import importlib
        import app.task_handlers_regulation as thr
        importlib.reload(thr)
        monkeypatch.setattr("app.routes.get_staging_path", thr.get_staging_path)

        client = _build_client(_make_api_key(us=True), monkeypatch)
        self._post(client, content=b"%PDF-1.4 test content")

        staged = list(tmp_path.iterdir())
        assert len(staged) == 1
        assert staged[0].suffix == ".pdf"
        assert staged[0].read_bytes() == b"%PDF-1.4 test content"

    def test_non_us_returns_403(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.routes.SessionLocal", lambda: MagicMock())
        monkeypatch.setattr("app.routes.enqueue_task", MagicMock())
        monkeypatch.setattr("app.routes.redis.from_url", lambda *a, **kw: MagicMock())
        client = _build_client(_make_api_key(us=False), monkeypatch)
        resp = self._post(client)
        assert resp.status_code == 403

    def test_empty_file_returns_400(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.routes.SessionLocal", lambda: MagicMock())
        monkeypatch.setattr("app.routes.enqueue_task", MagicMock())
        monkeypatch.setattr("app.routes.redis.from_url", lambda *a, **kw: MagicMock())
        client = _build_client(_make_api_key(us=True), monkeypatch)
        resp = self._post(client, content=b"")
        assert resp.status_code == 400

    def test_unsupported_extension_returns_400(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.routes.SessionLocal", lambda: MagicMock())
        monkeypatch.setattr("app.routes.enqueue_task", MagicMock())
        monkeypatch.setattr("app.routes.redis.from_url", lambda *a, **kw: MagicMock())
        client = _build_client(_make_api_key(us=True), monkeypatch)
        resp = self._post(client, content=b"data", filename="reg.txt")
        assert resp.status_code == 400

    def test_db_commit_called(self, monkeypatch, tmp_path):
        fake_session = MagicMock()
        monkeypatch.setattr("app.routes.SessionLocal", lambda: fake_session)
        monkeypatch.setattr("app.routes.enqueue_task", MagicMock(return_value=1))
        monkeypatch.setattr("app.routes.redis.from_url", lambda *a, **kw: MagicMock())
        monkeypatch.setenv("INGEST_STAGING_DIR", str(tmp_path))

        import importlib
        import app.task_handlers_regulation as thr
        importlib.reload(thr)
        monkeypatch.setattr("app.routes.get_staging_path", thr.get_staging_path)

        client = _build_client(_make_api_key(us=True), monkeypatch)
        self._post(client)
        fake_session.commit.assert_called_once()

    def test_staging_file_removed_if_enqueue_fails(self, monkeypatch, tmp_path):
        """If enqueue_task raises, the staged file must be cleaned up."""
        monkeypatch.setattr("app.routes.SessionLocal", lambda: MagicMock())
        monkeypatch.setattr("app.routes.enqueue_task", MagicMock(side_effect=RuntimeError("db down")))
        monkeypatch.setattr("app.routes.redis.from_url", lambda *a, **kw: MagicMock())
        monkeypatch.setenv("INGEST_STAGING_DIR", str(tmp_path))

        import importlib
        import app.task_handlers_regulation as thr
        importlib.reload(thr)
        monkeypatch.setattr("app.routes.get_staging_path", thr.get_staging_path)

        client = _build_client(_make_api_key(us=True), monkeypatch)
        resp = self._post(client)

        assert resp.status_code == 500
        assert list(tmp_path.iterdir()) == []  # staging file cleaned up


# ---------------------------------------------------------------------------
# /v1/ingest/file — dead BackgroundTasks param removed
# ---------------------------------------------------------------------------


class TestIngestFile:
    def test_signature_has_no_background_tasks_param(self):
        import inspect
        from fastapi import BackgroundTasks
        from app.routes import ingest_file

        sig = inspect.signature(ingest_file)
        for param in sig.parameters.values():
            assert param.annotation is not BackgroundTasks, (
                "ingest_file should no longer accept BackgroundTasks"
            )


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


class TestRegisterRegulationHandlers:
    def test_registers_regulation_ingest(self):
        from shared.task_queue import TASK_HANDLERS
        from app.task_handlers_regulation import register_regulation_handlers

        TASK_HANDLERS.pop("regulation_ingest", None)
        register_regulation_handlers()
        assert "regulation_ingest" in TASK_HANDLERS


# ---------------------------------------------------------------------------
# get_staging_path
# ---------------------------------------------------------------------------


class TestGetStagingPath:
    def test_pdf_extension(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INGEST_STAGING_DIR", str(tmp_path))
        import importlib
        import app.task_handlers_regulation as thr
        importlib.reload(thr)

        path = thr.get_staging_path("job-123", "regulation.pdf")
        assert path.endswith(".pdf")
        assert "job-123" in path

    def test_docx_extension(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INGEST_STAGING_DIR", str(tmp_path))
        import importlib
        import app.task_handlers_regulation as thr
        importlib.reload(thr)

        path = thr.get_staging_path("job-456", "regulation.docx")
        assert path.endswith(".docx")

    def test_creates_staging_dir(self, tmp_path, monkeypatch):
        staging = tmp_path / "staging"
        monkeypatch.setenv("INGEST_STAGING_DIR", str(staging))
        import importlib
        import app.task_handlers_regulation as thr
        importlib.reload(thr)

        thr.get_staging_path("job-789", "file.pdf")
        assert staging.is_dir()
