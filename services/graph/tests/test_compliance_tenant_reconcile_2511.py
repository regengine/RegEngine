"""Tenant-reconciliation regression tests for the graph FSMA export router (#2511).

The FDA/gap export handlers in
``services/graph/app/routers/fsma/compliance.py`` depend on BOTH
``get_current_tenant_id`` (resolved by ``TenantContextMiddleware``) and
``require_api_key`` (the authenticated API-key principal). Before this fix
the Neo4j database + query predicate were scoped from the *middleware*
tenant only, and ``api_key.tenant_id`` was never compared — so the two
sources could diverge (most concretely on the preshared master-key path,
where the key accepts a caller-supplied ``X-Tenant-ID``) and point Neo4j at
a different tenant than the key authenticates, with no fail-closed guard.

These tests pin the fix:

  * ``reconcile_tenant_scope`` returns the authenticated tenant when the
    two sources agree, 409s (``E_TENANT_MISMATCH``) when they diverge, and
    403s when the key has no tenant.
  * Each of the four export/gap endpoints returns 409 and performs **no**
    Neo4j read when the middleware tenant and the API-key tenant disagree.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from shared.auth import APIKey, reconcile_tenant_scope, require_api_key  # noqa: E402
from shared.middleware import get_current_tenant_id  # noqa: E402

TENANT_KEY = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"  # authenticated API-key tenant
TENANT_MIDDLEWARE = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"  # divergent middleware tenant


def _api_key(tenant_id):
    return APIKey(
        key_id="preshared-master",
        key_hash="",
        name="test",
        tenant_id=tenant_id,
        created_at=datetime.now(timezone.utc),
    )


# ─────────────────────────────────────────────────────────────────────
# reconcile_tenant_scope unit behavior
# ─────────────────────────────────────────────────────────────────────


def test_reconcile_returns_authenticated_tenant_on_agreement():
    out = reconcile_tenant_scope(_api_key(TENANT_KEY), uuid.UUID(TENANT_KEY))
    assert out == TENANT_KEY


def test_reconcile_409_on_divergence():
    with pytest.raises(HTTPException) as exc:
        reconcile_tenant_scope(_api_key(TENANT_KEY), uuid.UUID(TENANT_MIDDLEWARE))
    assert exc.value.status_code == 409
    assert exc.value.detail == "E_TENANT_MISMATCH"


def test_reconcile_403_when_key_has_no_tenant():
    with pytest.raises(HTTPException) as exc:
        reconcile_tenant_scope(_api_key(None), uuid.UUID(TENANT_MIDDLEWARE))
    assert exc.value.status_code == 403


def test_reconcile_uses_authenticated_not_middleware_tenant():
    """Even when both are present and equal, the returned value is the
    authenticated tenant (single source of truth for Neo4j scope)."""
    out = reconcile_tenant_scope(_api_key(TENANT_KEY), uuid.UUID(TENANT_KEY))
    assert out == TENANT_KEY  # not derived from the middleware value


# ─────────────────────────────────────────────────────────────────────
# End-to-end: the four graph FSMA handlers fail closed on divergence
# ─────────────────────────────────────────────────────────────────────


def _build_app():
    from services.graph.app.routers.fsma import compliance_router

    app = FastAPI()
    app.include_router(compliance_router, prefix="/v1/fsma/compliance")
    app.dependency_overrides[require_api_key] = lambda: _api_key(TENANT_KEY)
    app.dependency_overrides[get_current_tenant_id] = lambda: uuid.UUID(TENANT_MIDDLEWARE)
    return app


DIVERGENT_ENDPOINTS = [
    "/v1/fsma/compliance/export/fda-request?start_date=2026-01-01&end_date=2026-12-31",
    "/v1/fsma/compliance/gaps",
    "/v1/fsma/compliance/gaps/orphans",
    "/v1/fsma/compliance/export/gaps",
]


@pytest.mark.parametrize("url", DIVERGENT_ENDPOINTS)
def test_handlers_409_and_no_neo4j_read_on_divergence(url):
    """When the middleware tenant and api_key.tenant_id disagree, the
    handler must return 409 and never touch Neo4j."""
    app = _build_app()
    client = TestClient(app, raise_server_exceptions=False)

    with (
        patch("services.graph.app.routers.fsma.compliance.Neo4jClient") as mock_client_cls,
        patch("services.graph.app.routers.fsma.compliance.find_gaps", new_callable=AsyncMock) as mock_find_gaps,
        patch(
            "services.graph.app.routers.fsma.compliance.find_orphaned_lots",
            new_callable=AsyncMock,
        ) as mock_find_orphans,
    ):
        resp = client.get(url)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "E_TENANT_MISMATCH"
    # No Neo4j client constructed and no query helper invoked.
    mock_client_cls.assert_not_called()
    mock_find_gaps.assert_not_called()
    mock_find_orphans.assert_not_called()
