"""API tests for recall simulation endpoints."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.recall_simulations import _simulation_store, router as recall_simulations_router
from app.webhook_compat import _verify_api_key


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(recall_simulations_router)
    app.dependency_overrides[_verify_api_key] = lambda: None
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
