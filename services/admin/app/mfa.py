"""
TOTP-based Multi-Factor Authentication (MFA) for admin accounts.

This module provides:
- TOTP secret generation and validation
- QR code URI generation for authenticator apps
- Recovery codes (8 one-time-use codes)
- FastAPI dependency for MFA token verification
"""

import os
import secrets
import logging
from typing import TYPE_CHECKING, Optional
from datetime import datetime, timezone

if TYPE_CHECKING:
    # Forward-ref only; avoids a circular import between mfa and sqlalchemy_models.
    from .sqlalchemy_models import UserModel

try:
    import pyotp
except ImportError:
    raise ImportError(
        "pyotp is required for MFA support. Install with: pip install pyotp qrcode"
    )

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel

_logger = logging.getLogger("mfa")

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────
# TOTP time-step window: how many 30-second windows to accept (past + future)
# Standard is 1 (current window only), but 1 allows for clock skew tolerance
TOTP_WINDOW = int(os.getenv("TOTP_WINDOW", "1"))

# Recovery code count: number of one-time-use recovery codes to generate
RECOVERY_CODE_COUNT = int(os.getenv("RECOVERY_CODE_COUNT", "8"))

# Recovery code length in characters (base64-like, urlsafe)
RECOVERY_CODE_LENGTH = 8


# ──────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────
class MFAEnrollmentRequest(BaseModel):
    """Request to initiate MFA enrollment."""

    email: str


class MFAEnrollmentResponse(BaseModel):
    """Response with provisioning URI and recovery codes for MFA setup."""

    secret: str
    provisioning_uri: str
    recovery_codes: list[str]
    message: str = "Scan the QR code with your authenticator app, then verify with the 6-digit code"


class MFAVerificationRequest(BaseModel):
    """Request to verify TOTP token during enrollment or authentication."""

    token: str


class MFAVerificationResponse(BaseModel):
    """Response confirming MFA enrollment or authentication."""

    success: bool
    message: str


# ──────────────────────────────────────────────────────────────
# Core TOTP Functions
# ──────────────────────────────────────────────────────────────
def generate_mfa_secret() -> str:
    """
    Generate a random base32-encoded TOTP secret.

    Returns:
        str: Base32-encoded secret suitable for use with authenticator apps.
    """
    secret = pyotp.random_base32()
    _logger.debug("Generated new TOTP secret")
    return secret


def create_provisioning_uri(secret: str, email: str, issuer: str = "RegEngine") -> str:
    """
    Create a provisioning URI for TOTP setup in authenticator apps.

    The URI format allows users to scan a QR code with their authenticator app
    (Google Authenticator, Authy, 1Password, etc.) to automatically configure TOTP.

    Args:
        secret: Base32-encoded TOTP secret from generate_mfa_secret()
        email: User email address (displayed in authenticator app)
        issuer: Issuer name (displayed in authenticator app), defaults to "RegEngine"

    Returns:
        str: otpauth:// URI suitable for QR code generation
    """
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=email, issuer_name=issuer)
    _logger.debug(f"Created provisioning URI for {email}")
    return uri


def verify_totp(secret: str, token: str, window: int = TOTP_WINDOW) -> bool:
    """
    Verify a TOTP token against a secret.

    Accepts tokens from the current and adjacent time windows to allow for
    clock skew and user delays. By default, allows 1 window before/after current.

    Args:
        secret: Base32-encoded TOTP secret
        token: 6-digit TOTP code from user's authenticator app
        window: Number of adjacent windows to accept (default 1 = +/- 30 seconds)

    Returns:
        bool: True if token is valid, False otherwise
    """
    if not token or len(token) != 6 or not token.isdigit():
        _logger.warning(f"Invalid token format: {len(token)} chars, isdigit={token.isdigit() if token else 'N/A'}")
        return False

    try:
        totp = pyotp.TOTP(secret)
        is_valid = totp.verify(token, valid_window=window)
        if not is_valid:
            _logger.warning("TOTP verification failed: invalid token")
        return is_valid
    except Exception as e:
        _logger.error(f"TOTP verification error: {e}")
        return False


