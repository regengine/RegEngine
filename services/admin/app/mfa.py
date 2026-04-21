"""
TOTP-based Multi-Factor Authentication (MFA) for admin accounts.

This module provides:
- TOTP secret generation and validation
- QR code URI generation for authenticator apps
- Recovery codes (8 one-time-use codes)
- FastAPI dependency for MFA token verification
"""

import logging
import os
import secrets
import string
from typing import TYPE_CHECKING, Optional
from datetime import datetime, timezone

if TYPE_CHECKING:
    # Forward-ref only; avoids a circular import between mfa and sqlalchemy_models.
    from .sqlalchemy_models import UserModel
    from .session_store import RedisSessionStore

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

from .audit import AuditLogger

_logger = logging.getLogger("mfa")


# ──────────────────────────────────────────────────────────────
# Encryption at rest for TOTP secrets (#1376)
# ──────────────────────────────────────────────────────────────
# MFA_ENCRYPTION_KEY must be a urlsafe base64-encoded Fernet key, e.g. generated
# with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#
# If the env var is unset, new enrollments fall back to plaintext storage with a
# loud warning. This keeps local dev working but is rejected in production via
# the configuration check below (caller responsibility).

_MFA_KEY_ENV = "MFA_ENCRYPTION_KEY"


def _get_fernet():
    """Return a ``cryptography.fernet.Fernet`` instance, or ``None`` if no key is configured.

    Lazy-imported so environments without cryptography installed still import
    the module; MFA just falls back to plaintext storage in that case.
    """
    key = os.getenv(_MFA_KEY_ENV)
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        _logger.error("mfa_encryption_unavailable_cryptography_not_installed")
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        _logger.error(f"MFA_ENCRYPTION_KEY is set but invalid (Fernet key required): {exc}")
        return None


def encrypt_mfa_secret(plaintext_secret: str) -> Optional[str]:
    """Fernet-encrypt a base32 TOTP seed for at-rest storage (#1376).

    Returns the ciphertext as a string on success, or ``None`` if encryption
    is unavailable (caller must fall back to plaintext, with a warning).
    """
    f = _get_fernet()
    if f is None:
        return None
    return f.encrypt(plaintext_secret.encode("utf-8")).decode("ascii")


def decrypt_mfa_secret(ciphertext: str) -> str:
    """Fernet-decrypt a ciphertext produced by :func:`encrypt_mfa_secret`.

    Raises ``RuntimeError`` if the encryption key is not configured.
    Raises ``cryptography.fernet.InvalidToken`` if the ciphertext is corrupt
    or encrypted with a different key.
    """
    f = _get_fernet()
    if f is None:
        raise RuntimeError(
            f"Cannot decrypt MFA secret: {_MFA_KEY_ENV} is not set or invalid."
        )
    return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")


def resolve_user_mfa_secret(user: "UserModel") -> Optional[str]:
    """Return the plaintext base32 TOTP seed for a user, or ``None`` if not enrolled.

    Prefers the encrypted column when available (#1376) and falls back to the
    legacy plaintext column for rows not yet migrated. Errors during decryption
    are logged and treated as "not enrolled" rather than surfaced, so a rotated
    key never silently flips existing users to "MFA disabled".
    """
    ciphertext = getattr(user, "mfa_secret_ciphertext", None)
    if ciphertext:
        try:
            return decrypt_mfa_secret(ciphertext)
        except Exception as exc:
            _logger.error(
                f"mfa_decrypt_failed user_id={getattr(user, 'id', '?')} error={exc}"
            )
            # Fall through: if legacy plaintext also present we can still verify.
    plaintext = getattr(user, "mfa_secret", None)
    return plaintext or None

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

# MFA lockout / throttle (mirrors login lockout controls)
_MFA_LOCKOUT_THRESHOLD = int(os.getenv("MFA_LOCKOUT_THRESHOLD", "10"))
_MFA_LOCKOUT_DURATION = int(os.getenv("MFA_LOCKOUT_DURATION", "86400"))  # 24h
_MFA_PROGRESSIVE_DELAY_START = int(os.getenv("MFA_PROGRESSIVE_DELAY_START", "3"))
_MFA_PROGRESSIVE_DELAY_CAP_SECONDS = int(os.getenv("MFA_PROGRESSIVE_DELAY_CAP_SECONDS", "300"))
_MFA_TOTP_REPLAY_TTL_SECONDS = max((2 * TOTP_WINDOW + 1) * 30, 30)


