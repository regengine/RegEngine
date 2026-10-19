"""API tests for recall simulation endpoints."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.authz import IngestionPrincipal, get_ingestion_principal
from app.recall_simulations import _simulation_store, router as recall_simulations_router


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(recall_simulations_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        tenant_id="tenant-test",
        auth_mode="test",
    )
    _simulation_store.clear()
    with TestClient(app) as test_client:
        yield test_client


def test_run_and_fetch_simulation(client: TestClient) -> None:
    run_response = client.post(
        "/api/v1/simulations/run",
        json={"scenario_id": "romaine-ecoli"},
    )
    assert run_response.status_code == 201

    payload = run_response.json()
    simulation_id = payload["id"]
    assert payload["scenario_id"] == "romaine-ecoli"
    assert payload["metrics"]["time_reduction_percent"] > 0

    timeline_response = client.get(f"/api/v1/simulations/{simulation_id}/timeline")
    assert timeline_response.status_code == 200
    timeline_payload = timeline_response.json()
    assert len(timeline_payload["timeline"]) >= 3

    graph_response = client.get(f"/api/v1/simulations/{simulation_id}/impact-graph")
    assert graph_response.status_code == 200
    graph_payload = graph_response.json()
    assert len(graph_payload["nodes"]) > 0
    assert len(graph_payload["links"]) > 0


def test_scenarios_endpoint_contains_required_fields(client: TestClient) -> None:
    response = client.get("/api/v1/simulations/scenarios")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 3
    scenario = payload["scenarios"][0]
    assert "id" in scenario
    assert "name" in scenario
    assert "description" in scenario
    assert "product_category" in scenario


def test_unknown_scenario_returns_400(client: TestClient) -> None:
    response = client.post(
        "/api/v1/simulations/run",
        json={"scenario_id": "unknown-scenario"},
    )
    assert response.status_code == 400


def test_export_simulation_json_and_csv_views(client: TestClient) -> None:
    run_response = client.post(
        "/api/v1/simulations/run",
        json={"scenario_id": "romaine-ecoli"},
    )
    assert run_response.status_code == 201
    simulation_id = run_response.json()["id"]

    json_export = client.get(f"/api/v1/simulations/{simulation_id}/export")
    assert json_export.status_code == 200
    assert "attachment; filename=" in json_export.headers["content-disposition"]
    json_payload = json_export.json()
    assert json_payload["format"] == "application/json"
    assert json_payload["simulation_id"] == simulation_id

    csv_summary = client.get(
        f"/api/v1/simulations/{simulation_id}/export",
        params={"format": "csv", "view": "summary"},
    )
    assert csv_summary.status_code == 200
    assert csv_summary.headers["content-type"].startswith("text/csv")
    summary_text = csv_summary.text
    assert "scenario_name" in summary_text
    assert "time_reduction_percent" in summary_text

    csv_timeline = client.get(
        f"/api/v1/simulations/{simulation_id}/export",
        params={"format": "csv", "view": "timeline"},
    )
    assert csv_timeline.status_code == 200
    timeline_text = csv_timeline.text
    # Every cell is quoted (csv.QUOTE_ALL, #3311 formula-injection fix).
    assert '"timestamp","event","location","status"' in timeline_text
    assert "Contaminant introduced at source lot" in timeline_text

    csv_contacts = client.get(
        f"/api/v1/simulations/{simulation_id}/export",
        params={"format": "csv", "view": "contact_list"},
    )
    assert csv_contacts.status_code == 200
    contacts_text = csv_contacts.text
    assert "facility_name" in contacts_text
    assert "notification_priority" in contacts_text


# ---------------------------------------------------------------------------
# Tenant-scoping security tests (F-2 + F-7)
# ---------------------------------------------------------------------------


def _client_for_tenant(tenant_id: str | None) -> TestClient:
    app = FastAPI()
    app.include_router(recall_simulations_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id=f"test-key-{tenant_id or 'none'}",
        scopes=["*"],
        tenant_id=tenant_id,
        auth_mode="test",
    )
    return TestClient(app)


def test_simulation_read_rejects_cross_tenant() -> None:
    """F-2: tenant B cannot read tenant A's simulation by UUID — returns 404."""
    _simulation_store.clear()

    client_a = _client_for_tenant("tenant-A")
    client_b = _client_for_tenant("tenant-B")

    run = client_a.post(
        "/api/v1/simulations/run",
        json={"scenario_id": "romaine-ecoli"},
    )
    assert run.status_code == 201
    sim_id = run.json()["id"]

    # Tenant A can read its own.
    own = client_a.get(f"/api/v1/simulations/{sim_id}")
    assert own.status_code == 200

    # Tenant B sees 404 — no existence oracle.
    cross = client_b.get(f"/api/v1/simulations/{sim_id}")
    assert cross.status_code == 404

    # All read-side endpoints must enforce the same boundary.
    assert client_b.get(f"/api/v1/simulations/{sim_id}/timeline").status_code == 404
    assert client_b.get(f"/api/v1/simulations/{sim_id}/impact-graph").status_code == 404
    assert client_b.get(f"/api/v1/simulations/{sim_id}/export").status_code == 404


