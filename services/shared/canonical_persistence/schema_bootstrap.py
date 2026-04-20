"""
Schema bootstrap for canonical_persistence — NOT an Alembic migration.

This module bootstraps schema objects (grants, views, helper functions) that
depend on the runtime tenant context and therefore cannot live in Alembic
version history.  Alembic owns table DDL; this module owns the runtime
objects that are layered on top of those tables.

When to run
-----------
Run manually after a fresh schema apply, or via the service startup hook
before the first request is served.  Do NOT add this file to Alembic
version history — it is idempotent and safe to re-run, but it is not a
migration step.

What lives here vs. Alembic
----------------------------
* Alembic: CREATE TABLE, ALTER TABLE, CREATE INDEX, DROP COLUMN — anything
  that changes the physical schema and must be versioned and rolled back
  in sequence.
* This module: GRANT, CREATE OR REPLACE VIEW, CREATE OR REPLACE FUNCTION,
  SET row_level_security — objects that reference the runtime tenant GUC
  (``app.tenant_id``) or that must be refreshed when tenant configuration
  changes, independently of table schema evolution.

Usage
-----
::

    from shared.canonical_persistence.schema_bootstrap import bootstrap
    bootstrap(engine)          # idempotent; safe to call on every startup

"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger("canonical-persistence.schema_bootstrap")

# ---------------------------------------------------------------------------
# SQL fragments executed by bootstrap()
# ---------------------------------------------------------------------------
# Each statement is idempotent (CREATE OR REPLACE, IF NOT EXISTS, etc.) so
# calling bootstrap() multiple times is safe.

_BOOTSTRAP_SQL: list[str] = [
    # Ensure the helper function exists that returns the current tenant GUC.
    # Alembic creates the fsma schema + tables; this function is a runtime
    # convenience that depends on the GUC, not on any table structure.
    """
    CREATE OR REPLACE FUNCTION fsma.get_tenant_context()
    RETURNS text
    LANGUAGE sql
    STABLE
    AS $$
        SELECT current_setting('app.tenant_id', true)
    $$;
    """,

    # Grant usage on fsma schema to the application role so new tenants
    # created after initial deploy can reach the schema objects.
    # (pg_catalog.pg_roles is queried to make the GRANT idempotent.)
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'app_user'
        ) THEN
            GRANT USAGE ON SCHEMA fsma TO app_user;
            GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA fsma TO app_user;
        END IF;
    END
    $$;
    """,
]


def bootstrap(engine: "Engine") -> None:
    """Run all idempotent schema-bootstrap statements.

    This is NOT an Alembic migration.  It must be called from the service
    startup hook (or manually) after applying Alembic migrations on a fresh
    database.  It is safe to call multiple times.

    Args:
        engine: SQLAlchemy ``Engine`` connected to the target database.
    """
    from sqlalchemy import text

    with engine.begin() as conn:
        for stmt in _BOOTSTRAP_SQL:
            conn.execute(text(stmt))

    logger.info("canonical_persistence.schema_bootstrap completed")
