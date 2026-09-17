"""v124: point the Input TLCs rule at the field production payloads carry.

Finding from the 2026-09-02 production-grade data run (a real openFDA recall
reconstructed as a full CTE chain and ingested through the live webhook path):
"Transformation: Input TLCs Required" (critical) inspected
``kdes.input_traceability_lot_codes`` / ``kdes.input_tlcs`` -- names that no
production payload populates. The canonical webhook normalizer promotes the
top-level ``input_traceability_lot_codes`` into ``kdes.input_lot_codes`` and
the CSV template writes that same key, so every compliant transformation
event false-failed the lot-linkage rule. ``kdes.input_lot_codes`` becomes the
primary field; the old names stay as alternates. The seed in
``services/shared/rules/seeds.py`` changes in the same commit; this revision
brings already-seeded tenants in line (``seed_rule_definitions`` is
insert-only).

Same shape as v120: only rows still carrying the old logic change, the rule
version increments, an audit row records old and new values, repeating
upgrade is a no-op, and downgrade restores only rows this migration changed.

Revision ID: 26d215418784
Revises: e9f2a4c71b05
Create Date: 2026-09-17
"""

import json
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import op

revision = "26d215418784"  # pragma: allowlist secret
down_revision = "e9f2a4c71b05"  # pragma: allowlist secret
branch_labels = None
depends_on = None

TITLE = "Transformation: Input TLCs Required"
CHANGED_BY = "migration_v124"
OLD_LOGIC = {
    "type": "multi_field_presence",
    "field": "kdes.input_traceability_lot_codes",
    "params": {"fields": ["kdes.input_traceability_lot_codes", "kdes.input_tlcs"]},
}
NEW_LOGIC = {
    "type": "multi_field_presence",
    "field": "kdes.input_lot_codes",
    "params": {
        "fields": [
            "kdes.input_lot_codes",
            "kdes.input_traceability_lot_codes",
            "kdes.input_tlcs",
        ]
    },
}


def _input_tlc_rule(reverse: bool = False) -> None:
    old, new = OLD_LOGIC, NEW_LOGIC
    if reverse:
        old, new = new, old
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("""
        WITH candidates AS (
        SELECT rule_id, rule_version FROM fsma.rule_definitions
        WHERE title = :title
          AND evaluation_logic = CAST(:old AS jsonb)
          AND retired_date IS NULL
          AND rule_version = (SELECT MAX(r.rule_version) FROM fsma.rule_definitions r
                              WHERE r.title = :title AND r.retired_date IS NULL)
          AND (NOT :reverse OR EXISTS (
              SELECT 1 FROM fsma.rule_audit_log a
              WHERE a.rule_id = rule_definitions.rule_id AND a.changed_by = :changed_by
                AND a.new_values->'evaluation_logic' = CAST(:old AS jsonb)
                AND (a.new_values->>'rule_version')::integer = rule_definitions.rule_version
          ))
        FOR UPDATE
        )
        UPDATE fsma.rule_definitions d
        SET evaluation_logic = CAST(:new AS jsonb), updated_at = NOW(),
            rule_version = (SELECT MAX(r.rule_version) + 1 FROM fsma.rule_definitions r WHERE r.title = d.title)
        FROM candidates c WHERE d.rule_id = c.rule_id
        RETURNING d.rule_id, d.rule_version, c.rule_version
    """),
        {
            "title": TITLE,
            "old": json.dumps(old),
            "new": json.dumps(new),
            "reverse": reverse,
            "changed_by": CHANGED_BY,
        },
    ).fetchall()
    for rule_id, version, old_version in rows:
        conn.execute(
            sa.text("""
            INSERT INTO fsma.rule_audit_log (rule_id, action, old_values, new_values, changed_by)
            VALUES (:rule_id, 'updated', CAST(:old AS jsonb), CAST(:new AS jsonb), :changed_by)
        """),
            {
                "rule_id": rule_id,
                "old": json.dumps({"evaluation_logic": old, "rule_version": old_version}),
                "new": json.dumps({"evaluation_logic": new, "rule_version": version}),
                "changed_by": CHANGED_BY,
            },
        )


@contextmanager
def _rule_owner_writes():
    """Scope owner visibility to this transaction; runtime policies stay intact.

    Mirrors v120: the dedicated owner has NOBYPASSRLS. ALTER takes a table
    lock until commit, so no other session can observe the temporary NO FORCE
    state, and a failure rolls back both the data and the RLS changes.
    """
    conn = op.get_bind()
    forced = (
        conn.execute(
            sa.text("""SELECT relname FROM pg_class
                   WHERE oid IN ('fsma.rule_definitions'::regclass,
                                 'fsma.rule_audit_log'::regclass)
                     AND relforcerowsecurity ORDER BY relname""")
        )
        .scalars()
        .all()
    )
    for table in forced:
        # Names come only from the two fixed regclass values above.
        conn.execute(sa.text(f"ALTER TABLE fsma.{table} NO FORCE ROW LEVEL SECURITY"))
    yield
    for table in forced:
        conn.execute(sa.text(f"ALTER TABLE fsma.{table} FORCE ROW LEVEL SECURITY"))


def upgrade():
    with _rule_owner_writes():
        _input_tlc_rule()


def downgrade():
    with _rule_owner_writes():
        _input_tlc_rule(reverse=True)
