"""v120: correct runtime rule citations with versioned audit evidence (#3035).

Only rows with a known historical citation are changed. Custom citations remain
untouched. Every changed rule increments its version and records old/new values;
past evaluations are immutable. Repeating upgrade is a no-op. Downgrade restores
only rows still carrying this migration's citation and also records an audit row.
"""

import json
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import op

revision = "c6a120b4e901"  # pragma: allowlist secret
down_revision = "8b866e4b4798"  # pragma: allowlist secret
branch_labels = None
depends_on = None

CITATION_CORRECTIONS = {
    "Receiving: TLC Source Reference Required": ("21 CFR §1.1345(b)(7)", "21 CFR §1.1345(a)(7)"),
    "Receiving: Immediate Previous Source Required": ("21 CFR §1.1345(b)(5)", "21 CFR §1.1345(a)(4)"),
    "Receiving: Reference Document Required": ("21 CFR §1.1345(b)(6)", "21 CFR §1.1345(a)(8)"),
    "Receiving: Receive Date Required": ("21 CFR §1.1345(b)(2)", "21 CFR §1.1345(a)(6)"),
    "Shipping: Ship-From Location Required": ("21 CFR §1.1340(b)(3)", "21 CFR §1.1340(a)(5)"),
    "Shipping: Ship-To Location Required": ("21 CFR §1.1340(b)(4)", "21 CFR §1.1340(a)(4)"),
    "Shipping: Ship Date Required": ("21 CFR §1.1340(b)(2)", "21 CFR §1.1340(a)(6)"),
    "Shipping: Reference Document Required": ("21 CFR §1.1340(b)(6)", "21 CFR §1.1340(a)(8)"),
    "Harvesting: Harvest Date Required": ("21 CFR §1.1327(b)(2)", "21 CFR §1.1325(a)(1)(vii)"),
    "Harvesting: Farm Location Required": ("21 CFR §1.1327(b)(3)", "21 CFR §1.1325(a)(1)(iv)"),
    "Initial Packing: Packing Date Required": ("21 CFR §1.1335(b)(4)", "21 CFR §1.1330(a)(15)"),
    "Transformation: Transformation Date Required": ("21 CFR §1.1350(b)(4)", "21 CFR §1.1350(a)(2)(iii)"),
    "Cooling: Cooling Date Required": ("21 CFR §1.1325(b)(5)", "21 CFR §1.1325(b)(1)(v)"),
    "Cooling: Cooling Location Required": ("21 CFR §1.1325(b)(4)", "21 CFR §1.1325(b)(1)(iv)"),
    "Initial Packing: Packing Location Required": ("21 CFR §1.1335(b)(2)", "21 CFR §1.1330(a)(14)"),
    "Initial Packing: Harvest Location Reference Required": ("21 CFR §1.1335(b)(3)", "21 CFR §1.1330(a)(4)"),
    "First Land-Based Receiving: Entry Point Required": ("21 CFR §1.1325(c)(4)", "21 CFR §1.1335(e)"),
    "First Land-Based Receiving: Source Vessel / Origin Required": (
        "21 CFR §1.1325(c)(5)",
        "Operational source-vessel identification (supports 21 CFR §1.1335(d) harvest provenance)",
    ),
    "TLC Must Be Present": (
        "21 CFR §1.1310",
        "Operational lot linkage (supports 21 CFR §1.1320; harvesting and cooling precede TLC assignment)",
    ),
    "Product Description Required": (
        "21 CFR §1.1310(b)(1)",
        "21 CFR §§1.1325(a)(1)(ii), 1.1325(b)(1)(ii), 1.1330(a)(12), 1.1335(b), "
        "1.1340(a)(3), 1.1345(a)(3), 1.1350(a)(2)(iv)",
    ),
    "Quantity and Unit of Measure Required": (
        "21 CFR §1.1310(b)(2)",
        "21 CFR §§1.1325(a)(1)(iii), 1.1325(b)(1)(iii), 1.1330(a)(13), "
        "1.1335(c), 1.1340(a)(2), 1.1345(a)(2), 1.1350(a)(2)(v)",
    ),
    "Location Identifier Required": (
        "21 CFR §1.1310(b)(3)",
        "21 CFR §§1.1325(a)(1)(iv), 1.1325(b)(1)(iv), 1.1330(a)(14), 1.1335(e), "
        "1.1340(a)(5), 1.1345(a)(5), 1.1350(a)(2)(ii)",
    ),
    "GLN Format Validation": ("GS1 General Specifications §3.4.2", "GS1 General Specifications (GS1 check digit)"),
    "Shipping: TLC Source Reference Required": ("21 CFR §1.1340(b)(7)", "21 CFR §1.1340(a)(7)"),
    "Transformation: Input TLCs Required": ("21 CFR §1.1350(a)(4)", "21 CFR §1.1350(a)(1)(i)"),
    "Reference Document Required for All CTEs": (
        "21 CFR §1.1310(c)",
        "21 CFR §§1.1325(a)(1)(viii), 1.1325(b)(1)(vii), 1.1330(a)(16), "
        "1.1335(g), 1.1340(a)(8), 1.1345(a)(8), 1.1350(a)(2)(vi)",
    ),
    "First Land-Based Receiving: Landing Date Required": ("21 CFR §1.1325(b)(4)", "21 CFR §1.1335(f)"),
    "Harvesting: Commodity and Variety Required": ("21 CFR §1.1327(b)(1)", "21 CFR §1.1325(a)(1)(ii)"),
    "Receiving: Receiving Location Required": ("21 CFR §1.1345(b)(4)", "21 CFR §1.1345(a)(5)"),
    "Initial Packing: Harvester Business Name Required": ("21 CFR §1.1335(b)(8)", "21 CFR §1.1330(a)(7)"),
    "Identity Consistency: Product Must Not Change for Same TLC": (
        "21 CFR §1.1310(a)",
        "Operational product identity consistency (supports 21 CFR §1.1320 lot linkage)",
    ),
    "FTL Classification: Product Must Be Classified": (
        "21 CFR §1.1300",
        "Operational FTL classification (supports 21 CFR §1.1300 scope determination)",
    ),
}


