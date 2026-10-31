"""The API key's tenant is the single source of truth on every graph route.

Two dependencies resolve a tenant on the graph routers. ``require_api_key``
stores the authenticated principal on ``request.state.api_key``;
``get_current_tenant_id`` reads ``request.state.tenant_id`` (set by
``TenantContextMiddleware`` from a JWT claim or the internal header pair) and
falls back to that principal. Both seed the RLS contextvar that the SQLAlchemy
begin-hook turns into the Postgres tenant GUC, so the last writer decides which
tenant's rows RLS exposes. Since #3698 the key resolves first at router level,
which made the middleware tenant the last writer: a request carrying key tenant
A and middleware tenant B operated on B's rows on every router that did not
call ``reconcile_tenant_scope`` (recall, traceability, lineage).

``get_current_tenant_id`` now treats the principal's tenant as authoritative and
the middleware tenant as an assertion that must match it. A divergence is
rejected with 409 ``E_TENANT_MISMATCH`` (the ``reconcile_tenant_scope``
contract, #2511) before the handler runs. These tests drive the real middleware
and the real ``require_api_key`` (env bypass), with no dependency overrides,
against the router tree the monolith mounts.
"""

from __future__ import annotations

import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

REPO_ROOT = Path(__file__).resolve().parents[3]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "services")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.middleware.tenant_context import TenantContextMiddleware  # noqa: E402
from shared.tenant_context import get_rls_tenant_id  # noqa: E402

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
BYPASS_TOKEN = "graph-key-tenant-truth-test"  # noqa: S105 — test-only env bypass value
INTERNAL_SECRET = "graph-key-tenant-truth-internal"  # noqa: S105 — test-only header secret  # pragma: allowlist secret

KEY_ONLY = {"X-RegEngine-API-Key": BYPASS_TOKEN}

RECALL_ENGINE = "services.graph.app.routers.fsma.recall.get_recall_engine"
TRACE_NEO4J = "services.graph.app.routers.fsma.traceability.Neo4jClient"
LINEAGE_NEO4J = "services.graph.app.routers.lineage_traversal.Neo4jClient"
LABELS_NEO4J = "services.graph.app.routers.labels.Neo4jClient"

# A body that passes the labels request model, so the only thing that can stop
# the write is the tenant check.
LABEL_BATCH = {
    "packer_gln": "0614141000005",
    "product": {"gtin": "00614141000012", "description": "Romaine hearts", "expected_units": 10},
    "traceability": {"lot_number": "LOT-1", "pack_date": "2026-10-01"},
    "quantity": 1,
}


class _JwtClaimStub(BaseHTTPMiddleware):
    """Stand-in for the JWT layer: a validated claims dict on ``request.state.user``.

    Runs ahead of ``TenantContextMiddleware`` (added after it, so outermost), which
    reads the claim as its first tenant source. ``request.state`` is backed by the
    ASGI scope, so the value is visible to every layer below.
    """

    def __init__(self, app, tenant: str):
        super().__init__(app)
        self._tenant = tenant

    async def dispatch(self, request, call_next):
        request.state.user = {"tenant_id": self._tenant}
        return await call_next(request)


@pytest.fixture(autouse=True)
def _rate_limiter_off(monkeypatch):
    """Keep these GETs out of the shared 10/min quotas without touching Redis."""
    from shared.rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture
def _env(monkeypatch):
    """Real ``require_api_key`` via its test bypass, real internal-header secret."""
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_BYPASS_TOKEN", BYPASS_TOKEN)
    monkeypatch.setenv("AUTH_TEST_BYPASS_TENANT_ID", TENANT_A)
    monkeypatch.setenv("REGENGINE_INTERNAL_SECRET", INTERNAL_SECRET)


def _app(jwt_tenant: str | None = None) -> FastAPI:
    """The whole graph router tree behind the real tenant middleware, as the monolith mounts it."""
    from services.graph.app import routes as graph_routes

    app = FastAPI()
    app.add_middleware(TenantContextMiddleware)
    if jwt_tenant is not None:
        app.add_middleware(_JwtClaimStub, tenant=jwt_tenant)
    app.include_router(graph_routes.router, prefix="/api/v1")
    return app


def _with_middleware_tenant(tenant: str) -> dict[str, str]:
    """Key plus the authenticated internal header pair that resolves ``tenant`` in the middleware."""
    return {**KEY_ONLY, "X-RegEngine-Tenant-ID": tenant, "X-RegEngine-Internal-Secret": INTERNAL_SECRET}


def _recall_engine_stub(seen: list[tuple[str, str | None]]) -> MagicMock:
    """A recall engine whose SLA lookup records the tenant it was asked for and the RLS tenant in effect."""
    engine = MagicMock()

    def _sla(tenant_str: str) -> dict:
        seen.append((tenant_str, get_rls_tenant_id()))
        return {"sla_compliance_rate": 100, "total_drills": 0, "avg_trace_time": 0}

    engine.get_sla_metrics.side_effect = _sla
    return engine


def _neo4j_stub(seen: list[str | None]) -> MagicMock:
    """A Neo4jClient double whose construction records the RLS tenant in effect."""
    cls = MagicMock()
    cls.get_tenant_database_name.return_value = "tenant-db"
    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=MagicMock())
    instance.__aexit__ = AsyncMock(return_value=False)

    def _construct(**_kwargs):
        seen.append(get_rls_tenant_id())
        return instance

    cls.side_effect = _construct
    return cls


# ── Negative path: a middleware tenant that differs from the key tenant ─────────


