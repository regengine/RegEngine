"""v112 — seed_obligations_for_tenant: SECURITY DEFINER, pinned search_path, fail-closed.

Revision ID: d8b2056471a7
Revises: df664d92adba
Create Date: 2026-08-26

``seed_obligations_for_tenant`` copies a template catalogue out of the demo
tenant (``5946c58f-ddf9-4db0-9baa-acb11c6fce91``) into a brand new tenant.
Since v055 it has been declared without a security or search_path clause,
i.e. SECURITY INVOKER::

    grep -c "SECURITY DEFINER" \\
        alembic/versions/20260801_8633e0a7a84e_v106_tenant_seed_state_marker.py
    0

The caller is ``services/ingestion/app/onboarding.py`` line 38, on a
``shared.database.SessionLocal`` whose begin-hook has already pinned
``app.tenant_id`` to the NEW tenant, connected as ``regengine``
(NOBYPASSRLS after the #2461 cutover). Every template read in the body asks
for ``tenant_id = demo_tenant`` while the ``tenant_isolation_*`` policies
conjoin ``tenant_id = <new tenant>`` onto it — an unsatisfiable predicate.
RLS filters rather than raising, so the
result is zero rows and no error: onboarding reports success, seeds nothing,
and v106 then writes ``fsma.tenant_seed_state`` with ``obligation_count = 0``
— which is exactly the value that disables the #2708 fail-closed cross-check
in ``services/ingestion/app/compliance_score.py`` line 260
(``if marker_row and (marker_row[0] or 0) > 0``). The silent-seeding failure
therefore also disarms the detector built to catch silent RLS failures.

Two things are fixed here.

1. Function hardening (the #2832 ask), following the v109
   ``fsma.get_team_roster`` pattern:

   * ``SECURITY DEFINER`` so execution no longer depends on the caller's
     table grants, plus ``SET search_path = public, fsma`` so a caller
     cannot re-point any unqualified relation in the body. (PostgreSQL 17:
     ``gen_random_uuid()`` is in ``pg_catalog``, so pinning is safe.)
   * A fail-closed guard as the first statement: ``p_tenant_id`` must equal
     ``get_tenant_context()``, which itself raises when ``app.tenant_id`` is
     unset (v097 fail-hard). A SECURITY DEFINER function that seeds an
     arbitrary tenant id would otherwise be a cross-tenant write primitive.
   * ``REVOKE ALL ... FROM PUBLIC`` then an explicit ``GRANT EXECUTE`` to the
     app roles.

2. The copy itself is restaged so it works under least privilege.

   SECURITY DEFINER on its own does NOT fix the seed. It only helps if the
   definer bypasses RLS, and the definer here is the migration/owner role —
   ``public.obligations`` has been FORCE ROW LEVEL SECURITY since v051 (and
   v111 just brought ``controls``/``regulations`` in line), so the owner is
   subject to the very same tenant predicate. Relying on a BYPASSRLS definer
   would also turn this function into a standing cross-tenant read primitive,
   which is the posture #2461 deliberately dismantled.

   The real obstacle is that a single ``app.tenant_id`` value cannot satisfy
   a cross-tenant copy: each statement needs the demo tenant for its SELECT
   and the new tenant for its INSERT, and the obligation/control statements
   need to join demo rows against just-inserted new-tenant rows. So the body
   now stages the three template relations into ``pg_temp`` (temp tables are
   not subject to RLS) while ``app.tenant_id`` is transaction-locally pointed
   at the demo tenant, restores the caller's tenant, and then performs every
   INSERT under the caller's own tenant context. No RLS bypass is involved at
   any point; the policies still authorise every read and every write.

   The GUC is switched with ``set_config(..., true)`` — transaction-scoped —
   and restored to ``p_tenant_id`` (proven equal to the caller's context by
   the guard) on both the success and the error path, so no caller ever
   continues its transaction under the demo tenant.

The row-mapping logic, the "already seeded" early return and the
``fsma.tenant_seed_state`` marker upserts (including their WARNING-only
EXCEPTION wrappers) are carried over from v106 unchanged; only the demo-side
relations are replaced by their staged copies.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8b2056471a7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "df664d92adba"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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

    # Make the grantees exist rather than skipping the grant when they do not
    # (v104: "A conditional CREATE POLICY is what caused this incident" — the
    # same rule applies to a conditional GRANT on a REVOKEd function).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                CREATE ROLE regengine LOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                CREATE ROLE regengine_sysadmin LOGIN INHERIT;
            END IF;
        END $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION seed_obligations_for_tenant(uuid) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION seed_obligations_for_tenant(uuid) "
        "TO regengine, regengine_sysadmin"
    )


def downgrade() -> None:
    # Restore the v106 body verbatim: SECURITY INVOKER, no search_path pin,
    # no tenant guard, direct cross-tenant reads.
    op.execute(
        """
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
        """
    )
