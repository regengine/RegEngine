"""Live-DB gate: the retention layer's declared targets vs. the real schema (#2900).

``services/shared/data_retention.py`` used to interpolate ``RetentionPolicy``
enum values directly into SQL as table names. Against a database at
``alembic upgrade head`` none of them resolve::

    to_regclass('user_account')     -> NULL
    to_regclass('supplier_contact') -> NULL
    to_regclass('audit_log')        -> NULL
    to_regclass('transaction_log')  -> NULL
    to_regclass('temporary_pii')    -> NULL

and — decisively — the migrated schema holds **zero** columns named
``deleted_at``, which is the column the whole soft-delete layer writes. There
was nothing to repoint to: these statements were written against a schema that
has never existed in this repository.

``_RESOURCE_RELATIONS`` now records that explicitly. This test compares the
declaration against the database, in both directions, so the module can never
drift back into silent fiction:

  * a resource declared to have a backing relation must actually resolve;
  * a resource declared unbacked must still be unbacked — if someone migrates
    a real table for it, this fails and tells them to repoint the code rather
    than leaving a dead policy in place.

Picked up automatically by the ``live-db-suite`` CI job's
``tests/shared/test_*_live.py`` glob, where a skip is a job failure.
"""

from __future__ import annotations

import pytest
from shared.db_url import sync_postgres_url

from tests.migrations.rls_db import guarded_live_database_url

DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason=(
        "no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — "
        "skipping live retention relation test"
    ),
)


def _resolve(conn, name: str):
    from sqlalchemy import text

    return conn.execute(text("SELECT to_regclass(:n)"), {"n": name}).scalar()


def test_declared_retention_relations_match_the_migrated_schema() -> None:
    from shared.data_retention import _RESOURCE_RELATIONS
    from sqlalchemy import create_engine

    engine = create_engine(sync_postgres_url(DATABASE_URL))
    try:
        with engine.connect() as conn:
            missing = []
            unexpectedly_present = []
            for resource, relation in sorted(_RESOURCE_RELATIONS.items()):
                if relation is None:
                    # The name the pre-#2900 code used as a table name.
                    if _resolve(conn, "public." + resource) is not None:
                        unexpectedly_present.append(resource)
                    continue
                if _resolve(conn, relation) is None:
                    missing.append(f"{resource} -> {relation}")

        assert not missing, (
            "retention resources point at relations that do not exist after "
            f"`alembic upgrade head`: {missing}. This is the #2900 defect — every "
            "sweep and every erasure against them is a no-op or a 500."
        )
        assert not unexpectedly_present, (
            f"these resources are declared as having no backing relation, but one now exists: "
            f"{unexpectedly_present}. Repoint _RESOURCE_RELATIONS (and the SQL) at it "
            "instead of leaving the retention policy dead."
        )
    finally:
        engine.dispose()


def test_soft_delete_column_state_matches_what_the_module_declares() -> None:
    """``deleted_at`` is the column every retention statement reads and writes.

    Today the migrated schema has none — anywhere — which is the evidence that
    settled #2900: there was no rename and no table to repoint at, the schema
    these statements were written for never existed here. So the assertion
    runs in whichever direction the map declares, and always runs:

      * every declared relation must actually carry ``deleted_at``;
      * with nothing declared, no relation may carry it either — the day one
        appears, this fails and says to wire the retention layer up to it
        rather than leaving the policies dead.
    """
    from shared.data_retention import _RESOURCE_RELATIONS
    from sqlalchemy import create_engine, text

    declared = {r: rel for r, rel in _RESOURCE_RELATIONS.items() if rel}

    engine = create_engine(sync_postgres_url(DATABASE_URL))
    try:
        with engine.connect() as conn:
            if not declared:
                carriers = conn.execute(
                    text(
                        "SELECT table_schema || '.' || table_name FROM information_schema.columns "
                        "WHERE column_name = 'deleted_at' "
                        "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
                        "ORDER BY 1"
                    )
                ).fetchall()
                assert not carriers, (
                    "no retention resource declares a backing relation, yet these relations now have a "
                    f"deleted_at column: {[c[0] for c in carriers]}. Point _RESOURCE_RELATIONS (and the "
                    "retention SQL) at the right one instead of leaving every policy dead (#2900)."
                )
                return

            without = []
            for resource, relation in sorted(declared.items()):
                schema, _, table = relation.partition(".")
                has_col = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_schema = :s AND table_name = :t AND column_name = 'deleted_at'"
                    ),
                    {"s": schema, "t": table},
                ).scalar()
                if not has_col:
                    without.append(f"{resource} -> {relation}")
            assert not without, (
                f"these retention targets have no deleted_at column, so the soft-delete "
                f"UPDATE can only ever raise: {without}"
            )
    finally:
        engine.dispose()
