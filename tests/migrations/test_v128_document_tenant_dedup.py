"""Exercise document uniqueness migration without rewriting historical rows."""

import importlib.util
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.migrations.rls_db import _normalize_psycopg, guarded_live_database_url, skip_or_fail_db

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic/versions/20260928_f8b6c402a917_v128_document_tenant_dedup.py"


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("v128_document_tenant_dedup", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_compiles_offline_without_database_reads(migration):
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})

    with Operations.context(context):
        migration.upgrade()
        migration.downgrade()

    sql = output.getvalue()
    assert "UNIQUE (tenant_id, content_sha256)" in sql
    assert "UNIQUE (content_sha256)" in sql
    assert sql.count("ALTER TABLE ingestion.documents") == 2


def test_rebuild_timeout_is_set_in_a_separate_statement_before_alter(migration, monkeypatch):
    statements = []
    monkeypatch.setattr(migration.op, "execute", lambda statement: statements.append(str(statement).strip()))

    migration.upgrade()

    alter_commands = [index for index, sql in enumerate(statements) if sql.startswith("ALTER TABLE")]
    assert len(alter_commands) == 1, "ALTER must start after a separate statement sets its timeout"
    alter_index = alter_commands[0]
    assert "SET LOCAL statement_timeout = '60s'" in statements[:alter_index]
    assert "SET LOCAL lock_timeout = '10s'" in statements[:alter_index]
    assert "current_setting('statement_timeout')" in statements[0]
    assert "current_setting('lock_timeout')" in statements[0]
    assert "set_config('statement_timeout'" in statements[-1]
    assert "set_config('lock_timeout'" in statements[-1]


@pytest.fixture
def db(migration, monkeypatch):
    url = guarded_live_database_url()
    if not url:
        skip_or_fail_db("requires an explicitly configured disposable PostgreSQL migrated to head")
    engine = create_engine(_normalize_psycopg(url), future=True)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                assert connection.execute(text("SELECT to_regclass('ingestion.documents')")).scalar()
                monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _keys(connection):
    return dict(
        connection.execute(
            text("""SELECT c.conname,
                       ARRAY(SELECT a.attname::text FROM unnest(c.conkey) WITH ORDINALITY k(n, i)
                             JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n
                             ORDER BY k.i)
                    FROM pg_constraint c
                    WHERE c.conrelid = 'ingestion.documents'::regclass AND c.contype = 'u'""")
        ).all()
    )


def _posture(connection):
    return connection.execute(
        text("""SELECT relrowsecurity, relforcerowsecurity FROM pg_class
                WHERE oid = 'ingestion.documents'::regclass""")
    ).one()


def _insert(connection, tenant, digest, *, document_id=None, storage_key="s3://legacy/document.json"):
    document_id = document_id or uuid4()
    connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant)})
    connection.execute(
        text("""INSERT INTO ingestion.documents
                (id, tenant_id, title, source_type, document_type, vertical,
                 content_sha256, content_sha512, source_url, fetch_timestamp, storage_key)
                VALUES (:id, :tenant, 'synthetic', 'url', 'regulation', 'test',
                        :digest, :sha512, 'https://example.com/test', now(), :storage_key)"""),
        {
            "id": document_id,
            "tenant": tenant,
            "digest": digest,
            "sha512": "a" * 128,
            "storage_key": storage_key,
        },
    )
    return document_id


@pytest.mark.parametrize("statement_timeout", ["0", "2min"])
def test_upgrade_preserves_legacy_rows_and_scopes_uniqueness(db, migration, statement_timeout):
    db.execute(text("SELECT set_config('statement_timeout', :value, true)"), {"value": statement_timeout})
    db.execute(text("SET LOCAL lock_timeout = '1234ms'"))
    original_statement_timeout = db.execute(text("SELECT current_setting('statement_timeout')")).scalar_one()
    migration.downgrade()
    assert db.execute(text("SELECT current_setting('statement_timeout')")).scalar_one() == original_statement_timeout
    assert db.execute(text("SELECT current_setting('lock_timeout')")).scalar_one() == "1234ms"
    tenant_a, tenant_b = uuid4(), uuid4()
    digest = uuid4().hex * 2
    legacy_id = _insert(db, tenant_a, digest)
    original_posture = _posture(db)
    original_timeout = db.execute(text("SELECT current_setting('lock_timeout')")).scalar_one()

    migration.upgrade()

    assert _keys(db)["uq_ingestion_documents_tenant_content_sha256"] == ["tenant_id", "content_sha256"]
    assert "documents_content_sha256_key" not in _keys(db)
    _insert(db, tenant_b, digest)
    with pytest.raises(IntegrityError), db.begin_nested():
        _insert(db, tenant_a, digest)
    db.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant_a)})
    assert db.execute(
        text("SELECT id, storage_key FROM ingestion.documents WHERE id = :id"), {"id": legacy_id}
    ).one() == (legacy_id, "s3://legacy/document.json")
    assert _posture(db) == original_posture
    assert db.execute(text("SELECT current_setting('lock_timeout')")).scalar_one() == original_timeout
    assert db.execute(text("SELECT current_setting('statement_timeout')")).scalar_one() == original_statement_timeout


def test_downgrade_refuses_cross_tenant_duplicates_without_losing_rows(db, migration):
    db.execute(text("SET LOCAL statement_timeout = '2min'"))
    db.execute(text("SET LOCAL lock_timeout = '1234ms'"))
    tenant_a, tenant_b = uuid4(), uuid4()
    digest = uuid4().hex * 2
    first = _insert(db, tenant_a, digest)
    second = _insert(db, tenant_b, digest)
    original_posture = _posture(db)

    with pytest.raises(IntegrityError), db.begin_nested():
        migration.downgrade()

    assert "uq_ingestion_documents_tenant_content_sha256" in _keys(db)
    assert _posture(db) == original_posture
    assert db.execute(text("SELECT current_setting('statement_timeout')")).scalar_one() == "2min"
    assert db.execute(text("SELECT current_setting('lock_timeout')")).scalar_one() == "1234ms"
    for tenant, document_id in ((tenant_a, first), (tenant_b, second)):
        db.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant)})
        assert (
            db.execute(
                text("SELECT storage_key FROM ingestion.documents WHERE id = :id"), {"id": document_id}
            ).scalar_one()
            == "s3://legacy/document.json"
        )