def _mfa_subject_key(user: "UserModel") -> str:
    email = (getattr(user, "email", None) or "").strip().lower()
    if email:
        return email
    return str(getattr(user, "id", "unknown"))


def _mfa_lockout_key(subject_key: str) -> str:
    return f"mfa_lockout:{subject_key}"


def _mfa_lockout_delay_key(subject_key: str) -> str:
    return f"mfa_lockout_delay:{subject_key}"


def _mfa_replay_key(subject_key: str, token: str) -> str:
    return f"mfa_totp_used:{subject_key}:{token}"


def _mfa_progressive_delay_seconds(count: int) -> int:
    if count < _MFA_PROGRESSIVE_DELAY_START:
        return 0
    return min(2 ** (count - _MFA_PROGRESSIVE_DELAY_START), _MFA_PROGRESSIVE_DELAY_CAP_SECONDS)


async def _check_mfa_lockout(session_store: "RedisSessionStore", subject_key: str) -> None:
    client = await session_store._get_client()
    count_str = await client.get(_mfa_lockout_key(subject_key))
    if count_str and int(count_str) >= _MFA_LOCKOUT_THRESHOLD:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to repeated failed MFA attempts. Contact support or wait 24 hours.",
            headers={"Retry-After": str(_MFA_LOCKOUT_DURATION)},
        )

    delay_ttl = await client.ttl(_mfa_lockout_delay_key(subject_key))
    if delay_ttl and delay_ttl > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed MFA attempts. Please wait before trying again.",
            headers={"Retry-After": str(delay_ttl)},
        )


async def _record_mfa_lockout_attempt(session_store: "RedisSessionStore", subject_key: str) -> int:
    client = await session_store._get_client()
    key = _mfa_lockout_key(subject_key)
    async with client.pipeline(transaction=False) as pipe:
        pipe.incr(key)
        pipe.expire(key, _MFA_LOCKOUT_DURATION)
        results = await pipe.execute()
    count = int(results[0])

    delay = _mfa_progressive_delay_seconds(count)
    if delay > 0:
        await client.setex(_mfa_lockout_delay_key(subject_key), delay, "1")

    return count


async def _clear_mfa_lockout(session_store: "RedisSessionStore", subject_key: str) -> None:
    client = await session_store._get_client()
    await client.delete(_mfa_lockout_key(subject_key), _mfa_lockout_delay_key(subject_key))


async def _record_totp_replay_guard(
    session_store: "RedisSessionStore",
    subject_key: str,
    token: str,
) -> bool:
    client = await session_store._get_client()
    inserted = await client.set(
        _mfa_replay_key(subject_key, token),
        "1",
        ex=_MFA_TOTP_REPLAY_TTL_SECONDS,
        nx=True,
    )
    return bool(inserted)


def _emit_mfa_verification_failed_audit(
    db: Session,
    current_user: "UserModel",
    *,
    reason: str,
    token_type: str,
) -> None:
    try:
        from .models import TenantContext
        from .sqlalchemy_models import MembershipModel

        tenant_id = TenantContext.get_tenant_context(db)
        if not tenant_id:
            membership = db.execute(
                select(MembershipModel.tenant_id).where(
                    MembershipModel.user_id == getattr(current_user, "id", None),
                    MembershipModel.is_active == True,  # noqa: E712
                )
            ).scalar_one_or_none()
            tenant_id = membership
        if not tenant_id:
            return
        AuditLogger.log_event(
            db,
            tenant_id=tenant_id,
            event_type="audit.mfa_verification_failed",
            action="mfa.verify",
            event_category="authentication",
            severity="warning",
            actor_id=getattr(current_user, "id", None),
            actor_email=getattr(current_user, "email", None),
            resource_type="user",
            resource_id=str(getattr(current_user, "id", "")),
            metadata={"reason": reason, "token_type": token_type},
        )
    except Exception as exc:
        _logger.warning(f"mfa_failure_audit_logging_failed: {exc}")


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


