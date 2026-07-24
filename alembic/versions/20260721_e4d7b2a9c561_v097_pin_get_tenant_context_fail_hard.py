"""v097 -- pin get_tenant_context() to one canonical fail-hard, STABLE body (#2461).

Background
----------
Every ``fsma.*`` RLS policy is ``USING (tenant_id = get_tenant_context())``, and
the #2461 GUC-propagation work (v096 / PR #2607) rests on a promise repeated
throughout ``services/shared/tenant_context.py``: untenanted access fails CLOSED
because this function RAISEs when ``app.tenant_id`` is unset.

That promise was not reliably true. The function is created OUTSIDE the
migration chain -- ``scripts/init-postgres.sh`` and ``backend-ci.yml`` seeded a
FAIL-SOFT body (``EXCEPTION WHEN OTHERS THEN RETURN NULL``). v056
(``c2d3e4f5a6b7``) does define a fail-hard body, but only recreates the function
when its guard fires, and that guard is computed from name + zero args + UUID
return type -- it never inspects the BODY. The fail-soft variant satisfies it,
so v056 skipped its recreate and the weak body survived to head.

Verified on PostgreSQL 16: a database seeded fail-soft and migrated to
c3a51e2f7b90 (v096) still had the fail-soft body verbatim, and a non-BYPASSRLS
role with ``app.tenant_id`` unset received ZERO ROWS from ``fsma.cte_events``
instead of an error -- ``tenant_id = NULL`` is NULL, so the policy filtered
everything and the query succeeded empty. No data escapes (silent default-deny,
not a leak), but a path that forgets the GUC returns "no records" quietly
instead of failing loudly. For a traceability product the silent empty recall
trace is the more dangerous failure, and it is exactly what #2461 exists to
prevent.

STABLE is load-bearing, not cosmetic
------------------------------------
The emitted body is declared STABLE. PostgreSQL refuses to use a VOLATILE
function's result as an index-qual comparison value
(``match_clause_to_indexcol`` -> ``!contain_volatile_functions``), so a VOLATILE
``get_tenant_context()`` silently downgrades ``tenant_id =
get_tenant_context()`` from an index condition to a per-row filter on EVERY
tenant-scoped table.

Measured on ``fsma.cte_events`` (200k rows, 50k for the target tenant,
non-BYPASSRLS role, GUC set, freshly ANALYZEd) with an otherwise identical body:

    STABLE   -> Index Only Scan, Index Cond: (tenant_id = get_tenant_context())
                cost 7418,  execution 2.020 ms
    VOLATILE -> Seq Scan,     Filter: (tenant_id = get_tenant_context())
                150000 Rows Removed by Filter, cost 56695, execution 77.829 ms

38x, and it scales with total rows across ALL tenants. v056 and
``services/admin/app/database.py`` both emitted the function without STABLE, so
this migration is also the fix for that pre-existing regression wherever the
function is currently VOLATILE.

Why this does NOT reintroduce the #1247 CASCADE hazard
------------------------------------------------------
v056 needed ``DROP FUNCTION ... CASCADE`` because it CHANGED THE RETURN TYPE
(TEXT -> UUID); PostgreSQL requires a drop for that, and the drop cascaded into
every dependent RLS policy, silently un-protecting tables (#1227 / #1247).

This migration changes only the BODY and volatility. Name, argument types and
return type are unchanged, so ``CREATE OR REPLACE FUNCTION`` preserves the
``pg_proc`` OID; ``pg_policy`` depends on the function by OID via ``pg_depend``,
so every dependent policy stays attached. There is no DROP here, therefore no
CASCADE, therefore no policy loss. Verified: migrating a fail-soft database to
this revision left the ``fsma`` policy set byte-identical to a control database
(63 policies; a full schema|table|policy|qual|with_check|cmd|roles dump diffed
empty), with both v096 CASE-form policies intact.

If the function is found with a non-UUID return type (a pre-v056 database) this
migration REFUSES rather than reaching for a drop -- v056 owns that conversion.
That branch is defensive only: a TEXT-returning function actually kills the
chain far earlier, at v051, with ``operator does not exist: uuid = text``.

Unconditional by design
-----------------------
An earlier draft only replaced the body when it lacked ``RAISE EXCEPTION``.
That was the same class of bug this migration exists to fix -- v056 inspects the
signature, the draft inspected the source TEXT, and neither inspects BEHAVIOUR.
A body mentioning RAISE in a comment, or raising only on a malformed UUID,
would satisfy it. Worse, every CI fixture already contains a RAISE, so the
replace path would never have executed anywhere except production.

Since ``CREATE OR REPLACE`` is provably non-destructive here, the correct shape
is to apply the canonical definition unconditionally: idempotent, behaviour-
based rather than text-based, and exercised by every test run.

Ordering
--------
Re-asserted as a new head rather than edited into v056: v056 is long-applied in
production, and rebasing an applied revision corrupts ``alembic_version`` --
see ``docs/abandoned_migrations_20260420_incident/`` and the warning in
``20260613_70d5e59e3257_v082_merge_v081_heads.py``.

Revision ID: e4d7b2a9c561
Revises: c3a51e2f7b90
Create Date: 2026-07-21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e4d7b2a9c561"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c3a51e2f7b90"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PIN_FAIL_HARD = """
DO $mig$
DECLARE
    v_schema  text;
    v_rettype text;
BEGIN
    SELECT n.nspname, t.typname
      INTO v_schema, v_rettype
      FROM pg_proc p
      JOIN pg_type t ON p.prorettype = t.oid
      JOIN pg_namespace n ON p.pronamespace = n.oid
     WHERE p.proname = 'get_tenant_context'
       AND p.pronargs = 0
       AND n.nspname = ANY (current_schemas(true))
     ORDER BY array_position(current_schemas(true), n.nspname)
     LIMIT 1;

    IF v_rettype IS NOT NULL AND v_rettype <> 'uuid' THEN
        -- Pre-v056 TEXT-returning shape. Changing the return type requires a
        -- DROP, which is precisely the #1247 policy-cascade hazard. v056 owns
        -- that conversion; refuse loudly rather than drop policies here.
        RAISE EXCEPTION
            'get_tenant_context() returns % (expected uuid) - run v056 (c2d3e4f5a6b7) first',
            v_rettype;
    END IF;

    -- Unconditional: CREATE OR REPLACE preserves the pg_proc OID, so every
    -- dependent RLS policy stays attached (no DROP, no CASCADE, no #1247).
    -- STABLE is required for the predicate to remain an index condition.
    EXECUTE format($ddl$
        CREATE OR REPLACE FUNCTION %I.get_tenant_context()
        RETURNS UUID AS $fn$
        DECLARE
            tid TEXT;
        BEGIN
            tid := NULLIF(current_setting('app.tenant_id', TRUE), '');
            IF tid IS NULL THEN
                RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS';
            END IF;
            RETURN tid::UUID;
        END;
        $fn$ LANGUAGE plpgsql STABLE
    $ddl$, COALESCE(v_schema, 'public'));
END
$mig$;
"""


def upgrade() -> None:
    op.execute(_PIN_FAIL_HARD)


def downgrade() -> None:
    """Intentionally a no-op.

    The forward direction replaces a fail-SOFT body with a fail-HARD one. A
    faithful inverse would reinstate a function that silently returns NULL when
    ``app.tenant_id`` is unset, turning every ungated query into a quiet empty
    result and re-opening the exact hazard this revision closes. It would also
    restore the VOLATILE planner regression.

    Downgrading past this revision therefore leaves the hardened function in
    place. Nothing else here creates state, so this is a genuine no-op rather
    than an incomplete one.
    """
