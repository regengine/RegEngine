"""v110 -- allow authenticated users to create their own developer profile.

Revision ID: 6f8c2d1a4b90
Revises: 51701aedee57
Create Date: 2026-08-15

The developer portal requires a one-to-one ``developer_profiles`` row before
users can create sandbox API keys. Existing RLS policies permit users to read
and update their own row but do not permit the initial insert.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "6f8c2d1a4b90"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "51701aedee57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.developer_profiles') IS NULL THEN
                RAISE NOTICE 'public.developer_profiles does not exist - skipping insert policy';
                RETURN;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                RAISE NOTICE 'authenticated role does not exist - skipping insert policy';
                RETURN;
            END IF;

            DROP POLICY IF EXISTS developers_insert_own_profile
                ON public.developer_profiles;

            CREATE POLICY developers_insert_own_profile
                ON public.developer_profiles
                FOR INSERT
                TO authenticated
                WITH CHECK ((SELECT auth.uid()) = auth_user_id);
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.developer_profiles') IS NULL THEN
                RETURN;
            END IF;

            DROP POLICY IF EXISTS developers_insert_own_profile
                ON public.developer_profiles;
        END
        $$;
        """
    )
