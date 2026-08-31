"""Tenantless enqueue idempotency — #2852.

The enqueue-dedup index created by v063 is partial and, by PostgreSQL's
default ``NULLS DISTINCT`` rule, enforces nothing between two rows whose
``tenant_id`` is NULL. ``server.workers.task_processor.enqueue_task``
relies on that index via ``ON CONFLICT (tenant_id, idempotency_key)``, so
for tenantless rows the conflict never fired and every retry inserted
another copy — duplicating human-in-the-loop ``review_item`` rows enqueued
by ``_run_hardened_extraction`` for documents that carry no tenant.

These tests drive the *real* ``enqueue_task`` against a *real* Postgres,
over the index definition the migrations actually ship, so they fail if
migration v113 is reverted rather than merely asserting on its text.

The index DDL is not hard-coded: :func:`_effective_index_ddl` scans
``alembic/versions`` in migration order and takes the last statement that
creates ``idx_task_queue_idempotency``. That is what a migrated database
ends up with — v063's definition on ``main``, v113's after the fix.

Requires a real Postgres (15+, for ``NULLS NOT DISTINCT``); skips without
one unless ``REGENGINE_REQUIRE_DB=1``. See ``tests/migrations/rls_db.py``.

Run via:
    pytest tests/migrations/test_task_queue_tenantless_idempotency_2852.py -v
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from tests.migrations.rls_db import skip_or_fail_db
from tests.migrations.scratch_db import scratch_database_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"

TENANT_ID = "11111111-2222-3333-4444-555555555555"
REVIEW_KEY = "review_item:doc-2852:OBLIGATION:5"

# Matches a CREATE UNIQUE INDEX statement for the enqueue-dedup index, up to
# its terminating quote — enough to capture an optional NULLS NOT DISTINCT
# clause and the partial WHERE predicate.
_INDEX_RE = re.compile(
    r"CREATE\s+UNIQUE\s+INDEX(?:\s+IF\s+NOT\s+EXISTS)?\s+idx_task_queue_idempotency\b.*?(?=\"\"\")",
    re.IGNORECASE | re.DOTALL,
)

# The table columns enqueue_task actually writes plus the ones the dedup
# index and its recovery SELECT read. Deliberately a subset of v063's
# fsma.task_queue: this suite is about the index, not the full schema.
_TABLE_DDL = """
    CREATE TABLE fsma.task_queue (
        id              BIGSERIAL PRIMARY KEY,
        task_type       TEXT NOT NULL,
        payload         JSONB NOT NULL DEFAULT '{}',
        status          TEXT NOT NULL DEFAULT 'pending',
        priority        INT NOT NULL DEFAULT 0,
        tenant_id       TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        idempotency_key TEXT
    )
