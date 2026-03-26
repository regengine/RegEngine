"""Unit tests for the Exception & Remediation Queue Router."""

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
from app import exception_router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "tenant-exc-1"
OTHER_TENANT = "tenant-exc-other"


def _make_principal(
    tenant_id: str = TENANT,
    scopes: list[str] | None = None,
) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        tenant_id=tenant_id,
        scopes=scopes or ["exceptions.read", "exceptions.write"],
        auth_mode="test",
    )


def _build_client(
    principal: IngestionPrincipal,
    mock_svc: MagicMock | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(exception_router.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal

    fake_db = MagicMock()
    app.dependency_overrides[exception_router._get_db_session] = lambda: fake_db

    if mock_svc is not None:
        original_get_service = exception_router._get_service

        def _patched_get_service(db_session):
            return mock_svc

        exception_router._get_service = _patched_get_service  # type: ignore[assignment]

    client = TestClient(app)
    client._mock_svc = mock_svc  # stash for cleanup
    return client


@pytest.fixture(autouse=True)
def _patch_rate_limit(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))


@pytest.fixture(autouse=True)
def _restore_get_service():
    original = exception_router._get_service
    yield
    exception_router._get_service = original


@pytest.fixture()
def mock_svc():
    return MagicMock()


@pytest.fixture()
def client(mock_svc):
    principal = _make_principal()
    return _build_client(principal, mock_svc)


# ---------------------------------------------------------------------------
# List exceptions
# ---------------------------------------------------------------------------

def test_list_exceptions_returns_cases(client, mock_svc):
    mock_svc.list_exceptions.return_value = [
        {"case_id": "exc-1", "severity": "critical", "status": "open"},
        {"case_id": "exc-2", "severity": "warning", "status": "open"},
    ]
    resp = client.get("/api/v1/exceptions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == TENANT
    assert data["total"] == 2
    assert len(data["cases"]) == 2
    mock_svc.list_exceptions.assert_called_once()
    call_kwargs = mock_svc.list_exceptions.call_args.kwargs
    assert call_kwargs["tenant_id"] == TENANT


def test_list_exceptions_passes_filters(client, mock_svc):
    mock_svc.list_exceptions.return_value = []
    resp = client.get(
        "/api/v1/exceptions",
        params={
            "severity": "critical",
            "status": "open",
            "source_supplier": "ACME",
            "rule_category": "CTE_MISSING",
        },
    )
    assert resp.status_code == 200
    kw = mock_svc.list_exceptions.call_args.kwargs
    assert kw["severity"] == "critical"
    assert kw["status"] == "open"
    assert kw["source_supplier"] == "ACME"
    assert kw["rule_category"] == "CTE_MISSING"


# ---------------------------------------------------------------------------
# Get single exception
# ---------------------------------------------------------------------------

def test_get_exception_found(client, mock_svc):
    mock_svc.get_exception.return_value = {"case_id": "exc-1", "severity": "critical"}
    resp = client.get("/api/v1/exceptions/exc-1")
    assert resp.status_code == 200
    assert resp.json()["case_id"] == "exc-1"
    mock_svc.get_exception.assert_called_once_with(TENANT, "exc-1")


def test_get_exception_not_found(client, mock_svc):
    mock_svc.get_exception.return_value = None
    resp = client.get("/api/v1/exceptions/exc-missing")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Create exception
# ---------------------------------------------------------------------------

def test_create_exception(client, mock_svc):
    mock_svc.create_exception.return_value = "exc-new-1"
    resp = client.post(
        "/api/v1/exceptions",
        json={
            "severity": "critical",
            "linked_event_ids": ["evt-1"],
            "rule_category": "CTE_MISSING",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["case_id"] == "exc-new-1"
    assert data["status"] == "created"
    kw = mock_svc.create_exception.call_args.kwargs
    assert kw["tenant_id"] == TENANT
    assert kw["severity"] == "critical"
    assert kw["linked_event_ids"] == ["evt-1"]


# ---------------------------------------------------------------------------
# Assign owner
# ---------------------------------------------------------------------------

def test_assign_owner(client, mock_svc):
    resp = client.patch(
        "/api/v1/exceptions/exc-1/assign",
        json={"owner_user_id": "user-42"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == "exc-1"
    assert data["owner_user_id"] == "user-42"
    assert data["status"] == "assigned"
    mock_svc.assign_owner.assert_called_once_with(TENANT, "exc-1", "user-42")


# ---------------------------------------------------------------------------
# Resolve exception
# ---------------------------------------------------------------------------

def test_resolve_exception(client, mock_svc):
    resp = client.patch(
        "/api/v1/exceptions/exc-1/resolve",
        json={
            "resolution_summary": "Data corrected",
            "resolved_by": "user-42",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"
    mock_svc.resolve_exception.assert_called_once_with(
        TENANT, "exc-1", "Data corrected", "user-42",
    )


# ---------------------------------------------------------------------------
# Waive exception
# ---------------------------------------------------------------------------

def test_waive_exception(client, mock_svc):
    resp = client.patch(
        "/api/v1/exceptions/exc-1/waive",
        json={
            "waiver_reason": "Low-risk supplier",
            "waiver_approved_by": "admin-1",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "waived"
    mock_svc.waive_exception.assert_called_once_with(
        TENANT, "exc-1", "Low-risk supplier", "admin-1",
    )


# ---------------------------------------------------------------------------
# Blocking count
# ---------------------------------------------------------------------------

def test_blocking_count(client, mock_svc):
    mock_svc.get_unresolved_blocking_count.return_value = 3
    resp = client.get("/api/v1/exceptions/stats/blocking")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == TENANT
    assert data["blocking_count"] == 3


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def test_list_comments(client, mock_svc):
    mock_svc.list_comments.return_value = [
        {"comment_id": "c1", "comment_text": "investigating"},
    ]
    resp = client.get("/api/v1/exceptions/exc-1/comments")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["case_id"] == "exc-1"


def test_add_comment(client, mock_svc):
    mock_svc.add_comment.return_value = "comment-new-1"
    resp = client.post(
        "/api/v1/exceptions/exc-1/comments",
        json={
            "author_user_id": "user-42",
            "comment_text": "Root cause identified",
            "comment_type": "note",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["comment_id"] == "comment-new-1"


# ---------------------------------------------------------------------------
# Auth & tenant isolation
# ---------------------------------------------------------------------------

def test_read_only_scope_blocks_write(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    principal = _make_principal(scopes=["exceptions.read"])
    svc = MagicMock()
    c = _build_client(principal, svc)
    resp = c.post(
        "/api/v1/exceptions",
        json={"severity": "critical"},
    )
    assert resp.status_code == 403


def test_cross_tenant_request_blocked(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    principal = _make_principal(tenant_id=TENANT, scopes=["exceptions.read"])
    svc = MagicMock()
    c = _build_client(principal, svc)
    resp = c.get(
        "/api/v1/exceptions",
        params={"tenant_id": OTHER_TENANT},
    )
    assert resp.status_code == 403
    assert "tenant mismatch" in resp.json()["detail"].lower()


def test_wildcard_scope_allows_cross_tenant(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    principal = _make_principal(tenant_id=TENANT, scopes=["*"])
    svc = MagicMock()
    svc.list_exceptions.return_value = []
    c = _build_client(principal, svc)
    resp = c.get(
        "/api/v1/exceptions",
        params={"tenant_id": OTHER_TENANT},
    )
    assert resp.status_code == 200
