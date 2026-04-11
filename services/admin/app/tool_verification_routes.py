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
from shared.rate_limit import limiter

logger = structlog.get_logger("tool_verification")

router = APIRouter(prefix="/api/v1/tools", tags=["tool-verification"])

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
VERIFICATION_CODE_TTL = 600  # 10 minutes
MAX_VERIFICATION_ATTEMPTS = 3
TOOL_ACCESS_SECRET = os.environ.get(
    "TOOL_ACCESS_SECRET",
    os.environ.get("JWT_SIGNING_KEY", os.environ.get("AUTH_SECRET_KEY", "")),
)

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
            url = os.getenv("REDIS_URL", "redis://redis:6379/0")
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
        logger.warning("dev_mode_verification_code", email=email, code=code)

    return VerifyEmailResponse(
        status="code_sent",
        message=f"Verification code sent to {email}. Check your inbox.",
    )


@router.post("/confirm-code", response_model=ConfirmCodeResponse)
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
        logger.error("lead_save_failed", email=email, error=str(exc))

    # Sign a JWT for the cookie
    import jwt

    token = jwt.encode(
        {
            "email": email,
            "domain": domain,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "type": "tool_access",
        },
        TOOL_ACCESS_SECRET,
        algorithm="HS256",
    )

    logger.info("tool_lead_verified", email=email, domain=domain, tool=payload.tool_name)
    return ConfirmCodeResponse(status="verified", token=token)


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
