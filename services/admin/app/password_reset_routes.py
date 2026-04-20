"""Password-reset / forgot-password router.

#1374 — The authoritative ``POST /auth/change-password`` implementation lives
in :mod:`services.admin.app.auth_routes`. A second implementation used to live
here and was silently shadowed because ``main.py`` mounts ``auth_router``
before ``password_reset_router``, so FastAPI resolved the path to
``auth_routes.change_password`` and this function never ran.

#1086 — This module now provides the missing server-side password-recovery
initiation flow:

  * ``POST /auth/forgot-password``  — accepts an email address, calls
    ``supabase.auth.reset_password_for_email()`` to send a recovery link,
    and always returns the same generic 200 so that an attacker cannot
    enumerate registered addresses.

    Rate-limited to 3 requests per email per hour via a Redis TTL counter
    (same Redis client used by the existing session store).  Unknown email
    addresses receive the same response as known ones.

The ``POST /auth/reset-password`` endpoint (consuming the Supabase recovery
token to update the argon2 hash in RegEngine's own DB) already exists in
:mod:`services.admin.app.auth_routes` and is NOT duplicated here.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from shared.rate_limit import limiter
from shared.pii import mask_email
from shared.supabase_client import get_supabase
from .dependencies import get_session_store
from .session_store import RedisSessionStore

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger("auth")

# ---------------------------------------------------------------------------
# Rate-limit constants
# ---------------------------------------------------------------------------

# Allow at most 3 forgot-password requests per email address per hour.
# This is intentionally strict: legitimate users rarely need to request a
# reset link more than once; high-volume attempts indicate credential
# stuffing or abuse.
_FORGOT_PW_LIMIT = 3
_FORGOT_PW_WINDOW = 3600  # 1 hour in seconds

_FORGOT_PW_GENERIC_MSG = (
    "If that email address is registered you will receive a password-reset link shortly."
)


def _forgot_pw_rate_key(email: str) -> str:
    return f"auth:forgot_password:{email}"


async def _check_forgot_pw_rate_limit(
    session_store: RedisSessionStore, email: str
) -> None:
    """Raise 429 if this email has exceeded the forgot-password request limit."""
    try:
        client = await session_store._get_client()
        count_str = await client.get(_forgot_pw_rate_key(email))
        if count_str and int(count_str) >= _FORGOT_PW_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many password-reset requests. Please try again later.",
                headers={"Retry-After": str(_FORGOT_PW_WINDOW)},
            )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover — Redis unavailable: fail open
        logger.warning("forgot_password_rate_limit_redis_error", error=str(exc))


async def _record_forgot_pw_attempt(
    session_store: RedisSessionStore, email: str
) -> None:
    """Increment the per-email forgot-password counter (with TTL)."""
    try:
        client = await session_store._get_client()
        key = _forgot_pw_rate_key(email)
        async with client.pipeline(transaction=False) as pipe:
            pipe.incr(key)
            pipe.expire(key, _FORGOT_PW_WINDOW)
            await pipe.execute()
    except Exception as exc:  # pragma: no cover — Redis unavailable: fail open
        logger.warning("forgot_password_rate_record_redis_error", error=str(exc))


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


async def _forgot_password_handler(
    email: str,
    session_store: RedisSessionStore,
) -> ForgotPasswordResponse:
    """Core logic for forgot-password flow, extracted for testability.

    Called by ``forgot_password`` (the HTTP handler). Splitting the logic here
    allows unit tests to bypass the SlowAPI decorator without mocking starlette
    Request objects.
    """
    normalized = email.lower().strip()

    # 1. Per-email rate limit (3/hour)
    await _check_forgot_pw_rate_limit(session_store, normalized)

    # 2. Record the attempt BEFORE calling Supabase so errors don't bypass counter.
    await _record_forgot_pw_attempt(session_store, normalized)

    sb = get_supabase()
    if sb:
        try:
            sb.auth.reset_password_for_email(normalized)
            logger.info(
                "forgot_password_reset_email_sent",
                email=mask_email(normalized),
            )
        except Exception as exc:
            # Do NOT surface errors — prevents enumeration and keeps the
            # endpoint idempotent from the caller's perspective.
            logger.warning(
                "forgot_password_supabase_error",
                email=mask_email(normalized),
                error=str(exc),
            )
    else:
        logger.warning("forgot_password_supabase_unavailable", email=mask_email(normalized))

    return ForgotPasswordResponse(message=_FORGOT_PW_GENERIC_MSG)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("5/minute")
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    session_store: RedisSessionStore = Depends(get_session_store),
) -> ForgotPasswordResponse:
    """Initiate password recovery by sending a reset link via Supabase.

    Always returns HTTP 200 with a generic message regardless of whether
    the email address is registered — this prevents user enumeration.

    Rate-limited to 3 requests per email per hour (Redis counter).  A
    SlowAPI ``@limiter.limit`` guard is also applied at the HTTP layer to
    prevent burst abuse before the Redis counter even runs.

    #1086
    """
    return await _forgot_password_handler(payload.email, session_store)
