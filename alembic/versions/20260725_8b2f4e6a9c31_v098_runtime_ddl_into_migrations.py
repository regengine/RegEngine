"""v098 — move the remaining runtime DDL into migrations (#2461 follow-up).

After the #2461 least-privilege cutover the application connects as
``regengine`` (NOSUPERUSER / NOBYPASSRLS), yet four code paths still issued
CREATE TABLE/INDEX at runtime. That forced ``GRANT CREATE ON SCHEMA ... TO
regengine`` (runbooks/prod-least-privilege-db-role.sql, SAFETY note) and, in
prod, transferring ownership of the two scheduler tables to ``regengine`` so
its boot DDL would not fail. This migration adopts that DDL so the runtime
code paths can be deleted and the schema-CREATE privilege revoked:

* ``public.scheduler_seen_items`` — the two boot indexes that v093's
  forward-port of the table did not carry
  (services/scheduler/app/state.py).
* ``public.scheduler_job_runs`` — per-job last-run tracking (#1144),
  previously created only by scheduler boot DDL.
* ``fsma.incidents`` (+ ``idx_incidents_tenant``) — JSONB incident storage,
  previously created on first use by ingestion's incident_router.
* ``fsma.exchange_packages`` (+ ``idx_exchange_packages_receiver_status``)
  — B2B EPCIS exchange packages, previously created on first use by
  ingestion's exchange_api.

Everything is IF NOT EXISTS / ``to_regclass``-guarded: environments where
the runtime DDL already created these objects (prod) converge to the same
state as a fresh database.

All four tables get the v092 client-role lockdown (ENABLE + FORCE RLS,
permissive ``app_only`` policy TO ``regengine``/``regengine_sysadmin``,
REVOKE from PUBLIC / ``anon`` / ``authenticated``, explicit DML grants).
v092 applied that treatment only where the runtime-created tables happened
to exist; on a fresh database these tables are born here — after v092 —
and would otherwise ship with RLS disabled. The scheduler tables are the
same class of app-written public-schema infra table v092 covers
(``funnel_events``, ``audit_log_buffer``, ...), and the explicit grants
keep the app role working after the prod follow-up returns their ownership
to ``postgres`` (runbooks/prod-revoke-create-after-v098.sql). Tenant
isolation for the two fsma tables is enforced at the application layer
(tenant-scoped WHERE clauses + the ``set_tenant_guc_if_uuid`` backstop);
see the TABLES_EXEMPT entries in tests/migrations/test_rls_coverage.py.
Structural lockdown regression coverage lives in
tests/migrations/test_client_role_lockdown_v092.py (V098_TABLES).

downgrade() drops only rebuildable state (job-run telemetry, boot
indexes); the data-bearing fsma tables are left in place — see the
downgrade docstring.

Revision ID: 8b2f4e6a9c31 (random hex, not a credential)
Revises: e4d7b2a9c561
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "8b2f4e6a9c31"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "e4d7b2a9c561"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirrors v092's _lockdown_sql (force always on): idempotent client-role
# lockdown + app-role grants for a table this migration may have just
# created. Kept inline — migration files must stay self-contained.
def _client_role_lockdown_sql(schema: str, table: str) -> str:
    fq = f"{schema}.{table}"
    policy = f"app_only_{table}"
    return f"""
    DO $$
    DECLARE
        seqname text;
    BEGIN
        IF to_regclass('{fq}') IS NULL THEN
            RETURN;
        END IF;

        -- The regengine roles are the policy grantees; create them
        -- idempotently for environments provisioned without them
        -- (mirrors the v090/v092 guard).
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
            CREATE ROLE regengine LOGIN;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
            CREATE ROLE regengine_sysadmin LOGIN INHERIT;
        END IF;

        EXECUTE 'ALTER TABLE {fq} ENABLE ROW LEVEL SECURITY';
        EXECUTE 'ALTER TABLE {fq} FORCE ROW LEVEL SECURITY';

        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = '{schema}' AND tablename = '{table}'
              AND policyname = '{policy}'
        ) THEN
            EXECUTE 'CREATE POLICY {policy} ON {fq} '
                 || 'FOR ALL TO regengine, regengine_sysadmin '
                 || 'USING (true) WITH CHECK (true)';
        END IF;

        EXECUTE 'REVOKE ALL ON {fq} FROM PUBLIC';
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE 'REVOKE ALL ON {fq} FROM anon';
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE 'REVOKE ALL ON {fq} FROM authenticated';
        END IF;

        EXECUTE 'GRANT USAGE ON SCHEMA {schema} '
             || 'TO regengine, regengine_sysadmin';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON {fq} '
             || 'TO regengine, regengine_sysadmin';
        FOR seqname IN
            SELECT pg_get_serial_sequence('{fq}', a.attname)
            FROM pg_attribute a
            WHERE a.attrelid = '{fq}'::regclass
              AND a.attnum > 0 AND NOT a.attisdropped
              AND pg_get_serial_sequence('{fq}', a.attname) IS NOT NULL
        LOOP
            EXECUTE format(
                'GRANT USAGE, SELECT ON SEQUENCE %s '
                'TO regengine, regengine_sysadmin', seqname);
        END LOOP;
    END $$;
    """


def upgrade() -> None:
    # 1. scheduler_seen_items boot indexes — v093 ported the table but not
    #    the two indexes state.py created at boot.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_seen_items_source_type
            ON public.scheduler_seen_items (source_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_seen_items_last_seen
            ON public.scheduler_seen_items (last_seen_at)
        """
    )

    # 2. scheduler_job_runs — mirror the boot DDL from
    #    services/scheduler/app/state.py (#1144).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.scheduler_job_runs (
            job_id          VARCHAR(128) PRIMARY KEY,
            last_run_at     TIMESTAMP WITH TIME ZONE,
            last_success_at TIMESTAMP WITH TIME ZONE,
            last_status     VARCHAR(32),
            last_error      TEXT
        )
        """
    )

    # Client-role lockdown + app-role DML grants for the scheduler tables.
    # They are app-written public-schema infra tables — exactly the class
    # v092 locked away from Supabase-style client roles (funnel_events,
    # audit_log_buffer, ...): scheduler_job_runs.last_error carries internal
    # error text, and a forged scheduler_seen_items row marks a new
    # regulatory item as already-seen, silently suppressing ingestion.
    # The grants also keep regengine working after the #2461 follow-up
    # returns table ownership to postgres
    # (runbooks/prod-revoke-create-after-v098.sql).
    op.execute(_client_role_lockdown_sql("public", "scheduler_seen_items"))
    op.execute(_client_role_lockdown_sql("public", "scheduler_job_runs"))

    # 3. fsma.incidents — mirror the on-first-use DDL from
    #    services/ingestion/app/incident_router.py. pgcrypto for
    #    gen_random_uuid() on PG < 13 (v079 precedent).
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.incidents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_incidents_tenant
            ON fsma.incidents (tenant_id)
        """
    )

    # 4. fsma.exchange_packages — mirror the on-first-use DDL from
    #    services/ingestion/app/exchange_api.py.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.exchange_packages (
            id UUID PRIMARY KEY,
            sender_tenant_id TEXT NOT NULL,
            receiver_tenant_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'received')),
            traceability_lot_codes TEXT[] NOT NULL DEFAULT '{}',
            event_count INTEGER NOT NULL DEFAULT 0,
            notification_target TEXT,
            package_hash TEXT NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            received_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_exchange_packages_receiver_status
            ON fsma.exchange_packages (receiver_tenant_id, status, created_at DESC)
        """
    )

    # 5. Client-role lockdown for the two fsma tables (no-op where v092
    #    already applied it to a runtime-created copy).
    op.execute(_client_role_lockdown_sql("fsma", "incidents"))
    op.execute(_client_role_lockdown_sql("fsma", "exchange_packages"))


def downgrade() -> None:
    # Drop only rebuildable state that the previous revision's runtime DDL
    # recreates on demand (v093 precedent): the job-run telemetry table and
    # the seen_items boot indexes. fsma.incidents and fsma.exchange_packages
    # hold tenant business records (incidents, B2B exchange packages) and
    # are deliberately LEFT IN PLACE together with their RLS lockdown — on
    # databases where v098 created them they become out-of-band tables,
    # exactly like the pre-baseline environments v092 guards with
    # to_regclass. scheduler_seen_items returns to its v093 state (table
    # kept, lockdown removed); grants are not revoked, mirroring v092's
    # downgrade stance.
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.scheduler_seen_items') IS NULL THEN
                RETURN;
            END IF;
            EXECUTE 'DROP POLICY IF EXISTS app_only_scheduler_seen_items '
                 || 'ON public.scheduler_seen_items';
            EXECUTE 'ALTER TABLE public.scheduler_seen_items '
                 || 'NO FORCE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE public.scheduler_seen_items '
                 || 'DISABLE ROW LEVEL SECURITY';
        END $$;
        """
    )
    op.execute("DROP TABLE IF EXISTS public.scheduler_job_runs")
    op.execute("DROP INDEX IF EXISTS public.idx_seen_items_last_seen")
    op.execute("DROP INDEX IF EXISTS public.idx_seen_items_source_type")
