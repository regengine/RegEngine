"""Hermetic tenant-boundary regression tests.

The retired version of this module called optional services on localhost and
skipped the whole file when the Admin API was absent.  It also treated the
removed shared administrative header as a valid credential.  These tests use
the real tenant-context dependency through an in-process HTTP interface and
prove that client-controlled path, query, header, and JSON tenant assertions
cannot override the authenticated principal.

This is an application-boundary regression suite, not the route-complete
two-tenant staging matrix or direct production-role RLS proof required for
release approval.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from shared.tenant_context import TenantContext, resolve_tenant_context

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


def _tenant_app(*, bound_tenant: str | None, attach_principal: bool = True):
    app = FastAPI()
    effects: list[str] = []

    async def authenticated_tenant(request: Request) -> TenantContext:
        if attach_principal:
            request.state.api_key = SimpleNamespace(
                key_id="rge_tenant_a",
                tenant_id=bound_tenant,
            )
        return await resolve_tenant_context(request)

    @app.post("/tenants/{tenant_id}/records")
    async def create_record(
        tenant_id: str,
        ctx: TenantContext = Depends(authenticated_tenant),
    ):
        effects.append(tenant_id)
        return {
            "authenticated_tenant": ctx.tenant_id,
            "requested_tenant": tenant_id,
        }

    return app, effects


def test_matching_path_tenant_reaches_handler_under_bound_tenant():
    app, effects = _tenant_app(bound_tenant=TENANT_A)

    response = TestClient(app).post(f"/tenants/{TENANT_A}/records", json={"value": "tenant-a"})

    assert response.status_code == 200
    assert response.json() == {
        "authenticated_tenant": TENANT_A,
        "requested_tenant": TENANT_A,
    }
    assert effects == [TENANT_A]


def test_tenant_b_path_cannot_override_tenant_a_credential():
    app, effects = _tenant_app(bound_tenant=TENANT_A)

    response = TestClient(app).post(f"/tenants/{TENANT_B}/records")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "E_TENANT_MISMATCH"
    assert effects == []


def test_matching_path_with_conflicting_query_assertion_is_denied():
    app, effects = _tenant_app(bound_tenant=TENANT_A)

    response = TestClient(app).post(
        f"/tenants/{TENANT_A}/records",
        params={"tenant_id": TENANT_B},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "E_TENANT_MISMATCH"
    assert effects == []


def test_matching_path_with_conflicting_header_assertion_is_denied():
    app, effects = _tenant_app(bound_tenant=TENANT_A)

    response = TestClient(app).post(
        f"/tenants/{TENANT_A}/records",
        headers={"X-Tenant-ID": TENANT_B},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "E_TENANT_MISMATCH"
    assert effects == []


def test_matching_path_with_conflicting_body_assertion_is_denied():
    app, effects = _tenant_app(bound_tenant=TENANT_A)

    response = TestClient(app).post(
        f"/tenants/{TENANT_A}/records",
        json={"tenant_id": TENANT_B},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "E_TENANT_MISMATCH"
    assert effects == []


def test_missing_authenticated_principal_fails_closed():
    app, effects = _tenant_app(bound_tenant=None, attach_principal=False)

    response = TestClient(app).post(f"/tenants/{TENANT_A}/records")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "E_NO_PRINCIPAL"
    assert effects == []


def test_tenantless_authenticated_principal_fails_closed():
    app, effects = _tenant_app(bound_tenant=None)

    response = TestClient(app).post(f"/tenants/{TENANT_A}/records")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "E_NO_TENANT"
    assert effects == []
