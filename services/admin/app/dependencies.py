import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
import structlog
from fastapi import Depends, HTTPException, Path, Request, status
from fastapi.security.utils import get_authorization_scheme_param
from jwt.exceptions import PyJWTError as JWTError
from shared.env import requires_strict_auth_runtime
from shared.jwt_key_registry import JWTKeyRegistryBackendUnavailable
from shared.permissions import has_permission

# Supabase Integration
from shared.supabase_client import get_supabase
from shared.tenant_context import set_rls_tenant_id
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from .auth.session_auth import (
    AUTH_SESSION_COOKIE,
    get_auth_crypto_service,
    get_current_active_session_context,
)
from .auth_utils import (
    RevocationBackendUnavailable,
    check_revoked_async,
    decode_access_token,
    sync_keys_from_registry,
)
from .database import (
    arm_global_admin_context,
    bind_authenticated_user_context,
    disarm_global_admin_context,
    get_session,
    get_tenant_session,
)
from .models import TenantContext

# Redis Session Store
from .session_store import InMemorySessionStore, RedisSessionStore, redact_connection_url
from .sqlalchemy_models import MembershipModel, RoleModel, TenantModel, UserModel

logger = structlog.get_logger("auth_dependency")

# Global session store instance (singleton)
_session_store: Optional[RedisSessionStore] = None


def _optional_bearer_token(request: Request) -> Optional[str]:
    """Parse legacy bearer access tokens without advertising an OAuth flow.

    Browser authentication is the opaque session contract, and the removed
    email-code route was never an OAuth token endpoint. Keeping an
    ``OAuth2PasswordBearer`` dependency produced a stale token URL and leaked
    a misleading Bearer scheme into generated documentation.
    """
    scheme, parameter = get_authorization_scheme_param(request.headers.get("Authorization"))
    if scheme.lower() != "bearer" or not parameter:
        return None
    return parameter


def _should_use_in_memory_session_store() -> bool:
    if requires_strict_auth_runtime():
        # Reuse the startup policy here as defense in depth. Even if an
        # entrypoint forgets to initialize the auth runtime, a production
        # request must never activate the process-local session backend.
        from .auth_runtime import load_auth_runtime_config

        load_auth_runtime_config()
        return False

    backend = os.getenv("SESSION_STORE_BACKEND", "").strip().lower()
    if backend in {"memory", "inmemory", "local"}:
        return True

    allow_in_memory = os.getenv("ALLOW_INMEMORY_SESSION_STORE", "").strip().lower()
    if allow_in_memory in {"1", "true", "yes", "on"}:
        return True

    return not requires_strict_auth_runtime() and not os.getenv("REDIS_URL")


