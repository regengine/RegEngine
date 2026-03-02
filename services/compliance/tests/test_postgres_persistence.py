from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from services.compliance.main import app
from services.compliance.app.store import STORE


@pytest.mark.skipif(not STORE._db_enabled or STORE._engine is None, reason="Postgres persistence not enabled")
def test_analysis_and_audit_persist_to_postgres() -> None:
    tenant_id = str(uuid4())
    headers = {"X-Tenant-Id": tenant_id}
    client = TestClient(app)

    register = client.post(
        "/v1/models",
        json={
            "id": "credit_v4",
            "name": "Credit Model V4",
            "version": "4.0.0",
            "owner": "model-governance",
            "deployment_date": "2026-03-01",
            "status": "active",
        },
        headers=headers,
    )
    assert register.status_code == 200

    map_response = client.post(
        "/v1/regulatory/map",
        json={
            "source_name": "ECOA",
            "citation": "ECOA Section 701(a)",
            "section": "701(a)",
            "text": "Creditors must avoid discriminatory impact in lending decisions.",
        },
        headers=headers,
    )
    assert map_response.status_code == 200

    analyze_response = client.post(
        "/v1/fair-lending/analyze",
        json={
            "model_id": "credit_v4",
            "protected_attribute": "race",
            "groups": [
                {"name": "White", "approved": 7100, "denied": 2900},
                {"name": "Black", "approved": 5600, "denied": 4400},
            ],
            "analysis_type": ["DIR", "regression"],
        },
        headers=headers,
    )
    assert analyze_response.status_code == 200

    export_response = client.post(
        "/v1/audit/export",
        json={
            "model_id": "credit_v4",
            "output_type": "fair_lending_summary_report",
            "reviewer": "qa-auditor",
        },
        headers=headers,
    )
    assert export_response.status_code == 200

    assert STORE._engine is not None
    with STORE._engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )
        regulation_count = connection.execute(
            text("SELECT count(*) FROM regulations WHERE tenant_id = CAST(:tenant_id AS uuid)"),
            {"tenant_id": tenant_id},
        ).scalar()
        result_count = connection.execute(
            text("SELECT count(*) FROM model_compliance_results WHERE tenant_id = CAST(:tenant_id AS uuid)"),
            {"tenant_id": tenant_id},
        ).scalar()
        export_count = connection.execute(
            text("SELECT count(*) FROM audit_exports WHERE tenant_id = CAST(:tenant_id AS uuid)"),
            {"tenant_id": tenant_id},
        ).scalar()

    assert int(regulation_count or 0) >= 1
    assert int(result_count or 0) >= 1
    assert int(export_count or 0) >= 1
