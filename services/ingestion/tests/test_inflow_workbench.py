from __future__ import annotations

import importlib

import app.authz as authz
import app.inflow_workbench as workbench
import pytest
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.inflow_workbench import router
from app.sandbox.router import router as sandbox_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

sandbox_router_module = importlib.import_module("app.sandbox.router")


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


def _evaluate_csv(monkeypatch, csv_text: str) -> dict:
    monkeypatch.setattr(sandbox_router_module, "_check_sandbox_rate_limit", lambda _ip: None)
    app = FastAPI()
    app.include_router(sandbox_router)
    client = TestClient(app)
    response = client.post("/api/v1/sandbox/evaluate", json={"csv": csv_text})
    assert response.status_code == 200, response.text
    return response.json()


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


def test_wildcard_scope_rejects_cross_tenant_workbench_write(tmp_path, monkeypatch):
    """A tenant-scoped principal carrying wildcard ``*`` permission MUST
    still be denied cross-tenant writes. Wildcard grants action breadth,
    not tenant breadth. Regression for the 2026-05 audit finding
    (inflow_workbench.py:215)."""
    client = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["*"], tenant_id="tenant-a"),
    )

    response = client.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "tenant_id": "tenant-b",  # cross-tenant override attempt
            "source": "inflow-lab-data-feeder",
            "csv": "cte_type,traceability_lot_code\nshipping,TLC-FEED-002",
            "result": _sandbox_result(blocked=False),
        },
    )

    assert response.status_code == 403, response.text
    assert "Tenant mismatch" in response.json()["detail"]


def test_wildcard_scope_same_tenant_workbench_write_still_works(tmp_path, monkeypatch):
    """Regression guard: removing the wildcard tenant bypass must not
    break same-tenant writes for ``*``-scope principals."""
    client = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["*"], tenant_id="tenant-a"),
    )

    response = client.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "tenant_id": "tenant-a",
            "source": "inflow-lab-data-feeder",
            "csv": "cte_type,traceability_lot_code\nshipping,TLC-FEED-002",
            "result": _sandbox_result(blocked=False),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["tenant_id"] == "tenant-a"


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
        "demo-lot-0412-three-missing-ship-tos",
    }


def test_complete_romaine_fixture_is_export_ready_for_workbench(tmp_path, monkeypatch):
    result = _evaluate_csv(monkeypatch, workbench.COMPLETE_ROMAINE_CSV)

    assert result["total_events"] == 5
    assert result["compliant_events"] == 5
    assert result["non_compliant_events"] == 0
    assert result["total_kde_errors"] == 0
    assert result["total_rule_failures"] == 0
    assert result["submission_blocked"] is False
    assert result["blocking_reasons"] == []

    client = _client(tmp_path, monkeypatch)
    run_resp = client.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "tenant_id": "tenant-a",
            "source": "inflow-lab-data-feeder",
            "csv": workbench.COMPLETE_ROMAINE_CSV,
            "result": result,
        },
    )

    assert run_resp.status_code == 200, run_resp.text
    run = run_resp.json()
    assert run["readiness"]["score"] == 100
    assert run["fix_queue"] == []
    assert run["commit_gate"]["allowed"] is True
    assert run["commit_gate"]["export_eligible"] is False
    assert run["commit_gate"]["next_state"] == "production_evidence"


@pytest.mark.parametrize(
    ("csv_text", "expected_reason"),
    [
        (workbench.MISSING_DESTINATION_CSV, "ship_to_location"),
        (workbench.BROKEN_LINEAGE_CSV, "input TLCs"),
    ],
)
def test_negative_fixture_scenarios_still_block_and_create_fix_items(
    tmp_path,
    monkeypatch,
    csv_text: str,
    expected_reason: str,
):
    result = _evaluate_csv(monkeypatch, csv_text)

    assert result["submission_blocked"] is True
    assert result["non_compliant_events"] > 0
    assert result["total_kde_errors"] + result["total_rule_failures"] > 0
    assert any(expected_reason in reason for reason in result["blocking_reasons"])

    client = _client(tmp_path, monkeypatch)
    run_resp = client.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "tenant_id": "tenant-a",
            "source": "inflow-lab-data-feeder",
            "csv": csv_text,
            "result": result,
        },
    )

    assert run_resp.status_code == 200, run_resp.text
    run = run_resp.json()
    assert run["readiness"]["score"] < 100
    assert run["fix_queue"]
    assert run["commit_gate"]["allowed"] is False
    assert run["commit_gate"]["export_eligible"] is False


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


