"""Tests for ``services/ingestion/app/proof_recall_router.py``.

Public recall-drill endpoint. Coverage:

- Tenant isolation: endpoint accepts no tenant input and never reads
  tenant data. We assert (a) no auth is required, (b) the module does
  not import any tenant-scoped clients, and (c) calls succeed without
  a tenant header / API key.
- Schema validation: response shape matches the public spec; the
  endpoint takes no body so we exercise GET-rejection / extra-body
  tolerance.
- Failure modes: the 6th request inside a one-minute window returns
  429 (rate-limit triggers), and the response is deterministic across
  successive successful calls.
"""

from __future__ import annotations

import os
import sys
from itertools import count

import app.proof_recall_router as proof_recall_module
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address

FDA_24H_MANDATE_SECONDS = proof_recall_module.FDA_24H_MANDATE_SECONDS
FROZEN_LOT_CODE = proof_recall_module.FROZEN_LOT_CODE
OUTPUT_CSV_URL = proof_recall_module.OUTPUT_CSV_URL
proof_recall_router = proof_recall_module.router
limiter = proof_recall_module.limiter
_client_counter = count(1)


def _build_app() -> FastAPI:
    app = FastAPI()
    # slowapi requires the limiter to be attached to app.state for the
    # ``@limiter.limit`` decorator to find a key function.
    app.state.limiter = limiter
    app.include_router(proof_recall_router)
    return app


def _build_isolated_rate_limit_app() -> FastAPI:
    local_limiter = Limiter(key_func=get_remote_address)
    app = FastAPI()
    app.state.limiter = local_limiter

    @app.post("/api/v1/proof/recall-drill")
    @local_limiter.limit("5/minute")
    async def isolated_recall_drill(request: Request):
        return proof_recall_module._build_response()

    return app


def _reset_limiter_state() -> None:
    candidates = {limiter, proof_recall_module.limiter}
    for module_name in ("shared.rate_limit", "services.shared.rate_limit"):
        module = sys.modules.get(module_name)
        current = getattr(module, "limiter", None)
        if current is not None:
            candidates.add(current)

    for candidate in candidates:
        for reset_target in (
            candidate,
            getattr(candidate, "_storage", None),
            getattr(getattr(candidate, "limiter", None), "storage", None),
            getattr(getattr(candidate, "_limiter", None), "storage", None),
        ):
            if reset_target is None:
                continue
            if hasattr(reset_target, "reset"):
                reset_target.reset()
            elif hasattr(reset_target, "clear"):
                reset_target.clear()
            for attr in ("storage", "events", "expirations", "_MemoryStorage__expire_events"):
                store = getattr(reset_target, attr, None)
                if hasattr(store, "clear"):
                    store.clear()


@pytest.fixture
def client() -> TestClient:
    # Reset the shared slowapi limiter state between tests so the
    # 5/min limit doesn't leak across test cases. The host must be
    # unique per *process*, not just per test: ``count`` restarts at 1
    # in every pytest process, so without the pid the rate-limit key
    # collides across back-to-back runs whenever the limiter storage
    # is shared (e.g. RATELIMIT_STORAGE_URL pointing at Redis).
    _reset_limiter_state()
    host = f"proof-recall-test-{os.getpid()}-{next(_client_counter)}"
    return TestClient(_build_app(), client=(host, 50000))


