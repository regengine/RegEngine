"""v106 — obligation seed-state marker: deny-all reads stop impersonating unseeded tenants (#2708).

An RLS deny-all EMPTY read on ``obligations`` (0 rows, no exception) is
indistinguishable from an unseeded tenant, so a policy/GUC regression on
that table routed the compliance score's obligation dimension to the
50-point "rules not loaded" assumed default (silent-failure inventory;
read *errors* were already poisoned by #2700/#2705).

Distinguishing signal: ``fsma.tenant_seed_state`` — one row per tenant,
upserted by ``seed_obligations_for_tenant()`` (both when it seeds and
when it early-returns because the tenant already has data). The scoring
query cross-checks: marker says obligations exist, live read returns
zero → poison the dimension (fail closed) instead of the 50-point
default.

The marker upsert inside the function is wrapped in an EXCEPTION block —
it is an observability aid and must never make seeding itself fail
(e.g. if the session lacks the tenant GUC the RLS WITH CHECK rejects the
upsert; seeding still completes, with a WARNING).

Revision ID: 8633e0a7a84e
Revises: 323c945cf68d
Create Date: 2026-08-01
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "8633e0a7a84e"  # pragma: allowlist secret
down_revision = "323c945cf68d"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_TABLE = "fsma.tenant_seed_state"
_POLICY = "tenant_isolation_tenant_seed_state"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            tenant_id              UUID PRIMARY KEY,
            obligations_seeded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            obligation_count       INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    # Fail-closed tenant isolation (v095 pattern): FORCE so even the table
    # owner cannot bypass.
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(
        f"""
        CREATE POLICY {_POLICY} ON {_TABLE}
            FOR ALL
            USING (tenant_id = get_tenant_context())
            WITH CHECK (tenant_id = get_tenant_context())
        """
    )

    # Client-role lockdown + app-role grants (v092/v098/v103 pattern).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                CREATE ROLE regengine LOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                CREATE ROLE regengine_sysadmin LOGIN INHERIT;
            END IF;

            EXECUTE 'REVOKE ALL ON {_TABLE} FROM PUBLIC';
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL ON {_TABLE} FROM anon';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                EXECUTE 'REVOKE ALL ON {_TABLE} FROM authenticated';
            END IF;

            EXECUTE 'GRANT USAGE ON SCHEMA fsma TO regengine, regengine_sysadmin';
            EXECUTE 'GRANT SELECT, INSERT, UPDATE ON {_TABLE} TO regengine, regengine_sysadmin';
        END
        $$;
        """
    )

    # Rebuild seed_obligations_for_tenant (v055/v057 body) with the marker
    # upsert in BOTH exits: the early return ("already seeded") and the
    # post-seed path. Marker failure degrades to a WARNING, never breaks
    # seeding.
    op.execute("""
        CREATE OR REPLACE FUNCTION seed_obligations_for_tenant(p_tenant_id UUID)
        RETURNS void AS $fn$
        DECLARE
            demo_tenant UUID := '5946c58f-ddf9-4db0-9baa-acb11c6fce91';
            reg_count INT;
        BEGIN
            SELECT COUNT(*) INTO reg_count FROM regulations WHERE tenant_id = p_tenant_id;
            IF reg_count > 0 THEN
                RAISE NOTICE 'Tenant % already has % regulations - skipping seed',
                    p_tenant_id, reg_count;
                BEGIN
                    INSERT INTO fsma.tenant_seed_state (tenant_id, obligations_seeded_at, obligation_count)
                    VALUES (p_tenant_id, NOW(),
                            (SELECT COUNT(*) FROM obligations WHERE tenant_id = p_tenant_id))
                    ON CONFLICT (tenant_id) DO UPDATE
                        SET obligations_seeded_at = EXCLUDED.obligations_seeded_at,
                            obligation_count = EXCLUDED.obligation_count;
                EXCEPTION WHEN OTHERS THEN
                    RAISE WARNING 'tenant_seed_state marker write failed for %: %', p_tenant_id, SQLERRM;
                END;
                RETURN;
            END IF;

            INSERT INTO regulations (id, tenant_id, source_name, citation, section, text, effective_date)
            SELECT gen_random_uuid(), p_tenant_id, source_name, citation, section, text, effective_date
            FROM regulations WHERE tenant_id = demo_tenant;

            INSERT INTO obligations (id, tenant_id, regulation_id, title, description,
                                     risk_category, status, due_date, created_at)
            SELECT gen_random_uuid(), p_tenant_id,
                   (SELECT nr.id FROM regulations nr
                    JOIN regulations dr ON dr.id = o.regulation_id
                    WHERE nr.tenant_id = p_tenant_id AND nr.citation = dr.citation LIMIT 1),
                   o.title, o.description, o.risk_category, o.status, o.due_date, NOW()
            FROM obligations o WHERE o.tenant_id = demo_tenant;

            INSERT INTO controls (id, tenant_id, obligation_id, title, description,
                                  control_type, frequency, status, created_at)
            SELECT gen_random_uuid(), p_tenant_id,
                   (SELECT no2.id FROM obligations no2
                    JOIN obligations do2 ON do2.id = c.obligation_id
                    WHERE no2.tenant_id = p_tenant_id AND no2.title = do2.title LIMIT 1),
                   c.title, c.description, c.control_type, c.frequency, c.status, NOW()
            FROM controls c WHERE c.tenant_id = demo_tenant;

            BEGIN
                INSERT INTO fsma.tenant_seed_state (tenant_id, obligations_seeded_at, obligation_count)
                VALUES (p_tenant_id, NOW(),
                        (SELECT COUNT(*) FROM obligations WHERE tenant_id = p_tenant_id))
                ON CONFLICT (tenant_id) DO UPDATE
                    SET obligations_seeded_at = EXCLUDED.obligations_seeded_at,
                        obligation_count = EXCLUDED.obligation_count;
            EXCEPTION WHEN OTHERS THEN
                RAISE WARNING 'tenant_seed_state marker write failed for %: %', p_tenant_id, SQLERRM;
            END;

            RAISE NOTICE 'Seeded FSMA 204 obligations for tenant %', p_tenant_id;
        END;
        $fn$ LANGUAGE plpgsql
    """)