def test_staging_commit_gate_rejects_blocked_evaluation_with_zero_issue_counts(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    result = _sandbox_result(blocked=False)
    result["submission_blocked"] = True

    response = client.post(
        "/api/v1/inflow-workbench/commit-gate",
        json={"mode": "staging", "result": result},
    )

    assert response.status_code == 200, response.text
    decision = response.json()
    assert decision["allowed"] is False
    assert decision["export_eligible"] is False
    assert decision["next_state"] == "preflight"
    assert "blocking rule failures" in " ".join(decision["reasons"])


@pytest.mark.parametrize("kde_errors", [0, 1])
def test_commit_gate_rejects_negative_fix_count(tmp_path, monkeypatch, kde_errors):
    client = _client(tmp_path, monkeypatch)
    result = _sandbox_result(blocked=False)
    result["total_kde_errors"] = kde_errors

    response = client.post(
        "/api/v1/inflow-workbench/commit-gate",
        json={"mode": "staging", "result": result, "unresolved_fix_count": -1},
    )

    assert response.status_code == 422, response.text
    assert any(
        error["loc"] == ["body", "unresolved_fix_count"] and error["type"] == "greater_than_equal"
        for error in response.json()["detail"]
    )


@pytest.mark.parametrize("unresolved_fix_count", [0, 1])
def test_staging_commit_gate_preserves_clean_result_and_open_fix_boundary(tmp_path, monkeypatch, unresolved_fix_count):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/v1/inflow-workbench/commit-gate",
        json={
            "mode": "staging",
            "result": _sandbox_result(blocked=False),
            "unresolved_fix_count": unresolved_fix_count,
        },
    )

    assert response.status_code == 200, response.text
    decision = response.json()
    assert decision["allowed"] is (unresolved_fix_count == 0)
    assert decision["export_eligible"] is False
    assert decision["next_state"] == ("production_evidence" if unresolved_fix_count == 0 else "preflight")


@pytest.mark.parametrize(
    ("negative_count", "positive_count"),
    [
        ("total_kde_errors", "total_rule_failures"),
        ("total_rule_failures", "total_kde_errors"),
        ("non_compliant_events", "total_kde_errors"),
    ],
)
def test_commit_gate_rejects_negative_result_counts_before_cancellation(
    tmp_path, monkeypatch, negative_count, positive_count
):
    client = _client(tmp_path, monkeypatch)
    result = _sandbox_result(blocked=False)
    result[negative_count] = -1
    result[positive_count] = 1

    response = client.post(
        "/api/v1/inflow-workbench/commit-gate",
        json={"mode": "staging", "result": result},
    )

    assert response.status_code == 422, response.text
    assert any(
        error["loc"] == ["body", "result"] and negative_count in error["msg"] for error in response.json()["detail"]
    )


@pytest.mark.parametrize("blocked", [False, True])
def test_preflight_commit_gate_allows_diagnosis_without_export(tmp_path, monkeypatch, blocked):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/v1/inflow-workbench/commit-gate",
        json={"mode": "preflight", "result": _sandbox_result(blocked=blocked)},
    )

    assert response.status_code == 200, response.text
    decision = response.json()
    assert decision["allowed"] is True
    assert decision["export_eligible"] is False
    assert decision["next_state"] == ("preflight" if blocked else "staging")