# ---------------------------------------------------------------------------
# Tenant-isolation guarantees
# ---------------------------------------------------------------------------
class TestTenantIsolation:
    def test_endpoint_accepts_no_tenant_header_and_works(self, client: TestClient):
        """The endpoint must work with zero tenant context."""
        # NOTE: no X-Tenant-ID header, no API key, no body.
        resp = client.post("/api/v1/proof/recall-drill")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["lot_code"] == FROZEN_LOT_CODE
        assert data["output_csv_url"] == OUTPUT_CSV_URL

    def test_module_does_not_import_tenant_scoped_clients(self):
        """Defense-in-depth: the recall-drill module must not import
        any tenant-scoped persistence client. Static check restricted
        to actual import statements (docstring / comment mentions are
        permitted because they describe the constraint).
        """
        from app import proof_recall_router as mod

        src = open(mod.__file__).read()
        import_lines = [ln for ln in src.splitlines() if ln.lstrip().startswith(("import ", "from "))]
        forbidden = [
            "shared.database",
            "shared.cte_persistence",
            "CTEPersistence",
            "SessionLocal",
            "neo4j",
            "Neo4jClient",
            "shared.canonical_persistence",
            "shared.tenant_settings",
        ]
        joined = "\n".join(import_lines)
        offenders = [tok for tok in forbidden if tok in joined]
        assert not offenders, f"proof_recall_router imports tenant-scoped symbols: {offenders}\nImport lines:\n{joined}"

    def test_tenant_id_header_is_ignored(self, client: TestClient):
        """A caller-supplied tenant header must not change behavior."""
        resp_a = client.post("/api/v1/proof/recall-drill")
        resp_b = client.post(
            "/api/v1/proof/recall-drill",
            headers={"X-Tenant-ID": "00000000-0000-0000-0000-000000000000"},
        )
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        # The drill output (modulo timestamp) must be identical.
        a = resp_a.json()
        b = resp_b.json()
        a.pop("timestamp", None)
        b.pop("timestamp", None)
        assert a == b


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
class TestSchemaValidation:
    def test_response_shape_matches_spec(self, client: TestClient):
        resp = client.post("/api/v1/proof/recall-drill")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Top-level fields per the public spec.
        assert set(data.keys()) >= {
            "steps",
            "time_to_trace_seconds",
            "output_csv_url",
            "lot_code",
            "fda_24h_mandate_seconds",
        }

        # Constants.
        assert data["fda_24h_mandate_seconds"] == FDA_24H_MANDATE_SECONDS
        assert data["lot_code"] == FROZEN_LOT_CODE
        assert data["output_csv_url"] == OUTPUT_CSV_URL

        # time_to_trace_seconds must be a positive number well under
        # the FDA 24h mandate (otherwise the demo is misleading).
        assert isinstance(data["time_to_trace_seconds"], (int, float))
        assert 0 < data["time_to_trace_seconds"] < FDA_24H_MANDATE_SECONDS

        # Steps shape.
        steps = data["steps"]
        assert isinstance(steps, list) and len(steps) >= 1
        valid_status = {"ok", "warning", "error"}
        total_ms = 0
        for s in steps:
            assert set(s.keys()) >= {"name", "duration_ms", "status"}
            assert isinstance(s["name"], str) and s["name"]
            assert isinstance(s["duration_ms"], int) and s["duration_ms"] >= 0
            assert s["status"] in valid_status
            total_ms += s["duration_ms"]

        # time_to_trace_seconds must equal the sum of step durations
        # (deterministic by construction).
        assert abs(data["time_to_trace_seconds"] - total_ms / 1000.0) < 1e-6

    def test_get_method_not_allowed(self, client: TestClient):
        """GET on a POST-only route returns 405."""
        resp = client.get("/api/v1/proof/recall-drill")
        assert resp.status_code == 405

    def test_extra_body_is_tolerated(self, client: TestClient):
        """Endpoint takes no body. Sending one must not break it
        (FastAPI default: extra body is ignored when no model is
        declared)."""
        resp = client.post(
            "/api/v1/proof/recall-drill",
            json={"unexpected": "payload"},
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Failure modes — rate limit + determinism
# ---------------------------------------------------------------------------
class TestFailureModes:
    def test_rate_limit_triggers_at_sixth_request(self):
        """5 requests/minute/IP -- the 6th must be 429."""
        endpoint_key = (
            f"{proof_recall_module.run_recall_drill.__module__}."
            f"{proof_recall_module.run_recall_drill.__name__}"
        )
        registered_limits = limiter._route_limits.get(endpoint_key, [])
        assert any(str(limit.limit) == "5 per 1 minute" for limit in registered_limits)

        host = f"proof-recall-limit-{os.getpid()}-{next(_client_counter)}"
        with TestClient(_build_isolated_rate_limit_app(), client=(host, 50000)) as isolated_client:
            for i in range(5):
                resp = isolated_client.post("/api/v1/proof/recall-drill")
                assert resp.status_code == 200, (
                    f"request {i + 1}/5 unexpectedly failed: {resp.status_code} {resp.text}"
                )

            resp = isolated_client.post("/api/v1/proof/recall-drill")
            assert resp.status_code == 429, resp.text

    def test_response_is_deterministic_across_calls(self, client: TestClient):
        """Same input -> same output -- required for the cached
        ``output_csv_url`` to remain valid.
        """
        a = client.post("/api/v1/proof/recall-drill").json()
        b = client.post("/api/v1/proof/recall-drill").json()
        # Strip timestamps before comparing.
        a.pop("timestamp", None)
        b.pop("timestamp", None)
        assert a == b