def store_mfa_secret_on_user(user: "UserModel", secret: str) -> None:
    """Persist a newly-enrolled TOTP seed onto a user row (#1376).

    Writes the Fernet-encrypted seed to ``mfa_secret_ciphertext`` when an
    encryption key is available; otherwise falls back to ``mfa_secret`` with
    a loud warning. Clears the legacy plaintext column once we have ciphertext
    so a DB snapshot can never leak both versions.
    """
    ciphertext = encrypt_mfa_secret(secret)
    if ciphertext is not None:
        user.mfa_secret_ciphertext = ciphertext
        # Blank the legacy column so a backup of this row doesn't carry
        # plaintext forward.
        user.mfa_secret = None
    else:
        _logger.warning(
            "MFA_ENCRYPTION_KEY not set — storing TOTP secret in plaintext. "
            "This path is intended for local dev only."
        )
        user.mfa_secret = secret
        user.mfa_secret_ciphertext = None


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
# Recovery Codes (#1377)
# ──────────────────────────────────────────────────────────────
# Fixed alphabet so generated codes never contain '-' or '_' from urlsafe
# base64. Matches the normalization applied in ``normalize_recovery_code``.
_RECOVERY_CODE_ALPHABET = string.ascii_uppercase + string.digits  # 36 chars