def test_simulation_read_succeeds_for_own_tenant() -> None:
    """F-2: same-tenant reads continue to work after tenant-keying the store."""
    _simulation_store.clear()

    client_a = _client_for_tenant("tenant-A")
    run = client_a.post(
        "/api/v1/simulations/run",
        json={"scenario_id": "cheese-listeria"},
    )
    assert run.status_code == 201
    sim_id = run.json()["id"]

    fetched = client_a.get(f"/api/v1/simulations/{sim_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == sim_id


def test_simulation_run_rejects_query_tenant_mismatch() -> None:
    """F-2: authenticated as tenant A, posting with ?tenant_id=B → 403."""
    _simulation_store.clear()

    client_a = _client_for_tenant("tenant-A")
    resp = client_a.post(
        "/api/v1/simulations/run",
        params={"tenant_id": "tenant-B"},
        json={"scenario_id": "romaine-ecoli"},
    )
    assert resp.status_code == 403
    # Existence-oracle prevention: 403 (authenticated bad request), not 404.
    assert "Tenant mismatch" in resp.json()["detail"]


def test_simulation_run_uses_principal_tenant() -> None:
    """F-7: with no ?tenant_id query, the simulation is stored under the
    principal's tenant — never under the legacy "default" namespace."""
    _simulation_store.clear()

    client_a = _client_for_tenant("tenant-A")
    run = client_a.post(
        "/api/v1/simulations/run",
        json={"scenario_id": "shrimp-sulfite"},
    )
    assert run.status_code == 201
    sim_id = run.json()["id"]

    # Stored under (tenant-A, sim_id) — and NOT under any "default" key.
    assert ("tenant-A", sim_id) in _simulation_store
    assert ("default", sim_id) not in _simulation_store
    for key in _simulation_store.keys():
        assert key[0] != "default", f"unexpected 'default' tenant in store: {key!r}"


def test_default_namespace_no_longer_used() -> None:
    """F-7: a request with no tenant context (no principal tenant, no query,
    no header) is rejected with 400 — never silently namespaced as "default"."""
    _simulation_store.clear()

    client_no_tenant = _client_for_tenant(None)
    resp = client_no_tenant.post(
        "/api/v1/simulations/run",
        json={"scenario_id": "romaine-ecoli"},
    )
    # resolve_principal_tenant_id raises 400 when no tenant context exists.
    assert resp.status_code == 400
    assert "Tenant context required" in resp.json()["detail"]
    # Nothing was written to the store.
    assert _simulation_store == {}


def test_run_denied_without_simulations_write_scope() -> None:
    app = FastAPI()
    app.include_router(recall_simulations_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="limited-key",
        scopes=["simulations.read"],
        auth_mode="test",
    )
    _simulation_store.clear()

    with TestClient(app) as test_client:
        run_response = test_client.post(
            "/api/v1/simulations/run",
            json={"scenario_id": "romaine-ecoli"},
        )
        assert run_response.status_code == 403
        assert "requires 'simulations.write'" in run_response.json()["detail"]
