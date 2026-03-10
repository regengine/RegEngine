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
    assert "timestamp,event,location,status" in timeline_text
    assert "Contaminant introduced at source lot" in timeline_text

    csv_contacts = client.get(
        f"/api/v1/simulations/{simulation_id}/export",
        params={"format": "csv", "view": "contact_list"},
    )
    assert csv_contacts.status_code == 200
    contacts_text = csv_contacts.text
    assert "facility_name" in contacts_text
    assert "notification_priority" in contacts_text


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
