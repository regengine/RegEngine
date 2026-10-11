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
- #1068  retired shared-key path accepted an empty X-Tenant-ID
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

    from shared.tenant_context import resolve_tenant_context

    @router.get("/items")
    async def list_items(ctx: TenantContext = Depends(resolve_tenant_context)):
        # ctx.tenant_id is authoritative and RLS-safe
        ...

If the caller attempts to pass a competing ``tenant_id`` via path, query,
or body, the dependency raises ``HTTPException(409)`` with error code
``E_TENANT_MISMATCH``. Callers MUST NOT catch this.
"""

from __future__ import annotations

import contextvars
import os
import uuid as _uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Optional, Union

import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy import text

logger = structlog.get_logger("tenant_context")


def _is_unset_mock(value: Any) -> bool:
    """Return True for MagicMock auto-created attributes in unit tests."""
    return value is not None and type(value).__module__ == "unittest.mock"


@dataclass(frozen=True)
class TenantContext:
    """Authoritative tenant + principal pair for the current request.

    Attributes:
        tenant_id: UUID string. Never None, never empty, never a demo fallback.
        principal_kind: "api_key" | "jwt" | "test_bypass".
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
      3. Test-bypass path — only when ``REGENGINE_ENV`` is ``development``
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
    claimed_tenant_ids = list(_collect_claimed_tenant_ids(request))
    claimed_tenant_ids.extend(await _collect_json_body_tenant_ids(request))
    for source, value in claimed_tenant_ids:
        assert_tenant_claim_matches(
            principal,
            value,
            source=source,
            path=request.url.path,
        )

    # #2461: seed the RLS contextvar so the Engine begin-hook applies
    # app.tenant_id on every transaction this request opens. This is an
    # async dependency, so the set is visible to the handler and to sync
    # handlers via Starlette's context copy into the threadpool.
    set_rls_tenant_id(principal.tenant_id)
    return principal


def assert_tenant_claim_matches(
    ctx: TenantContext,
    claimed_tenant_id: Any,
    *,
    source: str,
    path: str | None = None,
) -> None:
    """Reject client-supplied tenant claims that conflict with auth context."""
    if claimed_tenant_id in (None, ""):
        return
    # Compare case-insensitively: UUID hex case carries no meaning, and a
    # 409 on a legitimate same-tenant request is an availability bug.
    claimed = str(claimed_tenant_id).strip().lower()
    if claimed == str(ctx.tenant_id).strip().lower():
        return

    logger.warning(
        "tenant_mismatch_attempt",
        principal_kind=ctx.principal_kind,
        principal_id=ctx.principal_id,
        claimed_source=source,
        claimed_tenant=claimed,
        authenticated_tenant=ctx.tenant_id,
        path=path,
    )
    raise TenantContextError(
        code="E_TENANT_MISMATCH",
        detail=f"request {source} tenant_id does not match authenticated tenant",
        status_code=status.HTTP_409_CONFLICT,
    )