def _apply(reverse=False):
    conn = op.get_bind()
    for title, (old, new) in CITATION_CORRECTIONS.items():
        if reverse:
            old, new = new, old
        rows = conn.execute(
            sa.text("""
            WITH candidates AS (
            SELECT rule_id, rule_version FROM fsma.rule_definitions
            WHERE title = :title AND citation_reference = :old
              AND retired_date IS NULL
              AND rule_version = (SELECT MAX(r.rule_version) FROM fsma.rule_definitions r WHERE r.title = :title AND r.retired_date IS NULL)
              AND (NOT :reverse OR EXISTS (
                  SELECT 1 FROM fsma.rule_audit_log a
                  WHERE a.rule_id = rule_definitions.rule_id AND a.changed_by = 'migration_v120'
                    AND a.new_values->>'citation_reference' = :old
                    AND (a.new_values->>'rule_version')::integer = rule_definitions.rule_version
              ))
            FOR UPDATE
            )
            UPDATE fsma.rule_definitions d
            SET citation_reference = :new, updated_at = NOW(),
                rule_version = (SELECT MAX(r.rule_version) + 1 FROM fsma.rule_definitions r WHERE r.title = d.title)
            FROM candidates c WHERE d.rule_id = c.rule_id
            RETURNING d.rule_id, d.rule_version, c.rule_version
        """),
            {"title": title, "old": old, "new": new, "reverse": reverse},
        ).fetchall()
        for rule_id, version, old_version in rows:
            conn.execute(
                sa.text("""
                INSERT INTO fsma.rule_audit_log
                    (rule_id, action, old_values, new_values, changed_by)
                VALUES (:rule_id, 'updated', CAST(:old AS jsonb), CAST(:new AS jsonb), 'migration_v120')
            """),
                {
                    "rule_id": rule_id,
                    "old": json.dumps({"citation_reference": old, "rule_version": old_version}),
                    "new": json.dumps({"citation_reference": new, "rule_version": version}),
                },
            )


def _phone_rule(reverse=False):
    old = {
        "type": "multi_field_presence",
        "field": "kdes.harvester_business_phone",
        "params": {"fields": ["kdes.harvester_business_phone", "from_entity_reference"]},
    }
    new = {"type": "field_presence", "field": "kdes.harvester_business_phone"}
    old_description = (
        "Initial packing events must include the harvester's phone number (or an entity reference resolvable to it)"
    )
    new_description = "Initial packing events must include the harvester's phone number"
    if reverse:
        old, new = new, old
        old_description, new_description = new_description, old_description
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("""
        WITH candidates AS (
        SELECT rule_id, rule_version, description FROM fsma.rule_definitions
        WHERE title = 'Initial Packing: Harvester Phone Required'
          AND evaluation_logic = CAST(:old AS jsonb)
          AND retired_date IS NULL
          AND rule_version = (SELECT MAX(r.rule_version) FROM fsma.rule_definitions r
                              WHERE r.title = 'Initial Packing: Harvester Phone Required' AND r.retired_date IS NULL)
          AND (NOT :reverse OR EXISTS (
              SELECT 1 FROM fsma.rule_audit_log a
              WHERE a.rule_id = rule_definitions.rule_id AND a.changed_by = 'migration_v120'
                AND a.new_values->'evaluation_logic' = CAST(:old AS jsonb)
                AND (a.new_values->>'rule_version')::integer = rule_definitions.rule_version
          ))
        FOR UPDATE
        )
        UPDATE fsma.rule_definitions d
        SET evaluation_logic = CAST(:new AS jsonb), updated_at = NOW(),
            description = CASE WHEN d.description = :old_description THEN :new_description ELSE d.description END,
            rule_version = (SELECT MAX(r.rule_version) + 1 FROM fsma.rule_definitions r WHERE r.title = d.title)
        FROM candidates c WHERE d.rule_id = c.rule_id
        RETURNING d.rule_id, d.rule_version, c.rule_version, c.description, d.description
    """),
        {
            "old": json.dumps(old),
            "new": json.dumps(new),
            "reverse": reverse,
            "old_description": old_description,
            "new_description": new_description,
        },
    ).fetchall()
    for rule_id, version, old_version, before_description, after_description in rows:
        conn.execute(
            sa.text("""
            INSERT INTO fsma.rule_audit_log (rule_id, action, old_values, new_values, changed_by)
            VALUES (:rule_id, 'updated', CAST(:old AS jsonb), CAST(:new AS jsonb), 'migration_v120')
        """),
            {
                "rule_id": rule_id,
                "old": json.dumps(
                    {"evaluation_logic": old, "rule_version": old_version, "description": before_description}
                ),
                "new": json.dumps({"evaluation_logic": new, "rule_version": version, "description": after_description}),
            },
        )


@contextmanager
def _rule_owner_writes():
    """Scope owner visibility to this transaction; runtime policies stay intact.

    The dedicated owner has NOBYPASSRLS. ALTER takes a table lock until
    commit, so no other session can observe the temporary NO FORCE state.
    On failure PostgreSQL rolls back both the data and RLS changes.
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
        _apply()
        _phone_rule()


def downgrade():
    with _rule_owner_writes():
        _phone_rule(reverse=True)
        _apply(reverse=True)
