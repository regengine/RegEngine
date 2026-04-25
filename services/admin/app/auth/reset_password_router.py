"""Reset-password route — extracted from auth_routes.py (Phase 1 sub-split 10/N).

Exposes:
  router                          — APIRouter with /reset-password registered
  reset_password                  — handler (re-exported from auth_routes for compat)
  ResetPasswordRequest            — request schema (re-exported from auth_routes for compat)
  _enforce_recovery_token_scope   — re-exported for source guardrail tests
  _claim_recovery_token_single_use — re-exported for source guardrail tests
"""
from __future__ import annotations

import time
from typing import Optional

import jwt as _jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_utils import get_password_hash
from ..database import get_session
from ..dependencies import get_session_store
from ..models import ResetPasswordResponse
from ..password_policy import validate_password, PasswordPolicyError
from ..session_store import RedisSessionStore
from ..sqlalchemy_models import UserModel
from .elevation_helpers import _revoke_all_elevation_tokens_for_user
from shared.pii import mask_email
from shared.rate_limit import limiter
from shared.supabase_client import get_supabase

router = APIRouter()
logger = structlog.get_logger("auth")


class ResetPasswordRequest(BaseModel):
    new_password: str


# #1087: recovery tokens must be fresh. Supabase recovery links are short-lived
# by default, but the *access token* minted after verifyOtp() inherits the
# session TTL. We cap the acceptable age at 15 minutes so a stolen session
# access token (even one originally obtained via OTP) can't be replayed as a
# recovery token hours or days later. This matches common industry practice
# for "re-authentication required" gates (OWASP ASVS V2.5.4).
_RECOVERY_TOKEN_MAX_AGE_SECONDS = 15 * 60

# #1087: valid Supabase amr.method values that indicate the token was issued
# via a code-to-email / code-to-phone / recovery flow (i.e. the caller
# demonstrated possession of the email/phone in the last few minutes). We
# explicitly EXCLUDE "password" (regular login — no proof of email ownership)
# and "oauth"/"saml" (third-party-only proof). "recovery" is what newer
# Supabase versions emit specifically for password-recovery flows; "otp"
# covers older versions and magic-link sessions.
_RECOVERY_ALLOWED_AMR_METHODS = frozenset({"otp", "recovery"})


def _parse_supabase_token_claims(token: str) -> dict:
    """Decode a Supabase JWT's payload WITHOUT verifying the signature.

    Why unverified? ``sb.auth.get_user()`` already verified the signature
    (it calls Supabase's API, which rejects unsigned/stale tokens). We
    just need the ``amr`` and ``iat`` claims for scope checks, and
    re-verifying would require the Supabase JWT secret on our side —
    which would then need to be rotated in lockstep with Supabase.
    """
    try:
        return _jwt.decode(token, options={"verify_signature": False})  # nosemgrep: python.jwt.security.unverified-jwt-decode.unverified-jwt-decode
    except _jwt.PyJWTError:
        return {}


def _enforce_recovery_token_scope(
    token: str,
    *,
    user_id: Optional[str] = None,
) -> None:
    """Reject Supabase tokens that were not issued for password recovery (#1087).

    Previously ``/auth/reset-password`` accepted any valid Supabase access
    token — including regular password-login session tokens. That meant an
    attacker with any stolen access token (XSS, exposed browser storage,
    cross-origin leak) could reset the victim's password and lock them out.

    Two layers of defense applied here:

    1. ``amr`` claim: the Supabase JWT's ``amr`` array records how the
       session was authenticated. Recovery flows always include a
       method in ``_RECOVERY_ALLOWED_AMR_METHODS``. Regular password
       logins have ``method == "password"`` and are refused.
    2. ``iat`` recency: even a legitimately-issued recovery token must
       be fresh. We reject anything older than
       ``_RECOVERY_TOKEN_MAX_AGE_SECONDS`` to limit the blast radius
       of a stolen token.

    Raises ``HTTPException(401)`` on any failure. Uses a single generic
    detail message so we don't leak which check failed to attackers.
    """
    claims = _parse_supabase_token_claims(token)
    amr = claims.get("amr") or []
    iat = claims.get("iat")

    # 1. amr claim must indicate an OTP / recovery flow.
    amr_ok = False
    if isinstance(amr, list):
        for entry in amr:
            if isinstance(entry, dict):
                method = entry.get("method")
                if isinstance(method, str) and method in _RECOVERY_ALLOWED_AMR_METHODS:
                    amr_ok = True
                    break
    if not amr_ok:
        logger.warning(
            "reset_password_wrong_token_scope",
            user_id=user_id,
            amr_methods=[
                entry.get("method")
                for entry in (amr if isinstance(amr, list) else [])
                if isinstance(entry, dict)
            ],
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )

    # 2. Token must be fresh.
    if not isinstance(iat, (int, float)):
        logger.warning("reset_password_token_missing_iat", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )
    age_seconds = int(time.time() - int(iat))
    # Allow small negative skew (clocks drift ±a few seconds); but reject
    # obviously-future iats as a sign of token tampering.
    if age_seconds < -300:
        logger.warning(
            "reset_password_token_future_iat",
            user_id=user_id,
            age_seconds=age_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )
    if age_seconds > _RECOVERY_TOKEN_MAX_AGE_SECONDS:
        logger.warning(
            "reset_password_stale_token",
            user_id=user_id,
            age_seconds=age_seconds,
            max_age_seconds=_RECOVERY_TOKEN_MAX_AGE_SECONDS,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )


