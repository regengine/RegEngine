"""v138 — fsma.traceability_events mutation policy (column allowlist trigger).

``fsma.traceability_events`` is the canonical FSMA 204 evidence table and
the chain hash is computed over its payload columns, yet until now nothing
in the database stopped an UPDATE or DELETE on it. ``fsma.cte_events`` has
had an append-only trigger since v107; the canonical table had none, so a
``UPDATE fsma.traceability_events SET quantity = ...`` from any role with
UPDATE privilege silently broke the evidence the FDA package is built on.

This revision installs a BEFORE UPDATE OR DELETE row trigger plus a BEFORE
TRUNCATE statement trigger that together enforce the sanctioned mutation
surface, which is exactly what the three production writers do today:

* ``services/shared/canonical_persistence/writer.py`` marks the row an
  amendment supersedes: ``status = 'superseded', amended_at = NOW()``.
* ``services/shared/rules/engine.py`` records the event-level verdict:
  ``evaluation_verdict``, ``no_verdict_reason``, ``evaluated_at``, and the
  evaluation error marker: ``evaluation_error``, ``evaluated_at``.

Allowed on UPDATE: changes confined to the allowlisted columns
(``status``, ``amended_at``, ``evaluation_verdict``, ``no_verdict_reason``,
``evaluation_error``, ``evaluated_at``), and ``status`` may only move from
``active`` to ``superseded``. Any other column change, any other status
transition, every DELETE and every TRUNCATE raise ``check_violation``.

Break-glass: ``SET LOCAL fsma.allow_mutation = 'true'`` lets the statement
through with a WARNING, the same GUC v095 and v107 use. The runtime resets
it per transaction (``services/shared/tenant_context.py``) and per pooled
connection (``services/admin/app/database.py``); the retention purge is
its only production user.

The comparison is ``to_jsonb(NEW) - allowlist = to_jsonb(OLD) - allowlist``
rather than a list of frozen column names, so the trigger is correct on
every catalog variant of the table (the Supabase twin has ``tenant_id
TEXT`` and no ``ingested_at``) and keeps protecting columns added later.

Idempotent: ``CREATE OR REPLACE`` functions, ``DROP TRIGGER IF EXISTS``
before ``CREATE TRIGGER``, ``to_regclass`` guard. No grant changes (v111
still grants UPDATE to the runtime role; the trigger is the enforcement).

Revision ID: 08c7cf36ddbe
Revises: a3f7ce361b0e
Create Date: 2026-10-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "08c7cf36ddbe"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "a3f7ce361b0e"  # pragma: allowlist secret
branch_labels = None
depends_on = None

TABLE = "fsma.traceability_events"
ROW_TRIGGER = "traceability_events_mutation_policy"
TRUNCATE_TRIGGER = "traceability_events_no_truncate"
ROW_FUNCTION = "fsma.prevent_traceability_event_mutation"
TRUNCATE_FUNCTION = "fsma.prevent_traceability_event_truncate"

# Columns the sanctioned writers may change. Keep in step with the module
# docstring and docs/engineering/SCHEMA_CHANGE_POLICY.md §5.
ALLOWLIST: tuple[str, ...] = (
    "status",
    "amended_at",
    "evaluation_verdict",
    "no_verdict_reason",
    "evaluation_error",
    "evaluated_at",
)

_ALLOWLIST_SQL = ", ".join(f"'{c}'" for c in ALLOWLIST)

_ROW_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {ROW_FUNCTION}()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    allowlist text[] := ARRAY[{_ALLOWLIST_SQL}];
    changed   text[];
BEGIN
    IF current_setting('fsma.allow_mutation', true) = 'true' THEN
        RAISE WARNING
            'traceability_events modification via break-glass. op=% user=% event_id=%',
            TG_OP, current_user, COALESCE(NEW.event_id::text, OLD.event_id::text);
        IF TG_OP = 'UPDATE' THEN
            RETURN NEW;
        END IF;
        RETURN OLD;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'traceability_events is append-only (FDA 21 CFR 1.1455). DELETE rejected for event_id=%. Set fsma.allow_mutation=true for authorized break-glass.',
            OLD.event_id
            USING ERRCODE = 'check_violation';
    END IF;

    -- UPDATE: every changed column must be on the allowlist.
    SELECT COALESCE(array_agg(key ORDER BY key), ARRAY[]::text[])
      INTO changed
      FROM (
          SELECT key FROM jsonb_each(to_jsonb(NEW) - allowlist)
          EXCEPT
          SELECT key FROM jsonb_each(to_jsonb(OLD) - allowlist)
          UNION
          SELECT n.key
            FROM jsonb_each(to_jsonb(NEW) - allowlist) n
            JOIN jsonb_each(to_jsonb(OLD) - allowlist) o ON o.key = n.key
           WHERE n.value IS DISTINCT FROM o.value
      ) diff;
    IF array_length(changed, 1) IS NOT NULL THEN
        RAISE EXCEPTION
            'traceability_events is append-only (FDA 21 CFR 1.1455). UPDATE rejected for event_id=%: column(s) % are not amendable. Corrections are new events that supersede the old one. Set fsma.allow_mutation=true for authorized break-glass.',
            OLD.event_id, array_to_string(changed, ', ')
            USING ERRCODE = 'check_violation';
    END IF;

    -- status may only move active -> superseded (an amendment landed).
    IF NEW.status IS DISTINCT FROM OLD.status
       AND NOT (OLD.status = 'active' AND NEW.status = 'superseded') THEN
        RAISE EXCEPTION
            'traceability_events status may only move from active to superseded; % -> % rejected for event_id=%. Set fsma.allow_mutation=true for authorized break-glass.',
            OLD.status, NEW.status, OLD.event_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;
"""

