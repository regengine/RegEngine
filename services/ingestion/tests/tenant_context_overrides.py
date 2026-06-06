"""Test helpers for legacy routers migrated to TenantContext auth."""

from __future__ import annotations

import sys

from fastapi import Request

from app.webhook_compat import require_tenant_context
from shared.tenant_context import TenantContext, assert_tenant_claim_matches


def install_tenant_context_override(
    app,
    *,
    default_tenant: str = "t1",
    enforce_claims: bool = False,
) -> None:
    """Install a request-aware TenantContext override for router unit tests."""

    async def _tenant_ctx(request: Request) -> TenantContext:
        tenant_id = request.path_params.get("tenant_id")
        if not tenant_id and request.method in {"POST", "PUT", "PATCH"}:
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type.lower():
                try:
                    body = await request.json()
                except Exception:
                    body = {}
                if isinstance(body, dict):
                    tenant_id = body.get("tenant_id") or body.get("tenantId")
        ctx = TenantContext(
            tenant_id=tenant_id or default_tenant,
            principal_kind="test",
            principal_id="router-test",
        )
        if enforce_claims:
            for name, value in request.path_params.items():
                if name in {"tenant_id", "tenantId"}:
                    assert_tenant_claim_matches(ctx, value, source=f"path_param.{name}")
            query_tenant = request.query_params.get("tenant_id")
            if query_tenant:
                assert_tenant_claim_matches(ctx, query_tenant, source="query_param.tenant_id")
            for header_name in ("x-tenant-id-override", "x-tenant-id", "x-regengine-tenant-id"):
                header_tenant = request.headers.get(header_name)
                if header_tenant:
                    assert_tenant_claim_matches(ctx, header_tenant, source=f"header.{header_name}")
        return ctx

    dependencies = {require_tenant_context}
    for module_name in ("app.webhook_compat", "services.ingestion.app.webhook_compat"):
        module = sys.modules.get(module_name)
        current = getattr(module, "require_tenant_context", None)
        if current is not None:
            dependencies.add(current)

    for dependency in dependencies:
        app.dependency_overrides[dependency] = _tenant_ctx