def _extract_principal(request: Request) -> Optional[TenantContext]:
    """Pull the principal set by verify_api_key / get_current_user.

    Returns a TenantContext even if tenant_id is empty; the caller is
    responsible for raising E_NO_TENANT so the distinction between
    "no auth" and "auth without tenant" is preserved.
    """
    api_key = getattr(request.state, "api_key", None)
    if api_key is not None:
        key_id = getattr(api_key, "key_id", "unknown")
        is_bypass = key_id == "test"
        kind = "test_bypass" if is_bypass else "api_key"
        return TenantContext(
            tenant_id=getattr(api_key, "tenant_id", "") or "",
            principal_kind=kind,
            principal_id=key_id,
            actor_email=None,
        )

    principal = getattr(request.state, "principal", None)
    if principal is not None and not _is_unset_mock(principal):
        return TenantContext(
            tenant_id=getattr(principal, "tenant_id", "") or "",
            principal_kind=getattr(principal, "auth_mode", None) or "rbac",
            principal_id=str(getattr(principal, "key_id", "unknown")),
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
    for name in ("tenant_id", "tenantId"):
        if name in path_params:
            yield (f"path_param.{name}", str(path_params[name]))

    try:
        qp_tenant = request.query_params.get("tenant_id")
    except Exception as exc:
        # #2696 (low): claim-absent on error skips the 409 mismatch
        # defense-in-depth check — say so instead of staying silent.
        logger.warning("tenant_claim_query_param_read_failed", error=str(exc))
        qp_tenant = None
    if qp_tenant:
        yield ("query_param.tenant_id", qp_tenant)

    for header_name in (
        "x-tenant-id-override",
        "x-tenant-id",
        "x-regengine-tenant-id",
    ):
        hdr_tenant = _get_header_value(request.headers, header_name)
        if hdr_tenant:
            yield (f"header.{header_name}", hdr_tenant)


async def _collect_json_body_tenant_ids(request: Request) -> list[tuple[str, str]]:
    """Return top-level tenant claims from JSON request bodies, if present."""
    method = getattr(request, "method", "").upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return []

    content_type = _get_header_value(getattr(request, "headers", {}), "content-type") or ""
    if "application/json" not in content_type.lower():
        return []

    try:
        body = await request.json()
    except Exception as exc:
        # #2696 (low): unparseable JSON is common (the endpoint will 422),
        # but log at debug so a systematic parse failure that skips the 409
        # mismatch check is at least observable.
        logger.debug("tenant_claim_body_parse_failed", error=str(exc))
        return []

    if not isinstance(body, dict):
        return []

    claims: list[tuple[str, str]] = []
    for name in ("tenant_id", "tenantId"):
        value = body.get(name)
        if value:
            claims.append((f"json_body.{name}", str(value)))
    return claims


def _get_header_value(headers: Any, name: str) -> Optional[str]:
    """Case-tolerant header lookup that also works with plain test dicts."""
    try:
        value = headers.get(name)
        if value:
            return value
    except Exception:
        return None

    title_name = "-".join(part.capitalize() for part in name.split("-"))
    try:
        value = headers.get(title_name)
        if value:
            return value
    except Exception:
        pass

    try:
        for key, value in headers.items():
            if str(key).lower() == name.lower() and value:
                return value
    except Exception:
        pass
    return None


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
# Phase B convergence is COMPLETE (WS-4 of the 2026-07-07 remediation
# plan): every Python call site that sets ``app.tenant_id`` now delegates
# to the canonical primitives below — CTEPersistence / CanonicalEventStore /
# ExceptionQueueService / canonical_router / api_key_store use
# ``set_tenant_guc``; the ingestion module helpers (inflow_workbench,
# integration_router, supplier_portal) use ``set_tenant_guc_if_uuid``
# because those paths can carry non-UUID tenant slugs. Two deliberate
# non-Python carve-outs remain: the SECURITY DEFINER SQL function called
# by ``DatabaseManager.set_tenant_context`` (autocommit psycopg layer —
# session scope is the correct shape there) and the admin pool-checkout
# listener that CLEARS the GUC ('' at session scope, pool hygiene).
#
# The ``adhoc-tenant-guc-set-config`` rule in ``.semgrep/tenant-trust.yaml``
# (a hard CI gate) blocks the single-line inline shapes prior call sites
# used (:tid / %s / $1 binds). It is defense-in-depth, not an exhaustive
# ban — multi-line SQL blocks can evade a regex; the fail-hard
# ``get_tenant_context()`` RLS predicate remains the actual security
# control. Grep for "app.tenant_id" when reviewing tenant-adjacent code.
#
# Scope is ``SET LOCAL`` (transaction-scoped, auto-resets at COMMIT/ROLLBACK)
# — never session-scoped. Pool-bleed safety relies on this: a connection
# returned to the pool should not carry a tenant_id from a prior request.
# ``services/admin/app/database.py`` ALSO registers a pool-checkout listener
# that proactively clears the GUC; that's the second layer of defense.


def _validate_tenant_guc_id(tenant_id: str) -> None:
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError(f"tenant_id must be a non-empty UUID string; got {type(tenant_id).__name__!s}={tenant_id!r}")
    try:
        _uuid.UUID(tenant_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"tenant_id is not a valid UUID: {tenant_id!r}") from exc


def set_tenant_guc_cursor(cursor: Any, tenant_id: str) -> None:
    """The canonical transaction-local tenant binding for raw psycopg cursors.

    The caller must hold the transaction through all tenant SQL and commit or
    rollback. Raw cursors require DB-API binds, not SQLAlchemy text clauses.
    """
    _validate_tenant_guc_id(tenant_id)
    cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))


