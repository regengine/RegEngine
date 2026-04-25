"""Authoritative tenant-context resolution (EPIC-A #1651).

This module is the **single source of truth** for deriving the
acting tenant_id from an authenticated request.

## Background

RegEngine has accumulated half-a-dozen ways to answer "what tenant is
this request for?" — some safe, some not. This module collapses them
into one function with a single supported input: the already-authenticated
principal (API key row or JWT claim). URL path, query string, request
body, and Supabase `user_metadata` are **not** accepted.

Consolidated the following bugs (all variants of the same pattern):

- #1065  PermissionChecker grants sysadmin without tenant context
- #1068  preshared master-key path accepts empty X-Tenant-ID
- #1106  FDA spreadsheet route trusts client X-Tenant-ID
- #1122  NLP extraction pipelines missing tenant_id thread-through
- #1405  ComplianceServiceSync.get_alert does not filter by tenant_id
- #1406  /admin/users reactivate no sysadmin-safety check
- #1407  /v1/supplier/demo/reset no RBAC / runs in any tenant
- #1414  AuditContextMiddleware trusts X-Forwarded-For blindly
- #1391  system_routes._resolve_tenant falls back to demo-tenant UUID
- (historical) #1345  get_current_user reads tenant_id from Supabase user_metadata

Semgrep rule ``.semgrep/tenant-trust.yaml`` enforces that no route
re-introduces the forbidden patterns.

## Usage

    from services.shared.tenant_context import resolve_tenant_context

    @router.get("/items")
    async def list_items(ctx: TenantContext = Depends(resolve_tenant_context)):
        # ctx.tenant_id is authoritative and RLS-safe
        ...

If the caller attempts to pass a competing ``tenant_id`` via path, query,
or body, the dependency raises ``HTTPException(409)`` with error code
``E_TENANT_MISMATCH``. Callers MUST NOT catch this.
"""

from __future__ import annotations

import os
import uuid as _uuid
from dataclasses import dataclass
from typing import Any, Optional

import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy import text

logger = structlog.get_logger("tenant_context")


@dataclass(frozen=True)
class TenantContext:
    """Authoritative tenant + principal pair for the current request.

    Attributes:
        tenant_id: UUID string. Never None, never empty, never a demo fallback.
        principal_kind: "api_key" | "jwt" | "preshared" | "test_bypass".
        principal_id:   Stable identifier for the principal (api_key.key_id,
                        user_id, etc.). Used as ``actor_id`` in audit logs.
        actor_email:    Optional email for audit-log readability. May be None
                        for API-key callers with no human bound.
    """

    tenant_id: str
    principal_kind: str
    principal_id: str
    actor_email: Optional[str] = None


