"""Regression tests for sandbox share endpoint error-handling paths.

Context: services/ingestion/app/sandbox/router.py previously used
`logging.getLogger("sandbox")` but called `logger.error("key", error=str(e))`
with kwargs that the stdlib Logger rejects. That meant every DB failure in
the /share POST or GET path raised TypeError from inside the except block,
masking the intended 503 with a 500.

These tests force the DB path to raise and assert we actually return 503.
Filed under #1342 test-coverage sweep / PR #1562.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import shared.database as shared_db
from app.sandbox.router import router as sandbox_router


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(sandbox_router)
    return TestClient(app)


@pytest.fixture()
def exploding_db(monkeypatch: pytest.MonkeyPatch):
    """Replace shared.database.get_db with a contextmanager that raises."""

    @contextmanager
    def _boom():
        raise RuntimeError("db is down")
        yield  # pragma: no cover

    monkeypatch.setattr(shared_db, "get_db", _boom)
    return _boom


def _share_payload() -> dict:
    return {
        "csv": "cte_type,traceability_lot_code\nshipping,TLC-1\n",
        "result": {
            "total_events": 1,
            "compliant_events": 1,
            "non_compliant_events": 0,
            "total_kde_errors": 0,
            "total_rule_failures": 0,
            "submission_blocked": False,
            "blocking_reasons": [],
            "events": [],
        },
    }


def test_share_post_returns_503_when_db_fails(client: TestClient, exploding_db) -> None:
    resp = client.post("/api/v1/sandbox/share", json=_share_payload())
    assert resp.status_code == 503
    assert "temporarily unavailable" in resp.json()["detail"].lower()


def test_share_get_returns_503_when_db_fails(client: TestClient, exploding_db) -> None:
    resp = client.get("/api/v1/sandbox/share/abc123")
    assert resp.status_code == 503
    assert "temporarily unavailable" in resp.json()["detail"].lower()
