"""Supplier records round-trip through ``fsma.tenant_suppliers`` — live Postgres.

``supplier_mgmt`` and ``supplier_validation`` treated the ``TEXT[]`` columns
``missing_kdes`` and ``products`` as JSON strings:

- ``_db_add_supplier`` bound ``json.dumps(list)``. Postgres rejected the
  array literal ``"[]"`` for every supplier, including ones with empty
  lists, and the resulting ``DataError`` was outside the except tuple, so
  ``POST /api/v1/suppliers/{tenant_id}`` raised instead of falling back.
- ``_db_get_suppliers`` and ``_fetch_suppliers`` called ``json.loads`` on
  the Python lists the driver returns. A row with a populated array raised
  ``TypeError``, the broad except returned ``None``, and the dashboard and
  the whole validation report came back empty for the tenant.

The ``id`` column is ``UUID``: the router generated ``{tenant}-sup-001`` ids
that Postgres rejects, and both readers handed the driver's ``uuid.UUID``
(and the ``datetime`` of ``last_submission``) to ``str`` pydantic fields.

The unit tests in ``test_supplier_mgmt_1342.py`` and
``test_supplier_validation_1342.py`` run against mocked sessions that never
parse SQL or type a bind, so they passed throughout. This module writes
through the real ``_db_add_supplier`` and reads back through both readers on
a real cluster at alembic head. Every test seeds a second tenant whose rows
would change the result if a statement lost its tenant filter.

Skips cleanly when no migrated Postgres is reachable, except under
``REGENGINE_REQUIRE_DB=1`` where an unreachable database fails rather than
skipping (#2530).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from shared.db_url import sync_postgres_url

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

DSN = os.environ.get(
    "REMEDIATION_TEST_SUPERUSER_DSN",
    "postgresql://regengine:regengine@localhost:55432/regengine",  # pragma: allowlist secret — throwaway scratch-DB role
)


def _schema_ready(dsn: str) -> bool:
    """True when a migrated database carrying ``fsma.tenant_suppliers`` is up."""
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(sync_postgres_url(dsn), pool_pre_ping=True)
        with engine.connect() as conn:
            found = conn.execute(text("SELECT to_regclass('fsma.tenant_suppliers') IS NOT NULL")).scalar()
        engine.dispose()
        return bool(found)
    except Exception:
        return False


_DB_READY = _schema_ready(DSN)

if not _DB_READY and os.environ.get("REGENGINE_REQUIRE_DB") == "1":
    raise RuntimeError(f"REGENGINE_REQUIRE_DB=1 but no migrated Postgres is reachable at {DSN!r} — refusing to skip.")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _DB_READY, reason="migrated Postgres with fsma schema not available"),
]


@pytest.fixture()
def conn(monkeypatch):
    """A connection whose transaction is rolled back, with the modules' sessions bound to it.

    Seeds are never committed: ``_db_add_supplier`` commits a savepoint of
    this transaction, every read runs in another, and the whole transaction
    is rolled back at teardown. Both modules call ``get_db_safe``, which
    reads ``SessionLocal`` from ``shared.database`` at call time, so the
    attribute is patched there.
    """
    import shared.database as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(sync_postgres_url(DSN))
    with engine.connect() as connection:
        outer = connection.begin()
        monkeypatch.setattr(
            db_mod,
            "SessionLocal",
            sessionmaker(bind=connection, join_transaction_mode="create_savepoint"),
        )
        try:
            yield connection
        finally:
            outer.rollback()
    engine.dispose()


@pytest.fixture(autouse=True)
def _isolate_module_state(monkeypatch):
    """No in-memory fallback rows or cached reports leak between tests; reports are not persisted."""
    from app import supplier_mgmt as sm, supplier_validation as sv

    sm._suppliers_store.clear()
    sv._reports_store.clear()
    monkeypatch.setattr(sv, "set_tenant_data", lambda tid, a, b, d: True)
    yield
    sm._suppliers_store.clear()
    sv._reports_store.clear()


def _record(**overrides):
    from app.supplier_mgmt import SupplierRecord

    fields = dict(
        id=str(uuid.uuid4()),
        name="Acme Farms",
        contact_email="contact@acme.example",
        portal_status="no_link",
        compliance_status="unknown",
    )
    fields.update(overrides)
    return SupplierRecord(**fields)


@pytest.fixture()
def seeded(conn, caplog):
    """Two suppliers for one tenant (populated arrays, empty arrays); another tenant's supplier shares the name."""
    from app import supplier_mgmt as sm

    tenant_id, other_tenant_id = str(uuid.uuid4()), str(uuid.uuid4())
    last_submission = (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat()
    full = _record(
        products=["Romaine", "Spinach"],
        missing_kdes=["traceability_lot_code", "gln"],
        submissions_count=3,
        last_submission=last_submission,
        compliance_status="partial",
    )
    bare = _record(name="Bare Farms", products=[], missing_kdes=[])
    # Same name as ``full``: a lost tenant filter would surface its "Leak" arrays.
    leak = _record(name=full.name, products=["Leak"], missing_kdes=["leak"])

    assert sm._db_add_supplier(tenant_id, full) is True, caplog.text
    assert sm._db_add_supplier(tenant_id, bare) is True, caplog.text
    assert sm._db_add_supplier(other_tenant_id, leak) is True, caplog.text
    return tenant_id, full, bare


# ---------------------------------------------------------------------------
# _db_add_supplier -> _db_get_suppliers (supplier_mgmt)
# ---------------------------------------------------------------------------


def test_db_get_suppliers_returns_the_tenants_rows_with_their_arrays(seeded, caplog):
    """Both rows come back as records with list fields. A lost tenant filter would add the "Leak" row."""
    from app import supplier_mgmt as sm

    tenant_id, full, bare = seeded

    records = sm._db_get_suppliers(tenant_id)

    assert records is not None, caplog.text  # None means db_read_failed: the fallback hid the rows
    by_id = {record.id: record for record in records}
    assert set(by_id) == {full.id, bare.id}
    assert by_id[full.id].products == ["Romaine", "Spinach"]
    assert by_id[full.id].missing_kdes == ["traceability_lot_code", "gln"]
    assert by_id[full.id].submissions_count == 3
    assert by_id[full.id].compliance_status == "partial"
    assert datetime.fromisoformat(by_id[full.id].last_submission) == datetime.fromisoformat(full.last_submission)
    assert by_id[bare.id].products == []
    assert by_id[bare.id].missing_kdes == []
    assert by_id[bare.id].last_submission is None


def test_db_get_suppliers_for_a_tenant_with_no_rows_is_empty_not_none(seeded):
    from app import supplier_mgmt as sm

    assert sm._db_get_suppliers(str(uuid.uuid4())) == []


def test_add_supplier_endpoint_persists_through_the_database_not_memory(conn, caplog):
    """The router's id is accepted by the UUID column, so the row lands in Postgres and no fallback copy is kept."""
    from app import supplier_mgmt as sm

    tenant_id = str(uuid.uuid4())
    request = sm.CreateSupplierRequest(name="Via Endpoint", contact_email="via@acme.example", products=["Kale"])

    body = asyncio.run(sm.add_supplier(tenant_id, request, ctx=SimpleNamespace(tenant_id=tenant_id)))

    assert body["created"] is True
    supplier_id = uuid.UUID(body["supplier"]["id"])
    assert tenant_id not in sm._suppliers_store, "the write fell back to memory"
    records = sm._db_get_suppliers(tenant_id)
    assert records is not None, caplog.text
    assert [(record.id, record.name, record.products) for record in records] == [
        (str(supplier_id), "Via Endpoint", ["Kale"])
    ]


def test_send_portal_link_updates_the_persisted_row_in_place(seeded, caplog):
    """The ON CONFLICT branch rewrites the row (arrays included) rather than inserting a second one."""
    from app import supplier_mgmt as sm

    tenant_id, full, bare = seeded

    body = asyncio.run(sm.send_portal_link(tenant_id, full.id, ctx=SimpleNamespace(tenant_id=tenant_id)))

    assert body["sent"] is True, body
    records = sm._db_get_suppliers(tenant_id)
    assert records is not None, caplog.text
    assert len(records) == 2
    updated = next(record for record in records if record.id == full.id)
    assert updated.portal_status == "active"
    assert updated.portal_link_id == f"portal-{full.id[-3:]}-new"
    assert updated.products == ["Romaine", "Spinach"]
    assert updated.missing_kdes == ["traceability_lot_code", "gln"]
    assert datetime.fromisoformat(updated.last_submission) == datetime.fromisoformat(full.last_submission)


@pytest.fixture(params=["SELECT", "SELECT, INSERT"], ids=["select-only", "missing-update"])
def restricted_client(conn, seeded, request):
    """Exercise real ACL failures in the enclosing rollback-only test transaction.

    SELECT-only mirrors v111's supplier runtime grant; INSERT without UPDATE
    also cannot execute the router's ON CONFLICT upsert. No existing role is
    modified, and the synthetic role, grants and tenant-scoped SELECT policy
    roll back with ``conn``. The policy lets this role read on migrated databases
    whose RLS policies otherwise apply only to the named application roles.
    """
    from app import supplier_mgmt as sm
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    tenant_id, full, bare = seeded
    role = f"supplier_qa_{uuid.uuid4().hex}"
    conn.execute(text(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS"))
    conn.execute(text(f"GRANT USAGE ON SCHEMA fsma TO {role}"))
    conn.execute(text(f"GRANT {request.param} ON fsma.tenant_suppliers TO {role}"))
    conn.execute(
        text(
            f"CREATE POLICY {role} ON fsma.tenant_suppliers FOR SELECT TO {role} "
            "USING (tenant_id::text = current_setting('app.tenant_id', true))"
        )
    )
    conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_id})
    conn.execute(text(f"SET LOCAL ROLE {role}"))
    assert conn.execute(text("SELECT current_user")).scalar() == role
    assert conn.execute(text("SELECT has_table_privilege(current_user, 'fsma.tenant_suppliers', 'SELECT')")).scalar()
    assert not conn.execute(
        text("SELECT has_table_privilege(current_user, 'fsma.tenant_suppliers', 'UPDATE')")
    ).scalar()
    assert {record.id for record in sm._db_get_suppliers(tenant_id)} == {full.id, bare.id}

    app = FastAPI()
    app.include_router(sm.router)
    app.dependency_overrides[sm.require_tenant_context] = lambda: SimpleNamespace(tenant_id=tenant_id)
    with TestClient(app) as client:
        yield client


def test_permission_denied_create_reports_failure_without_memory_success(restricted_client, seeded):
    from app import supplier_mgmt as sm

    tenant_id, full, bare = seeded
    response = restricted_client.post(
        f"/api/v1/suppliers/{tenant_id}",
        json={"name": "Denied Farms", "contact_email": "denied@example.test", "products": ["Kale"]},
    )

    assert response.status_code == 503, response.json()
    assert response.json() == {"detail": "Supplier changes could not be saved"}
    assert sm._suppliers_store == {}
    assert {record.id for record in sm._db_get_suppliers(tenant_id)} == {full.id, bare.id}


def test_permission_denied_send_link_does_not_report_sent_or_change_row(restricted_client, seeded):
    from app import supplier_mgmt as sm

    tenant_id, full, _ = seeded
    response = restricted_client.post(f"/api/v1/suppliers/{tenant_id}/{full.id}/send-link")

    assert response.status_code == 503, response.json()
    assert response.json() == {"detail": "Supplier changes could not be saved"}
    assert sm._suppliers_store == {}
    persisted = next(record for record in sm._db_get_suppliers(tenant_id) if record.id == full.id)
    assert persisted.portal_status == "no_link"
    assert persisted.portal_link_id is None


# ---------------------------------------------------------------------------
# _fetch_suppliers and the validation endpoints (supplier_validation)
# ---------------------------------------------------------------------------


def test_fetch_suppliers_returns_the_tenants_rows_with_their_arrays(seeded, caplog):
    from app import supplier_validation as sv

    tenant_id, full, bare = seeded

    rows = sv._fetch_suppliers(tenant_id)

    assert rows is not None, caplog.text  # None means db_read_failed: the report would be empty
    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {full.id, bare.id}  # str ids, not uuid.UUID
    assert by_id[full.id]["products"] == ["Romaine", "Spinach"]
    assert by_id[full.id]["missing_kdes"] == ["traceability_lot_code", "gln"]
    assert by_id[full.id]["name"] == full.name
    assert by_id[bare.id]["products"] == []
    assert by_id[bare.id]["missing_kdes"] == []


def test_validation_endpoints_score_the_persisted_suppliers(seeded):
    """The report covers both rows and a single-supplier validation finds its row by id."""
    from app import supplier_validation as sv

    tenant_id, full, bare = seeded
    ctx = SimpleNamespace(tenant_id=tenant_id)

    report = asyncio.run(sv.validate_all_suppliers(tenant_id, ctx=ctx))
    single = asyncio.run(sv.validate_single_supplier(tenant_id, full.id, ctx=ctx))

    assert report.total_suppliers == 2
    assert {result.supplier_id for result in report.suppliers} == {full.id, bare.id}
    assert single.supplier_name == full.name  # not the "Unknown" placeholder
    assert single.supplier_id == full.id
    recent = next(check for check in single.checks if check.name == "recent_submission")
    assert recent.passed is True  # the stored last_submission is 2 days old
    assert "Missing CTE types" in next(check for check in single.checks if check.name == "cte_type_coverage").details
