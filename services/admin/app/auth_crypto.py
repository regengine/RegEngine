"""Cryptographic helpers for high-assurance passwordless auth.

OTP codes have a tiny search space, so they must be stored as keyed HMAC
digests rather than password hashes or unsalted SHA-256 values.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from typing import Any

logger = logging.getLogger("auth_crypto")

_HMAC_SECRET_ENV = "AUTH_OTP_HMAC_SECRET"  # pragma: allowlist secret
_MIN_SECRET_BYTES = 32
_DEV_EPHEMERAL_HMAC_SECRET: str | None = None


class AuthCryptoService:
    """Small auth crypto boundary for OTP and opaque session tokens."""

    def __init__(self, hmac_secret: str | bytes | None = None):
        secret = self._fetch_hmac_secret_from_kms_or_env() if hmac_secret is None else hmac_secret
        self._hmac_secret = self._coerce_secret(secret)

    @staticmethod
    def generate_secure_otp() -> str:
        """Return a cryptographically secure 6-digit code as a zero-padded string."""
        return f"{secrets.randbelow(1_000_000):06d}"

    def hash_otp(
        self,
        challenge_id: Any,
        purpose: Any,
        email_fingerprint: str,
        code: str,
    ) -> str:
        """Return a context-bound HMAC-SHA-256 digest for a 6-digit OTP."""
        message = self._canonical_otp_message(
            challenge_id=challenge_id,
            purpose=purpose,
            email_fingerprint=email_fingerprint,
            code=code,
        )
        return hmac.new(self._hmac_secret, message, hashlib.sha256).hexdigest()

    def verify_otp_hash(
        self,
        expected_hash: str,
        challenge_id: Any,
        purpose: Any,
        email_fingerprint: str,
        code: str,
    ) -> bool:
        """Verify an OTP digest using constant-time comparison."""
        candidate_hash = self.hash_otp(
            challenge_id=challenge_id,
            purpose=purpose,
            email_fingerprint=email_fingerprint,
            code=code,
        )
        return hmac.compare_digest(str(expected_hash), candidate_hash)

    def fingerprint_email(self, email: str) -> str:
        """Return a keyed, normalized email fingerprint for auth state."""
        normalized_email = self._required_text("email", email).lower()
        return hmac.new(
            self._hmac_secret,
            f"email_fingerprint:{normalized_email}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def generate_opaque_session_token() -> str:
        """Return a URL-safe opaque token with 256 bits of randomness."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_session_token(token: str) -> str:
        """Hash an opaque session token for database storage."""
        if not isinstance(token, str) or not token:
            raise ValueError("session token is required")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def _fetch_hmac_secret_from_kms_or_env(cls) -> str:
        """Simulate KMS lookup with an environment-backed secret.

        Production must provide AUTH_OTP_HMAC_SECRET. Local development gets a
        process-local ephemeral secret so importing tests does not require KMS.
        """
        secret = os.getenv(_HMAC_SECRET_ENV)
        if secret:
            return secret

        if os.getenv("REGENGINE_ENV", "").lower() == "production":
            raise RuntimeError(f"{_HMAC_SECRET_ENV} must be set in production")

        global _DEV_EPHEMERAL_HMAC_SECRET
        if _DEV_EPHEMERAL_HMAC_SECRET is None:
            _DEV_EPHEMERAL_HMAC_SECRET = secrets.token_urlsafe(_MIN_SECRET_BYTES)
            logger.warning(
                "%s not set; using process-local ephemeral OTP HMAC secret",
                _HMAC_SECRET_ENV,
            )
        return _DEV_EPHEMERAL_HMAC_SECRET

    @staticmethod
    def _coerce_secret(secret: str | bytes) -> bytes:
        if isinstance(secret, bytes):
            secret_bytes = secret
        elif isinstance(secret, str):
            secret_bytes = secret.encode("utf-8")
        else:
            raise TypeError("hmac_secret must be str or bytes")

        if len(secret_bytes) < _MIN_SECRET_BYTES:
            raise ValueError("OTP HMAC secret must be at least 32 bytes")
        return secret_bytes

    @classmethod
    def _canonical_otp_message(
        cls,
        *,
        challenge_id: Any,
        purpose: Any,
        email_fingerprint: str,
        code: str,
    ) -> bytes:
        challenge = cls._required_text("challenge_id", challenge_id)
        purpose_value = getattr(purpose, "value", purpose)
        purpose_text = cls._required_text("purpose", purpose_value)
        fingerprint = cls._required_text("email_fingerprint", email_fingerprint)
        if not isinstance(code, str) or len(code) != 6 or not code.isdigit():
            raise ValueError("OTP code must be exactly 6 digits")

        return json.dumps(
            {
                "challenge_id": challenge,
                "purpose": purpose_text,
                "email_fingerprint": fingerprint,
                "code": code,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _required_text(name: str, value: Any) -> str:
        if value is None:
            raise ValueError(f"{name} is required")
        text = str(value).strip()
        if not text:
            raise ValueError(f"{name} is required")
        return text
