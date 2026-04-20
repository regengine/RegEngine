"""Coverage-sweep tests for ``app.identity_router`` (#1342).

The existing ``tests/test_identity_router.py`` patches ``_get_service``
and never calls the service-less DB failure branch, never exercises
the ``entity_type`` filter of ``list_entities`` (which toggles two
query-building lines), and never hits the ``/match`` endpoint.

This file closes the three remaining gaps:
    62       — ``_get_service(None)`` -> 503
    150-151  — ``list_entities`` with no search but an ``entity_type`` filter
    267-272  — ``find_matches`` (``GET /api/v1/identity/match``)
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.authz as authz  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app import identity_router  # noqa: E402
from app.identity_router import _get_service  # noqa: E402


TENANT = "tenant-id-1342"


def _make_principal() -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        tenant_id=TENANT,
        scopes=["identity.read", "identity.write"],
        auth_mode="test",
    )


@pytest.fixture(autouse=True)
def _patch_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))


@pytest.fixture(autouse=True)
def _restore_get_service():
    original = identity_router._get_service
    yield
    identity_router._get_service = original


# --------------------------------------------------------------------------- #
# Line 62: _get_service(None) -> 503
# --------------------------------------------------------------------------- #


class TestGetServiceNoDb:
    def test_raises_503_when_db_session_none(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _get_service(None, _make_principal())
        assert exc.value.status_code == 503
        assert exc.value.detail == "Database unavailable"

    def test_constructs_service_with_principal_tenant_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        class _FakeIdentityResolutionService:
            def __init__(self, db_session, *, principal_tenant_id, allow_cross_tenant):
                captured["db_session"] = db_session
                captured["principal_tenant_id"] = principal_tenant_id
                captured["allow_cross_tenant"] = allow_cross_tenant

        fake_module = types.ModuleType("shared.identity_resolution")
        fake_module.IdentityResolutionService = _FakeIdentityResolutionService  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "shared.identity_resolution", fake_module)

        session = MagicMock()
        _get_service(session, _make_principal())

        assert captured["db_session"] is session
        assert captured["principal_tenant_id"] == TENANT
        assert captured["allow_cross_tenant"] is False

    def test_allow_cross_tenant_flag_passed_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        class _FakeIdentityResolutionService:
            def __init__(self, db_session, *, principal_tenant_id, allow_cross_tenant):
                captured["allow_cross_tenant"] = allow_cross_tenant

        fake_module = types.ModuleType("shared.identity_resolution")
        fake_module.IdentityResolutionService = _FakeIdentityResolutionService  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "shared.identity_resolution", fake_module)

        _get_service(MagicMock(), _make_principal(), allow_cross_tenant=True)
        assert captured["allow_cross_tenant"] is True

    def test_no_principal_yields_none_tenant_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        class _FakeIdentityResolutionService:
            def __init__(self, db_session, *, principal_tenant_id, allow_cross_tenant):
                captured["principal_tenant_id"] = principal_tenant_id

        fake_module = types.ModuleType("shared.identity_resolution")
        fake_module.IdentityResolutionService = _FakeIdentityResolutionService  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "shared.identity_resolution", fake_module)

        _get_service(MagicMock(), principal=None)
        assert captured["principal_tenant_id"] is None


# --------------------------------------------------------------------------- #
# Lines 150-151: list_entities(entity_type=..., no search)
# Lines 267-272: find_matches endpoint
# --------------------------------------------------------------------------- #


def _build_client_with_stubbed_service(
    mock_svc: MagicMock, mock_db: MagicMock | None = None
) -> TestClient:
    app = FastAPI()
    app.include_router(identity_router.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: _make_principal()

    fake_db = mock_db or MagicMock()
    app.dependency_overrides[identity_router._get_db_session] = lambda: fake_db

    identity_router._get_service = lambda *_a, **_kw: mock_svc  # type: ignore[assignment]
    return TestClient(app)


class TestListEntitiesEntityTypeFilter:
    """Covers lines 150-151 (entity_type filter adds WHERE clause)."""

    def test_entity_type_filter_adds_where_clause(self) -> None:
        # The service isn't used here — list_entities does a raw SQL
        # query through db_session.execute() when no ``search`` is given.
        mock_svc = MagicMock()
        mock_db = MagicMock()
        # Provide two rows so we exercise the list comprehension.
        row_1 = ("ent-1", "firm", "Acme Farms", "gln-1", None, "verified", 0.95)
        row_2 = ("ent-2", "firm", "Beta Packing", None, None, None, None)
        mock_db.execute.return_value.fetchall.return_value = [row_1, row_2]

        client = _build_client_with_stubbed_service(mock_svc, mock_db)
        response = client.get("/api/v1/identity/entities?entity_type=firm")

        assert response.status_code == 200
        payload = response.json()
        assert payload["tenant_id"] == TENANT
        assert payload["total"] == 2
        assert payload["entities"][0]["entity_id"] == "ent-1"
        assert payload["entities"][1]["confidence_score"] == 1.0  # None → 1.0

        # Verify the SQL was built with the entity_type filter (lines 150-151).
        call_args = mock_db.execute.call_args
        sql_clause = str(call_args[0][0])
        assert "entity_type = :etype" in sql_clause
        assert call_args[0][1]["etype"] == "firm"
        assert call_args[0][1]["tid"] == TENANT

    def test_no_entity_type_skips_filter(self) -> None:
        # Baseline: without entity_type, the WHERE clause is not appended.
        mock_svc = MagicMock()
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        client = _build_client_with_stubbed_service(mock_svc, mock_db)
        response = client.get("/api/v1/identity/entities")

        assert response.status_code == 200
        call_args = mock_db.execute.call_args
        sql_clause = str(call_args[0][0])
        assert "entity_type = :etype" not in sql_clause
        assert "etype" not in call_args[0][1]


class TestFindMatchesEndpoint:
    """Covers lines 267-272 (GET /api/v1/identity/match)."""

    def test_happy_path_returns_matches(self) -> None:
        mock_svc = MagicMock()
        mock_svc.find_potential_matches.return_value = [
            {"entity_id": "ent-9", "canonical_name": "Acme", "confidence": 0.9},
            {"entity_id": "ent-10", "canonical_name": "Acme Inc.", "confidence": 0.85},
        ]
        client = _build_client_with_stubbed_service(mock_svc)

        response = client.get(
            "/api/v1/identity/match",
            params={"name": "acme", "entity_type": "firm", "min_confidence": 0.8},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["tenant_id"] == TENANT
        assert payload["total"] == 2
        assert payload["matches"][0]["entity_id"] == "ent-9"

        # Confirm args were threaded through.
        args, kwargs = mock_svc.find_potential_matches.call_args
        assert args[0] == TENANT
        assert args[1] == "acme"
        assert kwargs["entity_type"] == "firm"
        assert kwargs["min_confidence"] == 0.8

    def test_defaults_when_optional_params_omitted(self) -> None:
        mock_svc = MagicMock()
        mock_svc.find_potential_matches.return_value = []
        client = _build_client_with_stubbed_service(mock_svc)

        response = client.get("/api/v1/identity/match", params={"name": "acme"})
        assert response.status_code == 200
        _args, kwargs = mock_svc.find_potential_matches.call_args
        assert kwargs["entity_type"] is None
        # min_confidence default is 0.7.
        assert kwargs["min_confidence"] == 0.7
