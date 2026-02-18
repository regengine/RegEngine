"""Webhook security utilities for HMAC signature generation and verification.

This module provides cryptographic signing for outbound webhooks and
verification for inbound webhook callbacks (e.g., Stripe, identity providers).

Security Features:
- HMAC-SHA256 signature generation
- Timestamp-based replay attack prevention
- Constant-time signature comparison
- Secret rotation support with multiple valid secrets
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger("webhook-security")

# Default tolerance for timestamp validation (5 minutes)
DEFAULT_TIMESTAMP_TOLERANCE_SECONDS = 300

# Environment variable names
WEBHOOK_SECRET_ENV = "WEBHOOK_SIGNING_SECRET"
WEBHOOK_SECRET_PREVIOUS_ENV = "WEBHOOK_SIGNING_SECRET_PREVIOUS"


class WebhookSignatureError(Exception):
    """Raised when webhook signature verification fails."""
    pass


class WebhookTimestampError(Exception):
    """Raised when webhook timestamp is outside acceptable window."""
    pass


@dataclass
class WebhookSignature:
    """Parsed webhook signature components."""
    timestamp: int
    signature: str
    version: str = "v1"


def get_webhook_secret() -> str:
    """Get the current webhook signing secret.
    
    Returns:
        The webhook signing secret from environment.
        
    Raises:
        ValueError: If no secret is configured.
    """
    secret = os.getenv(WEBHOOK_SECRET_ENV)
    if not secret:
        raise ValueError(
            f"Webhook signing secret not configured. "
            f"Set {WEBHOOK_SECRET_ENV} environment variable."
        )
    return secret


def get_webhook_secrets() -> list[str]:
    """Get all valid webhook secrets (current + previous for rotation).
    
    Returns:
        List of valid secrets, with current secret first.
    """
    secrets = []
    
    current = os.getenv(WEBHOOK_SECRET_ENV)
    if current:
        secrets.append(current)
    
    # Support secret rotation by accepting previous secret temporarily
    previous = os.getenv(WEBHOOK_SECRET_PREVIOUS_ENV)
    if previous:
        secrets.append(previous)
    
    return secrets


def generate_signature(
    payload: bytes,
    secret: Optional[str] = None,
    timestamp: Optional[int] = None,
) -> str:
    """Generate HMAC-SHA256 signature for outbound webhook payload.
    
    Args:
        payload: Raw bytes of the webhook payload (JSON body).
        secret: Signing secret. If None, uses environment variable.
        timestamp: Unix timestamp. If None, uses current time.
        
    Returns:
        Signature header value in format: "t=<timestamp>,v1=<signature>"
        
    Raises:
        ValueError: If no secret is available.
        
    Example:
        >>> sig = generate_signature(b'{"event": "test"}')
        >>> # Returns: "t=1701234567,v1=abc123..."
    """
    if secret is None:
        secret = get_webhook_secret()
    
    if timestamp is None:
        timestamp = int(time.time())
    
    # Create signed payload: timestamp + "." + payload
    signed_payload = f"{timestamp}.".encode() + payload
    
    # Generate HMAC-SHA256 signature
    signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256
    ).hexdigest()
    
    header_value = f"t={timestamp},v1={signature}"
    
    logger.debug(
        "webhook_signature_generated",
        timestamp=timestamp,
        payload_bytes=len(payload),
    )
    
    return header_value


def parse_signature_header(header: str) -> WebhookSignature:
    """Parse webhook signature header into components.
    
    Args:
        header: Signature header value (e.g., "t=123,v1=abc...")
        
    Returns:
        WebhookSignature with parsed components.
        
    Raises:
        WebhookSignatureError: If header format is invalid.
    """
    if not header:
        raise WebhookSignatureError("Missing signature header")
    
    parts = {}
    for item in header.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parts[key.strip()] = value.strip()
    
    if "t" not in parts:
        raise WebhookSignatureError("Missing timestamp in signature header")
    
    if "v1" not in parts:
        raise WebhookSignatureError("Missing v1 signature in header")
    
    try:
        timestamp = int(parts["t"])
    except ValueError:
        raise WebhookSignatureError("Invalid timestamp format")
    
    return WebhookSignature(
        timestamp=timestamp,
        signature=parts["v1"],
        version="v1",
    )


def verify_signature(
    payload: bytes,
    signature_header: str,
    secret: Optional[str] = None,
    tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
) -> bool:
    """Verify HMAC-SHA256 signature for inbound webhook.
    
    Args:
        payload: Raw bytes of the webhook payload.
        signature_header: Value of the signature header.
        secret: Signing secret. If None, tries all configured secrets.
        tolerance_seconds: Maximum age of webhook in seconds (default 5 min).
        
    Returns:
        True if signature is valid.
        
    Raises:
        WebhookSignatureError: If signature is invalid.
        WebhookTimestampError: If timestamp is outside tolerance window.
        
    Example:
        >>> verify_signature(
        ...     payload=request.body,
        ...     signature_header=request.headers["X-Webhook-Signature"],
        ... )
    """
    parsed = parse_signature_header(signature_header)
    
    # Validate timestamp to prevent replay attacks
    current_time = int(time.time())
    time_diff = abs(current_time - parsed.timestamp)
    
    if time_diff > tolerance_seconds:
        logger.warning(
            "webhook_timestamp_rejected",
            timestamp=parsed.timestamp,
            current_time=current_time,
            diff_seconds=time_diff,
            tolerance=tolerance_seconds,
        )
        raise WebhookTimestampError(
            f"Webhook timestamp too old or in future. "
            f"Difference: {time_diff}s, tolerance: {tolerance_seconds}s"
        )
    
    # Get secrets to try
    if secret:
        secrets_to_try = [secret]
    else:
        secrets_to_try = get_webhook_secrets()
    
    if not secrets_to_try:
        raise WebhookSignatureError("No webhook secrets configured")
    
    # Create expected signed payload
    signed_payload = f"{parsed.timestamp}.".encode() + payload
    
    # Try each secret (supports rotation)
    for test_secret in secrets_to_try:
        expected_sig = hmac.new(
            test_secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(expected_sig, parsed.signature):
            logger.info(
                "webhook_signature_verified",
                timestamp=parsed.timestamp,
                payload_bytes=len(payload),
            )
            return True
    
    logger.warning(
        "webhook_signature_invalid",
        timestamp=parsed.timestamp,
        payload_bytes=len(payload),
    )
    raise WebhookSignatureError("Invalid webhook signature")


def verify_stripe_signature(
    payload: bytes,
    signature_header: str,
    secret: Optional[str] = None,
    tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
) -> bool:
    """Verify Stripe webhook signature.
    
    Stripe uses the same format: "t=<timestamp>,v1=<signature>"
    
    Args:
        payload: Raw request body bytes.
        signature_header: Value of Stripe-Signature header.
        secret: Stripe webhook endpoint secret (whsec_...).
        tolerance_seconds: Maximum age tolerance.
        
    Returns:
        True if signature is valid.
        
    Raises:
        WebhookSignatureError: If signature is invalid.
        WebhookTimestampError: If timestamp is outside tolerance.
    """
    stripe_secret = secret or os.getenv("STRIPE_WEBHOOK_SECRET")
    if not stripe_secret:
        raise WebhookSignatureError(
            "Stripe webhook secret not configured. "
            "Set STRIPE_WEBHOOK_SECRET environment variable."
        )
    
    return verify_signature(
        payload=payload,
        signature_header=signature_header,
        secret=stripe_secret,
        tolerance_seconds=tolerance_seconds,
    )


# Header names for different providers
WEBHOOK_SIGNATURE_HEADERS = {
    "regengine": "X-RegEngine-Signature",
    "stripe": "Stripe-Signature",
    "github": "X-Hub-Signature-256",
    "slack": "X-Slack-Signature",
}


def get_signature_header_name(provider: str = "regengine") -> str:
    """Get the expected signature header name for a provider.
    
    Args:
        provider: Provider name (regengine, stripe, github, slack).
        
    Returns:
        Header name string.
    """
    return WEBHOOK_SIGNATURE_HEADERS.get(provider, "X-Webhook-Signature")
