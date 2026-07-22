"""v096 -- system-context RLS arm for queue/audit metadata (#2461).

Background
----------
Issue #2461 (least-privilege ``regengine`` role cutover) requires every
DB access path to carry tenant context. Two surfaces are CROSS-TENANT by
design and can never satisfy a per-tenant ``app.tenant_id`` GUC:

  1. ``fsma.task_queue`` queue mechanics — the worker claim scan
     (``FOR UPDATE SKIP LOCKED`` with weighted fair queuing across
     tenants, ADR #1644), stale-lock release, state transitions, the
     30-day purge, and the sysadmin summary/replay operator views.
  2. ``fsma.fsma_audit_trail`` chain operations — the audit checksum
     chain is GLOBAL (each entry links to the previous entry's checksum
     regardless of tenant), so chain bootstrap/verification reads are
     cross-tenant by design. Decision recorded here: keep the global
     chain and grant these two tables the system arm rather than
     re-architecting to per-tenant chains.

The existing policy families offer no usable escape for an in-process
worker: family-(1) policies (v056/v074/v090 ``_TENANT_POLICY``) require
BOTH ``regengine.is_sysadmin`` AND ``current_user =
'regengine_sysadmin'`` — a second DATABASE_URL/engine in the same
process, plus audit.sysadmin_access_log flooding at the worker's
500ms-2s poll cadence. Family-(2) policies (plain
``tenant_id = get_tenant_context()``, including task_queue's v090
policy) have NO escape at all — only BYPASSRLS works, which is exactly
what #2461 removes. SECURITY DEFINER claim functions are the cleanest
long-term shape but require rewriting ~12 claim/complete/heartbeat
statements across two worker implementations — deferred as a hardening
follow-up.

This migration replaces the policies on EXACTLY these two
system-metadata tables with a two-arm form driven by an unprivileged
``regengine.system_context`` GUC that ``shared.tenant_context``'s
system_scope() / Engine begin-hook set transaction-scoped.

CRITICAL — CASE form, not OR
----------------------------
The predicate MUST be::

    CASE WHEN current_setting('regengine.system_context', true) = 'true'
         THEN true
         ELSE tenant_id = get_tenant_context()
    END

and NOT ``current_setting(...) = 'true' OR tenant_id =
get_tenant_context()``. Postgres does not guarantee OR operand
evaluation order, and ``get_tenant_context()`` RAISES when
``app.tenant_id`` is unset — an OR-form system arm could still blow up
on a system-context-only transaction. CASE guarantees lazy evaluation
of the ELSE branch. (The existing family-(1) sysadmin-arm policies
carry this same latent OR-ordering hazard — out of scope here; tracked
as a follow-up.)

Security tradeoff (documented, accepted)
----------------------------------------
``regengine.system_context`` is an unprivileged GUC — any connection
could set it. The blast radius is deliberately limited to queue
metadata and the audit-trail chain (no tenant DATA tables get the
arm — maintenance jobs touching those use per-tenant iteration), and
an attacker who can execute arbitrary SQL could equally set
``app.tenant_id``. RLS here defends against application bugs, not SQL
injection. The SECURITY DEFINER claim-function refactor is the
hardening follow-up.

Idempotent: DROP-IF-EXISTS + CREATE, to_regclass-guarded. Downgrade
restores each table's prior live policy text verbatim (v090's
fail-hard predicate for task_queue; v049/v067's text-compare for
fsma_audit_trail).

Revision ID: c3a51e2f7b90
Revises: c7a1e5f2b9d4
Create Date: 2026-07-15 (rebased onto v095 c7a1e5f2b9d4 on 2026-07-21)
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3a51e2f7b90"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c7a1e5f2b9d4"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# CASE form is mandatory — see module docstring. get_tenant_context()
# raises on an unset app.tenant_id GUC; CASE guarantees the ELSE branch
# is not evaluated when the system arm matches.
_SYSTEM_ARM_PREDICATE = """\
CASE WHEN current_setting('regengine.system_context', true) = 'true'
     THEN true
     ELSE tenant_id = get_tenant_context()
END"""

# (table, policy_name) — the ONLY two tables that get the system arm.
_SYSTEM_ARM_TABLES = (
    ("task_queue", "tenant_isolation_tasks"),
    ("fsma_audit_trail", "tenant_isolation_audit"),
)


def _install_system_arm(table: str, policy: str) -> str:
    fq = f"fsma.{table}"
    return f"""
        DO $mig$
        BEGIN
            IF to_regclass('{fq}') IS NULL THEN
                RETURN;
            END IF;

            EXECUTE 'ALTER TABLE {fq} ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE {fq} FORCE ROW LEVEL SECURITY';

            EXECUTE 'DROP POLICY IF EXISTS {policy} ON {fq}';
            EXECUTE $pol$
                CREATE POLICY {policy}
                    ON {fq}
                    FOR ALL
                    USING ({_SYSTEM_ARM_PREDICATE})
                    WITH CHECK ({_SYSTEM_ARM_PREDICATE})
            $pol$;
        END
        $mig$;
    """


def upgrade() -> None:
    for table, policy in _SYSTEM_ARM_TABLES:
        op.execute(_install_system_arm(table, policy))


def downgrade() -> None:
    # Restore the prior live policy text VERBATIM per table.
    #
    # task_queue: v090 (a128f7f95db8) fail-hard re-assertion.
    op.execute(
        """
        DO $mig$
        BEGIN
            IF to_regclass('fsma.task_queue') IS NULL THEN
                RETURN;
            END IF;

            EXECUTE 'ALTER TABLE fsma.task_queue ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE fsma.task_queue FORCE ROW LEVEL SECURITY';
            EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_tasks ON fsma.task_queue';
            EXECUTE 'CREATE POLICY tenant_isolation_tasks ON fsma.task_queue '
                    'USING (tenant_id = get_tenant_context())';
        END
        $mig$;
        """
    )

    # fsma_audit_trail: v049 text-compare, recreated verbatim by v067.
    op.execute(
        """
        DO $mig$
        BEGIN
            IF to_regclass('fsma.fsma_audit_trail') IS NULL THEN
                RETURN;
            END IF;

            EXECUTE 'ALTER TABLE fsma.fsma_audit_trail ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE fsma.fsma_audit_trail FORCE ROW LEVEL SECURITY';
            EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_audit ON fsma.fsma_audit_trail';
            EXECUTE $pol$
                CREATE POLICY tenant_isolation_audit ON fsma.fsma_audit_trail
                USING (tenant_id = get_tenant_context())
            $pol$;
        END
        $mig$;
        """
    )
