from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.authz as authz
import app.inflow_workbench as workbench
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.inflow_workbench import router


def _principal(
    *,
    scopes: list[str] | None = None,
    tenant_id: str | None = "tenant-a",
) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        scopes=scopes or ["*"],
        tenant_id=tenant_id,
        auth_mode="test",
    )


def _client(
    tmp_path,
    monkeypatch,
    *,
    principal: IngestionPrincipal | None = None,
    authenticated: bool = True,
) -> TestClient:
    monkeypatch.setenv("REGENGINE_INFLOW_WORKBENCH_PATH", str(tmp_path / "workbench.json"))
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    app = FastAPI()
    app.include_router(router)
    if authenticated:
        app.dependency_overrides[get_ingestion_principal] = lambda: principal or _principal()
    return TestClient(app)


def _sandbox_result(*, blocked: bool = True) -> dict:
    kde_errors = ["ship_to_location is required"] if blocked else []
    return {
        "total_events": 1,
        "compliant_events": 0 if blocked else 1,
        "non_compliant_events": 1 if blocked else 0,
        "total_kde_errors": len(kde_errors),
        "total_rule_failures": 1 if blocked else 0,
        "submission_blocked": blocked,
        "blocking_reasons": ["Event 1 (shipping): destination location missing"] if blocked else [],
        "duplicate_warnings": [],
        "entity_warnings": [],
        "normalizations": [],
        "events": [
            {
                "event_index": 0,
                "cte_type": "shipping",
                "traceability_lot_code": "TLC-FEED-002",
                "product_description": "Romaine Lettuce",
                "kde_errors": kde_errors,
                "rules_evaluated": 1,
                "rules_passed": 0 if blocked else 1,
                "rules_failed": 1 if blocked else 0,
                "rules_warned": 0,
                "compliant": not blocked,
                "blocking_defects": [
                    {
                        "rule_title": "Shipping destination required",
                        "severity": "critical",
                        "result": "fail",
                        "why_failed": "Destination location missing",
                        "citation": "21 CFR 1.1345",
                        "remediation": "Add ship_to_location before committing evidence.",
                        "category": "kde",
                        "evidence": None,
                    }
                ]
                if blocked
                else [],
                "all_results": [],
            }
        ],
    }


def test_anonymous_workbench_routes_require_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "production")
    client = _client(tmp_path, monkeypatch, authenticated=False)
    scenario_body = {
        "tenant_id": "tenant-a",
        "name": "Supplier missing BOL",
        "outcome": "Blocked reference document",
        "csv": "cte_type,traceability_lot_code\nshipping,TLC-1",
    }
    run_body = {
        "tenant_id": "tenant-a",
        "source": "inflow-lab-data-feeder",
        "csv": "cte_type,traceability_lot_code\nshipping,TLC-FEED-002",
        "result": _sandbox_result(blocked=True),
    }
    commit_body = {
        "mode": "staging",
        "tenant_id": "tenant-a",
        "result": _sandbox_result(blocked=False),
    }

    checks = [
        ("GET", "/api/v1/inflow-workbench/scenarios", None),
        ("POST", "/api/v1/inflow-workbench/scenarios", scenario_body),
        ("POST", "/api/v1/inflow-workbench/readiness/preview", _sandbox_result(blocked=False)),
        ("GET", "/api/v1/inflow-workbench/readiness/summary?tenant_id=tenant-a", None),
        ("POST", "/api/v1/inflow-workbench/commit-gate", commit_body),
        ("POST", "/api/v1/inflow-workbench/runs", run_body),
        ("GET", "/api/v1/inflow-workbench/runs/run-missing?tenant_id=tenant-a", None),
        ("GET", "/api/v1/inflow-workbench/fix-queue?tenant_id=tenant-a", None),
        ("PATCH", "/api/v1/inflow-workbench/fix-queue/item-1?tenant_id=tenant-a", {"status": "corrected"}),
    ]

    for method, url, body in checks:
        response = client.request(method, url, json=body) if body is not None else client.request(method, url)
        assert response.status_code == 401, (method, url, response.text)


def test_scoped_principal_rejects_cross_tenant_workbench_write(tmp_path, monkeypatch):
    client = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.write"], tenant_id="tenant-a"),
    )

    response = client.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "tenant_id": "tenant-b",
            "source": "inflow-lab-data-feeder",
            "csv": "cte_type,traceability_lot_code\nshipping,TLC-FEED-002",
            "result": _sandbox_result(blocked=False),
        },
    )

    assert response.status_code == 403
    assert "Tenant mismatch" in response.json()["detail"]


def test_scoped_principal_supplies_tenant_when_body_omits_it(tmp_path, monkeypatch):
    client = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.write"], tenant_id="tenant-a"),
    )

    response = client.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "source": "inflow-lab-data-feeder",
            "csv": "cte_type,traceability_lot_code\nshipping,TLC-FEED-002",
            "result": _sandbox_result(blocked=False),
        },
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant-a"


def test_workbench_scopes_split_read_and_write_permissions(tmp_path, monkeypatch):
    read_only = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.read"], tenant_id="tenant-a"),
    )
    write_denied = read_only.post(
        "/api/v1/inflow-workbench/scenarios",
        json={
            "tenant_id": "tenant-a",
            "name": "Supplier missing BOL",
            "outcome": "Blocked reference document",
            "csv": "cte_type,traceability_lot_code\nshipping,TLC-1",
        },
    )
    assert write_denied.status_code == 403

    write_only = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.write"], tenant_id="tenant-a"),
    )
    read_denied = write_only.get("/api/v1/inflow-workbench/scenarios")
    assert read_denied.status_code == 403