async def _claim_recovery_token_single_use(
    session_store: RedisSessionStore,
    token: str,
    *,
    user_id: Optional[str] = None,
) -> None:
    """Enforce single-use on a recovery-scoped Supabase token (#1087).

    Uses the JWT ``jti`` (or ``session_id`` fallback) as the dedup key.
    First caller wins; subsequent attempts with the same token receive
    401. Fails OPEN on Redis errors — the amr+iat gates are the primary
    defense, and we'd rather allow a legitimate retry during a Redis
    outage than block a user out of their own reset flow.
    """
    claims = _parse_supabase_token_claims(token)
    dedup_id = claims.get("jti") or claims.get("session_id")
    if not dedup_id or not isinstance(dedup_id, str):
        logger.warning("reset_password_token_missing_jti", user_id=user_id)
        return

    key = f"auth:recovery:used:{dedup_id}"
    try:
        client = await session_store._get_client()
        # SET NX EX: first writer wins, 1h TTL (longer than the 15-min
        # iat window so we cover any clock skew + retries).
        claimed = await client.set(key, "1", nx=True, ex=3600)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "reset_password_single_use_redis_error",
            user_id=user_id,
            error=str(exc),
        )
        return

    if not claimed:
        logger.warning(
            "reset_password_token_replay",
            user_id=user_id,
            dedup_id=dedup_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )


@router.post("/reset-password", response_model=ResetPasswordResponse)
@limiter.limit("5/minute")
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Reset a user's password using a Supabase recovery session token.

    The caller must include `Authorization: Bearer <supabase_access_token>`.
    The token is validated via sb.auth.get_user(); the user is looked up by
    email and their argon2 password hash is updated in the RegEngine DB.

    #1087 — in addition to signature validation, the token must:
      * Have an ``amr`` claim indicating an OTP/recovery flow (excludes
        regular password-login tokens and OAuth tokens).
      * Have been issued within the last 15 minutes.
      * Not have been consumed already (single-use via Redis jti check).
    These gates fail-closed on malformed/stale/replayed tokens and emit
    a generic 401 so an attacker can't distinguish failure modes.
    """
    # 1. Extract the Supabase access token from the Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )
    supabase_token = auth_header[7:]

    # 2. Validate the token with Supabase (service-role client)
    sb = get_supabase()
    if not sb:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unavailable",
        )

    try:
        user_response = sb.auth.get_user(supabase_token)
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired recovery token",
            )
        sb_user = user_response.user
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("reset_password_token_validation_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )

    # #1087 — Scope check. Supabase's ``get_user()`` only validates that the
    # token is a valid session token for SOME user; it doesn't distinguish
    # "password login session" from "recovery session". Before this fix, any
    # stolen password-session token could call reset-password and lock the
    # victim out. These gates reject any token that wasn't issued via an
    # OTP/recovery flow, or is older than 15 minutes.
    sb_user_id = getattr(sb_user, "id", None)
    _enforce_recovery_token_scope(supabase_token, user_id=str(sb_user_id) if sb_user_id else None)
    await _claim_recovery_token_single_use(
        session_store, supabase_token, user_id=str(sb_user_id) if sb_user_id else None
    )

    email = getattr(sb_user, "email", None)
    if not email:
        raise HTTPException(status_code=400, detail="No email associated with token")

    # 3. Validate the new password against the configured policy
    try:
        validate_password(payload.new_password, user_context={"email": email})
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    # 4. Find the user in the RegEngine DB (the authoritative store for login)
    normalized_email = email.strip().lower()
    user = db.execute(
        select(UserModel).where(UserModel.email == normalized_email)
    ).scalar_one_or_none()

    if not user:
        logger.warning("reset_password_user_not_found", email=mask_email(normalized_email))
        raise HTTPException(status_code=404, detail="User not found")

    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account disabled")

    # 5. Update the argon2 hash in the RegEngine DB
    user.password_hash = get_password_hash(payload.new_password)

    # #1349 — bump token_version so every outstanding JWT becomes stale.
    # get_current_user rejects tokens whose `tv` claim is below this value.
    # Coalesce None to 0 for rows created before the column existed.
    current_version = int(getattr(user, "token_version", 0) or 0)
    user.token_version = current_version + 1

    # 6. Keep Supabase in sync so both stores stay aligned
    try:
        sb.auth.admin.update_user_by_id(str(sb_user.id), {"password": payload.new_password})
    except Exception as exc:
        # Non-fatal — the RegEngine DB is the authoritative login store
        logger.warning(
            "reset_password_supabase_sync_failed",
            user_id=str(sb_user.id),
            error=str(exc),
        )

    db.commit()

    # #1349 — revoke every active session so stolen refresh tokens cannot be
    # replayed. This runs AFTER the commit so a Redis outage does not block
    # the password change itself. A Redis miss is logged but not fatal; the
    # token_version bump above is the primary defense.
    try:
        revoked_count = await session_store.revoke_all_for_user(user.id)
    except Exception as exc:
        logger.warning(
            "reset_password_session_revoke_failed",
            user_id=str(user.id),
            error=str(exc),
        )
        revoked_count = 0

    # #1380 — outstanding elevation tokens are now stale too.
    elevation_revoked = await _revoke_all_elevation_tokens_for_user(session_store, user.id)

    logger.info(
        "reset_password_success",
        user_id=str(user.id),
        sessions_revoked=revoked_count,
        elevation_tokens_revoked=elevation_revoked,
        new_token_version=user.token_version,
    )
    return {"status": "success"}
