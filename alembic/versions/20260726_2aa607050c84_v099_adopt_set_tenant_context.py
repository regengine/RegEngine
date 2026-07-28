"""v099 -- adopt set_tenant_context(); pin public.set_admin_context (#2461 follow-up).

v098 (8b2f4e6a9c31) moved the remaining runtime CREATE TABLE/INDEX into
migrations, but the three RLS helper functions were still created at boot by
``services/admin/app/database.py::init_db``. That boot DDL was load-bearing in
two distinct ways this migration closes:

* ``set_tenant_context`` had NO migration owner at all: init_db was the only
  thing that created it anywhere (``scripts/init-postgres.sh`` and
  ``backend-ci.yml`` seed only ``get_tenant_context``).

* ``set_admin_context`` has migration owners (v051/v056), but both CREATEs are
  UNQUALIFIED, and on a fresh sequential chain run they resolve into the
  ``fsma`` schema (a search_path leak inside those long-applied revisions --
  verified: a clean database migrated to 8b2f4e6a9c31 has ONLY
  ``fsma.set_admin_context``). The app calls the function unqualified on a
  default search_path (``services/admin/app/models.py::set_admin_context``:
  ``SELECT set_admin_context(:is_admin)``), so on fresh databases name
  resolution only worked because init_db re-created a ``public`` copy at every
  boot. This migration pins the canonical body at ``public.set_admin_context``
  explicitly. The stray ``fsma`` copy is left alone: nothing references it
  schema-qualified, and v051/v056 are long-applied revisions that must not be
  rebased (see the v097 Ordering note).

``get_tenant_context`` needs nothing here: the pre-baseline seed guarantees a
``public`` copy on every database that can run the chain at all, and v097
pinned its canonical body.

Under the #2461 least-privilege cutover that boot DDL fails with
InsufficientPrivilege (observed in prod as the non-fatal
``admin_database_init_skipped`` WARN on every boot of deploy 51ae1bb3), so the
runtime path is being deleted alongside this migration. Deleting it without
this migration would strand any fresh least-privilege database with no
``set_tenant_context`` at all -- and the function is a live runtime dependency:
``services/ingestion/regengine_ingestion/storage/database.py``
(``DatabaseManager.set_tenant_context``) executes ``SELECT set_tenant_context(%s)``
on its psycopg connections, and the manual RLS verification scripts under
``services/admin/migrations/verify_rls*.sql`` call it too.

The body is byte-for-byte the one init_db emitted: session-scoped
``set_config('app.tenant_id', tenant_id, false)``. Session scope (not SET
LOCAL) is deliberate and load-bearing -- the #1381 pool-bleed mitigation
(the ``checkout`` listener in services/admin/app/database.py) resets exactly
this session-level GUC, and DatabaseManager callers rely on the context
surviving across statements on the same connection. Do not "fix" it to
transaction-local here.

Like v097, the replace is unconditional and DROP-free: CREATE OR REPLACE with
an unchanged signature preserves the pg_proc OID, so nothing that references
the function by OID is disturbed, and environments where the boot DDL already
created it (prod, dev, CI) converge to the same state as a fresh database. If
a function of the same name exists with a non-text argument, this migration
REFUSES rather than silently adding an overload -- two candidates would make
the untyped ``SELECT set_tenant_context($1)`` call sites ambiguous.

Revision ID: 2aa607050c84 (random hex, not a credential)
Revises: 8b2f4e6a9c31
Create Date: 2026-07-26
"""

from typing import Sequence, Union

from alembic import op

revision: str = "2aa607050c84"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "8b2f4e6a9c31"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ADOPT_SET_TENANT_CONTEXT = """
DO $mig$
DECLARE
    v_schema  text;
    v_argtype text;
BEGIN
    SELECT n.nspname, format_type(p.proargtypes[0], NULL)
      INTO v_schema, v_argtype
      FROM pg_proc p
      JOIN pg_namespace n ON p.pronamespace = n.oid
     WHERE p.proname = 'set_tenant_context'
       AND p.pronargs = 1
       AND n.nspname = ANY (current_schemas(true))
     ORDER BY array_position(current_schemas(true), n.nspname)
     LIMIT 1;

    IF v_argtype IS NOT NULL AND v_argtype <> 'text' THEN
        -- Unknown shape. CREATE OR REPLACE with (tenant_id text) would ADD an
        -- overload beside it, making every untyped SELECT set_tenant_context($1)
        -- call ambiguous. No RegEngine code path has ever emitted a non-text
        -- variant, so this branch is defensive: refuse loudly.
        RAISE EXCEPTION
            'set_tenant_context(%) exists (expected text) - refusing to add an overload',
            v_argtype;
    END IF;

    -- Unconditional: CREATE OR REPLACE with an unchanged signature preserves
    -- the pg_proc OID (v097 precedent -- no DROP, no CASCADE). VOLATILE
    -- (the default) is required: the body is a set_config side effect.
    EXECUTE format($ddl$
        CREATE OR REPLACE FUNCTION %I.set_tenant_context(tenant_id text)
        RETURNS void AS $fn$
        BEGIN
            PERFORM set_config('app.tenant_id', tenant_id, false);
        END;
        $fn$ LANGUAGE plpgsql
    $ddl$, COALESCE(v_schema, 'public'));
END
$mig$;
"""


# The v056 canonical body, pinned at an EXPLICIT public qualification so the
# app's unqualified call sites resolve it on a default search_path. In
# environments where boot DDL already created public.set_admin_context (prod,
# dev, CI) this replaces it in place -- signature unchanged, pg_proc OID
# preserved, no DROP. The WARNING is advisory only: RLS policies also require
# current_user = 'regengine_sysadmin', so the GUC alone can never elevate.
_PIN_PUBLIC_SET_ADMIN_CONTEXT = """
CREATE OR REPLACE FUNCTION public.set_admin_context(p_is_sysadmin boolean)
RETURNS void AS $fn$
BEGIN
    IF p_is_sysadmin AND current_user != 'regengine_sysadmin' THEN
        RAISE WARNING 'set_admin_context(true) called by role "%" - '
                       'RLS bypass requires regengine_sysadmin role.', current_user;
    END IF;
    PERFORM set_config('regengine.is_sysadmin', p_is_sysadmin::text, false);
END;
$fn$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_ADOPT_SET_TENANT_CONTEXT)
    op.execute(_PIN_PUBLIC_SET_ADMIN_CONTEXT)


def downgrade() -> None:
    """Intentionally a no-op.

    On every database that has ever run the app, both functions predate this
    revision (boot DDL created them), so dropping them here would not restore
    the previous state -- it would break the running app: ingestion's storage
    path calls set_tenant_context at runtime and the admin models call
    set_admin_context. Environments that genuinely never had them are fresh
    databases where a downgrade below v099 has nothing to preserve.
    """
