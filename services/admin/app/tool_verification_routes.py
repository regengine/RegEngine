"""
Email verification endpoints for free tool access.

No authentication required — these are public endpoints for lead capture.
Visitors provide a work email, receive a 6-digit code, and verify it to
unlock free compliance tools. Verified leads are stored in tool_leads.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
import redis.asyncio as aioredis

from shared.blocked_email_domains import is_personal_email, extract_domain
from shared.env import is_production
from shared.pii import mask_email
from shared.rate_limit import limiter

from app.auth_utils import SESSION_ISSUER, TOOL_ACCESS_AUDIENCE

logger = structlog.get_logger("tool_verification")

router = APIRouter(prefix="/api/v1/tools", tags=["tool-verification"])

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
VERIFICATION_CODE_TTL = 600  # 10 minutes
MAX_VERIFICATION_ATTEMPTS = 3

# ---------------------------------------------------------------------------
# Tool-access JWT signing secret — MUST be separate from the session key (#1060)
#
# Prior revisions fell back through JWT_SIGNING_KEY → AUTH_SECRET_KEY, so a
# tool-access token signed during lead capture shared a signing secret with
# the admin session token. That made the two token types forgeable into each
# other: any future endpoint trusting a valid-signature tool_access cookie
# could be handed a session JWT and vice-versa.
#
# Rules:
#   • Production: TOOL_ACCESS_SECRET must be set explicitly — no fallbacks.
#   • Non-production: if unset, we derive a deterministic-per-process random
#     secret. Dev tokens won't survive restarts, but they're never trusted by
#     any production-grade consumer. We still refuse to re-use AUTH_SECRET_KEY.
# ---------------------------------------------------------------------------
_tool_access_secret_env = os.environ.get("TOOL_ACCESS_SECRET", "").strip()
if not _tool_access_secret_env:
    if is_production():
        raise RuntimeError(
            "TOOL_ACCESS_SECRET must be set in production. "
            "This key signs the tool-access cookie for free compliance tools "
            "and MUST be distinct from AUTH_SECRET_KEY / JWT_SIGNING_KEY "
            "(see issue #1060). "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )
    _tool_access_secret_env = secrets.token_urlsafe(48)
    logger.warning(
        "tool_access_secret_ephemeral",
        message=(
            "TOOL_ACCESS_SECRET not set — using ephemeral dev key. "
            "Tool-access cookies will NOT survive process restarts."
        ),
    )
TOOL_ACCESS_SECRET = _tool_access_secret_env

# ---------------------------------------------------------------------------
# Redis — reuse the pattern from bulk_upload/session_store.py
# Falls back to in-memory dict when Redis is unavailable (dev mode).
# ---------------------------------------------------------------------------
_redis_client: aioredis.Redis | None = None
_redis_available: bool | None = None
# In-memory store — ephemeral data (email verification codes with TTL). Intentionally not persisted.
_memory_store: dict[str, dict] = {}


async def _get_redis() -> aioredis.Redis | None:
    global _redis_client, _redis_available
    if _redis_available is False:
        return None
    if _redis_client is None:
        try:
            url = os.getenv("REDIS_URL", "rediss://redis:6379/0")
            _redis_client = aioredis.from_url(
                url, encoding="utf-8", decode_responses=True, max_connections=5,
            )
            await _redis_client.ping()
            _redis_available = True
        except Exception as exc:
            logger.warning("tool_verify_redis_unavailable", error=str(exc))
            _redis_available = False
            _redis_client = None
    return _redis_client


def _cleanup_memory() -> None:
    now = time.time()
    expired = [k for k, v in _memory_store.items() if v["expires"] <= now]
    for k in expired:
        _memory_store.pop(k, None)


async def _store_code(email: str, code: str) -> None:
    key = f"tool_verify:{email}"
    payload = f"{code}:{MAX_VERIFICATION_ATTEMPTS}"
    client = await _get_redis()
    if client is not None:
        await client.setex(key, VERIFICATION_CODE_TTL, payload)
        return
    _cleanup_memory()
    _memory_store[key] = {
        "code": code,
        "attempts": MAX_VERIFICATION_ATTEMPTS,
        "expires": time.time() + VERIFICATION_CODE_TTL,
    }


async def _check_code(email: str, code: str) -> tuple[bool, str]:
    """Return (success, error_message). Decrements attempts on failure."""
    key = f"tool_verify:{email}"
    client = await _get_redis()

    if client is not None:
        raw = await client.get(key)
        if not raw:
            return False, "Code expired or not found. Please request a new code."
        stored_code, attempts_str = raw.rsplit(":", 1)
        attempts = int(attempts_str)
        if attempts <= 0:
            await client.delete(key)
            return False, "Too many attempts. Please request a new code."
        if stored_code != code:
            await client.setex(key, VERIFICATION_CODE_TTL, f"{stored_code}:{attempts - 1}")
            remaining = attempts - 1
            return False, f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
        await client.delete(key)
        return True, ""

    # In-memory fallback
    _cleanup_memory()
    stored = _memory_store.get(key)
    if not stored:
        return False, "Code expired or not found. Please request a new code."
    if stored["expires"] < time.time():
        _memory_store.pop(key, None)
        return False, "Code expired. Please request a new code."
    if stored["attempts"] <= 0:
        _memory_store.pop(key, None)
        return False, "Too many attempts. Please request a new code."
    if stored["code"] != code:
        stored["attempts"] -= 1
        remaining = stored["attempts"]
        return False, f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
    _memory_store.pop(key, None)
    return True, ""


# ---------------------------------------------------------------------------
# GDPR #1095 — lead-erasure code helpers.
#
# Stored under the ``lead_erasure:`` namespace so an erasure code can
# never authenticate a verification flow (or vice versa). Same TTL and
# attempt-count semantics as the verify helpers above; the duplication
# is deliberate to keep the two flows from entangling.
# ---------------------------------------------------------------------------
async def _store_erasure_code(email: str, code: str) -> None:
    key = f"lead_erasure:{email}"
    payload = f"{code}:{MAX_VERIFICATION_ATTEMPTS}"
    client = await _get_redis()
    if client is not None:
        await client.setex(key, VERIFICATION_CODE_TTL, payload)
        return
    _cleanup_memory()
    _memory_store[key] = {
        "code": code,
        "attempts": MAX_VERIFICATION_ATTEMPTS,
        "expires": time.time() + VERIFICATION_CODE_TTL,
    }


async def _check_erasure_code(email: str, code: str) -> tuple[bool, str]:
    """Return (success, error_message). Decrements attempts on failure."""
    key = f"lead_erasure:{email}"
    client = await _get_redis()

    if client is not None:
        raw = await client.get(key)
        if not raw:
            return False, "Code expired or not found. Please request a new code."
        stored_code, attempts_str = raw.rsplit(":", 1)
        attempts = int(attempts_str)
        if attempts <= 0:
            await client.delete(key)
            return False, "Too many attempts. Please request a new code."
        if stored_code != code:
            await client.setex(key, VERIFICATION_CODE_TTL, f"{stored_code}:{attempts - 1}")
            remaining = attempts - 1
            return False, f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
        await client.delete(key)
        return True, ""

    # In-memory fallback
    _cleanup_memory()
    stored = _memory_store.get(key)
    if not stored:
        return False, "Code expired or not found. Please request a new code."
    if stored["expires"] < time.time():
        _memory_store.pop(key, None)
        return False, "Code expired. Please request a new code."
    if stored["attempts"] <= 0:
        _memory_store.pop(key, None)
        return False, "Too many attempts. Please request a new code."
    if stored["code"] != code:
        stored["attempts"] -= 1
        remaining = stored["attempts"]
        return False, f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
    _memory_store.pop(key, None)
    return True, ""


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class VerifyEmailRequest(BaseModel):
    email: EmailStr
    tool_name: str = "unknown"
    source_url: str = ""


class ConfirmCodeRequest(BaseModel):
    email: EmailStr
    code: str
    tool_name: str = "unknown"


class VerifyEmailResponse(BaseModel):
    status: str
    message: str


class ConfirmCodeResponse(BaseModel):
    status: str
    token: str = ""


# GDPR #1095 — public lead-erasure request bodies.
class LeadErasureRequest(BaseModel):
    email: EmailStr


class ConfirmLeadErasureRequest(BaseModel):
    email: EmailStr
    code: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


@router.post("/verify-email", response_model=VerifyEmailResponse)
@limiter.limit("3/minute")
async def verify_email(payload: VerifyEmailRequest, request: Request):
    """Step 1 — submit work email, receive a 6-digit code."""
    email = payload.email.strip().lower()

    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    if is_personal_email(email):
        raise HTTPException(
            status_code=422,
            detail="Please use your work email. Personal email addresses (Gmail, Yahoo, etc.) are not accepted.",
        )

    code = f"{secrets.randbelow(900000) + 100000}"
    await _store_code(email, code)

    # Send via Resend
    if RESEND_API_KEY:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "RegEngine <verify@regengine.co>",
                    "to": [email],
                    "subject": f"Your RegEngine verification code: {code}",
                    "html": _build_email_html(code),
                },
            )
            if resp.status_code not in (200, 201):
                logger.error("resend_api_error", status=resp.status_code, body=resp.text)
                raise HTTPException(status_code=500, detail="Failed to send verification email")
    else:
        logger.warning("dev_mode_verification_code", email=mask_email(email), code=code)

    return VerifyEmailResponse(
        status="code_sent",
        message="Verification code sent. Check your inbox.",
    )


@router.post("/confirm-code", response_model=ConfirmCodeResponse)
@limiter.limit("10/minute")
async def confirm_code(payload: ConfirmCodeRequest, request: Request):
    """Step 2 — submit the 6-digit code. Returns a signed JWT for the cookie."""
    email = payload.email.strip().lower()
    code = payload.code.strip()

    ok, err = await _check_code(email, code)
    if not ok:
        status = 429 if "Too many" in err else 400
        raise HTTPException(status_code=status, detail=err)

    # Save lead to Postgres (best-effort — don't block verification on DB failure)
    domain = extract_domain(email)
    try:
        _save_lead(email, domain, payload.tool_name)
    except Exception as exc:
        logger.error("lead_save_failed", email=mask_email(email), error=str(exc))

    # Sign a JWT for the cookie — aud/iss pin this to the tool-access domain
    # so it cannot be swapped in as a session token (#1060).
    import jwt

    token = jwt.encode(
        {
            "email": email,
            "domain": domain,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "type": "tool_access",
            "aud": TOOL_ACCESS_AUDIENCE,
            "iss": SESSION_ISSUER,
        },
        TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )

    logger.info("tool_lead_verified", email=mask_email(email), domain=domain, tool=payload.tool_name)
    return ConfirmCodeResponse(status="verified", token=token)


# ---------------------------------------------------------------------------
# GDPR #1095 — public lead-erasure endpoints.
#
# Art. 17 (right-to-erasure) and Art. 12(2) (ease-of-exercise) require
# that data subjects can erase their PII without undue burden. ``tool_leads``
# rows are PII captured from public visitors who have no authenticated
# session, so they cannot use the existing ``/v1/account/erasure``
# endpoint -- that path is gated by ``get_current_user``. Forcing them to
# open a support ticket also runs afoul of Art. 12(2).
#
# These two endpoints let them self-serve:
#   1. POST /lead-erasure/request  { email }       -- sends a 6-digit code
#   2. POST /lead-erasure/confirm  { email, code } -- deletes tool_leads row
#
# ``/request`` responds 202 regardless of whether the email is in
# ``tool_leads`` so the endpoint cannot be used as a user-existence
# oracle.
# ---------------------------------------------------------------------------
@router.post("/lead-erasure/request", status_code=202)
@limiter.limit("3/minute")
async def request_lead_erasure(request: Request, payload: LeadErasureRequest):
    """Step 1 -- submit the email whose lead row should be erased. Always 202."""
    email = payload.email.strip().lower()

    # Invalid format is a client bug, not an enumeration oracle, so the
    # 400 stays -- matches the verify-email contract above.
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    code = f"{secrets.randbelow(900000) + 100000}"
    await _store_erasure_code(email, code)
    await _send_erasure_email(email, code)

    logger.info("lead_erasure_code_sent", email=mask_email(email))
    # Same response whether or not ``email`` is in tool_leads -- no oracle.
    return {"status": "code_sent"}


@router.post("/lead-erasure/confirm", status_code=200)
@limiter.limit("10/minute")
async def confirm_lead_erasure(
    request: Request, payload: ConfirmLeadErasureRequest
):
    """Step 2 -- submit the 6-digit code. On success, DELETE tool_leads row."""
    email = payload.email.strip().lower()
    code = payload.code.strip()

    ok, err = await _check_erasure_code(email, code)
    if not ok:
        status = 429 if "Too many" in err else 400
        raise HTTPException(
            status_code=status, detail=err or "Invalid or expired code"
        )

    # Proof of email control established -- erase the lead row. LOWER()
    # catches any cased variant that slipped past the original insert's
    # .lower(). The statement runs even when no row exists; we do not
    # return DELETE rowcount -- exposing "0 deleted" would reintroduce
    # the enumeration oracle the /request endpoint is careful to avoid.
    from app.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    try:
        session.execute(
            text("DELETE FROM tool_leads WHERE LOWER(email) = :email"),
            {"email": email},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    logger.info("lead_erasure_completed", email=mask_email(email))
    return {"status": "erased"}


async def _send_erasure_email(email: str, code: str) -> None:
    """Send the erasure-confirmation email via Resend (falls back to log).

    Kept separate from the verify-email sender so subject/template can
    drift without entangling the two flows. Failures raise 500 when
    ``RESEND_API_KEY`` is configured -- same contract as ``verify_email``.
    """
    if RESEND_API_KEY:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "RegEngine <verify@regengine.co>",
                    "to": [email],
                    "subject": f"RegEngine data-erasure code: {code}",
                    "html": _build_erasure_email_html(code),
                },
            )
            if resp.status_code not in (200, 201):
                logger.error(
                    "resend_erasure_email_error",
                    status=resp.status_code,
                    body=resp.text,
                )
                raise HTTPException(
                    status_code=500, detail="Failed to send erasure email"
                )
    else:
        logger.warning(
            "dev_mode_erasure_code", email=mask_email(email), code=code
        )


def _build_erasure_email_html(code: str) -> str:
    """Plain template for the erasure confirmation email."""
    return f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
  <h2 style="color: #10b981; margin-bottom: 8px; font-size: 20px;">RegEngine</h2>
  <p style="color: #666; margin-bottom: 24px; font-size: 15px;">
    We received a request to erase any lead data we hold under this email address (GDPR Art. 17).
    To confirm the request and delete the data, enter this code:
  </p>
  <div style="background: #f8f9fa; border-radius: 8px; padding: 24px; text-align: center; margin-bottom: 24px;">
    <span style="font-size: 32px; font-weight: 600; letter-spacing: 8px; color: #1a1a1a;">{code}</span>
  </div>
  <p style="color: #999; font-size: 13px;">
    This code expires in 10 minutes. If you did not request erasure you can ignore this email; no action will be taken.
  </p>
  <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
  <p style="color: #bbb; font-size: 12px;">RegEngine &mdash; FSMA 204 compliance infrastructure for food traceability.</p>
</div>"""


