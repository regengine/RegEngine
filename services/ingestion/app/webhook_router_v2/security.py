"""Auth gate, webhook HMAC signature verification (#1243), and the
event-timestamp replay window (#1245).

Code moved verbatim from the original ``webhook_router_v2.py``.
Collaborators that lived at module level in the original file are
resolved through the package namespace (``_pkg``) at call time so that
monkeypatching ``app.webhook_router_v2.<name>`` keeps working exactly
as it did against the original module's globals.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Header, HTTPException, Request

_pkg = sys.modules[__package__]


# ---------------------------------------------------------------------------
# In-memory fallback REMOVED — production must have Postgres
# ---------------------------------------------------------------------------
# Previously, RegEngine would silently accept events into a module-level dict
# when DB was unavailable. This is dangerous: data vanishes on restart, chain
# integrity cannot be guaranteed, and operators have no visibility into lost data.
# Now the endpoint returns 503 Service Unavailable if Postgres is down.


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _is_production() -> bool:
    """Detect production using centralized environment detection."""
    from shared.env import is_production
    return is_production()


def _verify_api_key_present(
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> None:
    """Fail-closed defense-in-depth check on the X-RegEngine-API-Key header.

    NAMING (F-1, re-audit): this helper only checks header PRESENCE.
    It does NOT validate the key itself — that happens later in
    ``require_permission`` → ``get_ingestion_principal`` → ``require_api_key``
    against the database-backed key store. This gate only enforces that a
    header is present; it must not require or consult a generic environment
    key because that retired shared-credential path has no authority.

    NEVER use this dependency alone on a route that returns or mutates
    tenant-scoped data — chain it with ``require_permission(...)`` (which
    runs principal resolution + tenant cross-check) or call
    ``get_ingestion_principal`` and bind the URL/query ``tenant_id`` to
    the principal's tenant explicitly.

    Before the #1888 follow-up, this gate also required a generic key env var,
    so valid tenant keys failed after the shared credential was retired.
    """
    if not x_regengine_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# Backwards-compat alias. The descriptive name ``_verify_api_key_present``
# is preferred at call sites — but ``webhook_compat`` and many tests still
# reference the legacy name via ``Depends(_verify_api_key)`` /
# ``app.dependency_overrides[wr._verify_api_key]``. Keeping the alias avoids
# touching the ``/ingest`` endpoint and the broad test surface in this PR.
_verify_api_key = _verify_api_key_present


# ---------------------------------------------------------------------------
# Webhook HMAC signature verification (#1243)
# ---------------------------------------------------------------------------


def _webhook_hmac_secret() -> Optional[str]:
    """Configured webhook HMAC secret, or ``None`` if unset.

    Single global secret to start — per-tenant / per-integration
    rotation is planned as follow-up (see #1243 fix description). When
    the env is unset the dependency is a no-op, which preserves the
    existing partner-integration ramp. Production operators MUST set
    this before relying on webhook-ingest events.
    """
    secret = os.getenv("WEBHOOK_HMAC_SECRET", "").strip()
    return secret or None


def webhook_hmac_configured() -> bool:
    """Public helper for /health: is WEBHOOK_HMAC_SECRET set?

    F-5: lets ops dashboards alarm when prod drifts to fail-open."""
    return _pkg._webhook_hmac_secret() is not None


async def _verify_webhook_signature(
    request: Request,
    x_webhook_signature: Optional[str] = Header(default=None, alias="X-Webhook-Signature"),
) -> None:
    """Enforce HMAC-SHA256(secret, raw_body) on every ingest request.

    #1243: API-key auth alone makes any key leak (logs, proxies, .env)
    sufficient to forge a tenant's supply-chain events. A signed body
    adds proof that the sender holds the shared secret and that the
    bytes weren't tampered with in flight.

    Signature format (GitHub-style): ``X-Webhook-Signature:
    sha256=<hex>``. A bare hex digest is also accepted so existing
    Stripe-style senders don't need a separate code path.

    Behavior:
    - ``WEBHOOK_HMAC_SECRET`` unset → verification skipped (migration ramp).
    - Secret set + signature missing → HTTP 401.
    - Secret set + signature mismatch → HTTP 401 (timing-safe compare).
    - Unknown scheme → HTTP 401.
    """
    secret = _pkg._webhook_hmac_secret()
    if not secret:
        # F-5: record the fail-open path so ops can alarm on it. Behavior
        # itself unchanged — verification still skipped per the migration ramp.
        _pkg._record_hmac_skip()
        return

    if not x_webhook_signature:
        _pkg.logger.warning("webhook_signature_missing")
        raise HTTPException(
            status_code=401,
            detail={
                "error": "missing_webhook_signature",
                "message": (
                    "X-Webhook-Signature header is required when "
                    "WEBHOOK_HMAC_SECRET is configured. Format: "
                    "'sha256=<hex>' where hex = HMAC-SHA256(secret, raw_body)."
                ),
            },
        )

    sig = x_webhook_signature.strip()
    if "=" in sig:
        scheme, _, provided = sig.partition("=")
        scheme = scheme.strip().lower()
        provided = provided.strip().lower()
    else:
        scheme = "sha256"
        provided = sig.lower()

    if scheme != "sha256":
        # F-8: full scheme is logged server-side; in prod the response is
        # opaque so an attacker can't probe accepted schemes by varying input.
        _pkg.logger.warning("webhook_signature_unsupported_scheme scheme=%s", scheme)
        if _pkg._is_production():
            raise HTTPException(
                status_code=401,
                detail={"error": "invalid_webhook_signature"},
            )
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unsupported_signature_scheme",
                "message": "Only 'sha256' signatures are supported.",
            },
        )

    raw_body = await request.body()
    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()

    # ``provided`` comes from a request header, so it can carry non-ASCII
    # characters. ``hmac.compare_digest`` on str raises TypeError for
    # non-ASCII input, which would surface as a 500; a signature that is
    # not even comparable is simply invalid (401), same as a mismatch.
    try:
        signature_ok = hmac.compare_digest(expected, provided)
    except TypeError:
        signature_ok = False

    if not signature_ok:
        _pkg.logger.warning(
            "webhook_signature_mismatch body_len=%d",
            len(raw_body),
        )
        # F-8: opaque body in production so attackers can't probe;
        # verbose hint preserved in dev/test for partner-integration debugging.
        if _pkg._is_production():
            raise HTTPException(
                status_code=401,
                detail={"error": "invalid_webhook_signature"},
            )
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_webhook_signature",
                "message": (
                    "X-Webhook-Signature does not match the expected "
                    "HMAC of the request body. Verify the shared secret "
                    "and that the body bytes were not altered in flight."
                ),
            },
        )


# ---------------------------------------------------------------------------
# Event-timestamp replay window (#1245)
# ---------------------------------------------------------------------------


def _max_event_age_days() -> int:
    try:
        return max(0, int(os.getenv("WEBHOOK_MAX_EVENT_AGE_DAYS", "90")))
    except (ValueError, TypeError):
        return 90


def _max_event_future_hours() -> int:
    try:
        return max(0, int(os.getenv("WEBHOOK_MAX_EVENT_FUTURE_HOURS", "24")))
    except (ValueError, TypeError):
        return 24


def _validate_event_timestamp_window(timestamp: str) -> Optional[str]:
    """Return an error string if ``timestamp`` is outside the replay
    window, else ``None``. Separate from signature-level replay
    defense: this catches captured webhooks replayed months later with
    a freshly-computed signature.

    Window:
    - floor = now - WEBHOOK_MAX_EVENT_AGE_DAYS (default 90 days)
    - ceil  = now + WEBHOOK_MAX_EVENT_FUTURE_HOURS (default 24 h)
    """
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        # TypeError covers non-string input (e.g. a datetime object passed
        # to the helper directly); mirrors _classify_replay_rejection so
        # both helpers agree on what "unparseable" means.
        return f"event.timestamp is not parseable ISO-8601: {timestamp!r}"

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age_cap_days = _pkg._max_event_age_days()
    future_cap_hours = _pkg._max_event_future_hours()

    if dt < now - timedelta(days=age_cap_days):
        return (
            f"event.timestamp {timestamp} is older than "
            f"WEBHOOK_MAX_EVENT_AGE_DAYS={age_cap_days} — replay window "
            f"exceeded"
        )
    if dt > now + timedelta(hours=future_cap_hours):
        return (
            f"event.timestamp {timestamp} is more than "
            f"WEBHOOK_MAX_EVENT_FUTURE_HOURS={future_cap_hours} in the "
            f"future"
        )
    return None
