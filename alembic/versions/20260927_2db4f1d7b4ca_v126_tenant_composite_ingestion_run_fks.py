"""v126 — evidence rows may only reference an ingestion run of their own tenant.

``fsma.traceability_events``, ``fsma.manifest_records`` and
``fsma.manifest_blobs`` referenced ``fsma.ingestion_runs(id)`` through
single-column keys, so a row written under tenant A could name tenant B's
ingestion run. RLS still pins each row's own ``tenant_id`` to its writer, so
this was an integrity gap, not a read leak: an event exported for tenant A
could cite a run A cannot see.

Each single-column key is replaced by
``(ingestion_run_id, tenant_id) REFERENCES fsma.ingestion_runs (id, tenant_id)``
backed by the v079 unique index ``ux_ingestion_runs_id_tenant`` -- the shape
v079/v080 already use for receipts and agent artifacts. ON DELETE actions are
kept. Runtime FK checks run as the referenced table's owner with RLS
bypassed, so no runtime grant changes (v111 inventory untouched).

Validation runs as the schema owner, which is NOBYPASSRLS outside a
superuser deploy. PostgreSQL's bulk FK check applies that owner's RLS
policies under FORCE, so it raises ("app.tenant_id not set") or, with a
tenant context set, checks one tenant and passes the rest unchecked. The
child and ``ingestion_runs`` are therefore NO FORCE for this transaction only
(the v116/v120 pattern): ALTER holds ACCESS EXCLUSIVE until commit, nobody
observes the relaxed state, and any failure rolls it back.

Rows already misattached make the upgrade refuse; it never edits evidence.
List them from a superuser or BYPASSRLS session -- the owner under FORCE RLS
sees nothing -- with ``PREDEPLOY_CHECK_SQL`` below.

Downgrade restores the exact single-column keys (names, ON DELETE actions).

Revision ID: 2db4f1d7b4ca
Revises: 22a278f6dc78
Create Date: 2026-09-27
"""

from contextlib import contextmanager

import sqlalchemy as sa

from alembic import op

revision = "2db4f1d7b4ca"  # pragma: allowlist secret
down_revision = "22a278f6dc78"  # pragma: allowlist secret
branch_labels = None
depends_on = None

# Every ALTER below waits at most this long for its lock, so a long-running
# reader fails the deploy instead of queueing all traffic behind it.
LOCK_TIMEOUT = "10s"

# child table -> (row id column, ON DELETE clause, pre-v126 FK name)
CHILDREN = {
    "traceability_events": ("event_id", "", "traceability_events_ingestion_run_id_fkey"),
    "manifest_records": ("id", " ON DELETE CASCADE", "manifest_records_ingestion_run_id_fkey"),
    "manifest_blobs": ("ingestion_run_id", " ON DELETE CASCADE", "manifest_blobs_ingestion_run_id_fkey"),
}


def composite_fk_name(table: str) -> str:
    return f"fk_{table}_run_tenant"


def _misattached_sql(table: str, id_column: str) -> str:
    # Exactly the rows the composite key rejects: MATCH SIMPLE skips a NULL
    # run, and tenant_id is NOT NULL on every child.
    return f"""SELECT 'fsma.{table}' AS table_name, c.{id_column}::text AS row_id,
       c.tenant_id AS row_tenant_id, c.ingestion_run_id, r.tenant_id AS run_tenant_id
FROM fsma.{table} c
LEFT JOIN fsma.ingestion_runs r ON r.id = c.ingestion_run_id
WHERE c.ingestion_run_id IS NOT NULL
  AND (r.id IS NULL OR r.tenant_id <> c.tenant_id)"""


PREDEPLOY_CHECK_SQL = (
    "\nUNION ALL\n".join(_misattached_sql(table, spec[0]) for table, spec in CHILDREN.items()) + "\nORDER BY 1, 2;"
)


@contextmanager
def _owner_sees_all_rows():
    """Let a NOBYPASSRLS owner validate keys over every tenant's rows.

    Only tables that were FORCE are switched, and only they are restored. The
    lock_timeout is transaction-local and put back afterwards because Alembic
    runs every pending revision in this one transaction.
    """
    conn = op.get_bind()
    previous_lock_timeout = conn.execute(sa.text("SELECT current_setting('lock_timeout')")).scalar_one()
    conn.execute(sa.text("SELECT set_config('lock_timeout', :value, true)"), {"value": LOCK_TIMEOUT})
    regclasses = ", ".join(f"'fsma.{table}'::regclass" for table in ("ingestion_runs", *CHILDREN))
    forced = (
        conn.execute(
            sa.text(
                f"SELECT relname FROM pg_class WHERE oid IN ({regclasses}) AND relforcerowsecurity ORDER BY relname"
            )
        )
        .scalars()
        .all()
    )
    for table in forced:
        # Names come only from the fixed regclass list above.
        conn.execute(sa.text(f"ALTER TABLE fsma.{table} NO FORCE ROW LEVEL SECURITY"))
    yield conn
    for table in forced:
        conn.execute(sa.text(f"ALTER TABLE fsma.{table} FORCE ROW LEVEL SECURITY"))
    conn.execute(sa.text("SELECT set_config('lock_timeout', :value, true)"), {"value": previous_lock_timeout})


def upgrade() -> None:
    with _owner_sees_all_rows() as conn:
        misattached = {}
        for table, (id_column, _, _) in CHILDREN.items():
            count = conn.execute(sa.text(f"SELECT count(*) FROM ({_misattached_sql(table, id_column)}) m")).scalar_one()
            if count:
                misattached[f"fsma.{table}"] = count
        if misattached:
            counts = ", ".join(f"{table}={count}" for table, count in misattached.items())
            raise RuntimeError(
                f"v126 refused: rows reference an ingestion run of a different tenant ({counts}). "
                "No row was changed. List them from a superuser or BYPASSRLS session (the schema "
                "owner under FORCE RLS sees no rows), repair each one, then redeploy:\n" + PREDEPLOY_CHECK_SQL
            )
        for table, (_, on_delete, legacy_name) in CHILDREN.items():
            conn.execute(
                sa.text(
                    f"""ALTER TABLE fsma.{table}
                        DROP CONSTRAINT {legacy_name},
                        ADD CONSTRAINT {composite_fk_name(table)}
                            FOREIGN KEY (ingestion_run_id, tenant_id)
                            REFERENCES fsma.ingestion_runs (id, tenant_id){on_delete}"""
                )
            )


def downgrade() -> None:
    with _owner_sees_all_rows() as conn:
        for table, (_, on_delete, legacy_name) in CHILDREN.items():
            conn.execute(
                sa.text(
                    f"""ALTER TABLE fsma.{table}
                        DROP CONSTRAINT {composite_fk_name(table)},
                        ADD CONSTRAINT {legacy_name}
                            FOREIGN KEY (ingestion_run_id)
                            REFERENCES fsma.ingestion_runs (id){on_delete}"""
                )
            )
