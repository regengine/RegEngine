"""Backend auth boundary for the frontend public rewrites.

Audit re-frontend finding 7: ``frontend/next.config.js`` rewrites four
public API paths straight to this service at the edge, bypassing the
frontend auth preflight (``requireProxyAuth`` / ``validateProxySession``).
That is intentional, external API-key and webhook callers cannot pass the
browser session gate, but it leaves this backend as the ONLY gate on those
paths. If the backend side ever loosens, the unauthenticated
internet-facing surface widens silently.

This module pins the intended surface: every rewritten path that serves
tenant data must reject callers with no credential (401/403), and the one
intentional exception (``/health``, a public liveness probe) must stay
credential-free so monitoring keeps working.

Rewritten paths covered (see ``frontend/next.config.js`` rewrites):
    /api/v1/records      -> canonical_router (requires records.read)
    /api/v1/records/*    -> canonical_router (requires records.read)
    /api/v1/fda/*        -> fda_export router (requires fda.* + subscription)
    /api/v1/webhooks/*   -> webhook_router_v2 (requires API key + HMAC + subscription)
    /health              -> routes_health_metrics (intentionally public)
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app import authz  # noqa: E402
from app.canonical_router import router as canonical_router  # noqa: E402
from app.fda_export.router import router as fda_router  # noqa: E402
from app.routes_health_metrics import router as health_router  # noqa: E402
from app.webhook_router_v2.routes import router as webhook_router  # noqa: E402
from shared.database import get_db_session  # noqa: E402

TENANT_ID = "00000000-0000-0000-0000-000000000111"

# Rejection statuses: 401 (missing/invalid credential) or 403 (valid
# credential without the required scope). Either one keeps an
# unauthenticated caller out; anything else (2xx, 404, 422, 5xx reached
# without an auth check) means the gate has loosened.
REJECTED = (401, 403)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(canonical_router)
    app.include_router(fda_router)
    app.include_router(webhook_router)
    app.include_router(health_router)
    # Neutralize the database layer: auth dependencies run before any DB
    # access, so an unauthenticated request must be rejected before this
    # override matters. If auth is ever loosened, endpoints fall through
    # to a None session (503/404), never to real data.
    app.dependency_overrides[get_db_session] = lambda: None
    return app


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    # Fail closed even if the test runner inherits a dev-like environment:
    # without this, the dev-open fallback would authenticate nobody as
    # everybody and the rejection assertions below would be meaningless.
    monkeypatch.setattr(authz, "_is_dev_env", lambda: False)
    authz._get_auth_limiter().reset("testclient")
    return TestClient(_build_app())


def _webhook_body() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "source": "audit-probe",
        "events": [
            {
                "cte_type": "shipping",
                "traceability_lot_code": "TLC-AUDIT-001",
                "product_description": "audit probe apples",
                "quantity": 1,
                "unit_of_measure": "cases",
                "timestamp": now,
            }
        ],
    }


class TestPublicRewriteAuthBoundary:
    def test_records_list_rejects_unauthenticated(self, client: TestClient) -> None:
        resp = client.get("/api/v1/records", params={"tenant_id": TENANT_ID})
        assert resp.status_code in REJECTED, (
            f"GET /api/v1/records answered {resp.status_code} with no credential; "
            "the frontend rewrite bypasses its auth preflight, so the backend "
            "must be the gate."
        )

    def test_records_detail_rejects_unauthenticated(self, client: TestClient) -> None:
        resp = client.get("/api/v1/records/evt-no-such-event", params={"tenant_id": TENANT_ID})
        assert resp.status_code in REJECTED, (
            f"GET /api/v1/records/{{event_id}} answered {resp.status_code} with no "
            "credential; the frontend rewrite bypasses its auth preflight, so "
            "the backend must be the gate."
        )

    def test_fda_export_rejects_unauthenticated(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/fda/export",
            params={"tlc": "TLC-AUDIT-001", "tenant_id": TENANT_ID},
        )
        assert resp.status_code in REJECTED, (
            f"GET /api/v1/fda/export answered {resp.status_code} with no credential; "
            "the frontend rewrite bypasses its auth preflight, so the backend "
            "must be the gate."
        )

    def test_webhook_ingest_rejects_unauthenticated(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=_webhook_body(),
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert resp.status_code in REJECTED, (
            f"POST /api/v1/webhooks/ingest answered {resp.status_code} with no "
            "credential; the frontend rewrite bypasses its auth preflight, so "
            "the backend must be the gate."
        )

    def test_health_stays_public(self, client: TestClient) -> None:
        # Intentional exception: /health is a public liveness probe (polled by
        # the platform with no credential). This pins that decision so a
        # future auth requirement here, which would break monitoring, is a
        # deliberate change rather than drift.
        resp = client.get("/health")
        assert resp.status_code == 200
