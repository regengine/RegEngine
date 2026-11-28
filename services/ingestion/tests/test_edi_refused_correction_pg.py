"""A refused EDI correction must leave a durable, tenant-scoped rejection record.

Real PostgreSQL through the real ``/document`` route. ``ingest_events``, the
line registry, the ISA13 receipt and ``persist_edi_rejection`` are the real
ones, and every statement runs as the ``regengine`` role under forced row
security. Only the event writers are stand-ins, as in
``test_edi_line_identity_pg.py``.

``services/ingestion/conftest.py`` replaces ``persist_edi_rejection`` for every
ingestion test. This module puts the real one back, so the rows asserted here
are written by the code the routes run in production.

Run with REGENGINE_MIGRATION_TEST_DB pointing to a disposable Postgres server.
CI runs this via the existing live test_*_pg.py gate.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app import webhook_compat as compat
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.edi_ingestion import dedup, rejection_log, router, routes
from app.edi_line_identity import LINE_CONFLICT_ERROR
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared import edi_rejection_audit
from shared.canonical_persistence import CanonicalEventStore
from shared.cte_persistence import CTEPersistence
from shared.cte_persistence.models import StoreResult
from shared.rules_engine import RulesEngine
from shared.tenant_context import set_tenant_guc
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from tests.edi_documents import GTIN, shipping_advice

from tests.migrations.scratch_db import scratch_database_engine

# Taken at import, before the conftest fixture swaps it out for each test.
_REAL_PERSIST = edi_rejection_audit.persist_edi_rejection

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = (
    "20261108_c4a9d2e761b0_v143_edi_interchanges.py",
    "20261121_62355c37e367_v145_edi_line_identities.py",
    "20261124_056ffd2f8045_v146_edi_rejections.py",
)
TABLES = ("fsma.cte_events", "fsma.edi_line_identities", "fsma.edi_interchanges", "fsma.edi_rejections")
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
LINES = [("40", "LOT-A"), ("25", "LOT-B"), ("80", "LOT-C")]
# The same document with LOT-B's shipped quantity corrected from 25 to 30.
CORRECTED = [LINES[0], ("30", "LOT-B"), LINES[2]]
NEW_ENVELOPE = {"isa13": "000000202", "gs06": "2", "st02": "0002"}

_SCHEMA = """
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'regengine') THEN
        CREATE ROLE regengine NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END $$;
CREATE SCHEMA fsma;
GRANT USAGE ON SCHEMA fsma TO regengine;
-- Fails hard without a tenant, as scripts/init-postgres.sh defines it.
CREATE FUNCTION public.get_tenant_context() RETURNS uuid LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    tid text;
BEGIN
    tid := nullif(current_setting('app.tenant_id', true), '');
    IF tid IS NULL THEN
        RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS';
    END IF;
    RETURN tid::uuid;