def set_tenant_guc(session: Any, tenant_id: str) -> None:
    """Set ``app.tenant_id`` on the session at TRANSACTION scope.

    Canonical primitive. Every code path that needs to scope subsequent DB
    work to a tenant — RLS-enforced reads, RLS-enforced writes, anything
    that calls ``get_tenant_context()`` — must call this first.

    SQL form: ``SELECT set_config('app.tenant_id', :tid, true)``.

    Why ``set_config(..., true)`` instead of ``SET LOCAL app.tenant_id =
    :tid``:

      * Both are transaction-scoped — Postgres documents
        ``set_config(name, value, TRUE)`` as "almost equivalent" to
        ``SET LOCAL`` (the only difference is that ``set_config`` returns
        the value being set; we don't read the return).
      * Postgres does NOT allow parameter placeholders in the
        ``SET``/``SET LOCAL`` syntax. Under psycopg the driver does
        client-side substitution that papers over this for
        ``text("SET LOCAL ... = :tid")``, but under **asyncpg the
        same call fails with ``syntax error at or near "$1"``** (see
        #1879). ``set_config`` is a regular function call — bound
        parameters work in both drivers.
      * Single primitive that works everywhere (sync + async sessions)
        unifies the previously-bifurcated callsites:
        ``services/shared/api_key_store.py`` was the third
        Phase-B carve-out (#1942) BECAUSE the old ``SET LOCAL`` form
        crashed under asyncpg; with this form, that carve-out is
        unblocked.

    Args:
        session: A SQLAlchemy ``Session`` / ``AsyncSession`` (call
                 ``await session.execute(...)`` for the async case
                 — pass any object whose ``.execute(stmt, params)``
                 method accepts a SQLAlchemy ``text()`` clause and a
                 binding dict).
        tenant_id: A UUID string. Validated client-side before binding;
                   non-UUID values raise ``ValueError`` before any SQL
                   runs. The bind itself is parameterized so SQL
                   injection is impossible regardless of input shape;
                   the client-side check makes the failure mode loud
                   rather than "RLS returns 0 rows for unclear reasons."

    Raises:
        ValueError: ``tenant_id`` is empty, not a string, or not a
                    valid UUID.

    Returns:
        Whatever ``session.execute(...)`` returns. For sync sessions
        that's a ``Result`` object the caller can ignore. For async
        sessions (``AsyncSession``) that's a **coroutine the caller
        MUST await** before the GUC write lands; the helper itself is
        synchronous so it can't await internally. Sync callers can
        treat the return as if it were ``None``; async callers do
        ``await set_tenant_guc(...)`` (or the equivalent
        ``hasattr(result, "__await__")`` check if the session type
        is mixed).
    """
    _validate_tenant_guc_id(tenant_id)

    # Return whatever ``session.execute(...)`` returns. Sync sessions
    # return a ``Result`` object (caller can ignore); async sessions
    # return a coroutine that the caller MUST await before the GUC
    # write lands. Returning the value lets the same primitive serve
    # both worlds — see ``services/shared/api_key_store.py`` for the
    # async ``await`` pattern.
    return session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": tenant_id},
    )


def set_tenant_guc_if_uuid(session: Any, tenant_id: Any) -> Any:
    """Best-effort RLS backstop: set the tenant GUC only for UUID tenant ids.

    ``set_tenant_guc`` requires a UUID because the ``app.tenant_id`` GUC is
    cast ``::uuid`` by the RLS policies. Some callers (e.g. the ingestion read
    routers) carry non-UUID slug tenant ids, for which the GUC can't be set;
    rather than raise, we skip — the app-level ``WHERE tenant_id`` predicate
    still scopes those queries. For UUID tenants this adds the RLS backstop so
    isolation is enforced at the DB layer even if a WHERE clause is ever
    omitted.

    Returns the ``session.execute(...)`` result when the GUC was set (which the
    caller may need to ``await`` for async sessions), or ``None`` when skipped.
    """
    try:
        _uuid.UUID(str(tenant_id))
    except (ValueError, AttributeError, TypeError):
        return None
    # str-coerce so a uuid.UUID instance (or any object whose str() is a
    # valid UUID) sets the GUC rather than tripping set_tenant_guc's
    # isinstance(tenant_id, str) check — honoring this helper's documented
    # "set for UUID tenants, skip otherwise, never raise" contract.
    return set_tenant_guc(session, str(tenant_id))


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