@pytest.mark.parametrize("result_kind", ["omitted", "null", "empty"])
def test_staging_commit_gate_preserves_optional_result_advisory_behavior(tmp_path, monkeypatch, result_kind):
    client = _client(tmp_path, monkeypatch)
    payload = {"mode": "staging"}
    if result_kind == "null":
        payload["result"] = None
    elif result_kind == "empty":
        result = _sandbox_result(blocked=False)
        result.update(total_events=0, compliant_events=0, events=[])
        payload["result"] = result

    response = client.post("/api/v1/inflow-workbench/commit-gate", json=payload)

    assert response.status_code == 200, response.text
    decision = response.json()
    assert decision["allowed"] is True
    assert decision["export_eligible"] is False
    assert decision["next_state"] == "production_evidence"


@pytest.mark.parametrize("negative_count", ["total_kde_errors", "total_rule_failures", "non_compliant_events"])
def test_saved_run_rejects_negative_result_count_before_persistence(tmp_path, monkeypatch, negative_count):
    client = _client(tmp_path, monkeypatch)
    result = _sandbox_result(blocked=False)
    result[negative_count] = -1
    persisted_runs = []

    def capture_persistence(run):
        persisted_runs.append(run)
        return True

    monkeypatch.setattr(workbench, "_db_save_run", capture_persistence)

    response = client.post("/api/v1/inflow-workbench/runs", json={"result": result})

    assert response.status_code == 422, response.text
    assert persisted_runs == []
    assert not any(tmp_path.glob("workbench*.json"))
    assert any(
        error["loc"] == ["body", "result"] and negative_count in error["msg"] for error in response.json()["detail"]
    )


def test_read_only_principal_cannot_request_commit_gate(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, principal=_principal(scopes=["inflow.read"]))

    response = client.post(
        "/api/v1/inflow-workbench/commit-gate",
        json={"mode": "staging", "result": _sandbox_result(blocked=False)},
    )

    assert response.status_code == 403, response.text


@pytest.mark.parametrize("scopes", [["inflow.write"], ["*"]])
@pytest.mark.parametrize("tenant_source", ["body", "header"])
def test_commit_gate_rejects_cross_tenant_context(tmp_path, monkeypatch, scopes, tenant_source):
    client = _client(tmp_path, monkeypatch, principal=_principal(scopes=scopes, tenant_id="tenant-a"))
    payload = {"mode": "staging", "result": _sandbox_result(blocked=False)}
    headers = {}
    if tenant_source == "body":
        payload["tenant_id"] = "tenant-b"
    else:
        headers["X-Tenant-ID"] = "tenant-b"

    response = client.post("/api/v1/inflow-workbench/commit-gate", json=payload, headers=headers)

    assert response.status_code == 403, response.text
    assert "Tenant mismatch" in response.json()["detail"]


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
    tenant_id = "11111111-1111-1111-1111-111111111111"
    # 2026-05 wildcard-bypass fix (inflow_workbench.py:215): the principal
    # tenant must match the request tenant — wildcard scope no longer
    # waives this cross-check.
    client = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["*"], tenant_id=tenant_id),
    )
    captured: dict[str, workbench.WorkbenchRun] = {}

    def fake_db_save_run(run: workbench.WorkbenchRun) -> bool:
        captured["run"] = run
        return True

    monkeypatch.setattr(workbench, "_db_save_run", fake_db_save_run)

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
    tenant_id = "22222222-2222-2222-2222-222222222222"
    # 2026-05 wildcard-bypass fix: principal must own the tenant being acted on.
    client = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["*"], tenant_id=tenant_id),
    )
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


def test_production_db_failure_returns_503_not_silent_file_fallback(tmp_path, monkeypatch, caplog):
    """#2519: when DB persistence fails in production, save_run must return 503
    instead of silently writing to the ephemeral /tmp file store and returning
    a 2xx that falsely implies durable persistence."""
    monkeypatch.setattr(workbench, "_is_production", lambda: True)
    monkeypatch.setattr(workbench, "_db_save_run", lambda _run: False)
    client = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.write"], tenant_id="tenant-a"),
    )

    with caplog.at_level("ERROR", logger="inflow-workbench"):
        response = client.post(
            "/api/v1/inflow-workbench/runs",
            json={
                "source": "inflow-lab-data-feeder",
                "csv": "cte_type,traceability_lot_code\nshipping,TLC-FEED-002",
                "result": _sandbox_result(blocked=False),
            },
        )

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "Workbench persistence unavailable"
    # No commingled file should have been written in the production failure path.
    assert not any(tmp_path.glob("workbench*.json"))
    assert any("could not persist to DB in production" in rec.message for rec in caplog.records)


