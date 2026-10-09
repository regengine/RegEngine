"""Database-error export tests for ``app.epcis_export``.

A database failure must surface as HTTP 503, never as sample data with a
disclaimer. These tests drive the real ``_query_tenant_events`` helper
against a failing DB session: they fail on the old swallow-and-return-[]
behavior (which served sample evidence with HTTP 200) and pass on the
fixed code.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

pytest.importorskip("fastapi")

import app.epcis_export as epcis_export
from app.epcis_export import router as epcis_export_router
from app.webhook_compat import _verify_api_key, require_tenant_context
from shared.tenant_context import TenantContext


class _FailingSession:
    """Mimics a SQLAlchemy session whose query blows up."""

    def __init__(self) -> None:
        self.closed = False

    def execute(self, stmt: Any, params: Any | None = None) -> Any:
        raise RuntimeError("db down")

    def close(self) -> None:
        self.closed = True


class _EmptySession:
    """Mimics a healthy session for a tenant with no events."""

    def execute(self, stmt: Any, params: Any | None = None) -> Any:
        class _Result:
            @staticmethod
            def fetchall() -> list:
                return []

        return _Result()

    def close(self) -> None:
        pass


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(epcis_export_router)

    async def _tenant_ctx(request: Request) -> TenantContext:
        return TenantContext(
            tenant_id="tenant-x",
            principal_kind="test",
            principal_id="epcis-export-db-error-test",
        )

    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[require_tenant_context] = _tenant_ctx
    return TestClient(app, raise_server_exceptions=False)


class TestExportDbErrorReturns503:
    def test_epcis_returns_503_on_db_error(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: _FailingSession())
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": "tenant-x", "format": "epcis"},
        )
        assert response.status_code == 503
        # Must not masquerade as evidence: no sample document attached.
        assert "EPCISDocument" not in response.text

    def test_fda_returns_503_on_db_error(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: _FailingSession())
        response = client.post(
            "/api/v1/export/fda",
            json={"tenant_id": "tenant-x"},
        )
        assert response.status_code == 503
        assert "CTE_Type" not in response.text

    def test_unavailable_session_returns_503(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: None)
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": "tenant-x", "format": "epcis"},
        )
        assert response.status_code == 503

    def test_empty_result_still_serves_labeled_sample(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A genuine empty tenant (no rows, no error) keeps the sample
        # fallback so new tenants can preview the format.
        monkeypatch.setattr(epcis_export, "get_db_safe", lambda: _EmptySession())
        response = client.post(
            "/api/v1/export/epcis",
            json={"tenant_id": "tenant-x", "format": "epcis"},
        )
        assert response.status_code == 200
        assert response.json()["regengine:exportMetadata"]["dataSource"] == "sample"
