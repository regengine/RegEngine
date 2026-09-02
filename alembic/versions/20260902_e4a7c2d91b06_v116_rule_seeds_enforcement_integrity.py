"""v116 — repair already-seeded rule rows whose logic contradicted their claim.

Revision ID: e4a7c2d91b06
Revises: c1d4e8f20a37
Create Date: 2026-09-02

``seed_rule_definitions`` is insert-only (matched by title), so fixing
``services/shared/rules/seeds.py`` only helps fresh databases. This
migration brings already-seeded tenants' ``fsma.rule_definitions`` rows
in line with the corrected seeds:

#3038 — the seven date-KDE rules listed ``event_timestamp`` as an
acceptable alternate. Every canonical event carries ``event_timestamp``,
so the rules were tautologies: a receiving event with no
``kdes.receive_date`` passed "Receiving: Receive Date Required"
(severity: critical). Each is rewritten to plain ``field_presence`` on
the actual KDE date field.

#3041 — three rules promised checks their logic never performed:

* "Quantity and Unit of Measure Required" checked only ``quantity``;
  now ``multi_field_presence`` with ``require: all`` over both fields.
* "GLN Format Validation" promised check-digit verification but ran a
  regex that accepts any 13 digits; now the ``gs1_check_digit``
  evaluator (added in the same release) which verifies the GS1 mod-10
  check digit and skips non-numeric location descriptions.
* No rule enforced the harvester phone number required by
  21 CFR §1.1330(a)(7); "Initial Packing: Harvester Phone Required" is
  inserted where absent.

Also from #3041: the two relational rules cited a bare "21 CFR §1.1310"
(the definitions section — it mandates nothing). Temporal order and
mass balance are re-cited as operational integrity controls, and mass
balance is demoted critical → warning (its 1% tolerance is a heuristic;
a false positive should flag for review, not block a shipment).

Every touched row gets a ``fsma.rule_audit_log`` entry and a
``rule_version`` bump so evaluation results remain attributable to the
rule revision that produced them.

Downgrade restores the previous logic/citation/severity verbatim.
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e4a7c2d91b06"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c1d4e8f20a37"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# title -> (new_logic, old_logic)
_DATE_RULE_LOGIC = {
    "Receiving: Receive Date Required": ("kdes.receive_date",),
    "Shipping: Ship Date Required": ("kdes.ship_date",),
    "Harvesting: Harvest Date Required": ("kdes.harvest_date",),
    "Initial Packing: Packing Date Required": ("kdes.packing_date",),
    "Transformation: Transformation Date Required": ("kdes.transformation_date",),
    "Cooling: Cooling Date Required": ("kdes.cooling_date",),
    "First Land-Based Receiving: Landing Date Required": ("kdes.landing_date",),
}

_HARVESTER_PHONE_RULE = {
    "title": "Initial Packing: Harvester Phone Required",
    "description": (
        "Initial packing events must include the harvester's phone number (or an entity reference resolvable to it)"
    ),
    "severity": "warning",
    "category": "kde_presence",
    "applicability": json.dumps({"cte_types": ["initial_packing"], "ftl_scope": ["ALL"]}),
    "citation": "21 CFR \u00a71.1330(a)(7)",
    "logic": json.dumps(
        {
            "type": "multi_field_presence",
            "field": "kdes.harvester_business_phone",
            "params": {"fields": ["kdes.harvester_business_phone", "from_entity_reference"]},
        }
    ),
    "failure_template": "Initial packing event missing harvester phone number ({citation})",
    "remediation": "Record the harvester's phone number",
}


def _update_rule(conn, title: str, changed: str, **cols) -> None:
    """Apply column updates to one rule row (by title), bump rule_version,
    and record an audit entry. No-op when the title is absent."""
    sets = ", ".join(f"{c} = :{c}" for c in cols)
    result = conn.execute(
        sa.text(
            f"""
            UPDATE fsma.rule_definitions
            SET {sets}, rule_version = rule_version + 1
            WHERE title = :title
            RETURNING rule_id
            """
        ),
        {**cols, "title": title},
    ).fetchone()
    if result is None:
        return
    conn.execute(
        sa.text(
            """
            INSERT INTO fsma.rule_audit_log (rule_id, action, new_values, changed_by)
            VALUES (:rule_id, 'updated', CAST(:values AS jsonb), 'migration_v116')
            """
        ),
        {"rule_id": result[0], "values": json.dumps({"title": title, "changed": changed})},
    )


def upgrade() -> None:
    conn = op.get_bind()

    # #3038 — date rules: require the actual KDE date, drop the
    # event_timestamp tautology.
    for title, (field,) in _DATE_RULE_LOGIC.items():
        _update_rule(
            conn,
            title,
            changed="#3038 removed event_timestamp alternate",
            evaluation_logic=json.dumps({"type": "field_presence", "field": field}),
        )

    # #3041 — quantity rule must check unit_of_measure too.
    _update_rule(
        conn,
        "Quantity and Unit of Measure Required",
        changed="#3041 require quantity AND unit_of_measure",
        evaluation_logic=json.dumps(
            {
                "type": "multi_field_presence",
                "field": "quantity",
                "params": {"fields": ["quantity", "unit_of_measure"], "require": "all"},
            }
        ),
        failure_reason_template="Event missing {field_name} ({citation})",
    )

    # #3041 — GLN rule performs real check-digit verification.
    _update_rule(
        conn,
        "GLN Format Validation",
        changed="#3041 real GS1 check-digit verification",
        evaluation_logic=json.dumps({"type": "gs1_check_digit", "field": "from_facility_reference"}),
    )

    # #3041 — relational rules: honest citations; mass balance demoted.
    _update_rule(
        conn,
        "Temporal Order: CTE Chronology Must Be Causal",
        changed="#3041 recited as operational control",
        citation_reference=(
            "Operational integrity control (supports 21 CFR \u00a7\u00a71.1325\u20131.1350 date KDE accuracy)"
        ),
    )
    _update_rule(
        conn,
        "Mass Balance: Output Cannot Exceed Input for Same TLC",
        changed="#3041 recited as operational control; demoted to warning",
        citation_reference=("Operational integrity control (supports 21 CFR \u00a71.1350(a)(1) quantity linkage)"),
        severity="warning",
    )

    # #3041 — insert the harvester phone rule where absent (mirrors
    # seed_rule_definitions' idempotent-by-title insert).
    existing = conn.execute(
        sa.text("SELECT rule_id FROM fsma.rule_definitions WHERE title = :t"),
        {"t": _HARVESTER_PHONE_RULE["title"]},
    ).fetchone()
    if existing is None:
        row = conn.execute(
            sa.text(
                """
                INSERT INTO fsma.rule_definitions (
                    rule_id, title, description, severity, category,
                    applicability_conditions, citation_reference,
                    evaluation_logic, failure_reason_template,
                    remediation_suggestion
                ) VALUES (
                    gen_random_uuid(), :title, :description, :severity, :category,
                    CAST(:applicability AS jsonb), :citation,
                    CAST(:logic AS jsonb), :failure_template,
                    :remediation
                )
                RETURNING rule_id
                """
            ),
            _HARVESTER_PHONE_RULE,
        ).fetchone()
        conn.execute(
            sa.text(
                """
                INSERT INTO fsma.rule_audit_log (rule_id, action, new_values, changed_by)
                VALUES (:rule_id, 'created', CAST(:values AS jsonb), 'migration_v116')
                """
            ),
            {
                "rule_id": row[0],
                "values": json.dumps({"title": _HARVESTER_PHONE_RULE["title"], "severity": "warning"}),
            },
        )


def downgrade() -> None:
    conn = op.get_bind()

    for title, (field,) in _DATE_RULE_LOGIC.items():
        _update_rule(
            conn,
            title,
            changed="downgrade v116: restore event_timestamp alternate",
            evaluation_logic=json.dumps(
                {
                    "type": "multi_field_presence",
                    "field": field,
                    "params": {"fields": [field, "event_timestamp"]},
                }
            ),
        )

    _update_rule(
        conn,
        "Quantity and Unit of Measure Required",
        changed="downgrade v116",
        evaluation_logic=json.dumps({"type": "field_presence", "field": "quantity"}),
        failure_reason_template="Event missing quantity and unit of measure ({citation})",
    )
    _update_rule(
        conn,
        "GLN Format Validation",
        changed="downgrade v116",
        evaluation_logic=json.dumps(
            {
                "type": "field_format",
                "field": "from_facility_reference",
                "condition": "regex_if_present",
                "params": {"pattern": r"^\d{13}$|^[^0-9].*$|^$"},
            }
        ),
    )
    _update_rule(
        conn,
        "Temporal Order: CTE Chronology Must Be Causal",
        changed="downgrade v116",
        citation_reference="21 CFR \u00a71.1310",
    )
    _update_rule(
        conn,
        "Mass Balance: Output Cannot Exceed Input for Same TLC",
        changed="downgrade v116",
        citation_reference="21 CFR \u00a71.1310",
        severity="critical",
    )

    conn.execute(
        sa.text(
            "DELETE FROM fsma.rule_audit_log WHERE rule_id IN (SELECT rule_id FROM fsma.rule_definitions WHERE title = :t)"
        ),
        {"t": _HARVESTER_PHONE_RULE["title"]},
    )
    conn.execute(
        sa.text("DELETE FROM fsma.rule_definitions WHERE title = :t"),
        {"t": _HARVESTER_PHONE_RULE["title"]},
    )
