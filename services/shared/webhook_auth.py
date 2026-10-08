"""Fail-closed HMAC verification for inbound webhooks.

This module is the shared receiver template every connector and webhook
route must use. The rules are:

- A secret is required before webhooks are enabled. Call
  :func:`require_webhook_secret` at connector enable time and refuse to
  enable webhooks when it raises.
- Every request is verified with :func:`verify_webhook_signature`.
  A missing secret, a missing signature header, an unknown scheme, a
  stale timestamp, or a mismatch is a rejection. There is no path where
  verification is silently skipped.
- Comparison uses :func:`hmac.compare_digest` (constant time).
- When the provider embeds a timestamp (``t=<unix>,v1=<hex>``), it must
  fall inside the tolerance window. Providers that send no timestamp
  (GitHub-style ``sha256=<hex>`` or a bare hex digest) are checked on
  signature only.
- Webhook responses must carry only an accepted count, never tenant
  data. Use :func:`webhook_accepted_response` for that shape.

The fail-open shape below must never appear in new code (it is blocked
by the ``webhook-signature-failopen`` semgrep rule)::

    if secret and signature:
        verify(...)

The correct shape is a config-time refusal plus a request-time 401::

    secret = require_webhook_secret(config.webhook_secret)  # raises if unset
    verify_webhook_signature(payload, header, secret)        # raises if bad
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("webhook-auth")

#: Default replay window applied when the provider sends a timestamp.
DEFAULT_TIMESTAMP_TOLERANCE_SECONDS = 300

_SUPPORTED_ALGORITHMS = ("sha256", "sha1")


class WebhookVerificationError(Exception):
    """Base error for every webhook verification rejection.

    ``reason`` is a short machine-readable code safe to return to the
    sender. The secret itself and the expected digest never appear here.
    """

    reason = "webhook_rejected"
    status_code = 401


class WebhookSecretMissingError(WebhookVerificationError):
    """No secret is configured, so the webhook cannot be verified."""

    reason = "webhook_secret_not_configured"


class WebhookSignatureMissingError(WebhookVerificationError):
    """The request carries no signature header."""

    reason = "missing_webhook_signature"


class WebhookSignatureInvalidError(WebhookVerificationError):
    """The signature is malformed, uses an unknown scheme, or mismatches."""

    reason = "invalid_webhook_signature"


class WebhookTimestampError(WebhookVerificationError):
    """The provider timestamp is missing, malformed, or outside tolerance."""

    reason = "stale_webhook_timestamp"


@dataclass
class VerifiedWebhook:
    """Result of a successful verification."""

    scheme: str
    timestamp: Optional[int] = None


def require_webhook_secret(secret: Optional[str], *, connector_id: str = "webhook") -> str:
    """Config-time gate: refuse to enable webhooks without a secret.

    Call this when a connector or route is configured, not per request.
    Returns the secret unchanged when one is set.

    Raises:
        WebhookSecretMissingError: If the secret is missing or blank.
    """
    if not secret or not secret.strip():
        logger.error("webhook_secret_not_configured connector=%s", connector_id)
        raise WebhookSecretMissingError(
            "Webhooks cannot be enabled without a signing secret for connector "
            "'%s'. Configure a webhook secret first." % connector_id
        )
    return secret


def _digest(payload: bytes, secret: str, algorithm: str) -> str:
    try:
        digestmod: Callable[[bytes], Any] = getattr(hashlib, algorithm)
    except AttributeError:
        raise WebhookSignatureInvalidError(
            "Unsupported signature scheme '%s'. Supported schemes: %s." % (algorithm, ", ".join(_SUPPORTED_ALGORITHMS))
        )
    return hmac.new(secret.encode("utf-8"), payload, digestmod).hexdigest()


def sign_webhook_payload(
    payload: bytes,
    secret: str,
    *,
    timestamp: Optional[int] = None,
    algorithm: str = "sha256",
) -> str:
    """Sign a payload the way a provider would (used by tests and senders).

    With ``timestamp`` set, returns ``t=<ts>,v1=<hex>`` over
    ``"<ts>." + payload``. Without it, returns ``"<algorithm>=<hex>"``
    over the raw payload.
    """
    secret = require_webhook_secret(secret)
    if algorithm not in _SUPPORTED_ALGORITHMS:
        raise WebhookSignatureInvalidError(
            "Unsupported signature scheme '%s'. Supported schemes: %s." % (algorithm, ", ".join(_SUPPORTED_ALGORITHMS))
        )
    if timestamp is None:
        return "%s=%s" % (algorithm, _digest(payload, secret, algorithm))
    signed = ("%d." % timestamp).encode("utf-8") + payload
    return "t=%d,v1=%s" % (timestamp, _digest(signed, secret, algorithm))


def _parse_signature_header(header: str) -> tuple[str, str, Optional[int]]:
    """Return ``(scheme, provided_hex, timestamp_or_None)`` or raise."""
    text = header.strip()
    timestamp: Optional[int] = None

    if "," in text:
        parts: Dict[str, str] = {}
        for item in text.split(","):
            if "=" not in item:
                continue
            key, _, value = item.partition("=")
            parts[key.strip().lower()] = value.strip()
        if "t" not in parts or "v1" not in parts:
            raise WebhookSignatureInvalidError("Malformed timestamped signature header. Expected 't=<unix>,v1=<hex>'.")
        try:
            timestamp = int(parts["t"])
        except ValueError:
            raise WebhookSignatureInvalidError("Malformed timestamp in signature header.")
        return "v1", parts["v1"], timestamp

    if "=" in text:
        scheme, _, provided = text.partition("=")
        scheme = scheme.strip().lower()
        provided = provided.strip()
        if not scheme or not provided:
            raise WebhookSignatureInvalidError("Malformed signature header.")
        return scheme, provided, None

    if not text:
        raise WebhookSignatureMissingError("Missing webhook signature.")
    return "sha256", text, None


def verify_webhook_signature(
    payload: bytes,
    signature_header: Optional[str],
    secret: Optional[str],
    *,
    connector_id: str = "webhook",
    algorithm: str = "sha256",
    timestamp_tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
    now: Optional[int] = None,
) -> VerifiedWebhook:
    """Verify an inbound webhook, failing closed on every bad input.

    Args:
        payload: Raw request body bytes.
        signature_header: Provider signature header value, or None.
        secret: Configured signing secret. A missing or blank secret is
            a rejection, never a skip.
        connector_id: Used only for server-side logging.
        algorithm: Default scheme when the header is a bare hex digest.
        timestamp_tolerance_seconds: Replay window applied only when the
            provider embeds a timestamp.
        now: Unix time override (tests). Defaults to current time.

    Returns:
        VerifiedWebhook on success.

    Raises:
        WebhookSecretMissingError: No secret configured.
        WebhookSignatureMissingError: No signature header sent.
        WebhookSignatureInvalidError: Malformed header, unknown scheme,
            or digest mismatch (constant-time compare).
        WebhookTimestampError: Timestamp outside the tolerance window.
    """
    secret = require_webhook_secret(secret, connector_id=connector_id)

    if signature_header is None or not signature_header.strip():
        logger.warning("webhook_signature_missing connector=%s", connector_id)
        raise WebhookSignatureMissingError("Missing webhook signature.")

    scheme, provided, timestamp = _parse_signature_header(signature_header)

    if timestamp is not None:
        current = int(time.time()) if now is None else now
        skew = abs(current - timestamp)
        if skew > timestamp_tolerance_seconds:
            logger.warning(
                "webhook_timestamp_rejected connector=%s skew_seconds=%d tolerance=%d",
                connector_id,
                skew,
                timestamp_tolerance_seconds,
            )
            raise WebhookTimestampError(
                "Webhook timestamp is outside the accepted window "
                "(skew %ds, tolerance %ds)." % (skew, timestamp_tolerance_seconds)
            )
        signed_payload = ("%d." % timestamp).encode("utf-8") + payload
        expected = _digest(signed_payload, secret, "sha256")
        label = "v1"
    else:
        if scheme not in _SUPPORTED_ALGORITHMS:
            logger.warning("webhook_signature_unsupported_scheme connector=%s", connector_id)
            raise WebhookSignatureInvalidError(
                "Unsupported signature scheme '%s'. Supported schemes: %s." % (scheme, ", ".join(_SUPPORTED_ALGORITHMS))
            )
        expected = _digest(payload, secret, scheme)
        label = scheme

    if not hmac.compare_digest(expected, provided):
        logger.warning("webhook_signature_mismatch connector=%s", connector_id)
        raise WebhookSignatureInvalidError("Invalid webhook signature.")

    logger.info("webhook_signature_verified connector=%s", connector_id)
    return VerifiedWebhook(scheme=label, timestamp=timestamp)


def verification_http_exception(exc: WebhookVerificationError):  # type: ignore[no-untyped-def]
    """Convert a verification error to an HTTP 401 with a safe detail body."""
    from fastapi import HTTPException

    return HTTPException(status_code=401, detail={"error": exc.reason, "message": str(exc)})


def verify_webhook_or_401(
    payload: bytes,
    signature_header: Optional[str],
    secret: Optional[str],
    *,
    connector_id: str = "webhook",
    timestamp_tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
) -> VerifiedWebhook:
    """FastAPI-route helper: verify, raising HTTP 401 on any rejection."""
    from fastapi import HTTPException

    try:
        return verify_webhook_signature(
            payload,
            signature_header,
            secret,
            connector_id=connector_id,
            timestamp_tolerance_seconds=timestamp_tolerance_seconds,
        )
    except WebhookVerificationError as exc:
        raise verification_http_exception(exc) from exc
    except HTTPException:
        raise


def webhook_accepted_response(accepted: int) -> Dict[str, int]:
    """Response body for webhook receivers: an accepted count only.

    Tenant data must never be echoed back to the sender.
    """
    return {"accepted": accepted}