"""


def _effective_index_ddl() -> str:
    """The idx_task_queue_idempotency definition a migrated DB ends up with.

    Alembic filenames in this repo are date-prefixed and the index is only
    ever touched by whole-statement DROP/CREATE pairs, so the last CREATE
    in filename order is the one that survives ``upgrade head``.

    Only ``upgrade()`` is read: a migration that rebuilds this index also
    restores the previous definition in ``downgrade()``, and picking that
    one up would model a database that had been rolled back.
    """
    statements: list[str] = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        downgrade_at = source.find("def downgrade(")
        if downgrade_at != -1:
            source = source[:downgrade_at]
        for match in _INDEX_RE.finditer(source):
            statements.append(match.group(0).strip())
    assert statements, "no CREATE UNIQUE INDEX idx_task_queue_idempotency found in alembic/versions"
    return statements[-1]


@pytest.fixture(scope="module")
def enqueue_session_factory() -> Iterator[object]:
    """A disposable database carrying fsma.task_queue + the shipped index.

    Isolated rather than shared: this suite creates ``fsma.task_queue``
    itself, which must not disturb the migration gates running against the
    same server.
    """
    with scratch_database_engine("regengine_scratch_tq_2852") as engine:
        with engine.connect() as conn:
            version = conn.exec_driver_sql("SHOW server_version_num").scalar()
            if int(version) < 150000:
                skip_or_fail_db(f"#2852 needs PostgreSQL 15+ for NULLS NOT DISTINCT (got {version})")
            conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS fsma")
            conn.exec_driver_sql(_TABLE_DDL)
            conn.exec_driver_sql(_effective_index_ddl())
            conn.commit()
        yield sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _clean_queue(enqueue_session_factory) -> Iterator[None]:
    session = enqueue_session_factory()
    try:
        session.execute(text("DELETE FROM fsma.task_queue"))
        session.commit()
    finally:
        session.close()
    yield


@pytest.fixture
def enqueue(enqueue_session_factory, monkeypatch):
    """The real enqueue_task, bound to the test database.

    ``enqueue_task`` imports ``SessionLocal`` from ``shared.database``
    inside the function body, so patching the module attribute is enough
    to redirect it without touching import order.
    """
    import shared.database as shared_database

    from server.workers.task_processor import enqueue_task

    monkeypatch.setattr(shared_database, "SessionLocal", enqueue_session_factory)
    return enqueue_task


def _row_count(factory, *, tenant_id: str | None, key: str) -> int:
    session = factory()
    try:
        return session.execute(
            text(
                """
                SELECT count(*) FROM fsma.task_queue
                WHERE tenant_id IS NOT DISTINCT FROM :tenant_id
                  AND idempotency_key = :key
                """
            ),
            {"tenant_id": tenant_id, "key": key},
        ).scalar_one()
    finally:
        session.close()


def test_tenantless_review_item_enqueues_once(enqueue, enqueue_session_factory) -> None:
    """The #2852 regression: two tenantless enqueues of one key → one row.

    This is the shape ``_run_hardened_extraction`` produces for a document
    with no tenant (``tenant_id=str(tenant_id) if tenant_id else None``
    alongside an idempotency key). Before v113 the second call inserted a
    second review item and returned a new id, so a reviewer saw the same
    flagged extraction once per retry.
    """
    first = enqueue("review_item", {"document_id": "doc-2852"}, tenant_id=None, idempotency_key=REVIEW_KEY)
    second = enqueue("review_item", {"document_id": "doc-2852"}, tenant_id=None, idempotency_key=REVIEW_KEY)

    assert first is not None, "first tenantless enqueue should return a task id"
    assert _row_count(enqueue_session_factory, tenant_id=None, key=REVIEW_KEY) == 1, (
        "a tenantless idempotency key must dedupe — a second row here is a duplicate "
        "human-in-the-loop review item (#2852)"
    )
    assert second == first, (
        "the retry must resolve to the already-enqueued task id via the conflict-recovery "
        "SELECT, which is what makes enqueue_task_idempotent_hit observable"
    )


def test_tenantless_distinct_keys_still_coexist(enqueue, enqueue_session_factory) -> None:
    """NULLS NOT DISTINCT collapses equal keys, not the whole NULL tenant.

    Guards against over-correcting into an index that lets a tenantless
    caller enqueue only one task ever.
    """
    other_key = "review_item:doc-2852:OBLIGATION:9"
    first = enqueue("review_item", {"document_id": "doc-2852"}, tenant_id=None, idempotency_key=REVIEW_KEY)
    second = enqueue("review_item", {"document_id": "doc-2852"}, tenant_id=None, idempotency_key=other_key)

    assert first is not None and second is not None
    assert first != second, "distinct idempotency keys must remain distinct tasks"


def test_tenantless_rows_without_a_key_are_unconstrained(enqueue, enqueue_session_factory) -> None:
    """The partial predicate still excludes keyless rows.

    ``enqueue_task`` documents "if the key is None the legacy behavior is
    preserved (duplicates are possible)"; the index must not quietly start
    enforcing uniqueness there.
    """
    first = enqueue("review_item", {"document_id": "doc-2852"}, tenant_id=None)
    second = enqueue("review_item", {"document_id": "doc-2852"}, tenant_id=None)

    assert first is not None and second is not None
    assert first != second, "keyless enqueues keep the documented legacy duplicate behavior"


def test_tenanted_dedup_is_unaffected(enqueue, enqueue_session_factory) -> None:
    """Control: the authenticated path deduped correctly before v113 too.

    Present so a failure of the tenantless test above is attributable to
    NULL handling specifically, and so the migration is shown not to have
    regressed the path that already worked.
    """
    first = enqueue("review_item", {"document_id": "doc-2852"}, tenant_id=TENANT_ID, idempotency_key=REVIEW_KEY)
    second = enqueue("review_item", {"document_id": "doc-2852"}, tenant_id=TENANT_ID, idempotency_key=REVIEW_KEY)

    assert first is not None
    assert second == first
    assert _row_count(enqueue_session_factory, tenant_id=TENANT_ID, key=REVIEW_KEY) == 1


def test_tenanted_and_tenantless_keys_do_not_collide(enqueue, enqueue_session_factory) -> None:
    """A NULL tenant must not be treated as equal to a real tenant.

    ``NULLS NOT DISTINCT`` makes NULL equal to NULL, not NULL equal to
    everything — so system-scoped work and a tenant's work sharing a key
    stay separate rows and cross-tenant suppression is impossible.
    """
    tenantless = enqueue("review_item", {"document_id": "doc-2852"}, tenant_id=None, idempotency_key=REVIEW_KEY)
    tenanted = enqueue("review_item", {"document_id": "doc-2852"}, tenant_id=TENANT_ID, idempotency_key=REVIEW_KEY)

    assert tenantless is not None and tenanted is not None
    assert tenantless != tenanted, "a tenantless key must not suppress a tenant's task with the same key"
    assert _row_count(enqueue_session_factory, tenant_id=None, key=REVIEW_KEY) == 1
    assert _row_count(enqueue_session_factory, tenant_id=TENANT_ID, key=REVIEW_KEY) == 1
