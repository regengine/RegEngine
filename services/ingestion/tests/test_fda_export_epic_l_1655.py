"""EPIC-L (#1655) integration tests — FDA CSV export hardening.

These tests exercise the route-level behavior that EPIC-L added or
tightened:

* ``/export/all`` now requires BOTH ``start_date`` and ``end_date`` and
  caps the window at :data:`shared.fda_export.MAX_EXPORT_WINDOW_DAYS`
  (90 days). End-date-only exports are no longer permitted — they
  allowed a full-tenant dump through a single query param.

* ``/export/all`` returns HTTP 404 instead of HTTP 200 + an empty CSV
  when no records match the window. An empty CSV visually reads as
  "no compliance activity" and is easy to misinterpret — the hard
  failure forces the caller to widen the window or pick a different
  tenant explicitly.

The existing ``test_fda_export_router.py`` fixture stubs the
persistence + auth layers, which we reuse.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import shared.cte_persistence as shared_cte_persistence
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.fda_export_router import router as fda_router


class _Result:
    def __init__(self, rows: Optional[list] = None):
        self._rows = rows or []

    def fetchone(self):
        return None

    def fetchall(self):
        return self._rows


class _FakeSession:
    def execute(self, *_args, **_kwargs):
        return _Result()

    def commit(self) -> None:  # pragma: no cover — trivial
        return None

    def close(self) -> None:  # pragma: no cover — trivial
        return None


class _EmptyPersistence:
    """Persistence stub that returns zero events for any query.

    The ``/export/all`` handler calls ``query_all_events`` first and
    then batch-fetches by distinct TLC. Returning an empty list from
    the initial query is enough to drive the 404 path because the
    deduped set is empty regardless.
    """

    def __init__(self, _session):
        pass

    def query_all_events(self, **_kwargs):
        return ([], 0)

    def query_events_by_tlc(self, **_kwargs):
        return []

    def verify_chain(self, **_kwargs):  # pragma: no cover — unreached
        class _Dummy:
            valid = True
            chain_length = 0
            errors: list[str] = []
            checked_at = "1970-01-01T00:00:00+00:00"

        return _Dummy()

    def log_export(self, **_kwargs):  # pragma: no cover — unreached
        return "export-log-id"


def _install_fake_dependencies(monkeypatch, persistence_cls):
    fake_db = types.ModuleType("shared.database")
    fake_db.SessionLocal = lambda: _FakeSession()
    monkeypatch.setitem(sys.modules, "shared.database", fake_db)
    monkeypatch.setattr(shared_cte_persistence, "CTEPersistence", persistence_cls)


@pytest.fixture()
def client(monkeypatch):
    from app.subscription_gate import require_active_subscription

    app = FastAPI()
    app.include_router(fda_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        auth_mode="test",
    )
    app.dependency_overrides[require_active_subscription] = lambda: None
    _install_fake_dependencies(monkeypatch, persistence_cls=_EmptyPersistence)
    with TestClient(app) as c:
        yield c


TENANT = "00000000-0000-0000-0000-000000000111"


# ---------------------------------------------------------------------------
# Window validation on /export/all
# ---------------------------------------------------------------------------


def test_export_all_rejects_missing_start_date(client):
    r = client.get(
        "/api/v1/fda/export/all",
        params={"tenant_id": TENANT, "end_date": "2026-03-31"},
    )
    assert r.status_code == 400
    assert "start_date" in r.json()["detail"]


def test_export_all_rejects_missing_end_date(client):
    r = client.get(
        "/api/v1/fda/export/all",
        params={"tenant_id": TENANT, "start_date": "2026-03-01"},
    )
    assert r.status_code == 400
    assert "end_date" in r.json()["detail"]


def test_export_all_rejects_missing_both_dates(client):
    r = client.get(
        "/api/v1/fda/export/all",
        params={"tenant_id": TENANT},
    )
    assert r.status_code == 400


def test_export_all_rejects_malformed_date(client):
    r = client.get(
        "/api/v1/fda/export/all",
        params={"tenant_id": TENANT, "start_date": "not-a-date", "end_date": "2026-03-31"},
    )
    assert r.status_code == 400
    assert "ISO-8601" in r.json()["detail"]


def test_export_all_rejects_inverted_range(client):
    r = client.get(
        "/api/v1/fda/export/all",
        params={"tenant_id": TENANT, "start_date": "2026-03-31", "end_date": "2026-03-01"},
    )
    assert r.status_code == 400
    assert "on or after" in r.json()["detail"]


def test_export_all_rejects_excessive_range(client):
    r = client.get(
        "/api/v1/fda/export/all",
        params={"tenant_id": TENANT, "start_date": "2026-01-01", "end_date": "2026-12-31"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "exceeds" in detail and "90-day" in detail


# ---------------------------------------------------------------------------
# Empty-export 404 on /export/all
# ---------------------------------------------------------------------------


def test_export_all_returns_404_when_no_events(client):
    r = client.get(
        "/api/v1/fda/export/all",
        params={
            "tenant_id": TENANT,
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
        },
    )
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "No traceability records" in detail
    # No CSV/ZIP body leaked on the empty path.
    assert r.headers["content-type"].startswith("application/json")
    assert "Content-Disposition" not in r.headers
