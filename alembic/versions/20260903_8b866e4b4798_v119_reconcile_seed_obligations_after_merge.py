"""v119 — reconcile seed_obligations_for_tenant after the security-branch merge.

Two branches each ``CREATE OR REPLACE``d ``public.seed_obligations_for_tenant``:

* v112 (d8b2056471a7, #2832): FORCE-RLS-aware body — swaps ``app.tenant_id`` to
  copy the demo template into temp tables (required since v111-main put FORCE
  ROW LEVEL SECURITY on ``regulations``/``controls``), fails closed on tenant
  mismatch, marker write wrapped in an exception handler.
* v111-security (b71d9e4c2a60): reads ``public.regulations`` directly — under
  FORCE RLS that returns zero demo rows and seeds nothing, silently — but adds
  ``session_user = 'regengine'`` and the SECURITY DEFINER anti-hijack
  ``search_path = pg_catalog, public, fsma, pg_temp`` (pg_temp last).

With the security branch re-parented after v116, v111-security's body would
win. This revision reinstalls the v112 body verbatim and layers the two
v111-security hardenings on top, so the chain ends with one definition that
both #2832 and the runtime-role cutover tests expect.

Revision ID: 8b866e4b4798
Revises: b71d9e4c2a60
Create Date: 2026-09-03
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "8b866e4b4798"  # pragma: allowlist secret
down_revision = "b71d9e4c2a60"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION seed_obligations_for_tenant(p_tenant_id UUID)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, fsma, pg_temp
        AS $fn$
        DECLARE
            demo_tenant UUID := '5946c58f-ddf9-4db0-9baa-acb11c6fce91';
            reg_count INT;
        BEGIN
            -- v111-security guard, kept: only the runtime role may seed.
            IF session_user <> 'regengine' THEN
                RAISE EXCEPTION 'seed_obligations_for_tenant is restricted to regengine'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            -- Fail closed (#2832): a SECURITY DEFINER seeder must only ever
            -- write the session's own tenant. get_tenant_context() raises
            -- when app.tenant_id is unset (v097 fail-hard).
            IF p_tenant_id IS DISTINCT FROM get_tenant_context() THEN
                RAISE EXCEPTION
                    'tenant context mismatch for obligation seeding (requested %)',
                    p_tenant_id
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

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

            -- Phase 1: stage the demo tenant's template rows into pg_temp.
            -- Temp relations carry no RLS, so the joins in phase 2 can see
            -- demo rows and new-tenant rows at the same time. app.tenant_id
            -- is moved transaction-locally and restored on every exit.
            BEGIN
                PERFORM set_config('app.tenant_id', demo_tenant::text, true);

                DROP TABLE IF EXISTS pg_temp.seed_tpl_regulations;
                CREATE TEMP TABLE seed_tpl_regulations ON COMMIT DROP AS
                    SELECT id, source_name, citation, section, text, effective_date
                    FROM regulations
                    WHERE tenant_id = demo_tenant;

                DROP TABLE IF EXISTS pg_temp.seed_tpl_obligations;
                CREATE TEMP TABLE seed_tpl_obligations ON COMMIT DROP AS
                    SELECT id, regulation_id, title, description, risk_category, status, due_date
                    FROM obligations
                    WHERE tenant_id = demo_tenant;

                DROP TABLE IF EXISTS pg_temp.seed_tpl_controls;
                CREATE TEMP TABLE seed_tpl_controls ON COMMIT DROP AS
                    SELECT obligation_id, title, description, control_type, frequency, status
                    FROM controls
                    WHERE tenant_id = demo_tenant;

                PERFORM set_config('app.tenant_id', p_tenant_id::text, true);
            EXCEPTION WHEN OTHERS THEN
                -- Never leave the caller's transaction pointed at the demo
                -- tenant, whatever went wrong above.
                PERFORM set_config('app.tenant_id', p_tenant_id::text, true);
                RAISE;
            END;

            -- Phase 2: write under the caller's own tenant context. Every
            -- statement below is authorised by the ordinary tenant policies.
            INSERT INTO regulations (id, tenant_id, source_name, citation, section, text, effective_date)
            SELECT gen_random_uuid(), p_tenant_id, source_name, citation, section, text, effective_date
            FROM pg_temp.seed_tpl_regulations;

            INSERT INTO obligations (id, tenant_id, regulation_id, title, description,
                                     risk_category, status, due_date, created_at)
            SELECT gen_random_uuid(), p_tenant_id,
                   (SELECT nr.id FROM regulations nr
                    JOIN pg_temp.seed_tpl_regulations dr ON dr.id = o.regulation_id
                    WHERE nr.tenant_id = p_tenant_id AND nr.citation = dr.citation LIMIT 1),
                   o.title, o.description, o.risk_category, o.status, o.due_date, NOW()
            FROM pg_temp.seed_tpl_obligations o;

            INSERT INTO controls (id, tenant_id, obligation_id, title, description,
                                  control_type, frequency, status, created_at)
            SELECT gen_random_uuid(), p_tenant_id,
                   (SELECT no2.id FROM obligations no2
                    JOIN pg_temp.seed_tpl_obligations do2 ON do2.id = c.obligation_id
                    WHERE no2.tenant_id = p_tenant_id AND no2.title = do2.title LIMIT 1),
                   c.title, c.description, c.control_type, c.frequency, c.status, NOW()
            FROM pg_temp.seed_tpl_controls c;

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
        $fn$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION seed_obligations_for_tenant(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION seed_obligations_for_tenant(uuid) TO regengine, regengine_sysadmin")


def downgrade() -> None:
    # Back to the v111-security definition is not meaningful (it seeds nothing
    # under FORCE RLS); restore the v112 body, which is what main shipped.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION seed_obligations_for_tenant(p_tenant_id UUID)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public, fsma
        AS $fn$
        DECLARE
            demo_tenant UUID := '5946c58f-ddf9-4db0-9baa-acb11c6fce91';
            reg_count INT;
        BEGIN
            -- Fail closed (#2832): a SECURITY DEFINER seeder must only ever
            -- write the session's own tenant. get_tenant_context() raises
            -- when app.tenant_id is unset (v097 fail-hard).
            IF p_tenant_id IS DISTINCT FROM get_tenant_context() THEN
                RAISE EXCEPTION
                    'tenant context mismatch for obligation seeding (requested %)',
                    p_tenant_id
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

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

            -- Phase 1: stage the demo tenant's template rows into pg_temp.
            -- Temp relations carry no RLS, so the joins in phase 2 can see
            -- demo rows and new-tenant rows at the same time. app.tenant_id
            -- is moved transaction-locally and restored on every exit.
            BEGIN
                PERFORM set_config('app.tenant_id', demo_tenant::text, true);

                DROP TABLE IF EXISTS pg_temp.seed_tpl_regulations;
                CREATE TEMP TABLE seed_tpl_regulations ON COMMIT DROP AS
                    SELECT id, source_name, citation, section, text, effective_date
                    FROM regulations
                    WHERE tenant_id = demo_tenant;

                DROP TABLE IF EXISTS pg_temp.seed_tpl_obligations;
                CREATE TEMP TABLE seed_tpl_obligations ON COMMIT DROP AS
                    SELECT id, regulation_id, title, description, risk_category, status, due_date
                    FROM obligations
                    WHERE tenant_id = demo_tenant;

                DROP TABLE IF EXISTS pg_temp.seed_tpl_controls;
                CREATE TEMP TABLE seed_tpl_controls ON COMMIT DROP AS
                    SELECT obligation_id, title, description, control_type, frequency, status
                    FROM controls
                    WHERE tenant_id = demo_tenant;

                PERFORM set_config('app.tenant_id', p_tenant_id::text, true);
            EXCEPTION WHEN OTHERS THEN
                -- Never leave the caller's transaction pointed at the demo
                -- tenant, whatever went wrong above.
                PERFORM set_config('app.tenant_id', p_tenant_id::text, true);
                RAISE;
            END;

            -- Phase 2: write under the caller's own tenant context. Every
            -- statement below is authorised by the ordinary tenant policies.
            INSERT INTO regulations (id, tenant_id, source_name, citation, section, text, effective_date)
            SELECT gen_random_uuid(), p_tenant_id, source_name, citation, section, text, effective_date
            FROM pg_temp.seed_tpl_regulations;

            INSERT INTO obligations (id, tenant_id, regulation_id, title, description,
                                     risk_category, status, due_date, created_at)
            SELECT gen_random_uuid(), p_tenant_id,
                   (SELECT nr.id FROM regulations nr
                    JOIN pg_temp.seed_tpl_regulations dr ON dr.id = o.regulation_id
                    WHERE nr.tenant_id = p_tenant_id AND nr.citation = dr.citation LIMIT 1),
                   o.title, o.description, o.risk_category, o.status, o.due_date, NOW()
            FROM pg_temp.seed_tpl_obligations o;

            INSERT INTO controls (id, tenant_id, obligation_id, title, description,
                                  control_type, frequency, status, created_at)
            SELECT gen_random_uuid(), p_tenant_id,
                   (SELECT no2.id FROM obligations no2
                    JOIN pg_temp.seed_tpl_obligations do2 ON do2.id = c.obligation_id
                    WHERE no2.tenant_id = p_tenant_id AND no2.title = do2.title LIMIT 1),
                   c.title, c.description, c.control_type, c.frequency, c.status, NOW()
            FROM pg_temp.seed_tpl_controls c;

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
        $fn$;
        """
    )
