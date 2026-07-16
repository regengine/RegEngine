"""v094 -- backfill passwordless identity data.

Revision ID: feb267263e0a
Revises: 16cb29a3938c
Create Date: 2026-07-15

The v084 passwordless schema backfilled ``user_emails`` without computing
``email_fingerprint`` and created ``organizations`` /
``organization_memberships`` empty, so ``_load_valid_identity`` can never
match an existing user and every sign-in code email is suppressed
(``auth_challenge_email_suppressed_ineligible_identity``).

This migration:
1. Creates an organization per active legacy tenant (same id, so the
   mapping is deterministic and re-runnable).
2. Creates organization memberships from active legacy memberships,
   carrying the legacy role name (lowercased).
3. Backfills ``user_emails.email_fingerprint`` with the same keyed HMAC
   the runtime uses (``AuthCryptoService.fingerprint_email``). This needs
   ``AUTH_OTP_HMAC_SECRET``: missing in production is a hard error;
   missing in dev/test skips the fingerprint step (the runtime falls back
   to a process-local ephemeral secret there, so stored fingerprints
   could not match anyway).
"""

import hashlib
import hmac
import logging
import os
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

logger = logging.getLogger("alembic.runtime.migration")

revision: str = "feb267263e0a"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "16cb29a3938c"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fingerprint_email(secret: bytes, email: str) -> str:
    # Mirrors services/admin/app/auth_crypto.py::AuthCryptoService.fingerprint_email
    normalized_email = email.strip().lower()
    return hmac.new(
        secret,
        f"email_fingerprint:{normalized_email}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _is_production_like() -> bool:
    if os.getenv("REGENGINE_ENV", "").lower() == "production":
        return True
    if os.getenv("ENV", "").lower() == "production":
        return True
    return bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_ENVIRONMENT_NAME"))


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            INSERT INTO public.organizations (id, name, enforced_auth_policy)
            SELECT t.id, t.name, 'standard'
            FROM public.tenants t
            WHERE t.status = 'active'
            ON CONFLICT (id) DO NOTHING
            """
        )
    )

    conn.execute(
        sa.text(
            """
            INSERT INTO public.organization_memberships (user_id, organization_id, role)
            SELECT m.user_id, m.tenant_id, lower(r.name)
            FROM public.memberships m
            JOIN public.roles r ON r.id = m.role_id
            JOIN public.organizations o ON o.id = m.tenant_id
            WHERE m.is_active
            ON CONFLICT ON CONSTRAINT uq_organization_memberships_user_org DO NOTHING
            """
        )
    )

    secret = os.getenv("AUTH_OTP_HMAC_SECRET")
    if not secret:
        if _is_production_like():
            raise RuntimeError(
                "AUTH_OTP_HMAC_SECRET must be set in production to backfill user_emails.email_fingerprint"
            )
        logger.warning("AUTH_OTP_HMAC_SECRET not set; skipping user_emails.email_fingerprint backfill")
        return

    key = secret.encode("utf-8")
    rows = conn.execute(sa.text("SELECT id, email FROM public.user_emails WHERE email_fingerprint IS NULL")).fetchall()
    for row_id, email in rows:
        conn.execute(
            sa.text(
                """
                UPDATE public.user_emails
                SET email_fingerprint = :fp
                WHERE id = :id AND email_fingerprint IS NULL
                """
            ),
            {"fp": _fingerprint_email(key, email), "id": row_id},
        )


def downgrade() -> None:
    # Data-only backfill. Reversing would delete identity rows that the
    # passwordless flow may have started relying on, so leave data in place.
    pass
