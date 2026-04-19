"""Unit tests for the Identity Resolution Router."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.authz as authz
from app.authz import IngestionPrincipal, get_ingestion_principal
from app import identity_router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "tenant-id-1"
OTHER_TENANT = "tenant-id-other"


def _make_principal(
    tenant_id: str = TENANT,
    scopes: list[str] | None = None,
) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        tenant_id=tenant_id,
        scopes=scopes or ["identity.read", "identity.write"],
        auth_mode="test",
    )


def _build_client(
    principal: IngestionPrincipal,
    mock_svc: MagicMock | None = None,
    mock_db: MagicMock | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(identity_router.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal

    fake_db = mock_db or MagicMock()
    app.dependency_overrides[identity_router._get_db_session] = lambda: fake_db

    if mock_svc is not None:
        identity_router._get_service = lambda *_a, **_kw: mock_svc  # type: ignore[assignment]

    return TestClient(app)


@pytest.fixture(autouse=True)
def _patch_rate_limit(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))


@pytest.fixture(autouse=True)
def _restore_get_service():
    original = identity_router._get_service
    yield
    identity_router._get_service = original


@pytest.fixture()
def mock_svc():
    return MagicMock()


@pytest.fixture()
def client(mock_svc):
    principal = _make_principal()
    return _build_client(principal, mock_svc)


# ---------------------------------------------------------------------------
# List entities
# ---------------------------------------------------------------------------

def test_list_entities_with_search(client, mock_svc):
    mock_svc.find_potential_matches.return_value = [
        {"entity_id": "e-1", "canonical_name": "Acme Foods", "entity_type": "firm"},
    ]
    resp = client.get(
        "/api/v1/identity/entities",
        params={"search": "Acme"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == TENANT
    assert data["total"] == 1
    assert data["entities"][0]["entity_id"] == "e-1"
    mock_svc.find_potential_matches.assert_called_once()


def test_list_entities_without_search_queries_db(monkeypatch):
    """When no search param is passed, the endpoint runs a raw SQL query."""
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))

    mock_db = MagicMock()
    # Simulate a row returned from the raw SQL query
    fake_row = ("e-1", "firm", "Acme Foods", "1234567890123", None, "verified", 0.95)
    mock_db.execute.return_value.fetchall.return_value = [fake_row]

    principal = _make_principal()
    c = _build_client(principal, mock_svc=None, mock_db=mock_db)

    # We need to patch _get_service to NOT be called (the endpoint uses db_session directly)
    # But the endpoint also calls _get_service for the search path — for the non-search
    # path it uses db_session.execute directly, so we don't need a service mock.
    # However _get_service IS still called in the non-search branch — let's check the code.
    # Actually no — in the non-search branch, the code does NOT call _get_service, it uses
    # db_session directly. But wait, looking again at the code: it does NOT call _get_service
    # in the non-search path. It only calls svc when search is truthy.
    # Actually re-reading: it does NOT — it uses db_session.execute directly in the else branch.
    # So we just need the mock_db to work.
    resp = c.get("/api/v1/identity/entities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["entities"][0]["entity_id"] == "e-1"
    assert data["entities"][0]["confidence_score"] == 0.95


# ---------------------------------------------------------------------------
# Create entity
# ---------------------------------------------------------------------------

def test_register_entity(client, mock_svc):
    mock_svc.register_entity.return_value = "e-new-1"
    resp = client.post(
        "/api/v1/identity/entities",
        json={
            "entity_type": "firm",
            "canonical_name": "Acme Foods Inc.",
            "gln": "1234567890123",
            "country": "US",
            "created_by": "user-1",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["entity_id"] == "e-new-1"
    assert data["status"] == "registered"
    kw = mock_svc.register_entity.call_args.kwargs
    assert kw["tenant_id"] == TENANT
    assert kw["entity_type"] == "firm"
    assert kw["canonical_name"] == "Acme Foods Inc."
    assert kw["gln"] == "1234567890123"


# ---------------------------------------------------------------------------
# Get entity
# ---------------------------------------------------------------------------

def test_get_entity_found(client, mock_svc):
    mock_svc.get_entity.return_value = {
        "entity_id": "e-1",
        "canonical_name": "Acme Foods",
        "aliases": [{"alias_type": "name", "alias_value": "ACME FOODS LLC"}],
    }
    resp = client.get("/api/v1/identity/entities/e-1")
    assert resp.status_code == 200
    assert resp.json()["entity_id"] == "e-1"
    assert len(resp.json()["aliases"]) == 1
    mock_svc.get_entity.assert_called_once_with(TENANT, "e-1")


def test_get_entity_not_found(client, mock_svc):
    mock_svc.get_entity.return_value = None
    resp = client.get("/api/v1/identity/entities/e-missing")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Add alias
# ---------------------------------------------------------------------------

def test_add_alias(client, mock_svc):
    mock_svc.add_alias.return_value = "alias-new-1"
    resp = client.post(
        "/api/v1/identity/entities/e-1/aliases",
        json={
            "alias_type": "gln",
            "alias_value": "9876543210987",
            "source_system": "EDI",
            "created_by": "user-1",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["alias_id"] == "alias-new-1"
    assert data["status"] == "added"
    kw = mock_svc.add_alias.call_args.kwargs
    assert kw["entity_id"] == "e-1"
    assert kw["alias_type"] == "gln"
    assert kw["alias_value"] == "9876543210987"


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

def test_list_reviews(client, mock_svc):
    mock_svc.list_pending_reviews.return_value = [
        {"review_id": "rv-1", "status": "pending", "confidence_score": 0.82},
        {"review_id": "rv-2", "status": "pending", "confidence_score": 0.71},
    ]
    resp = client.get("/api/v1/identity/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == TENANT
    assert data["total"] == 2


def test_resolve_review(client, mock_svc):
    resp = client.patch(
        "/api/v1/identity/reviews/rv-1",
        json={
            "status": "confirmed_match",
            "resolved_by": "user-1",
            "resolution_notes": "Same entity, different spelling",
            "auto_merge": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["review_id"] == "rv-1"
    assert data["status"] == "confirmed_match"
    kw = mock_svc.resolve_review.call_args.kwargs
    assert kw["auto_merge"] is True


# ---------------------------------------------------------------------------
# Merge entities
# ---------------------------------------------------------------------------

def test_merge_entities(client, mock_svc):
    mock_svc.merge_entities.return_value = "merge-1"
    resp = client.post(
        "/api/v1/identity/merge",
        json={
            "source_entity_id": "e-dup",
            "target_entity_id": "e-canonical",
            "reason": "Duplicate identified",
            "performed_by": "user-1",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["merge_id"] == "merge-1"
    assert data["status"] == "merged"
    kw = mock_svc.merge_entities.call_args.kwargs
    assert kw["source_entity_id"] == "e-dup"
    assert kw["target_entity_id"] == "e-canonical"


def test_split_entities(client, mock_svc):
    resp = client.post(
        "/api/v1/identity/split",
        json={
            "merge_id": "merge-1",
            "performed_by": "user-1",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "split"
    mock_svc.split_entity.assert_called_once_with(TENANT, "merge-1", "user-1")


# ---------------------------------------------------------------------------
# Lookup by alias
# ---------------------------------------------------------------------------

def test_lookup_by_alias(client, mock_svc):
    mock_svc.find_entity_by_alias.return_value = [
        {"entity_id": "e-1", "canonical_name": "Acme Foods"},
    ]
    resp = client.get(
        "/api/v1/identity/lookup",
        params={"alias_value": "1234567890123", "alias_type": "gln"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    mock_svc.find_entity_by_alias.assert_called_once_with(TENANT, "1234567890123", "gln")


# ---------------------------------------------------------------------------
# Auth & tenant isolation
# ---------------------------------------------------------------------------

def test_read_only_scope_blocks_write(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    principal = _make_principal(scopes=["identity.read"])
    svc = MagicMock()
    c = _build_client(principal, svc)
    resp = c.post(
        "/api/v1/identity/entities",
        json={"entity_type": "firm", "canonical_name": "Test"},
    )
    assert resp.status_code == 403


def test_cross_tenant_request_blocked(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    principal = _make_principal(tenant_id=TENANT, scopes=["identity.read"])
    svc = MagicMock()
    c = _build_client(principal, svc)
    resp = c.get(
        "/api/v1/identity/entities",
        params={"tenant_id": OTHER_TENANT},
    )
    assert resp.status_code == 403
    assert "tenant mismatch" in resp.json()["detail"].lower()


def test_wildcard_scope_allows_cross_tenant(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    principal = _make_principal(tenant_id=TENANT, scopes=["*"])
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []
    c = _build_client(principal, mock_svc=None, mock_db=mock_db)
    resp = c.get(
        "/api/v1/identity/entities",
        params={"tenant_id": OTHER_TENANT},
    )
    assert resp.status_code == 200


def test_wrong_scope_blocks_access(monkeypatch):
    """A principal with scopes for a different domain cannot access identity endpoints."""
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    principal = _make_principal(scopes=["exceptions.read"])
    svc = MagicMock()
    c = _build_client(principal, svc)
    resp = c.post(
        "/api/v1/identity/entities",
        json={"entity_type": "firm", "canonical_name": "Test"},
    )
    assert resp.status_code == 403
