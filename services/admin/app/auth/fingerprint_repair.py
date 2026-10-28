"""Idempotent repair for ``user_emails.email_fingerprint`` NULLs left by v094.

The v094 migration skips fingerprint backfill when ``AUTH_OTP_HMAC_SECRET``
is unset (except production, where it raises). Environments that later
gain the secret still have NULL fingerprints, so ``_load_valid_identity``
never matches those users.

This repair fills remaining NULLs with the same keyed HMAC the runtime
uses. It is safe to run on every startup: already-fingerprinted rows are
untouched. Do not rewrite the applied Alembic revision.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_crypto import AuthCryptoService
from ..sqlalchemy_models import UserEmailModel

logger = logging.getLogger("auth.fingerprint_repair")

_HMAC_SECRET_ENV = "AUTH_OTP_HMAC_SECRET"  # pragma: allowlist secret
_BATCH_SIZE = 500


def _is_production_like() -> bool:
    # Same guard as alembic/versions/20260715_feb267263e0a_v094_*.py
    if os.getenv("REGENGINE_ENV", "").lower() == "production":
        return True
    if os.getenv("ENV", "").lower() == "production":
        return True
    return bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_ENVIRONMENT_NAME"))


def repair_null_email_fingerprints(
    *,
    session_factory: Callable[[], Session] | None = None,
    crypto_service: AuthCryptoService | None = None,
) -> int:
    """Fill ``user_emails.email_fingerprint IS NULL`` when the HMAC secret is set.

    Returns the number of rows updated. Unset secret in non-production is a
    no-op (0). Unset secret in production raises ``RuntimeError``, matching v094.
    """
    secret = os.getenv(_HMAC_SECRET_ENV)
    if crypto_service is None:
        if not secret:
            if _is_production_like():
                raise RuntimeError(
                    "AUTH_OTP_HMAC_SECRET must be set in production to backfill "
                    "user_emails.email_fingerprint"
                )
            # Log the env var *name* as a literal; do not pass the
            # secret-named constant through the logging data flow
            # (py/clear-text-logging-sensitive-data).
            logger.warning(
                "AUTH_OTP_HMAC_SECRET not set; skipping "
                "user_emails.email_fingerprint repair"
            )
            return 0
        crypto_service = AuthCryptoService(hmac_secret=secret)

    if session_factory is None:
        from ..database import SessionLocal

        session_factory = SessionLocal

    total = 0
    session = session_factory()
    try:
        while True:
            rows = (
                session.execute(
                    select(UserEmailModel)
                    .where(UserEmailModel.email_fingerprint.is_(None))
                    .order_by(UserEmailModel.id)
                    .limit(_BATCH_SIZE)
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for row in rows:
                row.email_fingerprint = crypto_service.fingerprint_email(row.email)
            total += len(rows)
            session.commit()
        return total
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