_TRUNCATE_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {TRUNCATE_FUNCTION}()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('fsma.allow_mutation', true) = 'true' THEN
        RAISE WARNING 'traceability_events TRUNCATE via break-glass. user=%', current_user;
        RETURN NULL;
    END IF;
    RAISE EXCEPTION
        'traceability_events is append-only (FDA 21 CFR 1.1455). TRUNCATE rejected. Set fsma.allow_mutation=true for authorized break-glass.'
        USING ERRCODE = 'check_violation';
END;
$$;
"""

_TRIGGERS_SQL = f"""
DO $$
BEGIN
    IF to_regclass('{TABLE}') IS NULL THEN
        RETURN;
    END IF;
    DROP TRIGGER IF EXISTS {ROW_TRIGGER} ON {TABLE};
    CREATE TRIGGER {ROW_TRIGGER}
        BEFORE UPDATE OR DELETE ON {TABLE}
        FOR EACH ROW EXECUTE FUNCTION {ROW_FUNCTION}();
    DROP TRIGGER IF EXISTS {TRUNCATE_TRIGGER} ON {TABLE};
    CREATE TRIGGER {TRUNCATE_TRIGGER}
        BEFORE TRUNCATE ON {TABLE}
        FOR EACH STATEMENT EXECUTE FUNCTION {TRUNCATE_FUNCTION}();
END $$;
"""

_DOWNGRADE_SQL = f"""
DO $$
BEGIN
    IF to_regclass('{TABLE}') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS {ROW_TRIGGER} ON {TABLE};
        DROP TRIGGER IF EXISTS {TRUNCATE_TRIGGER} ON {TABLE};
    END IF;
END $$;
DROP FUNCTION IF EXISTS {ROW_FUNCTION}();
DROP FUNCTION IF EXISTS {TRUNCATE_FUNCTION}();
"""


def upgrade() -> None:
    op.execute(_ROW_FUNCTION_SQL)
    op.execute(_TRUNCATE_FUNCTION_SQL)
    op.execute(_TRIGGERS_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
