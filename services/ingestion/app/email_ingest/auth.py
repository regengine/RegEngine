"""Basic-Auth webhook gate for the Postmark inbound-parse endpoint.

Precedent: ``webhook_router_v2/security.py`` (``_verify_webhook_signature``,
HMAC over the raw body, secret from ``WEBHOOK_HMAC_SECRET``) and
``services/shared/webhook_security.py`` (HMAC + ``hmac.compare_digest``,
env-configured secret). Postmark's inbound webhook, unlike Stripe/GitHub-style
webhooks, does not sign its POST body — the provider's own documented
mechanism for securing an inbound-parse endpoint is HTTP Basic Auth via
credentials embedded in the webhook URL Postmark is configured with. This
module keeps every other convention from the HMAC precedent: an
env-configured secret, ``hmac.compare_digest`` for a timing-safe comparison,
a ``logger.warning`` on each failure mirroring ``webhook_signature_mismatch``,
and a small ``email_inbound_auth_configured()`` health helper mirroring
``webhook_hmac_configured()``.

One deliberate divergence from the ``WEBHOOK_HMAC_SECRET`` precedent: that
gate fails OPEN (skips verification) when the secret is unset, but only in
local development and test as a migration ramp; on a closed gate
(production or any strict/cloud runtime) it fails CLOSED. This gate fails
CLOSED (401s every request) when unset, because there is no safe
unauthenticated mode for an endpoint that writes directly into
compliance ingestion.
"""

from __future__ import annotations

import base64
import hmac
import logging
import os
import threading
from typing import Optional

from fastapi import Header, HTTPException, Request

logger = logging.getLogger("email-ingest.auth")

# Brute-force budget for the shared Basic-Auth credential: same shape as
# ``app.authz``'s API-key limiter (15 failures per 5 minutes per client IP,
# Redis-backed with in-memory fallback), but a SEPARATE namespace so API-key
# probing and Postmark-delivery failures never share a budget.
_AUTH_FAIL_WINDOW = 300  # 5-minute window
_AUTH_FAIL_MAX = 15  # max failures before blocking
_email_auth_limiter = None
_email_auth_limiter_lock = threading.Lock()


def _get_email_auth_limiter():
    global _email_auth_limiter
    if _email_auth_limiter is None:
        with _email_auth_limiter_lock:
            if _email_auth_limiter is None:
                from shared.rate_limit import BruteForceLimiter

                _email_auth_limiter = BruteForceLimiter(
                    namespace="email_inbound_auth_fail",
                    max_failures=_AUTH_FAIL_MAX,
                    window_seconds=_AUTH_FAIL_WINDOW,
                )
    return _email_auth_limiter


def _client_ip(request: Optional[Request]) -> str:
    if request is not None and request.client is not None:
        return request.client.host
    return "unknown"


def _configured_credentials() -> Optional[tuple[str, str]]:
    user = os.getenv("EMAIL_INBOUND_BASIC_AUTH_USER", "").strip()
    password = os.getenv("EMAIL_INBOUND_BASIC_AUTH_PASSWORD", "").strip()
    return (user, password) if user and password else None


def email_inbound_auth_configured() -> bool:
    """Public helper for /health — mirrors ``webhook_hmac_configured()``."""
    return _configured_credentials() is not None


async def verify_inbound_email_auth(
    # Annotated as plain ``Request`` (not ``Optional[Request]``): FastAPI only
    # injects the request for that exact type, and builds a body field for
    # anything else, which raises FastAPIError at route registration and
    # stops the whole app from booting. The ``None`` default is ignored by
    # FastAPI and keeps direct unit calls without a request working.
    request: Request = None,  # type: ignore[assignment]
    authorization: Optional[str] = Header(default=None),
) -> None:
    """FastAPI dependency enforcing HTTP Basic Auth on the inbound webhook.

    ``request`` is only used to scope the brute-force budget by client IP;
    it may be ``None`` in direct unit calls, which share one ``"unknown"``
    budget.
    """
    client_ip = _client_ip(request)
    if _get_email_auth_limiter().is_limited(client_ip):
        logger.warning("email_inbound_auth_rate_limited client_ip=%s", client_ip)
        raise HTTPException(status_code=429, detail="Too many authentication failures")

    creds = _configured_credentials()
    if creds is None:
        # Unlike WEBHOOK_HMAC_SECRET's fail-open migration ramp, this gate
        # fails CLOSED when unset: this endpoint writes compliance data
        # straight into ingestion, so there is no safe "skip auth" mode.
        # Not counted toward the brute-force budget: with no credential
        # configured there is nothing to guess, and counting would risk
        # blocking Postmark's own addresses right after the operator sets
        # the credentials for the first time.
        logger.error("email_inbound_auth_not_configured")
        raise HTTPException(status_code=401, detail="Inbound email auth not configured")

    if not authorization or not authorization.lower().startswith("basic "):
        _get_email_auth_limiter().record_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Missing credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        decoded = base64.b64decode(authorization.split(" ", 1)[1], validate=True).decode("utf-8")
        user, _, password = decoded.partition(":")
    except Exception:
        logger.warning("email_inbound_auth_malformed_header")
        _get_email_auth_limiter().record_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    expected_user, expected_password = creds
    # Compare on the UTF-8 byte representations: ``hmac.compare_digest`` raises
    # ``TypeError`` for ``str`` inputs containing non-ASCII characters, and a
    # crafted Basic-Auth header can decode to valid non-ASCII UTF-8 (e.g.
    # "ünïcode:pass"). Comparing bytes avoids that crash and still yields a
    # clean 401 for mismatched credentials.
    # `&` instead of `and` so both compare_digest calls always run — avoids a
    # username-existence timing side-channel; the calls are cheap so the
    # non-short-circuit is free.
    ok = hmac.compare_digest(user.encode("utf-8"), expected_user.encode("utf-8")) & hmac.compare_digest(
        password.encode("utf-8"), expected_password.encode("utf-8")
    )
    if not ok:
        logger.warning("email_inbound_auth_mismatch")
        _get_email_auth_limiter().record_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