@pytest.mark.parametrize(
    "method, url, body, data_layer",
    [
        ("GET", "/api/v1/fsma/recall/sla", None, RECALL_ENGINE),
        ("POST", "/api/v1/fsma/recall/schedule", {}, RECALL_ENGINE),
        ("GET", "/api/v1/fsma/traceability/timeline/LOT-1", None, TRACE_NEO4J),
        ("GET", "/api/v1/lineage/LOT-1/history", None, LINEAGE_NEO4J),
        ("POST", "/api/v1/labels/batch/init", LABEL_BATCH, LABELS_NEO4J),
        # The science handlers answer 501 themselves; the 409 must still come first.
        ("GET", "/api/v1/fsma/science/mass-balance/LOT-1", None, None),
    ],
)
def test_middleware_tenant_that_differs_from_key_tenant_is_rejected(_env, method, url, body, data_layer):
    """Key tenant A + authenticated internal header for tenant B: 409, handler never reached."""
    client = TestClient(_app(), raise_server_exceptions=False)
    with ExitStack() as stack:
        entry = stack.enter_context(patch(data_layer)) if data_layer else None
        resp = client.request(method, url, json=body, headers=_with_middleware_tenant(TENANT_B))

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "E_TENANT_MISMATCH"
    if entry is not None:
        assert entry.mock_calls == [], f"{method} {url} reached its data layer with a divergent tenant"


def test_jwt_claim_tenant_that_differs_from_key_tenant_is_rejected(_env):
    """The middleware's first tenant source, a validated JWT claim, is held to the same check."""
    client = TestClient(_app(jwt_tenant=TENANT_B), raise_server_exceptions=False)
    with patch(RECALL_ENGINE) as entry:
        resp = client.get("/api/v1/fsma/recall/sla", headers=KEY_ONLY)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "E_TENANT_MISMATCH"
    assert entry.mock_calls == []


# ── Happy paths: the key tenant drives the handler and the RLS contextvar ───────


def test_key_only_recall_request_runs_as_the_key_tenant(_env):
    seen: list[tuple[str, str | None]] = []
    client = TestClient(_app(), raise_server_exceptions=False)
    with patch(RECALL_ENGINE, return_value=_recall_engine_stub(seen)):
        resp = client.get("/api/v1/fsma/recall/sla", headers=KEY_ONLY)

    assert resp.status_code == 200, resp.text
    assert resp.json()["tenant_id"] == TENANT_A
    # The handler scoped the engine call to the key tenant, and the RLS
    # contextvar the Postgres begin-hook would read held the same tenant.
    assert seen == [(TENANT_A, TENANT_A)]


def test_middleware_tenant_that_matches_key_tenant_is_accepted(_env):
    """Agreement between the two sources is not a mismatch: no 409 on legitimate requests."""
    seen: list[tuple[str, str | None]] = []
    client = TestClient(_app(), raise_server_exceptions=False)
    with patch(RECALL_ENGINE, return_value=_recall_engine_stub(seen)):
        resp = client.get("/api/v1/fsma/recall/sla", headers=_with_middleware_tenant(TENANT_A))

    assert resp.status_code == 200, resp.text
    assert seen == [(TENANT_A, TENANT_A)]


def test_jwt_claim_tenant_that_matches_key_tenant_is_accepted(_env):
    """A JWT claim naming the key's own tenant is agreement, not a mismatch."""
    seen: list[tuple[str, str | None]] = []
    client = TestClient(_app(jwt_tenant=TENANT_A), raise_server_exceptions=False)
    with patch(RECALL_ENGINE, return_value=_recall_engine_stub(seen)):
        resp = client.get("/api/v1/fsma/recall/sla", headers=KEY_ONLY)

    assert resp.status_code == 200, resp.text
    assert seen == [(TENANT_A, TENANT_A)]


def test_rejected_divergent_request_does_not_taint_the_next_request(_env):
    """Same client, two requests: a 409 for a tenant-B assertion leaves nothing behind for the key-only request that follows."""
    seen: list[tuple[str, str | None]] = []
    client = TestClient(_app(), raise_server_exceptions=False)
    with patch(RECALL_ENGINE, return_value=_recall_engine_stub(seen)):
        rejected = client.get("/api/v1/fsma/recall/sla", headers=_with_middleware_tenant(TENANT_B))
        accepted = client.get("/api/v1/fsma/recall/sla", headers=KEY_ONLY)

    assert rejected.status_code == 409, rejected.text
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["tenant_id"] == TENANT_A
    # Only the second request reached the engine, and it ran as A with RLS seeded A.
    assert seen == [(TENANT_A, TENANT_A)]


def test_key_only_traceability_request_runs_as_the_key_tenant(_env):
    seen: list[str | None] = []
    client = TestClient(_app(), raise_server_exceptions=False)
    with ExitStack() as stack:
        stack.enter_context(patch(TRACE_NEO4J, _neo4j_stub(seen)))
        timeline = AsyncMock(return_value=[])
        stack.enter_context(patch("services.graph.app.routers.fsma.traceability.get_lot_timeline", timeline))
        audit = MagicMock()
        audit.alog = AsyncMock()
        stack.enter_context(patch("services.graph.app.routers.fsma.traceability.get_audit_log", return_value=audit))
        resp = client.get("/api/v1/fsma/traceability/timeline/LOT-1", headers=KEY_ONLY)

    assert resp.status_code == 200, resp.text
    assert timeline.await_count == 1
    assert timeline.await_args.args[2] == TENANT_A
    assert audit.alog.await_args.kwargs["tenant_id"] == TENANT_A
    assert seen == [TENANT_A]
