"""Regression tests for the audit finding on disagreeing upload-size caps
and orphaned staged files in ``app.routes_ingest``.

Covers:
- all generic ingest paths (file upload, URL fetch, post-buffer check)
  share one cap instead of disagreeing silently;
- the regulation staging path removes its staged file when staging fails
  with ``OSError``, not only on ``HTTPException``.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import app.routes_ingest as routes_ingest
import app.task_handlers_regulation as thr
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.auth import APIKey, require_api_key

ENDPOINT = "/api/v1/regulatory/v1/ingest/regulation"


def _make_api_key() -> APIKey:
    key = MagicMock(spec=APIKey)
    key.tenant_id = "tenant-reg"
    key.allowed_jurisdictions = ["US"]
    return key


def _build_client(api_key: APIKey, monkeypatch) -> TestClient:
    monkeypatch.setattr(routes_ingest, "consume_tenant_rate_limit", lambda **kw: (True, 100))
    app = FastAPI()
    app.include_router(routes_ingest.router)
    app.dependency_overrides[require_api_key] = lambda: api_key
    return TestClient(app, raise_server_exceptions=True)


def _use_tmp_staging(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("INGEST_STAGING_DIR", str(tmp_path))
    importlib.reload(thr)
    monkeypatch.setattr(routes_ingest, "get_staging_path", thr.get_staging_path)


def test_generic_ingest_caps_agree():
    """URL fetch streaming cap must equal the post-buffer enforcement cap."""
    assert routes_ingest.MAX_FILE_SIZE == routes_ingest.MAX_PAYLOAD_BYTES


def test_regulation_cap_documents_larger_tier():
    """Regulation filings stage large PDFs, so their cap stays above generic."""
    assert routes_ingest.MAX_REGULATION_FILE_SIZE_BYTES > routes_ingest.MAX_PAYLOAD_BYTES


def test_staging_file_removed_on_oserror(monkeypatch, tmp_path):
    """An OSError while staging must not leave a partial file behind."""
    monkeypatch.setattr(routes_ingest, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr(routes_ingest, "enqueue_task", MagicMock())
    monkeypatch.setattr(routes_ingest.redis, "from_url", lambda *a, **kw: MagicMock())
    _use_tmp_staging(monkeypatch, tmp_path)

    async def _boom(file, destination, **kwargs):
        Path(str(destination)).write_bytes(b"%PDF-partial")
        raise OSError("disk boom")

    monkeypatch.setattr(routes_ingest, "stream_upload_to_file_with_limit", _boom)

    client = _build_client(_make_api_key(), monkeypatch)
    resp = client.post(
        ENDPOINT,
        params={"name": "food-safety-reg"},
        files={"file": ("reg.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert resp.status_code == 500
    assert list(tmp_path.iterdir()) == []