# ---------------------------------------------------------------------------
# RLS context propagation (#2461) — ContextVar + Engine-class "begin" hook
# ---------------------------------------------------------------------------
#
# The explicit ``set_tenant_guc`` call sites above cover the paths that
# remembered to call them. The #2461 audit found ~56/60 fsma-querying
# files never set the GUC, and several that do lose it on a mid-request
# ``commit()``/``rollback()`` (transaction-scoped ``set_config`` clears
# at transaction end). Rather than patching every session open/commit,
# the mechanism below:
#
#   1. carries the acting tenant in a :class:`~contextvars.ContextVar`
#      seeded at every tenant-resolution funnel (auth dependencies,
#      worker/job bodies via :func:`tenant_scope`), and
#   2. re-applies ``SELECT set_config('app.tenant_id', :tid, true)`` as
#      the FIRST statement of EVERY new transaction via a class-level
#      SQLAlchemy ``Engine`` "begin" listener. SQLAlchemy 2.x autobegin
#      re-fires the event after each commit()/rollback(), which
#      structurally eliminates the rollback-clears-GUC bug class.
#
# Class-level (not per-engine) registration is deliberate: the codebase
# constructs ad-hoc engines (fsma_recall builds one per call, fsma_audit
# and ingestion audit_log build lazy private engines, server/main builds
# a readiness throwaway), so instance registration cannot guarantee
# coverage. The handler no-ops on non-postgresql dialects (sqlite unit
# tests). Every PostgreSQL transaction first receives an explicit local
# fail-closed baseline, even when no context is seeded. This is required for
# transaction-mode poolers: checkout and the subsequent transaction may land
# on different server backends, so session-level state can never be trusted.
#
# The retired ``regengine.system_context`` GUC is still reset to ``false`` in
# the per-transaction baseline so stale state cannot survive a rolling
# deployment.  No current policy reads it and application code has no API for
# setting it true.  Cross-tenant maintenance uses the separately credentialed
# ``regengine_sysadmin`` role plus the exact-role ``regengine.is_sysadmin``
# policy arm.
#
# Out of hook coverage by construction: the raw-psycopg
# ``regengine_ingestion.storage.database.DatabaseManager`` (keeps its
# SECURITY DEFINER session-scoped carve-out) and any other direct
# psycopg.connect() usage.

_rls_tenant_id: ContextVar[Optional[str]] = ContextVar("rls_tenant_id", default=None)

_HOOK_INSTALLED = False

# Post-cutover canary: increments per transaction the hook touches.
# ``skipped_non_uuid`` counts slug-tolerant skips (mirrors
# set_tenant_guc_if_uuid). Defined here rather than shared/database.py
# to avoid an import cycle (database.py imports this module so the hook
# is installed before its module-level create_engine()).
_RLS_GUC_COUNTER: Any = None


def _rls_guc_counter():
    """Lazily create/fetch the regengine_rls_guc_applied_total counter."""
    global _RLS_GUC_COUNTER
    if _RLS_GUC_COUNTER is not None:
        return _RLS_GUC_COUNTER
    try:
        from prometheus_client import REGISTRY, Counter  # noqa: PLC0415

        try:
            _RLS_GUC_COUNTER = Counter(
                "regengine_rls_guc_applied",
                "Transactions where the RLS begin-hook applied (or skipped) a GUC.",
                ["kind"],
            )
        except ValueError:
            _RLS_GUC_COUNTER = REGISTRY._names_to_collectors.get("regengine_rls_guc_applied")
    except Exception:  # pragma: no cover — metrics must never break queries
        _RLS_GUC_COUNTER = None
    return _RLS_GUC_COUNTER


def _inc_rls_guc_metric(kind: str) -> None:
    try:
        counter = _rls_guc_counter()
        if counter is not None:
            counter.labels(kind=kind).inc()
    except Exception:  # pragma: no cover — metrics must never break queries
        pass


def get_rls_tenant_id() -> Optional[str]:
    """Read accessor for the RLS tenant contextvar.

    Named to avoid clashing with
    ``shared.middleware.tenant_context.get_current_tenant_id``.
    """
    return _rls_tenant_id.get()