class TenantContextError(HTTPException):
    """Raised when tenant context cannot be resolved safely.

    Wraps HTTPException so FastAPI renders a clean 401/409 with a
    machine-readable error code. Never returns a tenant_id fallback.
    """

    def __init__(self, code: str, detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(status_code=status_code, detail={"code": code, "message": detail})


async def resolve_tenant_context(request: Request) -> TenantContext:
    """Return the authoritative TenantContext for the current request.

    Resolution order (first match wins; **no fallback to demo tenant**):

      1. API-key principal set by ``services.shared.auth.verify_api_key`` —
         takes tenant_id from the server-side ``api_keys.tenant_id`` row.
      2. JWT principal set by ``services.shared.auth.get_current_user`` —
         takes tenant_id from the signed ``tenant_id`` claim.
      3. Preshared master key — takes tenant_id from ``X-Tenant-ID``
         header **only if** verify_api_key accepted the master key
         (so request.state.api_key is already populated).
      4. Test-bypass path — only when ``REGENGINE_ENV`` is ``development``
         or ``test`` AND ``AUTH_TEST_BYPASS_TOKEN`` matches.

    Tenant_id from URL path, query string, request body, or Supabase
    user_metadata is IGNORED. If any is provided and conflicts with the
    authenticated tenant, raises HTTP 409 ``E_TENANT_MISMATCH``.

    Args:
        request: FastAPI request. The authenticated principal is expected
                 on ``request.state.api_key`` (set by verify_api_key) or
                 ``request.state.user`` (set by get_current_user).

    Raises:
        TenantContextError(401, E_NO_PRINCIPAL):  no auth on request.
        TenantContextError(401, E_NO_TENANT):     principal has no tenant_id.
        TenantContextError(409, E_TENANT_MISMATCH): body/path/query tenant
                                                     disagrees with principal.

    Returns:
        TenantContext with a non-empty tenant_id guaranteed.
    """
    principal = _extract_principal(request)
    if principal is None:
        raise TenantContextError(code="E_NO_PRINCIPAL", detail="no authenticated principal on request")

    tenant_id = principal.tenant_id
    if not tenant_id:
        logger.error(
            "tenant_context_missing",
            principal_kind=principal.principal_kind,
            principal_id=principal.principal_id,
            path=request.url.path,
        )
        raise TenantContextError(code="E_NO_TENANT", detail="principal has no tenant_id")

    # Defense-in-depth: detect caller attempts to override tenant_id.
    for source, value in _collect_claimed_tenant_ids(request):
        if value and value != tenant_id:
            logger.warning(
                "tenant_mismatch_attempt",
                principal_kind=principal.principal_kind,
                principal_id=principal.principal_id,
                claimed_source=source,
                claimed_tenant=value,
                authenticated_tenant=tenant_id,
                path=request.url.path,
            )
            raise TenantContextError(
                code="E_TENANT_MISMATCH",
                detail=f"request {source} tenant_id does not match authenticated tenant",
                status_code=status.HTTP_409_CONFLICT,
            )

    return principal


def _extract_principal(request: Request) -> Optional[TenantContext]:
    """Pull the principal set by verify_api_key / get_current_user.

    Returns a TenantContext even if tenant_id is empty; the caller is
    responsible for raising E_NO_TENANT so the distinction between
    "no auth" and "auth without tenant" is preserved.
    """
    api_key = getattr(request.state, "api_key", None)
    if api_key is not None:
        key_id = getattr(api_key, "key_id", "unknown")
        is_master = key_id == "preshared-master"
        is_bypass = key_id == "test"
        kind = "preshared" if is_master else ("test_bypass" if is_bypass else "api_key")
        return TenantContext(
            tenant_id=getattr(api_key, "tenant_id", "") or "",
            principal_kind=kind,
            principal_id=key_id,
            actor_email=None,
        )

    user = getattr(request.state, "user", None)
    if user is not None:
        return TenantContext(
            tenant_id=getattr(user, "tenant_id", "") or "",
            principal_kind="jwt",
            principal_id=str(getattr(user, "id", "unknown")),
            actor_email=getattr(user, "email", None),
        )

    return None


def _collect_claimed_tenant_ids(request: Request):
    """Yield (source, tenant_id) pairs the request tries to assert.

    Used only for mismatch detection. The authoritative tenant is always
    the authenticated principal; these values are never trusted.
    """
    path_params = getattr(request, "path_params", {}) or {}
    if "tenant_id" in path_params:
        yield ("path_param", str(path_params["tenant_id"]))

    try:
        qp_tenant = request.query_params.get("tenant_id")
    except Exception:
        qp_tenant = None
    if qp_tenant:
        yield ("query_param", qp_tenant)

    hdr_tenant = request.headers.get("x-tenant-id-override")
    if hdr_tenant:
        yield ("header_x-tenant-id-override", hdr_tenant)


def is_production() -> bool:
    """Gate helper for destructive operations.

    Returns True unless REGENGINE_ENV is explicitly 'development' or 'test'.
    """
    return os.getenv("REGENGINE_ENV", "production").lower() not in {"development", "test"}


# ---------------------------------------------------------------------------
# DB session GUC helpers (Phase B of tenant-isolation convergence)
# ---------------------------------------------------------------------------
#
# Postgres RLS policies reference the ``app.tenant_id`` GUC via the canonical
# helper ``get_tenant_context()`` (returns UUID). Every tenant-scoped DB
# operation must set this GUC on the session before doing any work, or RLS
# either returns no rows (fail-hard policies post-v056) or — under the
# legacy fail-open V3 form that v056/v059 superseded — falls back to the
# sandbox tenant.
#
# Today there are at least 8 places that set ``app.tenant_id`` via ad-hoc
# code (``set_tenant_context`` methods on CTEPersistence /
# CanonicalEventStore / ExceptionQueueService, inline ``SET LOCAL`` in
# canonical_router and a few admin paths, plus a SECURITY DEFINER SQL
# function called from ``DatabaseManager.set_tenant_context``). Each
# implementation is correct in isolation but the duplication is a
# maintenance hazard — a future bug fix to the GUC name or scope has to be
# applied in eight places.
#
# These helpers are the canonical primitive: every caller that needs to
# set the GUC should use ``set_tenant_guc(session, tenant_id)``. Future
# sprints migrate the existing ad-hoc call sites one service at a time.
#
# Scope is ``SET LOCAL`` (transaction-scoped, auto-resets at COMMIT/ROLLBACK)
# — never session-scoped. Pool-bleed safety relies on this: a connection
# returned to the pool should not carry a tenant_id from a prior request.
# ``services/admin/app/database.py`` ALSO registers a pool-checkout listener
# that proactively clears the GUC; that's the second layer of defense.


def set_tenant_guc(session: Any, tenant_id: str) -> None:
    """Set ``app.tenant_id`` on the session at TRANSACTION scope.

    Canonical primitive. Every code path that needs to scope subsequent DB
    work to a tenant — RLS-enforced reads, RLS-enforced writes, anything
    that calls ``get_tenant_context()`` — must call this first.

    Args:
        session: A SQLAlchemy ``Session`` (sync) or any object with an
                 ``execute(stmt, params)`` method that takes a SQLAlchemy
                 ``text()`` clause and a binding dict. The async session
                 path is intentionally *not* supported here — async DB
                 work needs ``set_tenant_guc_async`` (see below).
        tenant_id: A UUID string. Validated client-side before binding;
                   non-UUID values raise ``ValueError`` before any SQL
                   runs. The bind itself is parameterized so SQL injection
                   is impossible regardless of input shape, but the
                   client-side check makes the failure mode loud rather
                   than "RLS returns 0 rows for unclear reasons."

    Raises:
        ValueError: ``tenant_id`` is empty, not a string, or not a
                    valid UUID.

    Returns:
        None.
    """
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError(
            "tenant_id must be a non-empty UUID string; "
            f"got {type(tenant_id).__name__!s}={tenant_id!r}"
        )
    try:
        _uuid.UUID(tenant_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"tenant_id is not a valid UUID: {tenant_id!r}"
        ) from exc

    session.execute(
        text("SET LOCAL app.tenant_id = :tid"),
        {"tid": tenant_id},
    )


def apply_tenant_context(session: Any, ctx: TenantContext) -> None:
    """Apply a resolved ``TenantContext`` to a DB session.

    Convenience wrapper over ``set_tenant_guc`` for the common case where
    a FastAPI handler receives a ``TenantContext`` from
    ``Depends(resolve_tenant_context)`` and wants to scope its session
    work to that tenant. Equivalent to::

        set_tenant_guc(session, ctx.tenant_id)

    Provided so the canonical pattern is one line and reads as a single
    intent — "apply this resolved tenant context to my DB session" — at
    every call site.
    """
    set_tenant_guc(session, ctx.tenant_id)
