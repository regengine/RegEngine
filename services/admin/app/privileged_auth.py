"""Authentication boundaries for privileged human and workload routes.

Human administration is authenticated only with the opaque browser session
cookie.  Workload tenant provisioning is authenticated only with a
database-backed, tenantless API key carrying one exact scope. Privileged
authentication realms use Redis-backed failure budgets in staging/cloud and
production; only explicit non-cloud local/test runs may use process memory.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from shared.api_key_store import APIKeyResponse, DatabaseAPIKeyStore
from shared.auth import get_key_store
from shared.env import CLOUD_ENV_VARS, get_environment
from shared.permissions import has_permission
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .auth.session_auth import (
    HIGH_ASSURANCE_AUTH_METHODS,
    ActiveSessionContext,
    get_auth_crypto_service,
    get_current_active_session_context,
)
from .auth_crypto import AuthCryptoService
from .database import (
    arm_global_admin_context,
    bind_authenticated_user_context,
    disarm_global_admin_context,
    get_session,
)
from .sqlalchemy_models import (
    MembershipModel,
    OrganizationMembershipModel,
    RoleModel,
    SessionModel,
    UserModel,
)

logger = structlog.get_logger("admin.privileged_auth")

PRIVILEGED_AUTH_MAX_FAILURES = 5
PRIVILEGED_AUTH_WINDOW_SECONDS = 60
TENANT_PROVISIONER_SCOPE = "internal.tenants.create"
TENANT_PROVISIONER_MAX_TTL = timedelta(days=90)
TENANT_PROVISIONER_MAX_RATE_PER_MINUTE = 10
_LOCAL_THROTTLE_ENVIRONMENTS = {"development", "local", "test"}
_ADMIN_AUTH_REALM = "human-admin"
_REVIEW_READ_AUTH_REALM = "review-read"
_REVIEW_DECIDE_AUTH_REALM = "review-decide"
_WORKLOAD_AUTH_REALM = "workload-tenant-provisioner"


def _authentication_service_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service temporarily unavailable.",
    )


def _rate_limited() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many failed privileged authentication attempts.",
        headers={"Retry-After": str(PRIVILEGED_AUTH_WINDOW_SECONDS)},
    )


_REDIS_CLIENT_UNSET = object()


class PrivilegedAuthThrottle:
    """Shared invalid-authentication counter with a local-development fallback.

    Restricted staging/cloud and production never fall back to process memory.
    If Redis is missing or an operation fails, privileged authentication
    returns 503 rather than serving a request with an unverifiable
    cross-replica failure budget.
    """

    def __init__(self, redis_client: object = _REDIS_CLIENT_UNSET) -> None:
        self._redis = None if redis_client is _REDIS_CLIENT_UNSET else redis_client
        self._redis_initialized = redis_client is not _REDIS_CLIENT_UNSET
        self._memory: dict[str, list[float]] = defaultdict(list)
        self._memory_lock = threading.Lock()
        self._degraded_logged = False

    @staticmethod
    def _redis_url() -> str | None:
        return os.getenv("REGENGINE_REDIS_URL") or os.getenv("REDIS_URL")

    async def _get_redis(self):
        if self._redis_initialized:
            return self._redis

        self._redis_initialized = True
        redis_url = self._redis_url()
        if not redis_url:
            return None

        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(
                redis_url,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
        except Exception as exc:  # pragma: no cover - import/config environment dependent
            self._backend_failure("initialize", exc)
        return self._redis

    @staticmethod
    def _memory_fallback_allowed() -> bool:
        environment = get_environment()
        cloud_deployment = any(os.getenv(name) for name in CLOUD_ENV_VARS)
        return not cloud_deployment and environment in _LOCAL_THROTTLE_ENVIRONMENTS

    def _backend_failure(self, operation: str, exc: Exception | None = None) -> None:
        fail_closed = not self._memory_fallback_allowed()
        if not self._degraded_logged:
            self._degraded_logged = True
            log = logger.error if fail_closed else logger.warning
            log(
                "privileged_auth_throttle_unavailable",
                operation=operation,
                error_class=type(exc).__name__ if exc else "Unavailable",
                fail_mode="closed" if fail_closed else "local_memory",
            )
        if fail_closed:
            raise _authentication_service_unavailable() from exc

    @staticmethod
    def _key(subject: str) -> str:
        # Avoid retaining a source IP verbatim in the Redis keyspace.
        digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        return f"privileged_auth:failures:{digest}"

    def _memory_is_limited(self, subject: str) -> bool:
        now = time.monotonic()
        with self._memory_lock:
            recent = [
                timestamp
                for timestamp in self._memory[subject]
                if now - timestamp < PRIVILEGED_AUTH_WINDOW_SECONDS
            ]
            self._memory[subject] = recent
            return len(recent) >= PRIVILEGED_AUTH_MAX_FAILURES

    def _memory_record_failure(self, subject: str) -> int:
        now = time.monotonic()
        with self._memory_lock:
            recent = [
                timestamp
                for timestamp in self._memory[subject]
                if now - timestamp < PRIVILEGED_AUTH_WINDOW_SECONDS
            ]
            recent.append(now)
            self._memory[subject] = recent[-(PRIVILEGED_AUTH_MAX_FAILURES * 2) :]
            return len(recent)

    async def is_limited(self, subject: str) -> bool:
        client = await self._get_redis()
        if client is None:
            self._backend_failure("read")
            return self._memory_is_limited(subject)

        try:
            raw_count = await client.get(self._key(subject))
            if raw_count is None:
                self._degraded_logged = False
                return False
            count = int(raw_count)
            self._degraded_logged = False
            return count >= PRIVILEGED_AUTH_MAX_FAILURES
        except HTTPException:
            raise
        except Exception as exc:
            self._backend_failure("read", exc)
            return self._memory_is_limited(subject)

    async def record_failure(self, subject: str) -> int:
        client = await self._get_redis()
        if client is None:
            self._backend_failure("increment")
            return self._memory_record_failure(subject)

        try:
            pipeline = client.pipeline(transaction=True)
            pipeline.incr(self._key(subject))
            pipeline.expire(self._key(subject), PRIVILEGED_AUTH_WINDOW_SECONDS)
            results = await pipeline.execute()
            self._degraded_logged = False
            return int(results[0])
        except HTTPException:
            raise
        except Exception as exc:
            self._backend_failure("increment", exc)
            return self._memory_record_failure(subject)

    async def reset(self, subject: str) -> None:
        client = await self._get_redis()
        if client is None:
            self._backend_failure("reset")
        else:
            try:
                await client.delete(self._key(subject))
                self._degraded_logged = False
            except HTTPException:
                raise
            except Exception as exc:
                self._backend_failure("reset", exc)

        with self._memory_lock:
            self._memory.pop(subject, None)


_privileged_auth_throttle = PrivilegedAuthThrottle()


def get_privileged_auth_throttle() -> PrivilegedAuthThrottle:
    return _privileged_auth_throttle


@dataclass(frozen=True)
class PrivilegedActor:
    actor_type: str
    actor_id: str
    actor_name: str | None = None
    session_id: str | None = None
    auth_method: str | None = None
    tenant_id: str | None = None
    permissions: tuple[str, ...] = ()
    user: UserModel | None = None
    session: SessionModel | None = None
    api_key: APIKeyResponse | None = None


def _request_audit_fields(request: Request) -> tuple[str, str]:
    audit_context = getattr(request.state, "audit_context", None)
    if isinstance(audit_context, dict):
        request_id = str(audit_context.get("request_id") or "")
        source_ip = str(audit_context.get("actor_ip") or "")
    else:
        request_id = ""
        source_ip = ""

    if not request_id:
        request_id = str(getattr(request.state, "privileged_request_id", "") or uuid.uuid4())
        request.state.privileged_request_id = request_id
    if not source_ip:
        source_ip = request.client.host if request.client else "unknown"
    return request_id, source_ip


def audit_privileged_action(
    request: Request,
    *,
    action: str,
    outcome: str,
    actor: PrivilegedActor | None = None,
    target: str | None = None,
    selected_tenant: str | None = None,
    reason: str | None = None,
) -> None:
    """Emit a secret-free, actor-attributed privileged security event."""
    request_id, source_ip = _request_audit_fields(request)
    bounded_selected_tenant = str(selected_tenant)[:64] if selected_tenant else None
    bounded_target = str(target)[:255] if target else None
    logger.info(
        "privileged_action_audit",
        request_id=request_id,
        source_ip=source_ip,
        method=request.method,
        path=request.url.path,
        action=action,
        outcome=outcome,
        target=bounded_target,
        selected_tenant=bounded_selected_tenant,
        actor_type=actor.actor_type if actor else "unauthenticated",
        actor_id=actor.actor_id if actor else None,
        actor_name=actor.actor_name if actor else None,
        session_id=actor.session_id if actor else None,
        auth_method=actor.auth_method if actor else None,
        reason=reason,
    )


def _throttle_subject(request: Request, *, realm: str) -> str:
    _, source_ip = _request_audit_fields(request)
    # Success in one authority domain must not reset another domain's failure
    # budget. The combined value is hashed before it enters Redis.
    return f"{realm}:{source_ip}"


async def _start_authentication(
    request: Request,
    throttle: PrivilegedAuthThrottle,
    *,
    realm: str,
) -> str:
    subject = _throttle_subject(request, realm=realm)
    if await throttle.is_limited(subject):
        audit_privileged_action(
            request,
            action="authenticate",
            outcome="denied",
            target=request.url.path,
            selected_tenant=request.headers.get("X-Tenant-ID"),
            reason="failure_budget_exhausted",
        )
        raise _rate_limited()
    if "x-admin-key" in request.headers:
        await throttle.record_failure(subject)
        audit_privileged_action(
            request,
            action="authenticate",
            outcome="denied",
            target=request.url.path,
            selected_tenant=request.headers.get("X-Tenant-ID"),
            reason="retired_admin_header_present",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Admin-Key is not an accepted authentication method.",
        )
    return subject


async def _deny_authentication(
    request: Request,
    throttle: PrivilegedAuthThrottle,
    subject: str,
    *,
    error: HTTPException,
    reason: str,
    actor: PrivilegedActor | None = None,
) -> None:
    if error.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
        await throttle.record_failure(subject)
    audit_privileged_action(
        request,
        action="authenticate",
        outcome="denied",
        actor=actor,
        target=request.url.path,
        selected_tenant=actor.tenant_id if actor else request.headers.get("X-Tenant-ID"),
        reason=reason,
    )
    raise error


async def _load_active_session(
    request: Request,
    db: Session,
    crypto_service: AuthCryptoService,
    throttle: PrivilegedAuthThrottle,
    *,
    realm: str,
) -> tuple[ActiveSessionContext, str]:
    subject = await _start_authentication(request, throttle, realm=realm)

    # The opaque cookie identifies a session before a tenant is known.  The
    # control-plane connection therefore starts from its checkout-time
    # ``is_sysadmin=false`` baseline, arms only for this identity lookup, and
    # is disarmed again before any authorization or route-specific work.
    try:
        arm_global_admin_context(db)
        context = get_current_active_session_context(
            request=request,
            db=db,
            crypto_service=crypto_service,
        )
    except HTTPException as exc:
        await _deny_authentication(
            request,
            throttle,
            subject,
            error=exc,
            reason="inactive_or_missing_session" if exc.status_code == 401 else "session_backend_unavailable",
        )
        raise AssertionError("unreachable")
    except Exception as exc:
        audit_privileged_action(
            request,
            action="authenticate",
            outcome="error",
            target=request.url.path,
            reason="session_backend_unavailable",
        )
        raise _authentication_service_unavailable() from exc
    finally:
        try:
            disarm_global_admin_context(db)
        except Exception as exc:
            audit_privileged_action(
                request,
                action="authenticate",
                outcome="error",
                target=request.url.path,
                reason="session_scope_disarm_failed",
            )
            raise _authentication_service_unavailable() from exc
    bind_authenticated_user_context(db, context.user.id)
    return context, subject


async def require_sysadmin_high_assurance(
    request: Request,
    db: Session = Depends(get_session),
    crypto_service: AuthCryptoService = Depends(get_auth_crypto_service),
    throttle: PrivilegedAuthThrottle = Depends(get_privileged_auth_throttle),
) -> PrivilegedActor:
    """Require an active WebAuthn/SSO browser session for a sysadmin."""
    context, subject = await _load_active_session(
        request,
        db,
        crypto_service,
        throttle,
        realm=_ADMIN_AUTH_REALM,
    )
    actor = PrivilegedActor(
        actor_type="staff_user",
        actor_id=str(context.user.id),
        session_id=str(context.session.id),
        auth_method=getattr(context.session, "auth_method", None),
        user=context.user,
        session=context.session,
    )

    if not bool(getattr(context.user, "is_sysadmin", False)):
        await _deny_authentication(
            request,
            throttle,
            subject,
            error=HTTPException(status_code=403, detail="System administrator access required."),
            reason="not_sysadmin",
            actor=actor,
        )

    if actor.auth_method not in HIGH_ASSURANCE_AUTH_METHODS:
        await _deny_authentication(
            request,
            throttle,
            subject,
            error=HTTPException(
                status_code=403,
                detail={
                    "code": "requires_step_up",
                    "message": "High assurance authentication required.",
                    "auth_method": actor.auth_method,
                },
            ),
            reason="low_assurance_session",
            actor=actor,
        )

    await throttle.reset(subject)
    audit_privileged_action(
        request,
        action="authenticate",
        outcome="succeeded",
        actor=actor,
        target=request.url.path,
    )
    return actor


async def _require_review_permission(
    request: Request,
    db: Session,
    crypto_service: AuthCryptoService,
    throttle: PrivilegedAuthThrottle,
    *,
    permission: str,
    high_assurance: bool,
) -> PrivilegedActor:
    context, subject = await _load_active_session(
        request,
        db,
        crypto_service,
        throttle,
        realm=_REVIEW_DECIDE_AUTH_REALM if high_assurance else _REVIEW_READ_AUTH_REALM,
    )
    provisional_actor = PrivilegedActor(
        actor_type="tenant_user",
        actor_id=str(context.user.id),
        session_id=str(context.session.id),
        auth_method=getattr(context.session, "auth_method", None),
        user=context.user,
        session=context.session,
    )

    if high_assurance and provisional_actor.auth_method not in HIGH_ASSURANCE_AUTH_METHODS:
        await _deny_authentication(
            request,
            throttle,
            subject,
            error=HTTPException(
                status_code=403,
                detail={
                    "code": "requires_step_up",
                    "message": "High assurance authentication required.",
                    "auth_method": provisional_actor.auth_method,
                },
            ),
            reason="low_assurance_session",
            actor=provisional_actor,
        )

    active_membership_id = getattr(context.session, "active_membership_id", None)
    if active_membership_id is None:
        await _deny_authentication(
            request,
            throttle,
            subject,
            error=HTTPException(status_code=403, detail="An active tenant membership is required."),
            reason="missing_active_membership",
            actor=provisional_actor,
        )

    try:
        # Resolve the session-selected organization and its tenant role while
        # the tenant is not known yet.  Review handlers receive only the
        # derived tenant ID and re-enter tenant RLS themselves.
        arm_global_admin_context(db)
        organization_membership = db.execute(
            select(OrganizationMembershipModel)
            .where(
                OrganizationMembershipModel.id == active_membership_id,
                OrganizationMembershipModel.user_id == context.user.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if organization_membership is None:
            await _deny_authentication(
                request,
                throttle,
                subject,
                error=HTTPException(status_code=401, detail="Authentication required."),
                reason="stale_active_membership",
                actor=provisional_actor,
            )

        tenant_id = organization_membership.organization_id
        role = db.execute(
            select(RoleModel)
            .join(MembershipModel, MembershipModel.role_id == RoleModel.id)
            .where(
                MembershipModel.user_id == context.user.id,
                MembershipModel.tenant_id == tenant_id,
                MembershipModel.is_active.is_(True),
                or_(RoleModel.tenant_id.is_(None), RoleModel.tenant_id == tenant_id),
            )
            .limit(1)
        ).scalar_one_or_none()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "review_permission_lookup_failed",
            user_id=str(context.user.id),
            error_class=type(exc).__name__,
        )
        audit_privileged_action(
            request,
            action="authenticate",
            outcome="error",
            actor=provisional_actor,
            target=request.url.path,
            reason="permission_backend_unavailable",
        )
        raise _authentication_service_unavailable() from exc
    finally:
        try:
            disarm_global_admin_context(db)
        except Exception as exc:
            audit_privileged_action(
                request,
                action="authenticate",
                outcome="error",
                actor=provisional_actor,
                target=request.url.path,
                reason="review_scope_disarm_failed",
            )
            raise _authentication_service_unavailable() from exc

    permissions = tuple(role.permissions or ()) if role is not None else ()
    actor = PrivilegedActor(
        actor_type="tenant_user",
        actor_id=str(context.user.id),
        session_id=str(context.session.id),
        auth_method=getattr(context.session, "auth_method", None),
        tenant_id=str(tenant_id),
        permissions=permissions,
        user=context.user,
        session=context.session,
    )
    if role is None or not has_permission(permissions, permission):
        await _deny_authentication(
            request,
            throttle,
            subject,
            error=HTTPException(status_code=403, detail="Insufficient permissions."),
            reason=f"missing_permission:{permission}",
            actor=actor,
        )

    await throttle.reset(subject)
    audit_privileged_action(
        request,
        action="authenticate",
        outcome="succeeded",
        actor=actor,
        target=request.url.path,
        selected_tenant=actor.tenant_id,
    )
    return actor


async def require_review_read(
    request: Request,
    db: Session = Depends(get_session),
    crypto_service: AuthCryptoService = Depends(get_auth_crypto_service),
    throttle: PrivilegedAuthThrottle = Depends(get_privileged_auth_throttle),
) -> PrivilegedActor:
    return await _require_review_permission(
        request,
        db,
        crypto_service,
        throttle,
        permission="review.read",
        high_assurance=False,
    )


async def require_review_decide(
    request: Request,
    db: Session = Depends(get_session),
    crypto_service: AuthCryptoService = Depends(get_auth_crypto_service),
    throttle: PrivilegedAuthThrottle = Depends(get_privileged_auth_throttle),
) -> PrivilegedActor:
    return await _require_review_permission(
        request,
        db,
        crypto_service,
        throttle,
        permission="review.decide",
        high_assurance=True,
    )


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _workload_key_policy_error(api_key: APIKeyResponse) -> str | None:
    if api_key.tenant_id is not None:
        return "tenant_bound_key"
    if list(api_key.scopes or []) != [TENANT_PROVISIONER_SCOPE]:
        return "scope_mismatch"
    if api_key.expires_at is None:
        return "expiry_required"

    created_at = _as_aware_utc(api_key.created_at)
    expires_at = _as_aware_utc(api_key.expires_at)
    now = datetime.now(timezone.utc)
    if expires_at <= now:
        return "expired"
    if expires_at - created_at > TENANT_PROVISIONER_MAX_TTL:
        return "expiry_exceeds_90_days"
    if not 1 <= api_key.rate_limit_per_minute <= TENANT_PROVISIONER_MAX_RATE_PER_MINUTE:
        return "rate_limit_configuration_invalid"
    return None


async def require_tenant_provisioner_key(
    request: Request,
    x_regengine_api_key: Optional[str] = Header(None, alias="X-RegEngine-API-Key"),
    throttle: PrivilegedAuthThrottle = Depends(get_privileged_auth_throttle),
) -> PrivilegedActor:
    """Authenticate the single-purpose Stripe tenant-provisioning workload."""
    subject = await _start_authentication(request, throttle, realm=_WORKLOAD_AUTH_REALM)
    if not x_regengine_api_key:
        await _deny_authentication(
            request,
            throttle,
            subject,
            error=HTTPException(
                status_code=401,
                detail="Missing workload API key.",
                headers={"WWW-Authenticate": "ApiKey"},
            ),
            reason="missing_workload_key",
        )

    try:
        key_store = get_key_store()
    except Exception as exc:
        audit_privileged_action(
            request,
            action="authenticate",
            outcome="error",
            target=request.url.path,
            reason="api_key_store_unavailable",
        )
        raise _authentication_service_unavailable() from exc

    if not isinstance(key_store, DatabaseAPIKeyStore):
        audit_privileged_action(
            request,
            action="authenticate",
            outcome="error",
            target=request.url.path,
            reason="database_api_key_store_required",
        )
        raise _authentication_service_unavailable()

    try:
        api_key = await key_store.validate_key(x_regengine_api_key)
    except Exception as exc:
        audit_privileged_action(
            request,
            action="authenticate",
            outcome="error",
            target=request.url.path,
            reason="api_key_validation_unavailable",
        )
        raise _authentication_service_unavailable() from exc

    if api_key is None:
        await _deny_authentication(
            request,
            throttle,
            subject,
            error=HTTPException(
                status_code=401,
                detail="Invalid workload API key.",
                headers={"WWW-Authenticate": "ApiKey"},
            ),
            reason="invalid_expired_or_revoked_workload_key",
        )

    actor = PrivilegedActor(
        actor_type="workload_api_key",
        actor_id=api_key.key_id,
        actor_name=api_key.name,
        auth_method="database_api_key",
        api_key=api_key,
    )
    policy_error = _workload_key_policy_error(api_key)
    if policy_error:
        await _deny_authentication(
            request,
            throttle,
            subject,
            error=HTTPException(status_code=403, detail="Workload key is not authorized for tenant provisioning."),
            reason=policy_error,
            actor=actor,
        )

    await throttle.reset(subject)
    ready = getattr(key_store, "rate_limit_backend_ready", None)
    if not callable(ready) or not ready():
        audit_privileged_action(
            request,
            action="authenticate",
            outcome="error",
            actor=actor,
            target=request.url.path,
            reason="workload_rate_limit_unavailable",
        )
        raise _authentication_service_unavailable()
    try:
        rate_info = await key_store.check_rate_limit(
            api_key.key_id,
            api_key.rate_limit_per_minute,
            window_seconds=PRIVILEGED_AUTH_WINDOW_SECONDS,
        )
    except Exception as exc:
        audit_privileged_action(
            request,
            action="authenticate",
            outcome="error",
            actor=actor,
            target=request.url.path,
            reason="workload_rate_limit_unavailable",
        )
        raise _authentication_service_unavailable() from exc

    if not rate_info.allowed:
        audit_privileged_action(
            request,
            action="authenticate",
            outcome="denied",
            actor=actor,
            target=request.url.path,
            reason="workload_rate_limit_exceeded",
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded.",
            headers={"Retry-After": str(rate_info.retry_after or PRIVILEGED_AUTH_WINDOW_SECONDS)},
        )

    audit_privileged_action(
        request,
        action="authenticate",
        outcome="succeeded",
        actor=actor,
        target=request.url.path,
    )
    return actor
