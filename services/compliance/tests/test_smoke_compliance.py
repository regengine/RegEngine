from uuid import uuid4

from fastapi.testclient import TestClient

from services.compliance.main import app


def _tenant_headers() -> dict:
    return {"X-Tenant-Id": str(uuid4())}


def test_health_and_root() -> None:
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "compliance-api"

    root = client.get("/")
    assert root.status_code == 200
    payload = root.json()
    assert payload["service"] == "compliance-api"
    assert "/v1/fair-lending/analyze" in payload["key_endpoints"]["fair_lending_analysis"]


def test_fair_lending_end_to_end_flow() -> None:
    client = TestClient(app)
    headers = _tenant_headers()

    model_payload = {
        "id": "credit_v3",
        "name": "Credit Underwriting Model",
        "version": "3.0.1",
        "owner": "fair-lending-team",
        "deployment_date": "2026-02-28",
        "status": "active",
    }
    register = client.post("/v1/models", json=model_payload, headers=headers)
    assert register.status_code == 200
    assert register.json()["deployment_locked"] is False

    analyze_payload = {
        "model_id": "credit_v3",
        "protected_attribute": "race",
        "groups": [
            {"name": "White", "approved": 7200, "denied": 2800},
            {"name": "Black", "approved": 5800, "denied": 4200},
        ],
        "analysis_type": ["DIR", "regression", "drift"],
        "historical_approval_rates": {
            "White": [0.69, 0.7, 0.72, 0.71],
            "Black": [0.55, 0.54, 0.52, 0.5],
        },
    }
    analyzed = client.post("/v1/fair-lending/analyze", json=analyze_payload, headers=headers)
    assert analyzed.status_code == 200
    analyzed_payload = analyzed.json()
    assert analyzed_payload["model_id"] == "credit_v3"
    assert analyzed_payload["risk_level"] in {"medium", "high"}
    assert analyzed_payload["analysis_id"]

    summary = client.get("/v1/risk/summary", params={"model_id": "credit_v3"}, headers=headers)
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["overall_fair_lending_risk"] in {"Low", "Medium", "High"}
    assert 0 <= summary_payload["exposure_score"] <= 100

    export_payload = {
        "model_id": "credit_v3",
        "output_type": "model_validation_dossier",
        "reviewer": "qa-reviewer",
    }
    exported = client.post("/v1/audit/export", json=export_payload, headers=headers)
    assert exported.status_code == 200
    export_body = exported.json()
    assert export_body["immutable"] is True
    assert export_body["hash_sha256"]

    ckg = client.get("/v1/ckg/summary", headers=headers)
    assert ckg.status_code == 200
    ckg_payload = ckg.json()
    assert ckg_payload["edge_count"] >= 1
