"""API tests for recall simulation endpoints."""

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from main import app


def test_run_and_fetch_simulation() -> None:
    with TestClient(app) as client:
        run_response = client.post(
            "/api/v1/simulations/run",
            json={"scenario_id": "romaine-ecoli"},
        )
        assert run_response.status_code == 200

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


def test_unknown_scenario_returns_404() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/simulations/run",
            json={"scenario_id": "unknown-scenario"},
        )
        assert response.status_code == 404
