"""v062: users.token_version + users.mfa_secret_ciphertext (#1349, #1375, #1376).

Revision ID: 8374fa2eb35b
Revises: 57e83b393ff6
Create Date: 2026-04-20

Forward-port of the never-run Flyway migration
``services/admin/migrations/V42__auth_hardening_token_version_mfa_encryption.sql``.

Why
---
Prod runs Alembic only (``scripts/run-migrations.sh`` → ``alembic upgrade
head``); Flyway V42 was never executed in Railway. The app code on
``main`` declares both columns on ``UserModel``
(``services/admin/app/sqlalchemy_models.py`` lines 82/84/88), so every
``SELECT users.* ...`` — including the login lookup in
``services/admin/app/auth_routes.py`` — fails with
``psycopg2.errors.UndefinedColumn: column users.token_version does not
exist``. The global handler in ``services/shared/error_handling.py``
converts that to the 500 users see on ``POST /api/admin/auth/login``:
``{"error":{"type":"internal_error","message":"An internal error occurred"}}``.

Columns
-------
* ``token_version INTEGER NOT NULL DEFAULT 0`` — monotonic counter
  bumped on password reset / logout-all to invalidate outstanding JWTs
  (#1349, #1375). JWTs carry the version at mint time; the auth
  dependency rejects tokens whose embedded version is stale.
* ``mfa_secret_ciphertext TEXT NULL`` — Fernet-encrypted TOTP seed
  (#1376). Code prefers ciphertext when present and falls back to the
  legacy plaintext ``mfa_secret`` column until the one-shot
  re-encryption tool runs.

Both additions are additive and backfilled with the column default, so
this migration is safe on a live database without blocking writes.
Uses ``ADD COLUMN IF NOT EXISTS`` for idempotence (local dev / CI
fixtures where Flyway may have run).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "8374fa2eb35b"
down_revision: Union[str, Sequence[str], None] = "57e83b393ff6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
        IF to_regclass('public.users') IS NOT NULL THEN
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;

        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS mfa_secret_ciphertext TEXT;

        COMMENT ON COLUMN users.token_version IS
            'Monotonic counter. Bumped on password reset / logout-all to invalidate outstanding JWTs (#1349, #1375).';
        COMMENT ON COLUMN users.mfa_secret_ciphertext IS
            'Fernet-encrypted TOTP seed. Falls back to users.mfa_secret if NULL (#1376). Requires MFA_ENCRYPTION_KEY env var.';
        END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
        IF to_regclass('public.users') IS NOT NULL THEN
        ALTER TABLE users DROP COLUMN IF EXISTS mfa_secret_ciphertext;
        ALTER TABLE users DROP COLUMN IF EXISTS token_version;
        END IF;
        END $$;
        """
    )