def _parse_token_version(value: object) -> Optional[int]:
    """Parse token-version values from JWT/app_metadata/ORM rows."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _is_supabase_token_rejection(exc: Exception) -> bool:
    """Return true for Supabase/Gotrue credential rejections such as invalid JWTs."""
    cls = exc.__class__
    module = getattr(cls, "__module__", "")
    name = getattr(cls, "__name__", "")
    return name in {"AuthApiError", "AuthInvalidCredentialsError"} and module.startswith(("supabase_auth.", "gotrue."))


def _is_supabase_transient_exception(exc: Exception) -> bool:
    """Return true for Supabase/Gotrue retryable infrastructure failures."""
    cls = exc.__class__
    module = getattr(cls, "__module__", "")
    name = getattr(cls, "__name__", "")
    return name == "AuthRetryableError" and module.startswith(("supabase_auth.", "gotrue."))


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _session_store_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service temporarily unavailable",
    )


async def _enforce_session_bound_token(
    *,
    local_session_id: UUID,
    token_user_id: Optional[str],
    user: UserModel,
    session_store: RedisSessionStore,
) -> None:
    try:
        session_data = await session_store.get_session(local_session_id)
    except Exception as exc:
        logger.error(
            "session_bound_token_store_unavailable",
            user_id=token_user_id,
            session_id=str(local_session_id),
            error=str(exc),
        )
        raise _session_store_exception() from exc

    if session_data is None:
        logger.warning(
            "missing_session_bound_token_rejected",
            user_id=token_user_id,
            session_id=str(local_session_id),
        )
        raise _credentials_exception()
    if session_data.is_revoked:
        logger.warning(
            "revoked_session_bound_token_rejected",
            user_id=token_user_id,
            session_id=str(local_session_id),
        )
        raise _credentials_exception()

    expires_at = session_data.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        logger.warning(
            "expired_session_bound_token_rejected",
            user_id=token_user_id,
            session_id=str(local_session_id),
        )
        raise _credentials_exception()
    if session_data.user_id != user.id:
        logger.warning(
            "wrong_user_session_bound_token_rejected",
            user_id=token_user_id,
            session_id=str(local_session_id),
            session_user_id=str(session_data.user_id),
        )
        raise _credentials_exception()


def get_session_store() -> RedisSessionStore:
    """Dependency injection for Redis session store.

    Returns singleton instance of RedisSessionStore.
    Lazily initialized on first call.
    """
    global _session_store
    if _session_store is None:
        if _should_use_in_memory_session_store():
            _session_store = InMemorySessionStore()
            logger.info("session_store_initialized", backend="in_memory")
        else:
            redis_url = os.getenv("REDIS_URL", "rediss://redis:6379/0")
            _session_store = RedisSessionStore(redis_url)
            logger.info(
                "session_store_initialized",
                backend="redis",
                redis_url=redact_connection_url(redis_url),
            )
    return _session_store


async def get_current_user(
    # Plain ``Request`` annotation (FastAPI special-cases it); the None
    # default only exists so unit tests can call this directly.
    request: Request = None,  # type: ignore[assignment]
    token: Optional[str] = Depends(_optional_bearer_token),
    db: Session = Depends(get_session),
    session_store: Optional[RedisSessionStore] = Depends(get_session_store),
) -> UserModel:
    credentials_exception = _credentials_exception()

    user_id = None
    tenant_id = None
    token_version_claim: Optional[int] = None
    local_session_id: Optional[UUID] = None
    session_cookie_auth = False

    # 0. Passwordless browser sessions carry only the opaque
    # __Host-regengine_session cookie — no Bearer token is ever issued to
    # the browser. Resolve the session row exactly like /auth/me does
    # (revocation, expiry, and user status are enforced by that lookup),
    # then fall through to the shared tenant/RLS binding below.
    if not token:
        # No cookie either → keep the historical bare-401 shape
        # (WWW-Authenticate: Bearer) that API clients and tests expect.
        # request is None only when unit tests call this directly.
        if request is None or not request.cookies.get(AUTH_SESSION_COOKIE):
            raise credentials_exception
        try:
            arm_global_admin_context(db)
            context = get_current_active_session_context(
                request=request,
                db=db,
                crypto_service=get_auth_crypto_service(),
            )
        finally:
            disarm_global_admin_context(db)
        user_id = str(context.user.id)
        session_cookie_auth = True

    # 1. Retain Supabase bearer compatibility only outside production.
    # RegEngine also issues its own signed JWTs from passwordless auth flows,
    # so a Supabase rejection in local/staging may still be a valid RegEngine
    # token and falls through to the local verifier.
    # Production/consolidated runtime accepts only RegEngine-issued local
    # bearer tokens, whose JTI, session row, and token_version all participate
    # in the local revocation domain. Do not even send bearer material to the
    # independent Supabase verifier in that runtime.
    sb = get_supabase() if token and not requires_strict_auth_runtime() else None
    if sb:
        try:
            # Supabase validates the JWT signature and expiration against the project
            user_response = sb.auth.get_user(token)
            if user_response and user_response.user:
                sb_user = user_response.user
                user_id = sb_user.id
                # SECURITY (#1345): tenant_id MUST come from app_metadata
                # (service-role-only writable), NEVER from user_metadata
                # (user-writable via supabase.auth.updateUser). Reading
                # user_metadata lets a multi-tenant user silently switch
                # which tenant they act as from the browser.
                app_meta = getattr(sb_user, "app_metadata", None) or {}
                tenant_id = app_meta.get("tenant_id")
                tv_raw = app_meta.get("tv")
                if tv_raw is None:
                    tv_raw = app_meta.get("token_version")
                token_version_claim = _parse_token_version(tv_raw)

                # User existence verified below (db.get raises if missing)
        except Exception as e:
            if _is_supabase_token_rejection(e):
                logger.warning(
                    "supabase_auth_token_rejected",
                    error=str(e),
                    error_type=e.__class__.__name__,
                )
                # Continue to the local RegEngine JWT verifier. If this token
                # is not a valid RegEngine session token either, the local
                # decode path below returns the same 401.
            else:
                # httpx transport failures (ConnectError, timeouts, …) are
                # infrastructure errors, not token verdicts — without this
                # they re-raise as 500s on every JWT-authed route whenever
                # Supabase is unreachable, instead of the fail-closed 401
                # (prod) / local-JWT fallback (dev) below.
                if not (
                    _is_supabase_transient_exception(e)
                    or isinstance(
                        e, (OSError, TimeoutError, ConnectionError, ValueError, AttributeError, httpx.HTTPError)
                    )
                ):
                    raise
                logger.warning("supabase_auth_failed", error=str(e))

    # 2. Fallback to local RegEngine JWT.
    # Reached when Supabase is not configured, or when Supabase rejects a token
    # that may be a RegEngine-issued session token. This is the only production
    # bearer path, so all production principals share one revocation domain.
    if not user_id:
        try:
            # Production workers refresh their verification cache before every
            # local-JWT verdict. A rotation or emergency key revocation on one
            # replica is therefore observed by every other replica on its next
            # request instead of waiting for a process restart.
            if requires_strict_auth_runtime():
                await sync_keys_from_registry()
            payload = decode_access_token(token)
            user_id = payload.get("sub")
            # ``payload`` is a verified JWT (decode_access_token validates
            # signature + expiry), not a request body. The tenant_id claim is
            # cryptographically signed by the auth issuer — this is the
            # canonical EPIC-A path for JWT auth.
            tenant_id = payload.get("tenant_id") or payload.get("tid")  # nosemgrep: tenant-id-from-request-body
            # #1349 / #1375 — capture the version the token was minted against.
            # The live user row carries the current version; a mismatch means
            # this token was invalidated by a password reset or logout-all.
            token_version_claim = _parse_token_version(payload.get("tv"))
            sid_raw = payload.get("sid")
            session_id_raw = payload.get("session_id")
            if sid_raw and session_id_raw and str(sid_raw) != str(session_id_raw):
                logger.warning(
                    "mismatched_session_claims_rejected",
                    user_id=user_id,
                    sid=str(sid_raw),
                    session_id=str(session_id_raw),
                )
                raise credentials_exception
            session_id_claim = sid_raw or session_id_raw
            if session_id_claim:
                try:
                    local_session_id = UUID(str(session_id_claim))
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "invalid_session_claim_rejected",
                        user_id=user_id,
                        session_id=str(session_id_claim),
                    )
                    raise credentials_exception from exc

            if user_id is None:
                raise credentials_exception

            # SECURITY (#1071): async Redis revocation check. The sync
            # `_check_revoked` inside `decode_access_token` only looks at
            # this worker's in-memory set — it cannot see a revocation
            # written by another worker because it is a sync function
            # called under a running event loop. We must re-check here
            # on the async path so a /logout on worker A immediately
            # blocks subsequent requests on every other worker, not just
            # A itself.
            jti = payload.get("jti")
            if jti and await check_revoked_async(jti):
                logger.warning(
                    "revoked_jti_rejected",
                    user_id=user_id,
                    jti=jti,
                )
                raise credentials_exception

        except (RevocationBackendUnavailable, JWTKeyRegistryBackendUnavailable) as exc:
            logger.error("jwt_auth_backend_unavailable", error_type=type(exc).__name__)
            raise _session_store_exception() from exc
        except JWTError:
            raise credentials_exception

    # SECURITY (#1383): clear any stale tenant context that may be lingering
    # on this pooled connection from a prior request. If this request's JWT
    # has no resolvable tenant and the user is not a sysadmin, we want RLS
    # to fail closed, not inherit the previous caller's scope.
    if db.bind:
        try:
            TenantContext.clear_tenant_context(db)
        except (RuntimeError, OSError, AttributeError) as exc:  # pragma: no cover
            # If the clear call itself fails we still proceed — the
            # subsequent set_tenant_context (or, absent that, the RLS
            # fail-closed default from #1091) is the primary guard.
            # #2696: but never silently — a failing hygiene clear on a
            # pooled connection is exactly the #1383 condition.
            logger.warning(
                "stale_tenant_context_clear_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )

    # Set a transaction-local user context so self-service RLS can load the
    # authenticated row without opening the global sysadmin branch.
    bind_authenticated_user_context(db, user_id)

    user = db.get(UserModel, UUID(user_id))
    if user is None:
        logger.warning("user_not_found_in_db", user_id=user_id)
        raise credentials_exception

    if local_session_id is not None:
        store = session_store
        if store is None or not hasattr(store, "get_session"):
            store = get_session_store()
        await _enforce_session_bound_token(
            local_session_id=local_session_id,
            token_user_id=user_id,
            user=user,
            session_store=store,
        )

    # SECURITY (#1860): enforce token_version. /auth/logout-all and
    # logout-all and account security events bump user.token_version expecting this check;
    # without it, stolen access tokens survive both for their full TTL.
    user_tv = _parse_token_version(getattr(user, "token_version", None)) or 0
    if token_version_claim is not None:
        if token_version_claim < user_tv:
            logger.warning(
                "stale_token_version_rejected",
                user_id=user_id,
                token_tv=token_version_claim,
                user_tv=user_tv,
            )
            raise credentials_exception
    elif user_tv > 0 and not session_cookie_auth:
        # Cookie sessions never carry a version claim; logout-all kills
        # them by revoking their SessionModel row instead (sessions_router).
        logger.warning(
            "missing_token_version_rejected",
            user_id=user_id,
            user_tv=user_tv,
        )
        raise credentials_exception

    logger.info("user_authenticated", user_id=user_id)

    # SECURITY (#1345): if no trusted tenant claim is present, derive from
    # the DB — but only when there is exactly one active membership. Users
    # who belong to multiple tenants must have tenant_id written into
    # app_metadata (or the local JWT) by the server; we refuse to guess.
    if not tenant_id:
        try:
            # Selecting a tenant is the final pre-tenant bootstrap query.  The
            # global arm is removed before any tenant-scoped route work.
            arm_global_admin_context(db)
            active_memberships = (
                db.execute(
                    select(MembershipModel).where(
                        MembershipModel.user_id == UUID(user_id),
                        MembershipModel.is_active == True,  # noqa: E712  (SQLAlchemy needs ==)
                    )
                )
                .scalars()
                .all()
            )
        finally:
            disarm_global_admin_context(db)
        if len(active_memberships) == 1:
            tenant_id = str(active_memberships[0].tenant_id)
            logger.info(
                "tenant_derived_from_sole_membership",
                user_id=user_id,
                tenant_id=tenant_id,
            )
        elif len(active_memberships) > 1 and not user.is_sysadmin:
            logger.warning(
                "ambiguous_tenant_no_trusted_claim",
                user_id=user_id,
                membership_count=len(active_memberships),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant selection required — no app_metadata.tenant_id set",
                headers={"WWW-Authenticate": "Bearer"},
            )
        elif not user.is_sysadmin:
            # SECURITY (#1383): zero memberships AND not a sysadmin AND no
            # tenant claim means this token cannot be bound to any tenant
            # scope. Previously we returned the user with tenant_context
            # unset, which — combined with fail-open RLS on pooled
            # connections — could leak data across tenants. Reject at the
            # auth layer so tenant-scoped routes never see this request.
            logger.warning(
                "tenant_required_no_membership",
                user_id=user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant required — no tenant claim and no active memberships",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Store tenant context in request state or handle via DB session context
    if tenant_id:
        try:
            # PostgreSQL uses session-scoped RLS state; SQLite stores the same
            # tenant context in session.info so local/dev parity is preserved.
            TenantContext.set_tenant_context(db, UUID(tenant_id))
            # #2461: also seed the RLS contextvar so the Engine begin-hook
            # re-applies app.tenant_id on every transaction (the legacy
            # session-scoped GUC above survives commits, the hook makes the
            # transaction-scoped layer idempotent with it). Async dependency
            # — the set is visible downstream.
            set_rls_tenant_id(tenant_id)
            # Verify membership exists for this tenant
            membership = db.execute(
                select(MembershipModel).where(
                    MembershipModel.user_id == UUID(user_id), MembershipModel.tenant_id == UUID(tenant_id)
                )
            ).scalar_one_or_none()

            if not membership:
                logger.warning("invalid_tenant_context", user_id=user_id, tenant_id=tenant_id)
                raise credentials_exception

            if not membership.is_active:
                logger.warning("deactivated_user_access_attempt", user_id=user_id, tenant_id=tenant_id)
                raise credentials_exception

        except (RuntimeError, OSError, ValueError, KeyError, AttributeError) as e:
            logger.error("tenant_context_error", error=str(e))
            raise credentials_exception

        # SECURITY (#2687 follow-up): enforce live tenant status on the opaque
        # __Host-regengine_session path. JWT paths carry a mint-time
        # tenant_status claim that the edge middleware checks, but an opaque
        # cookie is unreadable at the edge and carries no claims — without
        # this check a suspended tenant's browser session retained full
        # access. Fail closed: a status read error denies (503), it never
        # allows. Global sysadmins are exempt — suspension is a tenant-level
        # control, not an operator control, and sysadmins must retain access
        # to manage suspended tenants.
        if session_cookie_auth and not user.is_sysadmin:
            try:
                # populate_existing: always read live status from the DB —
                # an identity-map hit could serve a stale "active".
                tenant = db.get(TenantModel, UUID(tenant_id), populate_existing=True)
            except Exception as exc:
                logger.error(
                    "tenant_status_lookup_failed",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    error=str(exc),
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service temporarily unavailable",
                ) from exc
            tenant_status = getattr(tenant, "status", None) if tenant is not None else None
            if tenant_status not in ("active", "trial"):
                # Uniform 401 body — same as every other credential failure,
                # so responses expose no tenant-existence or status oracle.
                logger.warning(
                    "suspended_tenant_session_rejected",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    tenant_status=tenant_status,
                )
                raise credentials_exception

    return user


class PermissionChecker:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    def __call__(self, user: UserModel = Depends(get_current_user), db: Session = Depends(get_session)):
        # Inspect current tenant context from session?
        # Since set_tenant_context was called in get_current_user, RLS is active.
        # But we need to check the Roles/Permissions for the current tenant.

        # We need to retrieve the tenant_id embedded in the current RLS context
        # OR we parse it from the token again (but get_current_user already did).
        # We can also get it from `db` if we trust `get_tenant_context`.

        current_tenant_id = TenantContext.get_tenant_context(db)
        if not current_tenant_id:
            # SECURITY (#1065): fail closed for everyone — including sysadmins.
            # Previously this short-circuited with `return True` when
            # `user.is_sysadmin`, granting access to tenant-scoped endpoints
            # with no bound tenant. That breaks the fail-closed invariant:
            # a sysadmin performing a tenant-scoped operation MUST supply a
            # tenant context (X-Tenant-ID / JWT claim). Global sysadmin
            # privilege is still honored on the normal path below once a
            # tenant is bound.
            raise HTTPException(
                status_code=403,
                detail="E_NO_TENANT_CONTEXT: tenant-scoped endpoint requires X-Tenant-ID",
            )

        # Get Membership and Role
        stmt = (
            select(RoleModel)
            .join(MembershipModel)
            .where(
                MembershipModel.user_id == user.id,
                MembershipModel.tenant_id == current_tenant_id,
                or_(
                    RoleModel.tenant_id.is_(None),
                    RoleModel.tenant_id == current_tenant_id,
                ),
            )
        )
        role = db.execute(stmt).scalar_one_or_none()

        if not role:
            raise HTTPException(status_code=403, detail="Role not found")

        # Check permissions with wildcard and namespace support.
        if has_permission(role.permissions or [], self.required_permission):
            return True

        raise HTTPException(status_code=403, detail="Insufficient permissions")


def verify_path_tenant_matches(
    tenant_id: str = Path(...),
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UUID:
    """Reject a request when the URL path ``tenant_id`` does not match the
    caller's authenticated tenant context.

    Without this, routes shaped as ``/v1/compliance/{tenant_id}/...`` accept
    any UUID in the path and pass it straight to the service layer, producing
    a trivial IDOR: caller in tenant A supplies tenant B's UUID and reads or
    mutates tenant B's data. See #1328.
    """
    try:
        path_tenant = UUID(tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid tenant_id format")

    auth_tenant = TenantContext.get_tenant_context(db)
    if auth_tenant is None:
        logger.warning("path_tenant_check_no_context", user_id=str(user.id))
        raise HTTPException(status_code=403, detail="No tenant context active")

    if path_tenant != auth_tenant:
        logger.warning(
            "cross_tenant_path_access_denied",
            user_id=str(user.id),
            auth_tenant=str(auth_tenant),
            path_tenant=str(path_tenant),
        )
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    return path_tenant


async def get_tenant_scoped_session(
    tenant_id: UUID = Depends(verify_path_tenant_matches),
):
    """Yield a SQLAlchemy session with ``app.tenant_id`` GUC bound for RLS.

    Usage in routes shaped as ``/v1/foo/{tenant_id}/...``::

        @router.get("/items/{tenant_id}")
        def list_items(
            session: Session = Depends(get_tenant_scoped_session),
        ):
            return session.execute(select(Item)).scalars().all()

    The dependency runs ``verify_path_tenant_matches`` first (rejects path
    vs auth-context mismatch with 403, malformed UUID with 400) and then
    yields a session with ``app.tenant_id`` set at transaction scope via
    the canonical ``set_tenant_guc`` primitive. Any RLS policy on tables
    referenced inside the request will be enforced by Postgres — even if
    a query in the handler forgets its ``WHERE tenant_id = ...`` clause.

    Global sysadmin status is intentionally not a bypass. Cross-tenant
    control-plane operations must use a distinct high-assurance sysadmin
    route and must not reuse this tenant-scoped dependency.

    Defense-in-depth, not a substitute for tenant scoping in service code.
    Routes still verify tenant on writes; this just guarantees that an
    accidentally-omitted predicate fails closed instead of leaking.

    #2461: async generator (was a sync ``def``) so the ``set_rls_tenant_id``
    seed below is visible downstream — a sync dependency runs in a
    threadpool context copy whose contextvar sets never propagate to the
    handler. Seeding the VERIFIED path tenant (rather than relying on the
    auth tenant seeded by ``get_current_user``) makes the Engine begin-hook
    re-apply the verified tenant on every transaction, including after a
    mid-request commit()/rollback() clears the transaction-scoped GUC that
    ``get_tenant_session`` set.
    """
    set_rls_tenant_id(str(tenant_id))
    # Drive the sync generator manually (``async def`` can't ``yield from``
    # a sync generator) — same pattern as ``get_auth_scoped_session``.
    gen = get_tenant_session(str(tenant_id))
    session = next(gen)
    try:
        yield session
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


# Imports for ``get_auth_scoped_session``. Aliased to avoid colliding
# with the local ``models.TenantContext`` (a session-context helper)
# that's already imported above — same name, different class.
from shared.tenant_context import (  # noqa: E402
    TenantContext as AuthTenantContext,
    resolve_tenant_context,
)


async def get_auth_scoped_session(
    ctx: AuthTenantContext = Depends(resolve_tenant_context),
):
    """Yield a session with ``app.tenant_id`` bound from the AUTHENTICATED
    principal's tenant — companion to ``get_tenant_scoped_session`` for
    routes WITHOUT a ``{tenant_id}`` path parameter.

    Usage on routes where the operating tenant comes from the auth
    context (API-key row tenant or signed session claim), not from the
    URL path::

        @router.post("/v1/audit/export")
        async def export_audit_logs(
            session: Session = Depends(get_auth_scoped_session),
        ):
            # RLS enforced via app.tenant_id even if the handler
            # forgets to filter on tenant_id explicitly.
            ...

    Resolution order is the canonical EPIC-A one (see
    ``shared.tenant_context.resolve_tenant_context`` for the full
    contract): API-key principal → signed session principal. Tenant from
    URL path / query / body /
    Supabase ``user_metadata`` is rejected with HTTP 409 if it
    conflicts with the principal's tenant.

    Use ``get_tenant_scoped_session`` instead when the route HAS a
    ``{tenant_id}`` path segment that must be cross-checked against
    the caller's auth context — the two deps cover orthogonal route
    shapes.
    """
    # Drive the sync ``get_tenant_session`` generator manually because
    # ``async def`` can't ``yield from`` a sync generator. Cleanup
    # (rollback + close inside ``get_tenant_session``) runs when this
    # async generator is closed by FastAPI on request completion.
    gen = get_tenant_session(ctx.tenant_id)
    session = next(gen)
    try:
        yield session
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


# --- API Key Auth (Remediation Phase 1) ---
from fastapi.security import APIKeyHeader
from shared.api_key_store import get_db_key_store

api_key_header = APIKeyHeader(name="X-RegEngine-API-Key", auto_error=False)


async def get_current_tenant(key: str = Depends(api_key_header), db: Session = Depends(get_session)) -> UUID:
    """
    Validates API Key and returns the associated Tenant ID.
    Enforces Strict Security Boundary (Constitution 4.1).
    Sets the RLS session context for the database connection.
    """
    if not key:
        raise HTTPException(status_code=401, detail="Missing API Key")

    store = await get_db_key_store()
    api_key_data = await store.validate_key(key)

    if not api_key_data:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    if not api_key_data.tenant_id:
        raise HTTPException(status_code=403, detail="API Key not associated with a Tenant")

    tenant_id = UUID(api_key_data.tenant_id)

    # SECURITY: enforce live tenant status on the API-key path, mirroring
    # the opaque-session check in get_current_user. Without this, a
    # suspended tenant's API keys retain full access. Fail closed: a status
    # read error denies (503), it never allows. The rejection body matches
    # the invalid-key response so it exposes no tenant-status oracle.
    try:
        tenant = db.get(TenantModel, tenant_id, populate_existing=True)
    except Exception as exc:
        logger.error(
            "api_key_tenant_status_lookup_failed",
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        ) from exc
    tenant_status = getattr(tenant, "status", None) if tenant is not None else None
    if tenant_status not in ("active", "trial"):
        logger.warning(
            "suspended_tenant_api_key_rejected",
            tenant_id=str(tenant_id),
            tenant_status=tenant_status,
        )
        raise HTTPException(status_code=403, detail="Invalid API Key")

    # SEC-RLS: Ensure the database session is restricted to this tenant
    TenantContext.set_tenant_context(db, tenant_id)

    return tenant_id