END
$fn$;
-- Stand-in for the event table: what the registry joins and the fake store writes.
CREATE TABLE fsma.cte_events (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    traceability_lot_code text NOT NULL,
    quantity double precision NOT NULL,
    sha256_hash text NOT NULL,
    chain_hash text NOT NULL
);
GRANT SELECT, INSERT ON fsma.cte_events TO regengine;
"""


def _migration(name: str):
    spec = importlib.util.spec_from_file_location(
        "edi_refusal_migration_" + name.split("_")[1], ROOT / "alembic/versions" / name
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def database():
    if not os.getenv("REGENGINE_MIGRATION_TEST_DB") and not (
        os.getenv("CI") == "true" and os.getenv("REGENGINE_REQUIRE_DB") == "1"
    ):
        pytest.skip("set REGENGINE_MIGRATION_TEST_DB to run live EDI refusal tests")
    with scratch_database_engine("edi_refusal_" + uuid4().hex[:12]) as engine:
        with engine.begin() as conn:
            conn.exec_driver_sql(_SCHEMA)
            with Operations.context(MigrationContext.configure(conn)):
                for name in MIGRATIONS:
                    _migration(name).upgrade()
        yield engine


@pytest.fixture()
def db(database):
    with database.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(TABLES)))
    return database


def _session(db) -> Session:
    """A session acting as the runtime role, so its grants and row security apply."""
    session = Session(db)
    session.execute(text("SET LOCAL ROLE regengine"))
    return session


def _counts(db) -> dict[str, int]:
    """Rows per table, read as the owner on a connection of its own."""
    with db.connect() as conn:
        return {table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in TABLES}


@pytest.fixture()
def stack(db, monkeypatch):
    """The real route, ingest, registry, receipt and rejection writer on the scratch database."""
    runs: list[str] = []

    def sessions() -> Iterator[Session]:
        with _session(db) as session:
            yield session

    def store(self, **kwargs: Any) -> StoreResult:
        event_id = str(uuid4())
        self.session.execute(
            text(
                "INSERT INTO fsma.cte_events VALUES "
                "(CAST(:id AS uuid), CAST(:tenant AS uuid), :lot, :quantity, 'sha', 'chain')"
            ),
            {
                "id": event_id,
                "tenant": kwargs["tenant_id"],
                "lot": kwargs["traceability_lot_code"],
                "quantity": kwargs["quantity"],
            },
        )
        return StoreResult(success=True, event_id=event_id, sha256_hash="sha", chain_hash="chain", idempotent=False)

    def open_run(session: Any, tenant_id: str, source: str, receipt: Any) -> str:
        """Stand-in for ``fsma.ingestion_runs``: one entry per document retained."""
        runs.append(receipt.sha256)
        return str(uuid4())

    monkeypatch.setattr(compat, "_get_db_session", sessions)
    monkeypatch.setattr(compat, "_verify_api_key_sync", lambda **kwargs: None)
    monkeypatch.setattr(compat, "_check_rate_limit", lambda *args: None)
    monkeypatch.setattr(compat, "_generate_alerts", lambda *args: [])
    monkeypatch.setattr(compat, "_publish_graph_sync", lambda *args: None)
    monkeypatch.setattr(compat, "record_outcomes", lambda *args: None)
    monkeypatch.setattr(compat, "_open_ingestion_run", open_run)
    monkeypatch.setattr(compat, "_close_ingestion_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(CTEPersistence, "store_event", store)
    monkeypatch.setattr(CanonicalEventStore, "persist_event", lambda self, event: SimpleNamespace(idempotent=False))
    monkeypatch.setattr(RulesEngine, "evaluate_event", lambda *args, **kwargs: SimpleNamespace(compliant=True))
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    # No cache: the ISA13 gate is the receipt in PostgreSQL.
    monkeypatch.setattr(dedup, "_redis_client", lambda: None)
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    monkeypatch.setattr(routes, "ingest_events", compat.ingest_events)
    # The rejection writer and the receipt peek open their own sessions.
    monkeypatch.setattr("shared.database.SessionLocal", lambda: _session(db))
    monkeypatch.setattr(edi_rejection_audit, "persist_edi_rejection", _REAL_PERSIST)
    rejection_log.reset_edi_rejections()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", tenant_id=TENANT, scopes=["*"], auth_mode="test"
    )

    def send(raw: bytes):
        with TestClient(app) as client:
            return client.post(
                "/api/v1/ingest/edi/document",
                data={
                    "tenant_id": TENANT,
                    "traceability_lot_code": f"{GTIN}-LOT001",
                    "tlc_source_reference": "0061414100001",
                },
                files={"file": ("advice.edi", raw, "application/edi-x12")},
            )

    return SimpleNamespace(send=send, runs=runs)


def _event_ids(response) -> list[str]:
    return [event["event_id"] for event in response.json()["ingestion_result"]["events"]]


def test_a_refused_correction_is_recorded_durably_for_its_tenant(db, stack) -> None:
    first = stack.send(shipping_advice(LINES))
    assert first.status_code == 201, first.text
    assert first.json()["ingestion_result"]["accepted"] == 3
    stored = _counts(db)
    assert stored == {
        "fsma.cte_events": 3,
        "fsma.edi_line_identities": 3,
        "fsma.edi_interchanges": 1,
        "fsma.edi_rejections": 0,
    }

    refused = stack.send(shipping_advice(CORRECTED, **NEW_ENVELOPE))

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["error"] == LINE_CONFLICT_ERROR
    assert detail["needs_review"] is True
    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT rejection_id, tenant_id, transaction_set, reason, needs_review, errors FROM fsma.edi_rejections"
            )
        ).all()
    assert len(rows) == 1
    rejection_id, tenant_id, transaction_set, reason, needs_review, errors = rows[0]
    assert rejection_id == detail["rejection_id"]
    assert (str(tenant_id), transaction_set, reason, needs_review) == (TENANT, "945", LINE_CONFLICT_ERROR, True)
    (error,) = errors
    assert (error["loc"], error["type"]) == (["line", 2], LINE_CONFLICT_ERROR)
    # The line as the partner submitted it, with the corrected quantity.
    assert (error["input"]["traceability_lot_code"], error["input"]["quantity"]) == (f"{GTIN}-LOT-B", 30.0)

    # Nothing else moved: no event, identity or receipt, and the document was not retained.
    assert _counts(db) == {**stored, "fsma.edi_rejections": 1}
    assert len(stack.runs) == 1
    with db.connect() as conn:
        quantity = conn.execute(
            text("SELECT quantity FROM fsma.cte_events WHERE traceability_lot_code = :lot"), {"lot": f"{GTIN}-LOT-B"}
        ).scalar_one()
    assert quantity == 25.0

    # The runtime role reads the row for its own tenant only, and cannot remove it.
    with _session(db) as session:
        set_tenant_guc(session, TENANT)
        assert session.execute(text("SELECT rejection_id FROM fsma.edi_rejections")).scalars().all() == [rejection_id]
        with pytest.raises(DBAPIError):
            session.execute(text("DELETE FROM fsma.edi_rejections"))
    with _session(db) as session:
        set_tenant_guc(session, OTHER_TENANT)
        assert session.execute(text("SELECT count(*) FROM fsma.edi_rejections")).scalar_one() == 0

    # The refused envelope left no receipt, so the unchanged document may still use its ISA13.
    resend = stack.send(shipping_advice(LINES, **NEW_ENVELOPE))
    assert resend.status_code == 201, resend.text
    assert _event_ids(resend) == _event_ids(first)
    assert _counts(db) == {**stored, "fsma.edi_interchanges": 2, "fsma.edi_rejections": 1}


def test_a_refusal_that_cannot_be_stored_answers_503_and_stores_nothing(db, stack) -> None:
    assert stack.send(shipping_advice(LINES)).status_code == 201
    stored = _counts(db)
    corrected = shipping_advice(CORRECTED, **NEW_ENVELOPE)

    # The runtime role loses the grant, so the real INSERT fails in the database.
    with db.begin() as conn:
        conn.execute(text("REVOKE INSERT ON fsma.edi_rejections FROM regengine"))
    try:
        unrecorded = stack.send(corrected)
    finally:
        with db.begin() as conn:
            conn.execute(text("GRANT INSERT ON fsma.edi_rejections TO regengine"))

    assert unrecorded.status_code == 503, unrecorded.text
    # No id for a record that does not exist, and no conflict detail either.
    assert "rejection_id" not in unrecorded.text
    assert LINE_CONFLICT_ERROR not in unrecorded.text
    assert _counts(db) == stored
    assert len(stack.runs) == 1
    assert rejection_log.list_edi_rejections(TENANT) == []

    # Nothing was stored and the ISA13 is free, so the same document sent again is refused with a record.
    retried = stack.send(corrected)
    assert retried.status_code == 409, retried.text
    with db.connect() as conn:
        recorded = conn.execute(text("SELECT rejection_id FROM fsma.edi_rejections")).scalars().all()
    assert recorded == [retried.json()["detail"]["rejection_id"]]
    assert _counts(db) == {**stored, "fsma.edi_rejections": 1}