def set_rls_tenant_id(tenant_id: Union[str, _uuid.UUID, None]) -> contextvars.Token:
    """Seed the RLS tenant contextvar for the current context.

    str-coerces ``uuid.UUID``; ``None`` clears. NO validation here — the
    begin-hook decides at apply time (mirrors ``set_tenant_guc_if_uuid``
    slug tolerance: non-UUID values are stored but skipped, never raised
    on). Returns the token for callers that want explicit reset.

    Only call this from async dependencies or inside handler/thread/job
    bodies — a sync ``def`` FastAPI dependency runs in a threadpool
    context copy whose sets are invisible downstream.
    """
    if tenant_id is None:
        return _rls_tenant_id.set(None)
    return _rls_tenant_id.set(str(tenant_id))


def reset_rls_tenant_id(token: contextvars.Token) -> None:
    """Reset the RLS tenant contextvar to its pre-``set_rls_tenant_id`` state."""
    _rls_tenant_id.reset(token)


@contextmanager
def tenant_scope(tenant_id: Union[str, _uuid.UUID]) -> Iterator[None]:
    """Scope all DB transactions in this context to ``tenant_id``.

    Pure contextvar — no SQL — so it is equally valid in sync code,
    async code, and thread bodies. The begin-hook applies the GUC on
    every transaction started while the scope is active.
    """
    token = set_rls_tenant_id(tenant_id)
    try:
        yield
    finally:
        _rls_tenant_id.reset(token)


def _apply_rls_gucs_on_begin(conn: Any) -> None:
    """SQLAlchemy Connection ``begin`` handler — first statements of every txn."""
    try:
        if conn.dialect.name != "postgresql":
            return  # sqlite fallback engines / unit tests
    except AttributeError:  # pragma: no cover — defensive
        return

    # Establish the complete security-GUC baseline on the same backend and in
    # the same transaction that will execute the application query.  SET LOCAL
    # semantics (set_config(..., true)) make a later COMMIT/ROLLBACK clear the
    # values automatically.  One SELECT keeps the hook to a single round trip;
    # Connection.execute inside SQLAlchemy's ``begin`` event does not recurse.
    conn.execute(
        text(
            """
            SELECT
                set_config('app.tenant_id', '', true),
                set_config('app.portal_link_token', '', true),
                set_config('app.remediation_token_hash', '', true),
                set_config('regengine.tenant_id', '', true),
                set_config('regengine.user_id', '', true),
                set_config('regengine.is_sysadmin', 'false', true),
                set_config('regengine.system_context', 'false', true),
                set_config('regengine.api_key_lookup_id', '', true),
                set_config('regengine.api_key_lookup_hash_current', '', true),
                set_config('regengine.api_key_lookup_hash_legacy', '', true),
                set_config('audit.allow_break_glass', 'false', true),
                set_config('fsma.allow_mutation', 'false', true)
            """
        )
    )
    _inc_rls_guc_metric("baseline")

    tid = _rls_tenant_id.get()
    if tid is not None:
        try:
            _uuid.UUID(str(tid))
        except (ValueError, AttributeError, TypeError):
            # Slug tolerance — skip, matching set_tenant_guc_if_uuid.
            _inc_rls_guc_metric("skipped_non_uuid")
            tid = None
    if tid is not None:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tid)},
        )
        _inc_rls_guc_metric("tenant")


def install_rls_guc_hook() -> None:
    """Register :func:`_apply_rls_gucs_on_begin` on the Engine CLASS.

    Idempotent (module-level flag). Class-level registration covers
    engines created before AND after this call — required because
    fsma_recall/fsma_audit/audit_log/readiness construct engines lazily
    or per-call. Called at module import below; shared/database.py and
    services/admin/app/database.py import this module before their
    ``create_engine()`` so coverage is guaranteed either way.
    """
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED:
        return
    from sqlalchemy import event as _sa_event  # noqa: PLC0415
    from sqlalchemy.engine import Engine as _SAEngine  # noqa: PLC0415

    _sa_event.listen(_SAEngine, "begin", _apply_rls_gucs_on_begin)
    _HOOK_INSTALLED = True


install_rls_guc_hook()
