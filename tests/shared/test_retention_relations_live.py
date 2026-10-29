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


def test_runtime_role_can_hard_delete_expired_partner_files() -> None:
    """regengine must be able to hard-delete an expired partner_files row.

    The retention sweep runs as the ordinary runtime role (get_db →
    DATABASE_URL). v138 puts partner_files in the hard-delete path; without
    DELETE the job fails on privileges and retries forever. This proves the
    grant + sweep path on a migrated scratch DB using only structural rows
    (no realistic partner payloads).
    """
    import asyncio
    from datetime import datetime, timedelta, timezone
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    from shared.data_retention import (
        AuditActor,
        DataRetentionManager,
        RetentionPolicy,
    )
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(sync_postgres_url(DATABASE_URL))
    tenant_id = str(uuid4())
    file_id = str(uuid4())
    engagement_id = str(uuid4())
    expired_at = datetime.now(timezone.utc) - timedelta(days=31)

    try:
        # Privilege gate (independent of session role): cutover + v138.
        with engine.connect() as conn:
            has_delete_files = conn.execute(
                text("SELECT has_table_privilege('regengine', to_regclass('public.partner_files'), 'DELETE')")
            ).scalar()
            has_delete_derived = conn.execute(
                text("SELECT has_table_privilege('regengine', to_regclass('public.partner_file_derived'), 'DELETE')")
            ).scalar()
            has_delete_log = conn.execute(
                text(
                    "SELECT has_table_privilege('regengine', to_regclass('public.partner_file_deletion_log'), 'DELETE')"
                )
            ).scalar()
            conn.commit()
        assert has_delete_files is True, (
            "regengine lacks DELETE on public.partner_files — retention "
            "hard-delete will fail once rows age past 30 days"
        )
        assert has_delete_derived is True, "regengine lacks DELETE on public.partner_file_derived"
        assert has_delete_log is False, "partner_file_deletion_log must stay append-only (no DELETE)"

        # Seed as the live-suite provider (postgres / superuser). Minimal
        # structural columns only — synthetic path/hash, not a real file.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO public.tenants (id, name, slug) VALUES (CAST(:id AS uuid), 'retention sweep', :slug)"
                ),
                {"id": tenant_id, "slug": f"ret-{tenant_id[:8]}"},
            )
            conn.execute(text("ALTER TABLE public.partner_files DISABLE ROW LEVEL SECURITY"))
            conn.execute(
                text(
                    """
                    INSERT INTO public.partner_files (
                        id, tenant_id, engagement_id, storage_path,
                        content_sha256, original_filename, byte_size,
                        content_type, status, deleted_at
                    ) VALUES (
                        CAST(:id AS uuid),
                        CAST(:tenant_id AS uuid),
                        CAST(:engagement_id AS uuid),
                        'tenants/' || :tenant_id || '/structural.csv',
                        repeat('a', 64),
                        'structural.csv',
                        12,
                        'text/csv',
                        'deleted',
                        :deleted_at
                    )
                    """
                ),
                {
                    "id": file_id,
                    "tenant_id": tenant_id,
                    "engagement_id": engagement_id,
                    "deleted_at": expired_at,
                },
            )
            conn.execute(text("ALTER TABLE public.partner_files ENABLE ROW LEVEL SECURITY"))

        # Prove the DELETE as the runtime role under tenant RLS.
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            session.execute(text("SET LOCAL ROLE regengine"))
            session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": tenant_id},
            )
            audit = MagicMock()
            audit.log_data_modification = AsyncMock(return_value=None)
            mgr = DataRetentionManager(audit_logger=audit)
            actor = AuditActor(
                actor_id="system:retention_cleanup",
                actor_type="system",
                username="system",
            )
            deleted_ok = asyncio.run(
                mgr.hard_delete_record(
                    db=session,
                    resource_type=RetentionPolicy.PARTNER_FILES.value,
                    record_id=file_id,
                    actor=actor,
                )
            )
            assert deleted_ok is True
        finally:
            session.close()

        # Row must be gone even when inspected as the provider role.
        with engine.connect() as conn:
            still_there = conn.execute(
                text("SELECT 1 FROM public.partner_files WHERE id = CAST(:id AS uuid)"),
                {"id": file_id},
            ).scalar()
            conn.commit()
        assert still_there is None, "expired partner_files row survived hard-delete as regengine"
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM public.partner_files WHERE id = CAST(:id AS uuid)"),
                {"id": file_id},
            )
            conn.execute(
                text("DELETE FROM public.tenants WHERE id = CAST(:id AS uuid)"),
                {"id": tenant_id},
            )
        engine.dispose()
