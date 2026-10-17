"""Remove the ingestion_runs guard when its denied roles do not exist.

v128 intended to create this guard only when a permissive policy could reach
anon or authenticated. Its condition was built but not used, so the guard was
created even on databases without either role. The PUBLIC guard changes the
boot-time RLS canary manifest for ingestion_runs and prevents startup there.

Revision ID: a9ea09050a30
Revises: 0a329588b824
Create Date: 2026-10-17
"""

from alembic import op

revision = "a9ea09050a30"  # pragma: allowlist secret
down_revision = "0a329588b824"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $repair$
        DECLARE previous_lock_timeout text := pg_catalog.current_setting('lock_timeout');
        BEGIN
            PERFORM set_config('lock_timeout', '10s', true);
            IF to_regclass('fsma.ingestion_runs') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM pg_policy
                   WHERE polrelid = to_regclass('fsma.ingestion_runs')
                     AND polname = 'v128_client_guard_ingestion_runs'
               )
               AND NOT EXISTS (
                   SELECT 1 FROM pg_roles
                   WHERE rolname IN ('anon', 'authenticated')
               ) THEN
                DROP POLICY v128_client_guard_ingestion_runs ON fsma.ingestion_runs;
            END IF;
            PERFORM set_config('lock_timeout', previous_lock_timeout, true);
        END
        $repair$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $rollback$
        DECLARE
            previous_lock_timeout text := pg_catalog.current_setting('lock_timeout');
            tenant_cast text;
        BEGIN
            PERFORM set_config('lock_timeout', '10s', true);
            IF to_regclass('fsma.ingestion_runs') IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM pg_policy
                   WHERE polrelid = to_regclass('fsma.ingestion_runs')
                     AND polname = 'v128_client_guard_ingestion_runs'
               ) THEN
                SELECT CASE WHEN atttypid = 'uuid'::regtype THEN '()' ELSE '()::text' END
                INTO tenant_cast
                FROM pg_attribute
                WHERE attrelid = to_regclass('fsma.ingestion_runs')
                  AND attname = 'tenant_id';
                EXECUTE replace($policy$
                    CREATE POLICY v128_client_guard_ingestion_runs ON fsma.ingestion_runs
                        AS RESTRICTIVE FOR ALL TO PUBLIC
                        USING ((tenant_id = public.get_tenant_context()::text)
                               AND current_user NOT IN ('anon', 'authenticated'))
                        WITH CHECK ((tenant_id = public.get_tenant_context()::text)
                                    AND current_user NOT IN ('anon', 'authenticated'))
                $policy$, '()::text', tenant_cast);
            END IF;
            PERFORM set_config('lock_timeout', previous_lock_timeout, true);
        END
        $rollback$;
        """
    )
