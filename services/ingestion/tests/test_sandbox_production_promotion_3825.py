"""Promotion-gate evidence for the `sandbox` router — #3825.

`PRODUCTION_SURFACE.md` ("Promotion Rule") requires a route entering the
production surface to carry a tenant-isolation test, a schema/contract test, a
failure-mode test for invalid input, documented ownership, and a stated reason
it belongs to the FSMA pipeline. The first three are in this file; the last two
are in `PRODUCTION_SURFACE.md` and `docs/engineering/ROUTER_SURFACE.md`.

The promotion rests entirely on the evaluator being STATELESS — it persists
nothing, takes no tenant identifier, and reads no tenant data, so there is no
tenant boundary for it to cross. These tests exist to fail loudly if that ever
stops being true, and to keep the persisted share endpoints out of the
production allowlist.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.sandbox.models import (  # noqa: E402
    SandboxEvent,
    SandboxRequest,
    SandboxTraceRequest,
)
from app.sandbox.router import router as sandbox_router  # noqa: E402

from server.router_policy import (  # noqa: E402
    EXPERIMENTAL_ROUTERS,
    PRODUCTION_ENABLED_ROUTERS,
    VALID_ROUTER_NAMES,
    RouterPolicy,
)

sandbox_router_mod = sys.modules["app.sandbox.router"]

SAMPLE_CSV = (
    "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,"
    "location_name,timestamp,reference_document\n"
    "shipping,TLC-3825-001,Romaine Lettuce,100,cases,Valley Farms,"
    "2026-11-01T14:00:00Z,BOL-3825\n"
)


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """The per-IP limiter is covered by its own tests; keep it out of the way."""
    monkeypatch.setattr(sandbox_router_mod, "_check_sandbox_rate_limit", lambda ip: None)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(sandbox_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Release-gate membership
# ---------------------------------------------------------------------------


class TestReleaseGate:
    def test_sandbox_is_release_approved(self):
        assert "sandbox" in PRODUCTION_ENABLED_ROUTERS

    def test_sandbox_is_no_longer_experimental(self):
        assert "sandbox" not in EXPERIMENTAL_ROUTERS

    def test_share_owner_is_a_known_router(self):
        assert "sandbox_share" in VALID_ROUTER_NAMES
        assert "sandbox_share" in EXPERIMENTAL_ROUTERS

    def test_share_owner_is_not_release_approved(self):
        """The whole point of the #3825 split.

        `sandbox_share` writes caller-supplied CSV into `sandbox_shares` with
        no auth and no tenant. If a future change promotes it, this fails.
        """
        assert "sandbox_share" not in PRODUCTION_ENABLED_ROUTERS

    def test_production_policy_enables_evaluator_but_not_share(self):
        policy = RouterPolicy.from_environment(
            production=True,
            environ={"ENABLED_ROUTERS": ",".join(sorted(PRODUCTION_ENABLED_ROUTERS))},
        )
        assert policy.is_enabled("sandbox") is True
        assert policy.is_enabled("sandbox_share") is False


# ---------------------------------------------------------------------------
# Tenant isolation — by absence, which is the claim being made
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    def test_router_exposes_only_the_two_stateless_routes(self):
        paths = {route.path for route in sandbox_router.routes}
        assert paths == {"/api/v1/sandbox/evaluate", "/api/v1/sandbox/trace"}, (
            f"sandbox router exposes {sorted(paths)}. Promotion (#3825) covered the "
            f"stateless evaluator only — a new route here enters production without "
            f"its own promotion review."
        )

    def test_router_module_has_no_database_or_persistence_path(self):
        """Statelessness is the promotion's entire basis, so assert it in source."""
        source = Path(sandbox_router_mod.__file__).read_text(encoding="utf-8")
        for forbidden in ("shared.database", "get_db", "sqlalchemy", "INSERT", "UPDATE", "DELETE"):
            assert forbidden not in source, (
                f"{forbidden!r} appears in the production-enabled sandbox router. "
                f"#3825 promoted it because it persists nothing; a write path makes "
                f"it an unauthenticated, tenant-less writer and voids that review."
            )

    def test_no_route_accepts_a_tenant_path_parameter(self):
        """No caller-supplied tenant id — the repo's hard rule."""
        for route in sandbox_router.routes:
            for field_name in getattr(route, "param_convertors", {}):
                assert "tenant" not in field_name.lower(), (
                    f"{route.path} takes a tenant-shaped path parameter {field_name!r}"
                )

    @pytest.mark.parametrize("model", [SandboxRequest, SandboxEvent, SandboxTraceRequest])
    def test_request_models_declare_no_tenant_field(self, model):
        """Checked on the models themselves, not FastAPI internals, so the
        assertion survives framework upgrades."""
        for field_name in model.model_fields:
            assert "tenant" not in field_name.lower(), (
                f"{model.__name__} declares a tenant-shaped field {field_name!r}; the "
                f"sandbox must never take a caller-supplied tenant id (#3825)."
            )

    def test_caller_supplied_tenant_id_is_ignored_not_honored(self, client):
        """An attacker-supplied tenant id must not be echoed or acted on."""
        resp = client.post(
            "/api/v1/sandbox/evaluate",
            json={"csv": SAMPLE_CSV, "tenant_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 200
        assert "tenant" not in resp.text.lower()

    def test_tenant_header_does_not_change_the_result(self, client):
        """Same input, with and without X-Tenant-ID, yields the same evaluation."""
        payload = {"csv": SAMPLE_CSV}
        plain = client.post("/api/v1/sandbox/evaluate", json=payload)
        spoofed = client.post(
            "/api/v1/sandbox/evaluate",
            json=payload,
            headers={"X-Tenant-ID": "00000000-0000-0000-0000-000000000001"},
        )
        assert plain.status_code == spoofed.status_code == 200
        assert plain.json() == spoofed.json()


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


class TestContract:
    def test_evaluate_returns_the_documented_summary_shape(self, client):
        resp = client.post("/api/v1/sandbox/evaluate", json={"csv": SAMPLE_CSV})
        assert resp.status_code == 200
        body = resp.json()

        for key in (
            "total_events",
            "compliant_events",
            "non_compliant_events",
            "total_kde_errors",
            "total_rule_failures",
            "submission_blocked",
            "blocking_reasons",
            "events",
        ):
            assert key in body, f"missing {key!r} from the evaluate contract"

        assert body["total_events"] == 1
        assert isinstance(body["submission_blocked"], bool)
        assert isinstance(body["blocking_reasons"], list)
        assert len(body["events"]) == 1

        event = body["events"][0]
        for key in ("event_index", "cte_type", "traceability_lot_code", "compliant", "all_results"):
            assert key in event, f"missing {key!r} from the per-event contract"
        assert event["cte_type"] == "shipping"
        assert event["traceability_lot_code"] == "TLC-3825-001"

    def test_rules_actually_run(self, client):
        """A contract test that passed on an empty rule set would prove nothing."""
        resp = client.post("/api/v1/sandbox/evaluate", json={"csv": SAMPLE_CSV})
        event = resp.json()["events"][0]

        assert event["rules_evaluated"] > 0
        # Tallies must account for every returned result. `skip` is a real
        # bucket alongside pass/fail/warn, so the counted three need not sum
        # to the total — but the result list must.
        assert event["rules_evaluated"] == len(event["all_results"])
        buckets = Counter(result["result"] for result in event["all_results"])
        assert buckets["pass"] == event["rules_passed"]
        assert buckets["fail"] == event["rules_failed"]
        assert buckets["warn"] == event["rules_warned"]
        assert set(buckets) <= {"pass", "fail", "warn", "skip"}, f"unknown verdict in {dict(buckets)}"

        # Real rule content, not placeholders.
        assert any(result["rule_title"] for result in event["all_results"])
        assert any(result.get("citation") for result in event["all_results"])


# ---------------------------------------------------------------------------
# Failure modes for invalid input
# ---------------------------------------------------------------------------


class TestFailureModes:
    def test_neither_events_nor_csv_is_rejected(self, client):
        resp = client.post("/api/v1/sandbox/evaluate", json={})
        assert resp.status_code == 400
        assert "events" in resp.json()["detail"].lower()

    def test_csv_without_cte_type_is_rejected(self, client):
        resp = client.post(
            "/api/v1/sandbox/evaluate",
            json={"csv": "product_description,quantity\nRomaine,100\n"},
        )
        assert resp.status_code == 400
        assert "cte_type" in resp.json()["detail"]

    def test_oversize_csv_is_rejected_before_parsing(self, client):
        resp = client.post("/api/v1/sandbox/evaluate", json={"csv": "x" * 2_000_001})
        assert resp.status_code == 413
        assert "2MB" in resp.json()["detail"]

    def test_event_count_cap_is_enforced(self, client):
        header = "cte_type,traceability_lot_code\n"
        rows = "".join(f"shipping,TLC-{i}\n" for i in range(501))
        resp = client.post("/api/v1/sandbox/evaluate", json={"csv": header + rows})
        assert resp.status_code == 400
        assert "500" in resp.json()["detail"]

    def test_malformed_body_is_a_422_not_a_500(self, client):
        resp = client.post("/api/v1/sandbox/evaluate", json={"events": "not-a-list"})
        assert resp.status_code == 422

    def test_garbage_csv_does_not_crash_the_endpoint(self, client):
        resp = client.post("/api/v1/sandbox/evaluate", json={"csv": "\x00\x01 not,really;csv\n\n"})
        assert resp.status_code in {400, 413}, f"unexpected {resp.status_code}: {resp.text[:200]}"
