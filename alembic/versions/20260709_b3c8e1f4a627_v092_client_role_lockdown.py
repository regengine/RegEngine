"""v092 -- lock remaining RLS-disabled tables away from Supabase client roles.

Supabase's security advisor flags every table with RLS disabled as fully
exposed to the ``anon`` / ``authenticated`` roles used by its client
libraries (PostgREST). After the v081/v083/v090 RLS work, the remaining
RLS-disabled tables fall into two groups, neither of which is
tenant-scoped, so the standard ``get_tenant_context()`` predicate is the
wrong tool:

* Global regulatory metadata (``fsma.rule_definitions``,
  ``fsma.rule_audit_log``) — shared across tenants by design
  (TABLES_EXEMPT in tests/migrations/test_rls_coverage.py), but with RLS
  off the anon key can REWRITE THE COMPLIANCE RULES CATALOG.
* Service/infra tables written by the application without a tenant GUC
  (``public.funnel_events``, ``public.audit_log_buffer``,
  ``public.sandbox_shares``, ``public.tool_leads``) and credential
  material (``public.admin_mfa_recovery_codes``,
  ``public.password_reset_tokens``) — a tenant predicate would break
  their write paths (get_tenant_context() raises when the GUC is unset),
  and exposure of the credential tables is outright dangerous.

Treatment: ENABLE + FORCE row level security with a single permissive
app-role policy (``USING (true) WITH CHECK (true)`` TO ``regengine``,
``regengine_sysadmin``), plus REVOKE from PUBLIC / ``anon`` /
``authenticated``. Client roles get deny-all (RLS with no applicable
policy); the application is unaffected — production connects as the
Supabase ``postgres`` role (BYPASSRLS) and self-hosted deployments
connect as ``regengine``/``regengine_sysadmin``, which the policy
covers.

Migration-infra tables (``public.alembic_version``,
``public.schema_migrations``) get ENABLE (not FORCE) + revokes so the
table owner running migrations can never lock itself out.

Tables that exist only in some environments (created out-of-band before
alembic baselining: ``fsma.incidents``, ``public.password_reset_tokens``,
``public.schema_migrations``, ``public.tool_leads``,
``public.sandbox_shares``) are guarded with ``to_regclass`` so the
migration is a no-op where they are absent.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c8e1f4a627"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "127a24ffb54c"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (schema, table, force_rls). Migration-infra tables keep force=False so
# the owner role that runs alembic can never be locked out.
_TABLES: list[tuple[str, str, bool]] = [
    ("fsma", "rule_definitions", True),
    ("fsma", "rule_audit_log", True),
    ("fsma", "incidents", True),
    ("public", "funnel_events", True),
    ("public", "audit_log_buffer", True),
    ("public", "admin_mfa_recovery_codes", True),
    ("public", "password_reset_tokens", True),
    ("public", "tool_leads", True),
    ("public", "sandbox_shares", True),
    ("public", "alembic_version", False),
    ("public", "schema_migrations", False),
]


def _lockdown_sql(schema: str, table: str, force: bool) -> str:
    fq = f"{schema}.{table}"
    policy = f"app_only_{table}"
    force_stmt = f"EXECUTE 'ALTER TABLE {fq} FORCE ROW LEVEL SECURITY';" if force else ""
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
        -- (mirrors the v090 guard).
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
            CREATE ROLE regengine LOGIN;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
            CREATE ROLE regengine_sysadmin LOGIN INHERIT;
        END IF;

        EXECUTE 'ALTER TABLE {fq} ENABLE ROW LEVEL SECURITY';
        {force_stmt}

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

        -- Self-hosted deployments connect as regengine (no BYPASSRLS,
        -- no owner rights); grant the statement-level privileges the
        -- app_only policy assumes, plus any owned serial sequences.
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
    for schema, table, force in _TABLES:
        op.execute(_lockdown_sql(schema, table, force))


def downgrade() -> None:
    # Drop the app-only policy and disable RLS. Grants revoked in
    # upgrade() are NOT restored — the pre-v092 client-role exposure is
    # the vulnerability this migration exists to remove.
    for schema, table, _force in _TABLES:
        fq = f"{schema}.{table}"
        policy = f"app_only_{table}"
        op.execute(
            f"""
            DO $$
            BEGIN
                IF to_regclass('{fq}') IS NULL THEN
                    RETURN;
                END IF;
                EXECUTE 'DROP POLICY IF EXISTS {policy} ON {fq}';
                EXECUTE 'ALTER TABLE {fq} NO FORCE ROW LEVEL SECURITY';
                EXECUTE 'ALTER TABLE {fq} DISABLE ROW LEVEL SECURITY';
            END $$;
            """
        )