# ──────────────────────────────────────────────────────────────
# Recovery Codes
# ──────────────────────────────────────────────────────────────
def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """
    Generate one-time-use recovery codes for MFA account recovery.

    Each code is a random URL-safe string that should be stored securely
    by the user and the admin system. They bypass TOTP verification for
    account recovery if the user loses their authenticator device.

    Args:
        count: Number of recovery codes to generate (default 8)

    Returns:
        list[str]: List of recovery codes in format "XXXX-XXXX"
    """
    codes = []
    for _ in range(count):
        # Generate urlsafe random bytes, encoded as base32-like (alphanumeric + dash)
        code_part1 = secrets.token_urlsafe(RECOVERY_CODE_LENGTH // 2)[:4]
        code_part2 = secrets.token_urlsafe(RECOVERY_CODE_LENGTH // 2)[:4]
        code = f"{code_part1}-{code_part2}".upper()
        codes.append(code)

    _logger.debug(f"Generated {count} recovery codes")
    return codes


def hash_recovery_code(code: str) -> str:
    """
    Hash a recovery code for secure storage in the database.

    Recovery codes should never be stored in plaintext. Hash them like passwords
    before storing in the admin_mfa_recovery_codes table.

    Args:
        code: Recovery code (e.g., "ABCD-EFGH")

    Returns:
        str: SHA256 hex digest of the code
    """
    import hashlib

    hashed = hashlib.sha256(code.encode()).hexdigest()
    return hashed


def verify_recovery_code(code: str, hashed_code: str) -> bool:
    """
    Verify a recovery code against its hash.

    Args:
        code: Recovery code provided by user
        hashed_code: Stored hash from database

    Returns:
        bool: True if code matches hash, False otherwise
    """
    return hash_recovery_code(code) == hashed_code


# ──────────────────────────────────────────────────────────────
# FastAPI Dependency
# ──────────────────────────────────────────────────────────────
async def require_mfa(
    x_mfa_token: Optional[str] = Header(None),
    current_user: "UserModel" = Depends(lambda: None),
    db: Session = Depends(lambda: None),
) -> str:
    """
    FastAPI dependency to cryptographically verify MFA token from X-MFA-Token header.

    Verifies TOTP codes against the user's enrolled secret, or validates
    one-time recovery codes against stored hashes (marking them as used).

    Requires both ``get_current_user`` and ``get_session`` to be wired via
    dependency_overrides or the helper ``require_mfa_dependency()``.

    Args:
        x_mfa_token: MFA token from X-MFA-Token header
        current_user: Authenticated user (injected via dependency override)
        db: Database session (injected via dependency override)

    Returns:
        str: Verified MFA token

    Raises:
        HTTPException: 403 if token is missing, invalid format, or fails verification
    """
    from .sqlalchemy_models import MFARecoveryCodeModel

    if not x_mfa_token:
        _logger.warning("MFA token missing from request")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA token required (X-MFA-Token header)",
        )

    if not current_user or not current_user.mfa_secret:
        _logger.warning("MFA required but user has no MFA secret enrolled")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA not enrolled for this account",
        )

    # Classify token format
    is_totp = len(x_mfa_token) == 6 and x_mfa_token.isdigit()
    is_recovery = (
        len(x_mfa_token) == 9
        and x_mfa_token[4] == "-"
        and x_mfa_token[:4].isalnum()
        and x_mfa_token[5:].isalnum()
    )

    if not (is_totp or is_recovery):
        _logger.warning("Invalid MFA token format")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid MFA token format",
        )

    # TOTP verification
    if is_totp:
        if not verify_totp(secret=current_user.mfa_secret, token=x_mfa_token):
            _logger.warning(f"TOTP verification failed for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid MFA token",
            )
        return x_mfa_token

    # Recovery code verification
    code_hash = hash_recovery_code(x_mfa_token.upper())
    recovery = db.execute(
        select(MFARecoveryCodeModel).where(
            MFARecoveryCodeModel.user_id == current_user.id,
            MFARecoveryCodeModel.code_hash == code_hash,
            MFARecoveryCodeModel.used_at.is_(None),
        )
    ).scalar_one_or_none()

    if not recovery:
        _logger.warning(f"Recovery code verification failed for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid MFA token",
        )

    # Mark recovery code as consumed (one-time use)
    recovery.used_at = datetime.now(timezone.utc)
    db.commit()
    _logger.info(f"Recovery code consumed for user {current_user.id}")
    return x_mfa_token


def require_mfa_dependency():
    """
    Factory that returns ``require_mfa`` wired with real auth + DB dependencies.

    Usage in routes::

        @router.post("/admin/protected")
        async def protected_route(mfa_token: str = Depends(require_mfa_dependency())):
            ...
    """
    from .dependencies import get_current_user
    from .database import get_session

    async def _require_mfa(
        x_mfa_token: Optional[str] = Header(None),
        current_user=Depends(get_current_user),
        db: Session = Depends(get_session),
    ) -> str:
        return await require_mfa(
            x_mfa_token=x_mfa_token,
            current_user=current_user,
            db=db,
        )

    return _require_mfa


# ──────────────────────────────────────────────────────────────
# Enrollment Flow Helpers
# ──────────────────────────────────────────────────────────────
class MFAEnrollmentState(BaseModel):
    """State object for tracking MFA enrollment in progress."""

    admin_id: str
    secret: str
    recovery_codes: list[str]
    recovery_codes_hashed: list[str]
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


def create_enrollment_state(admin_id: str, hours_until_expiry: int = 1) -> MFAEnrollmentState:
    """
    Create an enrollment state object for an admin initiating MFA setup.

    The state should be stored temporarily (e.g., in Redis) and expires after
    a configurable duration. Once the admin confirms the TOTP token, the state
    is committed to the database.

    Args:
        admin_id: ID of the admin account
        hours_until_expiry: How long the enrollment is valid (default 1 hour)

    Returns:
        MFAEnrollmentState: Enrollment state with secret and recovery codes
    """
    secret = generate_mfa_secret()
    recovery_codes = generate_recovery_codes()
    recovery_codes_hashed = [hash_recovery_code(code) for code in recovery_codes]

    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(
        now.timestamp() + (hours_until_expiry * 3600), tz=timezone.utc
    )

    state = MFAEnrollmentState(
        admin_id=admin_id,
        secret=secret,
        recovery_codes=recovery_codes,
        recovery_codes_hashed=recovery_codes_hashed,
        created_at=now,
        expires_at=expires_at,
    )

    _logger.debug(f"Created enrollment state for admin {admin_id}")
    return state


def validate_enrollment_state(state: MFAEnrollmentState) -> bool:
    """
    Check if an enrollment state is still valid (not expired).

    Args:
        state: MFAEnrollmentState to validate

    Returns:
        bool: True if state is valid, False if expired
    """
    now = datetime.now(timezone.utc)
    is_valid = now < state.expires_at
    if not is_valid:
        _logger.warning(f"Enrollment state expired for admin {state.admin_id}")
    return is_valid