def test_db_save_run_failure_logs_exception_with_tenant_and_run(tmp_path, monkeypatch, caplog):
    """#2519: a failing _db_save_run logs the underlying exception with the
    tenant_id and run_id so real outages are observable instead of swallowed."""
    tenant_id = "33333333-3333-3333-3333-333333333333"

    def boom(_db, _tenant):  # _set_tenant_context replacement that always fails
        raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(workbench, "_set_tenant_context", boom)

    run = workbench.WorkbenchRun(
        run_id="run-abc123",
        tenant_id=tenant_id,
        source="inflow-lab",
        csv="",
        result=workbench.SandboxResponse(**_sandbox_result(blocked=False)),
        readiness=workbench.build_readiness_summary(workbench.SandboxResponse(**_sandbox_result(blocked=False))),
        fix_queue=[],
        commit_gate=workbench.decide_commit_gate(workbench.CommitGateRequest(mode="staging", tenant_id=tenant_id)),
        saved_at="2026-04-30T00:00:00+00:00",
    )

    # object() has no .rollback/.close — guard against AttributeError masking
    # the logging assertion by giving the fake session those no-op methods.
    class _FakeSession:
        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(workbench, "_db_session_for_tenant", lambda _tid: _FakeSession())

    with caplog.at_level("ERROR", logger="inflow-workbench"):
        ok = workbench._db_save_run(run)

    assert ok is False
    failure = next(rec for rec in caplog.records if "DB save_run failed" in rec.message)
    assert tenant_id in failure.getMessage()
    assert "run-abc123" in failure.getMessage()


_PROD_UUID_TENANT = "44444444-4444-4444-4444-444444444444"


class _BoomSession:
    """A DB session whose tenant-context/query step will fail (see boom below)."""

    def rollback(self):
        pass

    def close(self):
        pass


def _force_db_read_failure(monkeypatch):
    """Make every _db_* helper hit its exception path as if the DB errored
    mid-read (a reachable session with a failing query). A UUID tenant is
    required so the helpers pass their _tenant_uuid() guard and actually reach
    the DB path — in production tenant ids are always UUIDs."""

    def boom(_db, _tenant):
        raise RuntimeError("simulated DB read outage")

    monkeypatch.setattr(workbench, "_set_tenant_context", boom)
    monkeypatch.setattr(workbench, "_db_session_for_tenant", lambda _tid: _BoomSession())


def test_production_db_read_failure_returns_503_not_silent_empty(tmp_path, monkeypatch, caplog):
    """A read that fails against the DB in production must 503, not fall back to
    the per-worker /tmp store and render as "no saved scenarios" (empty list)."""
    monkeypatch.setattr(workbench, "_is_production", lambda: True)
    _force_db_read_failure(monkeypatch)
    client = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.read"], tenant_id=_PROD_UUID_TENANT),
    )

    with caplog.at_level("ERROR", logger="inflow-workbench"):
        response = client.get("/api/v1/inflow-workbench/scenarios")

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "Workbench persistence unavailable"
    assert any("could not reach the DB in production" in rec.message for rec in caplog.records)


def test_production_db_failure_update_fix_item_returns_503_not_404(tmp_path, monkeypatch):
    """Regression: update_fix_item was left out of the #2519 write-path gate, so
    a DB outage in production surfaced as 404 "not found" instead of 503. It is a
    write endpoint and must fail loudly like save_run/create_scenario."""
    monkeypatch.setattr(workbench, "_is_production", lambda: True)
    _force_db_read_failure(monkeypatch)
    client = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.write"], tenant_id=_PROD_UUID_TENANT),
    )

    response = client.patch(
        "/api/v1/inflow-workbench/fix-queue/fix-does-not-matter",
        json={"status": "corrected"},
    )

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "Workbench persistence unavailable"


