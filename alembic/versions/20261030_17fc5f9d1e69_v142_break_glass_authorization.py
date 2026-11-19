"""v142 — authorize the fsma.allow_mutation break-glass by role, not by GUC alone.

Revision ID: 17fc5f9d1e69
Revises: 08c7cf36ddbe
Create Date: 2026-10-30

Three append-only guards (v078/v107 ``fsma.prevent_cte_mutation`` on
``fsma.cte_events`` and ``fsma.hash_chain``, v095 ``fsma.prevent_patch_*`` on
``fsma.correction_patches``, v141 ``fsma.prevent_traceability_event_*`` on
``fsma.traceability_events``) let any statement through as soon as the
transaction-local GUC ``fsma.allow_mutation`` reads ``'true'``. PostgreSQL
lets every role ``SET`` an unreserved two-part GUC, so a session holding the
runtime role (``regengine``, which v111 grants UPDATE or DELETE on these
tables) could arm the break-glass itself and rewrite evidence. The GUC was
an intent flag, never an authorization.

This revision keeps the GUC as the intent flag and adds the authorization:

* ``fsma.break_glass_authorized(oid)`` (SECURITY INVOKER) is true only when
  the GUC is set AND the invoking role is a superuser or a member of the
  guarded table's owner (the migration role; the runtime roles are never
  members of it). Operator and migration-credential sessions keep the
  documented ``SET LOCAL fsma.allow_mutation = 'true'`` contract; the
  runtime roles lose it.
* The retention purge (``services/scheduler/service.py``) is the one
  production mutation that ran as the runtime role. It now arms a narrow
  path instead: ``fsma.arm_retention_purge(tenant_id, min_age)`` (SECURITY
  DEFINER, owner-only table ``fsma.break_glass_arms``) records the current
  transaction, tenant, table and minimum age; ``fsma.prevent_cte_mutation``
  then permits a DELETE on ``fsma.cte_events`` only for a row of that tenant
  older than that minimum age (``fsma.retention_purge_permits``). The floor
  is the FSMA 204 24-month retention (``interval '730 days'``). Nothing else
  is reachable through the arm: no UPDATE, no other table, no younger row.
* The trigger bodies are otherwise unchanged (same allowlist, same messages,
  same SQLSTATE), so every behavioural test of v095/v107/v141 still passes
  when it runs as the superuser the CI databases use.

Grants: the runtime roles need EXECUTE on the two read-only helpers (the
triggers call them as the invoking role) and on the arm function. v111's
closed inventory carries the same three grants behind ``to_regprocedure``
guards so ``scripts/apply_runtime_role_cutover.py`` keeps them after every
deploy. ``fsma.break_glass_arms`` itself is owner-only (FORCE RLS with the
standard tenant predicate; the runtime roles hold no privilege on it).

Downgrade restores the GUC-only bodies of all five trigger functions, drops
the helpers and the arm table. The scheduler change in the same change set
calls ``fsma.arm_retention_purge``; a database downgraded past this revision
needs the previous scheduler build.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "17fc5f9d1e69"  # pragma: allowlist secret
down_revision = "08c7cf36ddbe"  # pragma: allowlist secret
branch_labels = None
depends_on = None

ARM_TABLE = "fsma.break_glass_arms"
ARM_POLICY = "tenant_isolation_break_glass_arms"
AUTHORIZED_FN = "fsma.break_glass_authorized"
PERMITS_FN = "fsma.retention_purge_permits"
ARM_FN = "fsma.arm_retention_purge"
RETENTION_FLOOR = "interval '730 days'"

# The exact GUC test every guarded trigger function carried, and what
# replaces it. The replacement is applied by string substitution on the
# v141 bodies so the allowlist logic stays byte-identical to v141.
GUC_CHECK = "IF current_setting('fsma.allow_mutation', true) = 'true' THEN"
AUTH_CHECK = f"IF {AUTHORIZED_FN}(TG_RELID) THEN"

_V141_FILE = Path(__file__).with_name("20261028_08c7cf36ddbe_v141_traceability_events_append_only.py")


def _load_v141():
    spec = importlib.util.spec_from_file_location("regengine_v141_bodies", _V141_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load v141 trigger bodies from {_V141_FILE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _with_authorization(sql: str) -> str:
    if sql.count(GUC_CHECK) != 1:
        raise RuntimeError("expected exactly one break-glass GUC check in the trigger body")
    return sql.replace(GUC_CHECK, AUTH_CHECK)


_ENSURE_ROLES_SQL = """
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

_ARM_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {ARM_TABLE} (
    txid        BIGINT      NOT NULL,
    relid       OID         NOT NULL,
    tenant_id   UUID        NOT NULL,
    purpose     TEXT        NOT NULL,
    min_age     INTERVAL    NOT NULL,
    armed_by    TEXT        NOT NULL,
    armed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (txid, relid, tenant_id)
);
COMMENT ON TABLE {ARM_TABLE} IS
    'v142: transaction-scoped break-glass arms written only by SECURITY DEFINER helpers; read by the append-only triggers';
