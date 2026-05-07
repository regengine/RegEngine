"""
Subscription Gate — FastAPI dependency for paid endpoint access control.

Checks Redis for the tenant's subscription status and rejects requests
with HTTP 402 Payment Required if no active subscription exists.

Redis key pattern: billing:tenant:{tenant_id} (hash with "status" field)
Allowed statuses: "active", "trialing"

Fail-closed semantics (#1182):
- Missing Redis key  -> 402 (no silent paid-access grant to unbilled tenants).
- Redis error/timeout -> 503 (cannot confirm subscription state).
- Explicit ``SUBSCRIPTION_GATE_FAIL_OPEN=true`` env flag bypasses the gate
  during incidents; intended for manual operator use only. Every bypass
  logs loudly so it shows up in the audit trail.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query, Request

from shared.circuit_breaker import CircuitOpenError, redis_circuit

logger = logging.getLogger("subscription-gate")


def _fail_open_override_enabled() -> bool:
    """Return True if an operator has set ``SUBSCRIPTION_GATE_FAIL_OPEN=true``.

    This is an incident-response escape hatch — it disables the gate
    entirely and logs a critical-level warning on every request. Default
    is disabled (fail-closed).
    """
    return os.getenv("SUBSCRIPTION_GATE_FAIL_OPEN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_tenant_id_from_request(request: Request) -> Optional[str]:
    """Extract tenant_id for subscription-status lookup.

    Resolution order (PRINCIPAL FIRST per EPIC-A #1651):
      1. RBAC principal on ``request.state.principal`` (authoritative —
         set by an upstream auth dependency).
      2. ``X-Tenant-ID`` header (transition-period fallback for master-key
         callers; ideally migrate to principal-only).

    Query-string ``tenant_id`` is NO LONGER read (EPIC-A #1651). A request
    that asserts a tenant_id only via query string cannot bypass the
    paywall by claiming to be a paying tenant — the gate falls through
    and lets downstream auth reject the unauthenticated request. The
    Semgrep rule ``tenant-id-from-query-string`` correctly flags
    attacker-controllable input as untrustworthy for trust decisions
    (subscription-status lookup IS a trust decision — it determines
    whether to accept billing for the request).
    """
    # 1. RBAC principal (set by upstream auth dependency)
    principal = getattr(request.state, "principal", None)
    if principal and getattr(principal, "tenant_id", None):
        return principal.tenant_id

    # 2. X-Tenant-ID header (transition-period fallback)
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return tenant_id

    return None


def _check_subscription_and_redis_health(tenant_id: str) -> tuple[Optional[str], bool]:
    """Return ``(status, redis_available)``.

    ``redis_available`` is ``False`` iff Redis raised an error (so the caller
    can distinguish "no key" from "Redis down" — the former is 402, the
    latter is 503). A ``None`` status with ``redis_available=True`` means
    Redis is healthy but the tenant has no billing key.
    """
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        # No Redis configured — same as Redis unavailable.
        return None, False

    try:
        import redis as redis_lib

        redis_circuit._check_state()
        client = redis_lib.from_url(redis_url, decode_responses=True)
        status = client.hget(f"billing:tenant:{tenant_id}", "status")
        redis_circuit._record_success()
        return status, True
    except CircuitOpenError:
        raise
    except Exception as exc:
        redis_circuit._record_failure(exc)
        logger.warning(
            "subscription_gate_redis_unavailable tenant_id=%s error=%s",
            tenant_id,
            str(exc),
        )
        return None, False


async def require_active_subscription(request: Request) -> None:
    """FastAPI dependency that gates access to paid endpoints.

    Fail-closed semantics (#1182):
    1. Extract tenant_id from the request context.
    2. Query Redis for ``billing:tenant:{tenant_id}`` -> ``status``.
    3. Allow if status is ``active`` or ``trialing``.
    4. HTTP 402 if the subscription is missing, cancelled, or unpaid.
    5. HTTP 503 if Redis is down / the circuit breaker is open — we cannot
       confirm subscription state, so access is denied.
    6. HTTP 402 if the Redis key is simply missing (no active subscription).
    7. ``SUBSCRIPTION_GATE_FAIL_OPEN=true`` bypasses the gate and logs
       loudly. Intended for incident response only.
    """
    tenant_id = _get_tenant_id_from_request(request)
    if not tenant_id:
        # Cannot determine the tenant — let downstream auth handle rejection.
        # Unauthenticated health probes etc. are not paid endpoints.
        return

    if _fail_open_override_enabled():
        logger.critical(
            "subscription_gate_bypassed_via_env_flag tenant_id=%s "
            "(SUBSCRIPTION_GATE_FAIL_OPEN enabled — incident-only override)",
            tenant_id,
        )
        return

    try:
        status, redis_available = _check_subscription_and_redis_health(tenant_id)
    except CircuitOpenError:
        logger.warning(
            "subscription_gate_circuit_open tenant_id=%s (denying paid access)",
            tenant_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Subscription check unavailable. Please try again shortly.",
        )

    if not redis_available:
        # Redis errored — we cannot confirm subscription state. Fail CLOSED
        # to prevent unbilled/compromised tenants from slipping through
        # during Redis outages.
        logger.warning(
            "subscription_gate_redis_unavailable_fail_closed tenant_id=%s",
            tenant_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Subscription check unavailable. Please try again shortly.",
        )

    if status is None:
        # Redis up, but no billing key for this tenant. Before #1182 this
        # was "fail open"; now it is a hard 402 — the admin service is
        # responsible for pre-populating a ``status=trialing`` (or pending)
        # entry atomically with tenant creation.
        logger.info(
            "subscription_gate_missing_key tenant_id=%s (fail-closed)",
            tenant_id,
        )
        raise HTTPException(
            status_code=402,
            detail=(
                "No active subscription found for this tenant. "
                "If you just signed up, wait a few seconds and retry. "
                "Otherwise visit https://regengine.co/billing."
            ),
        )

    allowed_statuses = {"active", "trialing"}
    if status.lower() in allowed_statuses:
        return

    logger.info(
        "subscription_gate_blocked tenant_id=%s status=%s",
        tenant_id,
        status,
    )
    raise HTTPException(
        status_code=402,
        detail=(
            f"Active subscription required. Current status: '{status}'. "
            "Please subscribe or update your billing at https://regengine.co/billing."
        ),
    )