def test_non_production_read_failure_still_falls_back_to_file_store(tmp_path, monkeypatch):
    """The DB-less dev/test path is preserved: outside production a failing DB
    read falls back to the file store (built-in scenarios still returned)."""
    monkeypatch.setattr(workbench, "_is_production", lambda: False)
    _force_db_read_failure(monkeypatch)
    client = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.read"], tenant_id=_PROD_UUID_TENANT),
    )

    response = client.get("/api/v1/inflow-workbench/scenarios")

    assert response.status_code == 200, response.text
    assert len(response.json()) >= len(workbench.BUILT_IN_SCENARIOS)


def test_dev_file_store_isolates_tenants(tmp_path, monkeypatch):
    """#2519 acceptance: in dev (non-prod), two tenants saving runs must not
    share one commingled file. Tenant B cannot read tenant A's run."""
    writer_a = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.write"], tenant_id="tenant-a"),
    )
    run_a = writer_a.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "source": "inflow-lab",
            "csv": "cte_type,traceability_lot_code\nshipping,TLC-A",
            "result": _sandbox_result(blocked=False),
        },
    )
    assert run_a.status_code == 200, run_a.text
    run_a_id = run_a.json()["run_id"]

    # Tenant B saves their own run, then tries to read tenant A's run id.
    writer_b = _client(
        tmp_path,
        monkeypatch,
        principal=_principal(scopes=["inflow.write", "inflow.read"], tenant_id="tenant-b"),
    )
    writer_b.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "source": "inflow-lab",
            "csv": "cte_type,traceability_lot_code\nshipping,TLC-B",
            "result": _sandbox_result(blocked=False),
        },
    )

    cross = writer_b.get(f"/api/v1/inflow-workbench/runs/{run_a_id}")
    assert cross.status_code == 404, cross.text

    # The two tenants must occupy distinct files on disk.
    assert workbench._store_path("tenant-a") != workbench._store_path("tenant-b")


def test_demo_lot_0412_three_missing_ship_tos_blocks_readiness(tmp_path, monkeypatch):
    """DEMO-LOT-0412 fixture has 3 shipping events all missing ship_to_location.
    This must produce submission_blocked=True, ≥3 fix queue items (one per shipping),
    commit_gate.allowed=False, and export_eligible=False. No fake green."""
    result = _evaluate_csv(monkeypatch, workbench.THREE_MISSING_SHIPTO_CSV)

    assert result["submission_blocked"] is True, "Submission must be blocked"
    assert result["non_compliant_events"] >= 3, "At least 3 non-compliant shipping events expected"
    assert result["total_kde_errors"] >= 3, "At least 3 KDE errors (ship_to_location) expected"
    assert any("ship_to" in reason.lower() for reason in result["blocking_reasons"]), (
        "Blocking reasons must mention ship_to"
    )

    client = _client(tmp_path, monkeypatch)
    run_resp = client.post(
        "/api/v1/inflow-workbench/runs",
        json={
            "tenant_id": "tenant-a",
            "source": "inflow-lab-data-feeder",
            "csv": workbench.THREE_MISSING_SHIPTO_CSV,
            "result": result,
        },
    )

    assert run_resp.status_code == 200, run_resp.text
    run = run_resp.json()

    # Readiness must be degraded, not fake green
    assert run["readiness"]["score"] < 100, "Readiness score must be below 100 (blocked condition)"
    assert run["readiness"]["label"] in {"blocked", "needs remediation"}, (
        f"Readiness label must indicate blocking, got: {run['readiness']['label']}"
    )

    # Fix queue must have ≥3 items for the 3 shipping defects
    assert len(run["fix_queue"]) >= 3, f"Fix queue must have ≥3 items, got {len(run['fix_queue'])}"
    ship_to_fixes = [
        item
        for item in run["fix_queue"]
        if "ship" in item["title"].lower() and item["severity"] in {"blocked", "warning"}
    ]
    assert len(ship_to_fixes) >= 3, f"At least 3 shipping fix items expected, found {len(ship_to_fixes)}"

    # Commit gate must remain closed
    assert run["commit_gate"]["allowed"] is False, "Commit gate must be closed"
    assert run["commit_gate"]["export_eligible"] is False, "Must NOT be export eligible"
