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
from typing import Optional

from fastapi import Header, HTTPException

logger = logging.getLogger("email-ingest.auth")


def _configured_credentials() -> Optional[tuple[str, str]]:
    user = os.getenv("EMAIL_INBOUND_BASIC_AUTH_USER", "").strip()
    password = os.getenv("EMAIL_INBOUND_BASIC_AUTH_PASSWORD", "").strip()
    return (user, password) if user and password else None


def email_inbound_auth_configured() -> bool:
    """Public helper for /health — mirrors ``webhook_hmac_configured()``."""
    return _configured_credentials() is not None


async def verify_inbound_email_auth(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """FastAPI dependency enforcing HTTP Basic Auth on the inbound webhook."""
    creds = _configured_credentials()
    if creds is None:
        # Unlike WEBHOOK_HMAC_SECRET's fail-open migration ramp, this gate
        # fails CLOSED when unset: this endpoint writes compliance data
        # straight into ingestion, so there is no safe "skip auth" mode.
        logger.error("email_inbound_auth_not_configured")
        raise HTTPException(status_code=401, detail="Inbound email auth not configured")

    if not authorization or not authorization.lower().startswith("basic "):
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
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