def decode_tool_access_token(token: str) -> dict:
    """Verify a tool-access cookie JWT.

    Signed with the dedicated ``TOOL_ACCESS_SECRET`` and required to carry
    ``aud=TOOL_ACCESS_AUDIENCE`` — a session JWT cannot pass this check
    even if the attacker controls the signing key, because its aud is
    ``regengine-api`` (see #1060).

    During the transitional rollout legacy tokens (minted before aud was
    added) have no ``aud`` claim; we accept those so existing cookies keep
    working until they expire. A token with the *wrong* aud — e.g. an
    attacker pasting a session token — raises ``InvalidAudienceError``.
    """
    import jwt as _jwt

    try:
        return _jwt.decode(
            token,
            TOOL_ACCESS_SECRET,
            algorithms=["HS256"],
            audience=TOOL_ACCESS_AUDIENCE,
            issuer=SESSION_ISSUER,
        )
    except _jwt.exceptions.MissingRequiredClaimError:
        # Legacy token predates aud/iss — verify signature only.
        return _jwt.decode(
            token,
            TOOL_ACCESS_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False, "verify_iss": False},
        )


# ---------------------------------------------------------------------------
# Database — save lead (sync, uses existing SQLAlchemy session pattern)
# ---------------------------------------------------------------------------
def _save_lead(email: str, domain: str, tool_name: str) -> None:
    """Insert or update a tool lead row. Uses the Admin DB sync session."""
    from app.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    try:
        session.execute(
            text("""
                INSERT INTO tool_leads (email, domain, first_tool_used)
                VALUES (:email, :domain, :tool)
                ON CONFLICT (email) DO UPDATE SET
                    last_tool_access = NOW(),
                    access_count = tool_leads.access_count + 1
            """),
            {"email": email, "domain": domain, "tool": tool_name},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Email template
# ---------------------------------------------------------------------------
def _build_email_html(code: str) -> str:
    return f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
  <h2 style="color: #10b981; margin-bottom: 8px; font-size: 20px;">RegEngine</h2>
  <p style="color: #666; margin-bottom: 24px; font-size: 15px;">Your verification code for accessing free compliance tools:</p>
  <div style="background: #f8f9fa; border-radius: 8px; padding: 24px; text-align: center; margin-bottom: 24px;">
    <span style="font-size: 32px; font-weight: 600; letter-spacing: 8px; color: #1a1a1a;">{code}</span>
  </div>
  <p style="color: #999; font-size: 13px;">This code expires in 10 minutes. If you didn't request this, you can ignore this email.</p>
  <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
  <p style="color: #bbb; font-size: 12px;">RegEngine &mdash; FSMA 204 compliance infrastructure for food traceability.</p>
</div>"""