def test_workbench_run_reads_are_tenant_scoped(tmp_path, monkeypatch):
    writer = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.write"], tenant_id="tenant-a"),
    )
    run_resp = writer.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "source": "inflow-lab-data-feeder",
            "csv": "cte_type,traceability_lot_code\nshipping,TLC-FEED-002",
            "result": _sandbox_result(blocked=False),
        },
    )
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]

    other_tenant_reader = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.read"], tenant_id="tenant-b"),
    )
    response = other_tenant_reader.get(f"/api/v1/inflow-workbench/runs/{run_id}")

    assert response.status_code == 404


def test_lists_built_in_scenarios(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    body = client.get("/api/v1/inflow-workbench/scenarios").json()

    assert {item["id"] for item in body} >= {
        "complete-romaine-flow",
        "missing-shipping-destination",
        "broken-lineage",
    }


def test_persists_custom_scenario_and_saved_run(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    scenario_resp = client.post(
        "/api/v1/inflow-workbench/scenarios",
        json={
            "tenant_id": "tenant-a",
            "name": "Supplier missing BOL",
            "outcome": "Blocked reference document",
            "csv": "cte_type,traceability_lot_code\nshipping,TLC-1",
        },
    )
    assert scenario_resp.status_code == 200
    assert scenario_resp.json()["built_in"] is False

    run_resp = client.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "tenant_id": "tenant-a",
            "source": "inflow-lab-data-feeder",
            "csv": "cte_type,traceability_lot_code\nshipping,TLC-FEED-002",
            "result": _sandbox_result(blocked=True),
        },
    )
    assert run_resp.status_code == 200
    run = run_resp.json()
    assert run["readiness"]["score"] < 100
    assert run["fix_queue"][0]["severity"] == "blocked"
    assert run["commit_gate"]["allowed"] is False

    queue = client.get("/api/v1/inflow-workbench/fix-queue?tenant_id=tenant-a").json()
    assert len(queue) >= 1
    item_id = queue[0]["id"]

    snapshot = client.get("/api/v1/inflow-workbench/readiness/summary?tenant_id=tenant-a").json()
    assert snapshot["run_id"] == run["run_id"]
    assert snapshot["score"] == run["readiness"]["score"]
    assert snapshot["unresolved_fix_count"] >= 1

    patch_resp = client.patch(
        f"/api/v1/inflow-workbench/fix-queue/{item_id}",
        json={"status": "corrected", "owner": "Supplier A"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "corrected"
    assert patch_resp.json()["owner"] == "Supplier A"


def test_commit_gate_enforces_evidence_boundary(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    denied = client.post(
        "/api/v1/inflow-workbench/commit-gate",
        json={
            "mode": "production_evidence",
            "tenant_id": "tenant-a",
            "result": _sandbox_result(blocked=False),
            "authenticated": False,
            "persisted": False,
            "provenance_attached": False,
        },
    ).json()
    assert denied["allowed"] is False
    assert "authenticated session" in " ".join(denied["reasons"])

    allowed = client.post(
        "/api/v1/inflow-workbench/commit-gate",
        json={
            "mode": "production_evidence",
            "tenant_id": "tenant-a",
            "result": _sandbox_result(blocked=False),
            "authenticated": True,
            "persisted": True,
            "provenance_attached": True,
        },
    ).json()
    assert allowed["allowed"] is True
    assert allowed["export_eligible"] is True


def test_uuid_tenant_saved_run_prefers_db_store_and_hashes_inputs(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    captured: dict[str, workbench.WorkbenchRun] = {}

    def fake_db_save_run(run: workbench.WorkbenchRun) -> bool:
        captured["run"] = run
        return True

    monkeypatch.setattr(workbench, "_db_save_run", fake_db_save_run)

    tenant_id = "11111111-1111-1111-1111-111111111111"
    csv = "cte_type,traceability_lot_code\nshipping,TLC-FEED-002"
    response = client.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "tenant_id": tenant_id,
            "source": "inflow-lab-data-feeder",
            "csv": csv,
            "result": _sandbox_result(blocked=False),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == tenant_id
    assert body["input_hash"] == workbench._sha256_text(csv)
    assert len(body["result_hash"]) == 64
    assert captured["run"].commit_decision_id == f"{body['run_id']}:staging"
    assert not (tmp_path / "workbench.json").exists()


def test_tenant_qualified_fix_update_can_use_db_store(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    tenant_id = "22222222-2222-2222-2222-222222222222"
    calls: list[tuple[str, str, str | None]] = []

    def fake_db_update_fix_item(
        item_id: str,
        update_tenant_id: str,
        payload: workbench.UpdateFixItemRequest,
    ) -> workbench.FixQueueItem:
        calls.append((item_id, update_tenant_id, payload.status))
        return workbench.FixQueueItem(
            id=item_id,
            run_id="run-db",
            tenant_id=update_tenant_id,
            title="Row 1 fixed",
            owner=payload.owner or "Supplier A",
            status=payload.status or "corrected",
            severity="warning",
            impact="Ready for replay",
            source="TLC-1",
            created_at="2026-04-30T00:00:00+00:00",
            updated_at="2026-04-30T00:00:00+00:00",
        )

    monkeypatch.setattr(workbench, "_db_update_fix_item", fake_db_update_fix_item)

    response = client.patch(
        f"/api/v1/inflow-workbench/fix-queue/item-1?tenant_id={tenant_id}",
        json={"status": "corrected", "owner": "Supplier A"},
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == tenant_id
    assert calls == [("item-1", tenant_id, "corrected")]