def normalize_recovery_code(raw: str) -> str:
    """Canonicalize a recovery code supplied by the user (#1377).

    Uppercases, strips whitespace/dashes/underscores, and returns the result.
    Empty string is returned for unparseable input; callers should treat that
    as "invalid".
    """
    if not raw:
        return ""
    cleaned = []
    for ch in raw:
        if ch.isalnum():
            cleaned.append(ch.upper())
    return "".join(cleaned)


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Generate one-time-use recovery codes for MFA account recovery.

    Codes are drawn from ``A-Z0-9`` so the redeem-side format check can be a
    simple ``isalnum`` + length assertion without rejecting URL-safe base64
    characters like ``-`` / ``_`` (old bug — #1377 — rejected ~12% of codes).

    Returns codes in the user-facing format ``XXXX-XXXX`` (8 alnum chars
    with a single dash for readability). The dash is optional when
    redeeming; normalization strips it before hashing.
    """
    codes = []
    for _ in range(count):
        first = "".join(secrets.choice(_RECOVERY_CODE_ALPHABET) for _ in range(4))
        second = "".join(secrets.choice(_RECOVERY_CODE_ALPHABET) for _ in range(4))
        codes.append(f"{first}-{second}")

    _logger.debug(f"Generated {count} recovery codes")
    return codes


def hash_recovery_code(code: str) -> str:
    """Hash a recovery code for secure storage in the database (#1041).

    Normalizes the code (uppercase, strip non-alnum) before hashing so that
    dashes/casing differences between generation and redemption don't produce
    different hashes.

    Uses argon2id via the shared ``pwd_context`` (same cost parameters as
    password hashing) rather than SHA-256. Recovery codes are auth credentials
    and warrant the same protection — SHA-256 is a fast hash attackable at GPU
    speed (~2^47.6 for 8-char alphanum codes).
    """
    from .auth_utils import pwd_context

    canonical = normalize_recovery_code(code)
    return pwd_context.hash(canonical)


def verify_recovery_code(code: str, hashed_code: str) -> bool:
    """Verify a recovery code against its argon2 hash (#1041).

    Returns False (not a crash) for legacy SHA-256 hashes — passlib cannot
    identify them as a known argon2 hash and raises ValueError, which we catch
    and treat as a failed verification so affected users are prompted to
    regenerate their recovery codes.
    """
    from .auth_utils import pwd_context

    canonical = normalize_recovery_code(code)
    try:
        return pwd_context.verify(canonical, hashed_code)
    except Exception:
        # hashed_code is not a valid argon2 hash (e.g. legacy SHA-256 hex
        # digest). Treat as mismatch — callers will prompt the user to
        # regenerate recovery codes.
        return False


# ──────────────────────────────────────────────────────────────
# FastAPI Dependency
# ──────────────────────────────────────────────────────────────
async def require_mfa(
    x_mfa_token: Optional[str] = Header(None),
    current_user: "UserModel" = Depends(lambda: None),
    db: Session = Depends(lambda: None),
    session_store: Optional["RedisSessionStore"] = Depends(lambda: None),
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

    # Resolve the TOTP secret via the encryption-aware helper (#1376). This
    # transparently reads mfa_secret_ciphertext when populated, falling back
    # to the legacy plaintext column during the encryption migration.
    if not current_user:
        _logger.warning("MFA required but no current_user in scope")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA not enrolled for this account",
        )
    user_secret = resolve_user_mfa_secret(current_user)
    if not user_secret:
        _logger.warning("MFA required but user has no MFA secret enrolled")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA not enrolled for this account",
        )

    if not session_store:
        _logger.error("MFA verification requires a session store for lockout enforcement")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA verification temporarily unavailable",
        )

    subject_key = _mfa_subject_key(current_user)
    await _check_mfa_lockout(session_store, subject_key)

    async def _raise_invalid_token(*, reason: str, token_type: str, detail: str = "Invalid MFA token") -> None:
        await _record_mfa_lockout_attempt(session_store, subject_key)
        _emit_mfa_verification_failed_audit(
            db,
            current_user,
            reason=reason,
            token_type=token_type,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )

    # Classify token format. TOTP = 6 digits. Recovery = normalized 8 alnum
    # chars (after stripping dash/space/etc).
    is_totp = len(x_mfa_token) == 6 and x_mfa_token.isdigit()
    normalized_recovery = normalize_recovery_code(x_mfa_token)
    is_recovery = len(normalized_recovery) == 8 and normalized_recovery.isalnum()

    if not (is_totp or is_recovery):
        _logger.warning("Invalid MFA token format")
        await _raise_invalid_token(
            reason="invalid_format",
            token_type="unknown",
            detail="Invalid MFA token format",
        )

    # TOTP verification
    if is_totp:
        if not verify_totp(secret=user_secret, token=x_mfa_token):
            _logger.warning(f"TOTP verification failed for user {current_user.id}")
            await _raise_invalid_token(reason="invalid_totp", token_type="totp")

        if not await _record_totp_replay_guard(session_store, subject_key, x_mfa_token):
            _logger.warning(f"TOTP replay rejected for user {current_user.id}")
            await _raise_invalid_token(reason="totp_replay", token_type="totp")

        await _clear_mfa_lockout(session_store, subject_key)
        return x_mfa_token

    # Recovery code verification (#1041) — argon2 hashes are salted so we
    # cannot look up by hash directly. Instead, fetch all unused codes for
    # the user (max RECOVERY_CODE_COUNT rows) and verify each one. This is a
    # bounded scan (≤ 8 rows by default) and is done only when the token
    # format matches a recovery code, so the overhead is negligible.
    # normalize_recovery_code / verify_recovery_code both normalize, so
    # "ABCD-EFGH", "abcd-efgh", etc. all match (#1377).
    unused_codes = db.execute(
        select(MFARecoveryCodeModel).where(
            MFARecoveryCodeModel.user_id == current_user.id,
            MFARecoveryCodeModel.used_at.is_(None),
        )
    ).scalars().all()

    recovery = None
    for candidate in unused_codes:
        if verify_recovery_code(x_mfa_token, candidate.code_hash):
            recovery = candidate
            break

    if not recovery:
        _logger.warning(f"Recovery code verification failed for user {current_user.id}")
        await _raise_invalid_token(reason="invalid_recovery_code", token_type="recovery")

    # Mark recovery code as consumed (one-time use)
    recovery.used_at = datetime.now(timezone.utc)
    db.commit()
    await _clear_mfa_lockout(session_store, subject_key)
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
    from .dependencies import get_session_store

    async def _require_mfa(
        x_mfa_token: Optional[str] = Header(None),
        current_user=Depends(get_current_user),
        db: Session = Depends(get_session),
        session_store=Depends(get_session_store),
    ) -> str:
        return await require_mfa(
            x_mfa_token=x_mfa_token,
            current_user=current_user,
            db=db,
            session_store=session_store,
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
