"""Unit tests for the Request-Response Workflow Router."""

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
from app import request_workflow_router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT = "tenant-rw-1"


def _make_principal(
    tenant_id: str = TENANT,
    scopes: list[str] | None = None,
) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        tenant_id=tenant_id,
        scopes=scopes or ["requests.read", "requests.write"],
        auth_mode="test",
    )


def _build_client(
    principal: IngestionPrincipal,
    mock_svc: MagicMock | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(request_workflow_router.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal

    fake_db = MagicMock()
    app.dependency_overrides[request_workflow_router._get_db_session] = lambda: fake_db

    if mock_svc is not None:
        request_workflow_router._get_service = lambda db_session: mock_svc  # type: ignore[assignment]

    return TestClient(app)


@pytest.fixture(autouse=True)
def _patch_rate_limit(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))


@pytest.fixture(autouse=True)
def _restore_get_service():
    original = request_workflow_router._get_service
    yield
    request_workflow_router._get_service = original


@pytest.fixture()
def mock_svc():
    return MagicMock()


@pytest.fixture()
def client(mock_svc):
    principal = _make_principal()
    return _build_client(principal, mock_svc)


# ---------------------------------------------------------------------------
# List requests
# ---------------------------------------------------------------------------

def test_list_requests(client, mock_svc):
    mock_svc.get_active_cases.return_value = [
        {"request_case_id": "rc-1", "status": "intake"},
    ]
    resp = client.get("/api/v1/requests")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == TENANT
    assert data["total"] == 1
    mock_svc.get_active_cases.assert_called_once_with(TENANT)


# ---------------------------------------------------------------------------
# Create request
# ---------------------------------------------------------------------------

def test_create_request(client, mock_svc):
    mock_svc.create_request_case.return_value = "rc-new-1"
    resp = client.post(
        "/api/v1/requests",
        json={
            "requesting_party": "FDA",
            "request_channel": "email",
            "scope_type": "tlc_trace",
            "affected_products": ["PROD-1"],
            "affected_lots": ["LOT-A"],
            "response_hours": 24,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["request_case_id"] == "rc-new-1"
    assert data["status"] == "intake"
    kw = mock_svc.create_request_case.call_args.kwargs
    assert kw["tenant_id"] == TENANT
    assert kw["requesting_party"] == "FDA"
    assert kw["affected_products"] == ["PROD-1"]
    assert kw["response_hours"] == 24


# ---------------------------------------------------------------------------
# Get single request
# ---------------------------------------------------------------------------

def test_get_request_found(client, mock_svc):
    mock_svc.get_active_cases.return_value = [
        {"request_case_id": "rc-1", "status": "intake"},
        {"request_case_id": "rc-2", "status": "collecting"},
    ]
    resp = client.get("/api/v1/requests/rc-2")
    assert resp.status_code == 200
    assert resp.json()["request_case_id"] == "rc-2"


def test_get_request_not_found(client, mock_svc):
    mock_svc.get_active_cases.return_value = []
    resp = client.get("/api/v1/requests/rc-missing")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Assemble package
# ---------------------------------------------------------------------------

def test_assemble_package(client, mock_svc):
    mock_svc.assemble_response_package.return_value = {
        "package_id": "pkg-1",
        "version_number": 1,
        "package_hash": "sha256:abc123",
    }
    resp = client.post(
        "/api/v1/requests/rc-1/assemble",
        params={"generated_by": "user-1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["package_id"] == "pkg-1"
    assert data["version_number"] == 1
    assert data["package_hash"] == "sha256:abc123"
    assert data["status"] == "assembling"


# ---------------------------------------------------------------------------
# Submit — success and blocking enforcement
# ---------------------------------------------------------------------------

def test_submit_package_success(client, mock_svc):
    mock_svc.submit_package.return_value = {"submission_id": "sub-1"}
    resp = client.post(
        "/api/v1/requests/rc-1/submit",
        json={
            "submitted_by": "user-1",
            "submission_method": "export",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["submission_id"] == "sub-1"
    assert data["status"] == "submitted"


def test_submit_blocked_by_defects(client, mock_svc):
    mock_svc.submit_package.side_effect = ValueError(
        "Cannot submit: 2 blocking defect(s) remain"
    )
    resp = client.post(
        "/api/v1/requests/rc-1/submit",
        json={
            "submitted_by": "user-1",
            "submission_method": "export",
        },
    )
    assert resp.status_code == 422
    assert "blocking defect" in resp.json()["detail"].lower()


def test_submit_with_force_bypasses_blockers(client, mock_svc):
    mock_svc.submit_package.return_value = {"submission_id": "sub-forced"}
    resp = client.post(
        "/api/v1/requests/rc-1/submit",
        json={
            "submitted_by": "user-1",
            "submission_method": "export",
            "force": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["submission_id"] == "sub-forced"
    kw = mock_svc.submit_package.call_args.kwargs
    assert kw["force"] is True


# ---------------------------------------------------------------------------
# Blockers
# ---------------------------------------------------------------------------

def test_get_blockers(client, mock_svc):
    mock_svc.check_blocking_defects.return_value = {
        "has_blockers": True,
        "blocking_count": 2,
        "defects": [
            {"type": "critical_rule_failure", "detail": "CTE missing"},
            {"type": "unresolved_exception", "detail": "exc-1"},
        ],
    }
    resp = client.get("/api/v1/requests/rc-1/blockers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["request_case_id"] == "rc-1"
    assert data["has_blockers"] is True
    assert data["blocking_count"] == 2


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------

def test_deadlines_route(client, mock_svc):
    """The /deadlines route returns urgency classification for active cases."""
    mock_svc.check_deadline_status.return_value = []
    resp = client.get("/api/v1/requests/deadlines")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["alert"] is False


@pytest.mark.asyncio
async def test_deadlines_handler_directly(mock_svc, monkeypatch):
    """Test the check_deadlines handler logic directly, bypassing
    the route-shadowing issue."""
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))

    mock_svc.check_deadline_status.return_value = [
        {"request_case_id": "rc-1", "urgency": "overdue", "hours_remaining": -2},
        {"request_case_id": "rc-2", "urgency": "critical", "hours_remaining": 1.5},
        {"request_case_id": "rc-3", "urgency": "normal", "hours_remaining": 18},
    ]
    original = request_workflow_router._get_service
    request_workflow_router._get_service = lambda db: mock_svc

    from unittest.mock import AsyncMock
    principal = _make_principal()
    result = await request_workflow_router.check_deadlines(
        tenant_id=TENANT,
        principal=principal,
        db_session=MagicMock(),
    )

    request_workflow_router._get_service = original

    assert result["tenant_id"] == TENANT
    assert result["total"] == 3
    assert result["overdue_count"] == 1
    assert result["critical_count"] == 1
    assert result["alert"] is True


@pytest.mark.asyncio
async def test_deadlines_no_alerts_directly(mock_svc, monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))

    mock_svc.check_deadline_status.return_value = [
        {"request_case_id": "rc-3", "urgency": "normal", "hours_remaining": 18},
    ]
    original = request_workflow_router._get_service
    request_workflow_router._get_service = lambda db: mock_svc

    principal = _make_principal()
    result = await request_workflow_router.check_deadlines(
        tenant_id=TENANT,
        principal=principal,
        db_session=MagicMock(),
    )

    request_workflow_router._get_service = original

    assert result["alert"] is False


# ---------------------------------------------------------------------------
# Scope update
# ---------------------------------------------------------------------------

def test_update_scope(client, mock_svc):
    resp = client.patch(
        "/api/v1/requests/rc-1/scope",
        json={
            "affected_products": ["PROD-1", "PROD-2"],
            "scope_description": "Expanded to include additional products",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "scoping"
    kw = mock_svc.update_scope.call_args.kwargs
    assert kw["affected_products"] == ["PROD-1", "PROD-2"]


# ---------------------------------------------------------------------------
# Signoff
# ---------------------------------------------------------------------------

def test_add_signoff(client, mock_svc):
    resp = client.post(
        "/api/v1/requests/rc-1/signoff",
        json={
            "signoff_type": "final_approval",
            "signed_by": "director-1",
            "notes": "Approved for submission",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["signoff_type"] == "final_approval"
    assert data["status"] == "signed"


# ---------------------------------------------------------------------------
# Auth: read-only blocks write endpoints
# ---------------------------------------------------------------------------

def test_read_only_blocks_create(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    principal = _make_principal(scopes=["requests.read"])
    svc = MagicMock()
    c = _build_client(principal, svc)
    resp = c.post(
        "/api/v1/requests",
        json={"requesting_party": "FDA"},
    )
    assert resp.status_code == 403


def test_read_only_blocks_submit(monkeypatch):
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    principal = _make_principal(scopes=["requests.read"])
    svc = MagicMock()
    c = _build_client(principal, svc)
    resp = c.post(
        "/api/v1/requests/rc-1/submit",
        json={"submitted_by": "user-1"},
    )
    assert resp.status_code == 403