ALTER TABLE {ARM_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {ARM_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {ARM_POLICY} ON {ARM_TABLE};
CREATE POLICY {ARM_POLICY} ON {ARM_TABLE}
    FOR ALL TO PUBLIC
    USING (tenant_id = get_tenant_context())
    WITH CHECK (tenant_id = get_tenant_context());
REVOKE ALL ON TABLE {ARM_TABLE} FROM PUBLIC, regengine, regengine_sysadmin;
"""

_AUTHORIZED_FN_SQL = f"""
CREATE OR REPLACE FUNCTION {AUTHORIZED_FN}(p_relid oid)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    owner_oid oid;
BEGIN
    -- Intent flag first: without it nothing is authorized, whoever asks.
    IF current_setting('fsma.allow_mutation', true) IS DISTINCT FROM 'true' THEN
        RETURN false;
    END IF;
    -- Superusers (the CI and scratch databases) keep the GUC-only contract.
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = current_user AND rolsuper) THEN
        RETURN true;
    END IF;
    -- So does the owner of the guarded table (the migration role) and its
    -- members. The runtime roles are never members of it.
    SELECT relowner INTO owner_oid FROM pg_catalog.pg_class WHERE oid = p_relid;
    IF owner_oid IS NULL THEN
        RETURN false;
    END IF;
    RETURN pg_catalog.pg_has_role(current_user, owner_oid, 'MEMBER');
END;
$$;
REVOKE ALL ON FUNCTION {AUTHORIZED_FN}(oid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {AUTHORIZED_FN}(oid) TO regengine, regengine_sysadmin;
"""

_PERMITS_FN_SQL = f"""
CREATE OR REPLACE FUNCTION {PERMITS_FN}(p_relid oid, p_tenant_id uuid, p_age_anchor timestamptz)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = fsma, public, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1
          FROM {ARM_TABLE} AS arm
         WHERE arm.txid = txid_current()
           AND arm.relid = p_relid
           AND arm.tenant_id = p_tenant_id
           AND arm.purpose = 'retention_purge'
           AND p_age_anchor IS NOT NULL
           AND p_age_anchor < now() - arm.min_age
    );
$$;
REVOKE ALL ON FUNCTION {PERMITS_FN}(oid, uuid, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {PERMITS_FN}(oid, uuid, timestamptz) TO regengine, regengine_sysadmin;
"""

_ARM_FN_SQL = f"""
CREATE OR REPLACE FUNCTION {ARM_FN}(p_tenant_id uuid, p_min_age interval DEFAULT interval '1095 days')
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = fsma, public, pg_temp
AS $$
BEGIN
    IF p_tenant_id IS NULL THEN
        RAISE EXCEPTION 'arm_retention_purge: tenant_id is required'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_min_age IS NULL OR p_min_age < {RETENTION_FLOOR} THEN
        RAISE EXCEPTION 'arm_retention_purge: min_age % is below the FSMA 204 24-month retention floor', p_min_age
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_tenant_id IS DISTINCT FROM get_tenant_context() THEN
        RAISE EXCEPTION 'arm_retention_purge: tenant % is not the current tenant context', p_tenant_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    -- Arms are keyed by transaction id and never reused; prune this tenant's
    -- stale rows so the table does not grow with every sweep.
    DELETE FROM {ARM_TABLE} WHERE tenant_id = p_tenant_id AND armed_at < now() - interval '1 day';
    INSERT INTO {ARM_TABLE} (txid, relid, tenant_id, purpose, min_age, armed_by)
    VALUES (txid_current(), 'fsma.cte_events'::regclass, p_tenant_id, 'retention_purge', p_min_age, session_user::text)
    ON CONFLICT (txid, relid, tenant_id)
    DO UPDATE SET min_age = EXCLUDED.min_age, armed_by = EXCLUDED.armed_by, armed_at = now();
    RAISE WARNING 'retention purge armed. table=fsma.cte_events tenant=% min_age=% session_user=%',
        p_tenant_id, p_min_age, session_user;
END;
$$;
REVOKE ALL ON FUNCTION {ARM_FN}(uuid, interval) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {ARM_FN}(uuid, interval) TO regengine, regengine_sysadmin;
"""

# v078/v107 body with the authorization check and the retention-purge path.
# The function is attached to fsma.cte_events and fsma.hash_chain; only
# cte_events carries tenant_id and ingested_at, so the purge branch is
# limited to it by name before OLD's fields are touched.
_CTE_MUTATION_FN_V142 = f"""
CREATE OR REPLACE FUNCTION fsma.prevent_cte_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF {AUTHORIZED_FN}(TG_RELID) THEN
        IF TG_OP = 'UPDATE' THEN
            RETURN NEW;
        END IF;
        RETURN OLD;
    END IF;
    IF TG_OP = 'DELETE'
       AND TG_TABLE_SCHEMA = 'fsma' AND TG_TABLE_NAME = 'cte_events'
       AND {PERMITS_FN}(TG_RELID, OLD.tenant_id, OLD.ingested_at) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION
        'CTE records are append-only (FDA 21 CFR 1.1455). Set fsma.allow_mutation=true for authorized corrections. Table: %, Operation: %',
        TG_TABLE_NAME, TG_OP;
END;
$$;
"""

# Exact v107 body, restored on downgrade.
_CTE_MUTATION_FN_V107 = """
CREATE OR REPLACE FUNCTION fsma.prevent_cte_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('fsma.allow_mutation', true) = 'true' THEN
        IF TG_OP = 'UPDATE' THEN
            RETURN NEW;
        END IF;
        RETURN OLD;
    END IF;
    RAISE EXCEPTION
        'CTE records are append-only (FDA 21 CFR 1.1455). Set fsma.allow_mutation=true for authorized corrections. Table: %, Operation: %',
        TG_TABLE_NAME, TG_OP;
END;
$$;
"""

# Exact v095 bodies, restored on downgrade; the v142 versions substitute the
# authorization check for the GUC test and change nothing else.
_PATCH_MUTATION_FN_V095 = """
CREATE OR REPLACE FUNCTION fsma.prevent_patch_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('fsma.allow_mutation', true) = 'true' THEN
        RAISE WARNING
            'correction_patches modification via break-glass. op=% user=% row_id=%',
            TG_OP, current_user, COALESCE(NEW.id::text, OLD.id::text);
        RETURN COALESCE(NEW, OLD);
    END IF;
    RAISE EXCEPTION
        'correction_patches is append-only. Operation % rejected. Set fsma.allow_mutation=true for authorized break-glass.',
        TG_OP
        USING ERRCODE = 'check_violation';
END;
$$;
"""

_PATCH_TRUNCATE_FN_V095 = """
CREATE OR REPLACE FUNCTION fsma.prevent_patch_truncate()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('fsma.allow_mutation', true) = 'true' THEN
        RAISE WARNING 'correction_patches TRUNCATE via break-glass. user=%', current_user;
        RETURN NULL;
    END IF;
    RAISE EXCEPTION
        'correction_patches is append-only. TRUNCATE rejected. Set fsma.allow_mutation=true for authorized break-glass.'
        USING ERRCODE = 'check_violation';
END;
$$;
"""

_PATCH_MUTATION_FN_V142 = _with_authorization(_PATCH_MUTATION_FN_V095)
_PATCH_TRUNCATE_FN_V142 = _with_authorization(_PATCH_TRUNCATE_FN_V095)

_DROP_SQL = f"""
DROP FUNCTION IF EXISTS {ARM_FN}(uuid, interval);
DROP FUNCTION IF EXISTS {PERMITS_FN}(oid, uuid, timestamptz);
DROP FUNCTION IF EXISTS {AUTHORIZED_FN}(oid);
DROP TABLE IF EXISTS {ARM_TABLE};
"""


def upgrade_statements() -> list[str]:
    """The idempotent upgrade, statement by statement.

    Exposed so the behavioural test can re-apply it on a database whose
    function bodies an earlier suite rewrote (the v141 idempotency test
    executes v141's own bodies directly, which is correct for v141 and
    would otherwise leave this revision's bodies missing at head).
    """
    v141 = _load_v141()
    return [
        _ENSURE_ROLES_SQL,
        _ARM_TABLE_SQL,
        _AUTHORIZED_FN_SQL,
        _PERMITS_FN_SQL,
        _ARM_FN_SQL,
        # CREATE OR REPLACE keeps every existing trigger bound to the
        # function, so no trigger is dropped or re-created and no table
        # lock beyond the function replacement is taken.
        _CTE_MUTATION_FN_V142,
        _PATCH_MUTATION_FN_V142,
        _PATCH_TRUNCATE_FN_V142,
        _with_authorization(v141._ROW_FUNCTION_SQL),
        _with_authorization(v141._TRUNCATE_FUNCTION_SQL),
    ]


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '10s'")
    for statement in upgrade_statements():
        op.execute(statement)


def downgrade() -> None:
    v141 = _load_v141()
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.execute(v141._ROW_FUNCTION_SQL)
    op.execute(v141._TRUNCATE_FUNCTION_SQL)
    op.execute(_PATCH_MUTATION_FN_V095)
    op.execute(_PATCH_TRUNCATE_FN_V095)
    op.execute(_CTE_MUTATION_FN_V107)
    op.execute(_DROP_SQL)