def downgrade() -> None:
    # Restore the v055/v057 function body (no marker writes).
    op.execute("""
        CREATE OR REPLACE FUNCTION seed_obligations_for_tenant(p_tenant_id UUID)
        RETURNS void AS $fn$
        DECLARE
            demo_tenant UUID := '5946c58f-ddf9-4db0-9baa-acb11c6fce91';
            reg_count INT;
        BEGIN
            SELECT COUNT(*) INTO reg_count FROM regulations WHERE tenant_id = p_tenant_id;
            IF reg_count > 0 THEN
                RAISE NOTICE 'Tenant % already has % regulations - skipping seed',
                    p_tenant_id, reg_count;
                RETURN;
            END IF;

            INSERT INTO regulations (id, tenant_id, source_name, citation, section, text, effective_date)
            SELECT gen_random_uuid(), p_tenant_id, source_name, citation, section, text, effective_date
            FROM regulations WHERE tenant_id = demo_tenant;

            INSERT INTO obligations (id, tenant_id, regulation_id, title, description,
                                     risk_category, status, due_date, created_at)
            SELECT gen_random_uuid(), p_tenant_id,
                   (SELECT nr.id FROM regulations nr
                    JOIN regulations dr ON dr.id = o.regulation_id
                    WHERE nr.tenant_id = p_tenant_id AND nr.citation = dr.citation LIMIT 1),
                   o.title, o.description, o.risk_category, o.status, o.due_date, NOW()
            FROM obligations o WHERE o.tenant_id = demo_tenant;

            INSERT INTO controls (id, tenant_id, obligation_id, title, description,
                                  control_type, frequency, status, created_at)
            SELECT gen_random_uuid(), p_tenant_id,
                   (SELECT no2.id FROM obligations no2
                    JOIN obligations do2 ON do2.id = c.obligation_id
                    WHERE no2.tenant_id = p_tenant_id AND no2.title = do2.title LIMIT 1),
                   c.title, c.description, c.control_type, c.frequency, c.status, NOW()
            FROM controls c WHERE c.tenant_id = demo_tenant;

            RAISE NOTICE 'Seeded FSMA 204 obligations for tenant %', p_tenant_id;
        END;
        $fn$ LANGUAGE plpgsql
    """)
    op.execute(f"DROP TABLE IF EXISTS {_TABLE}")
