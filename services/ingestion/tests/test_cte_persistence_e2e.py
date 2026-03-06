"""
FSMA 204 CTE Persistence — End-to-End Integration Test.

Covers the complete traceability chain that RegEngine promises:
    Ingest events → Verify hash chain → Query by TLC → FDA export → Verify export hash

Uses a real Postgres container (testcontainers). Requires Docker.

Run these tests:
    pytest services/ingestion/tests/test_cte_persistence_e2e.py -v -m integration

Skip in CI where Docker is unavailable:
    pytest -m "not integration"
"""

from __future__ import annotations

import csv
import hashlib
import io
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

# Ensure services/ is on sys.path for shared imports
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

# ---------------------------------------------------------------------------
# Optional-dependency guards — tests are skipped cleanly if Docker/libs absent
# ---------------------------------------------------------------------------

try:
    from testcontainers.postgres import PostgresContainer
    _HAS_TESTCONTAINERS = True
except ImportError:
    _HAS_TESTCONTAINERS = False

try:
    import psycopg2  # noqa: F401
    _HAS_PSYCOPG2 = True
except ImportError:
    _HAS_PSYCOPG2 = False

_SKIP_REASON = "testcontainers[postgresql] and psycopg2 required (pip install testcontainers[postgresql] psycopg2-binary)"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_HAS_TESTCONTAINERS and _HAS_PSYCOPG2),
        reason=_SKIP_REASON,
    ),
]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_MIGRATION_V002 = _REPO_ROOT / "migrations" / "V002__fsma_cte_persistence.sql"

# ---------------------------------------------------------------------------
# Preamble: objects the V002 migration depends on
# (normally in a V001 base migration; created here for test isolation)
# ---------------------------------------------------------------------------

_PREAMBLE_STMTS = [
    # pgcrypto provides gen_random_uuid()
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    # role referenced in RLS policies
    "CREATE ROLE IF NOT EXISTS regengine",
    # get_tenant_context() is the RLS policy function
    """
    CREATE OR REPLACE FUNCTION get_tenant_context()
    RETURNS UUID AS $$
    DECLARE
        raw TEXT;
    BEGIN
        raw := current_setting('regengine.tenant_id', true);
        IF raw IS NULL OR raw = '' THEN
            RETURN NULL;
        END IF;
        RETURN raw::UUID;
    EXCEPTION WHEN OTHERS THEN
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql
    """,
]


def _split_sql_statements(sql_text: str) -> list[str]:
    """
    Split a SQL file into individual executable statements.

    Strips comment lines and splits on semicolons. Safe for the V002
    migration file (no dollar-quoting or embedded semicolons in DDL).
    Skips bare BEGIN/COMMIT since we manage the transaction ourselves.
    """
    lines = [
        line for line in sql_text.splitlines()
        if not line.strip().startswith("--")
    ]
    stmts = []
    for stmt in "\n".join(lines).split(";"):
        stmt = stmt.strip()
        if stmt and stmt.upper() not in ("BEGIN", "COMMIT"):
            stmts.append(stmt)
    return stmts


# ---------------------------------------------------------------------------
# Inline FDA CSV generator
# (mirrors fda_export_router._generate_csv — intentional duplication so the
#  test doesn't depend on the production module for column layout assertions)
# ---------------------------------------------------------------------------

_FDA_COLUMNS = [
    "Traceability Lot Code (TLC)", "Product Description", "Quantity",
    "Unit of Measure", "Event Type (CTE)", "Event Date", "Event Time",
    "Location GLN", "Location Name", "Ship From GLN", "Ship From Name",
    "Ship To GLN", "Ship To Name", "Immediate Previous Source",
    "TLC Source GLN", "TLC Source FDA Registration", "Source Document",
    "Record Hash (SHA-256)", "Chain Hash",
]


def _event_to_row(event: dict) -> dict:
    kdes = event.get("kdes", {})
    ts = event.get("event_timestamp", "")
    event_date = event_time = ""
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            event_date = dt.strftime("%Y-%m-%d")
            event_time = dt.strftime("%H:%M:%S %Z")
        except (ValueError, AttributeError):
            event_date = str(ts)[:10]
    return {
        "Traceability Lot Code (TLC)": event.get("traceability_lot_code", ""),
        "Product Description": event.get("product_description", ""),
        "Quantity": event.get("quantity", ""),
        "Unit of Measure": event.get("unit_of_measure", ""),
        "Event Type (CTE)": event.get("event_type", ""),
        "Event Date": event_date,
        "Event Time": event_time,
        "Location GLN": event.get("location_gln") or "",
        "Location Name": event.get("location_name") or "",
        "Ship From GLN": kdes.get("ship_from_gln", ""),
        "Ship From Name": kdes.get("ship_from_location", ""),
        "Ship To GLN": kdes.get("ship_to_gln", ""),
        "Ship To Name": kdes.get("ship_to_location", kdes.get("receiving_location", "")),
        "Immediate Previous Source": kdes.get("immediate_previous_source", ""),
        "TLC Source GLN": kdes.get("tlc_source_gln", ""),
        "TLC Source FDA Registration": kdes.get("tlc_source_fda_reg", ""),
        "Source Document": event.get("source", ""),
        "Record Hash (SHA-256)": event.get("sha256_hash", ""),
        "Chain Hash": event.get("chain_hash", ""),
    }


def _generate_csv(events: list) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=_FDA_COLUMNS)
    writer.writeheader()
    for event in events:
        writer.writerow(_event_to_row(event))
    return out.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def postgres_engine():
    """
    Start a Postgres 15 container, run the FSMA V002 migration, and yield
    a SQLAlchemy engine. The container is torn down after the module.

    Runs as the container's default superuser — superusers bypass RLS
    automatically, so we can read/write any tenant's data in tests.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    assert _MIGRATION_V002.exists(), (
        f"Migration file not found: {_MIGRATION_V002}\n"
        "Ensure the repo root is correct and V002 has been created."
    )

    with PostgresContainer("postgres:15-alpine") as pg:
        host = pg.get_container_host_ip()
        port = pg.get_exposed_port(5432)
        db = pg.POSTGRES_DB
        user = pg.POSTGRES_USER
        password = pg.POSTGRES_PASSWORD

        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
        engine = create_engine(url, echo=False)

        # Run preamble + migration using AUTOCOMMIT so each DDL statement
        # is its own transaction (matches how migrations run in production).
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for stmt in _PREAMBLE_STMTS:
                try:
                    conn.execute(text(stmt))
                except OperationalError as exc:
                    # Tolerate "already exists" errors (idempotent preamble)
                    if "already exists" not in str(exc).lower():
                        raise

            migration_sql = _MIGRATION_V002.read_text()
            for stmt in _split_sql_statements(migration_sql):
                conn.execute(text(stmt))

        yield engine


@pytest.fixture
def db_session(postgres_engine):
    """
    Yield a fresh SQLAlchemy session for each test.

    Tests use unique tenant IDs (via _fresh_tenant()) for isolation —
    no rollback needed between tests.
    """
    from sqlalchemy.orm import Session
    with Session(postgres_engine) as sess:
        yield sess


def _fresh_tenant() -> str:
    """Unique UUID string — ensures per-test DB isolation without rollbacks."""
    return str(uuid4())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCTEPersistenceE2E:
    """
    End-to-end integration tests for the FSMA 204 CTE persistence layer.

    Each test method uses a unique tenant_id generated by _fresh_tenant(),
    ensuring complete data isolation even though tests share one Postgres
    instance. No rollbacks or DB truncations are needed.
    """

    # -----------------------------------------------------------------------
    # 1. Basic store — hashes are present and mathematically correct
    # -----------------------------------------------------------------------

    def test_store_single_event_returns_valid_hashes(self, db_session):
        """
        Storing a single event must return a 64-char SHA-256 hash and a
        chain_hash that matches the genesis formula (no previous event).
        """
        from shared.cte_persistence import CTEPersistence, compute_event_hash, compute_chain_hash

        tenant_id = _fresh_tenant()
        p = CTEPersistence(db_session)

        result = p.store_event(
            tenant_id=tenant_id,
            event_type="harvesting",
            traceability_lot_code="TOM-E2E-001",
            product_description="Roma Tomatoes",
            quantity=500.0,
            unit_of_measure="cases",
            event_timestamp="2026-03-01T00:00:00+00:00",
            source="e2e_test",
            location_name="Valley Fresh Farms",
            kdes={"harvest_date": "2026-03-01", "field_id": "FIELD-A7"},
        )
        db_session.commit()

        assert result.success is True
        assert result.event_id is not None
        assert len(result.sha256_hash) == 64, "sha256_hash must be a 64-char hex string"
        assert len(result.chain_hash) == 64, "chain_hash must be a 64-char hex string"
        assert result.idempotent is False

        # Recompute hashes manually from the returned event_id and verify
        expected_sha256 = compute_event_hash(
            result.event_id, "harvesting", "TOM-E2E-001",
            "Roma Tomatoes", 500.0, "cases",
            None, "Valley Fresh Farms", "2026-03-01T00:00:00+00:00",
            {"harvest_date": "2026-03-01", "field_id": "FIELD-A7"},
        )
        # Genesis: no previous chain → previous_chain_hash = None → seed = "GENESIS"
        expected_chain = compute_chain_hash(expected_sha256, None)

        assert result.sha256_hash == expected_sha256, "SHA-256 hash does not match recomputed value"
        assert result.chain_hash == expected_chain, "Chain hash (genesis) does not match recomputed value"

    # -----------------------------------------------------------------------
    # 2. Sequential chain linkage
    # -----------------------------------------------------------------------

    def test_chain_hashes_link_sequentially(self, db_session):
        """
        Chain hashes must satisfy: chain[N] = SHA-256(chain[N-1] | sha256[N]).
        Verified for a 3-event sequence: harvest → cooling → shipping.
        """
        from shared.cte_persistence import CTEPersistence, compute_chain_hash

        tenant_id = _fresh_tenant()
        p = CTEPersistence(db_session)

        r1 = p.store_event(
            tenant_id=tenant_id, event_type="harvesting",
            traceability_lot_code="CHAIN-001", product_description="Leaf Lettuce",
            quantity=200.0, unit_of_measure="cases",
            event_timestamp="2026-03-01T08:00:00+00:00", source="e2e_test",
            kdes={"harvest_date": "2026-03-01"},
        )
        r2 = p.store_event(
            tenant_id=tenant_id, event_type="cooling",
            traceability_lot_code="CHAIN-001", product_description="Leaf Lettuce",
            quantity=200.0, unit_of_measure="cases",
            event_timestamp="2026-03-01T12:00:00+00:00", source="e2e_test",
            kdes={"cooling_date": "2026-03-01", "temperature_celsius": "2.5"},
        )
        r3 = p.store_event(
            tenant_id=tenant_id, event_type="shipping",
            traceability_lot_code="CHAIN-001", product_description="Leaf Lettuce",
            quantity=200.0, unit_of_measure="cases",
            event_timestamp="2026-03-02T06:00:00+00:00", source="e2e_test",
            kdes={"ship_date": "2026-03-02", "ship_from_location": "Farm", "ship_to_location": "DC"},
        )
        db_session.commit()

        # r1: genesis   → chain = SHA-256("GENESIS" | sha256_1)
        # r2: prev=r1   → chain = SHA-256(r1.chain_hash | sha256_2)
        # r3: prev=r2   → chain = SHA-256(r2.chain_hash | sha256_3)
        assert r1.chain_hash == compute_chain_hash(r1.sha256_hash, None)
        assert r2.chain_hash == compute_chain_hash(r2.sha256_hash, r1.chain_hash)
        assert r3.chain_hash == compute_chain_hash(r3.sha256_hash, r2.chain_hash)

    # -----------------------------------------------------------------------
    # 3. verify_chain() — clean chain
    # -----------------------------------------------------------------------

    def test_verify_chain_valid_on_clean_chain(self, db_session):
        """verify_chain() must return valid=True and the correct chain_length."""
        from shared.cte_persistence import CTEPersistence

        tenant_id = _fresh_tenant()
        p = CTEPersistence(db_session)

        for i in range(4):
            p.store_event(
                tenant_id=tenant_id, event_type="harvesting",
                traceability_lot_code=f"VERIFY-{i:03d}",
                product_description="Spinach", quantity=100.0 + i, unit_of_measure="lbs",
                event_timestamp=f"2026-03-0{i+1}T00:00:00+00:00", source="e2e_test",
                kdes={"harvest_date": f"2026-03-0{i+1}"},
            )
        db_session.commit()

        result = p.verify_chain(tenant_id)

        assert result.valid is True, f"Chain should be valid. Errors: {result.errors}"
        assert result.chain_length == 4
        assert result.errors == []
        assert result.checked_at is not None

    # -----------------------------------------------------------------------
    # 4. verify_chain() — tamper detection
    # -----------------------------------------------------------------------

    def test_verify_chain_detects_tampered_hash(self, postgres_engine, db_session):
        """
        Corrupting a stored chain_hash must be caught by verify_chain().
        This proves the chain walk actually recomputes and compares values
        rather than just reading them.
        """
        from sqlalchemy import text
        from sqlalchemy.orm import Session
        from shared.cte_persistence import CTEPersistence

        tenant_id = _fresh_tenant()
        p = CTEPersistence(db_session)

        for i in range(3):
            p.store_event(
                tenant_id=tenant_id, event_type="receiving",
                traceability_lot_code="TAMPER-001", product_description="Strawberries",
                quantity=50.0, unit_of_measure="flats",
                event_timestamp=f"2026-03-{i+1:02d}T00:00:00+00:00", source="e2e_test",
                kdes={"receive_date": f"2026-03-{i+1:02d}", "receiving_location": "Warehouse"},
            )
        db_session.commit()

        # Surgically corrupt the chain_hash of sequence_num=2
        with postgres_engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE fsma.hash_chain
                    SET chain_hash = 'deadbeef' || SUBSTRING(chain_hash FROM 9)
                    WHERE tenant_id = :tid AND sequence_num = 2
                """),
                {"tid": tenant_id},
            )
            conn.commit()

        # New session so we read fresh DB state (not cached)
        with Session(postgres_engine) as verify_session:
            result = CTEPersistence(verify_session).verify_chain(tenant_id)

        assert result.valid is False, "Tampered chain must fail verification"
        assert len(result.errors) > 0
        # The tamper is at seq=2; the linkage break cascades to seq=3
        assert any("seq=2" in e or "Tamper" in e for e in result.errors), (
            f"Expected tamper error at seq=2. Got errors: {result.errors}"
        )

    # -----------------------------------------------------------------------
    # 5. verify_chain() — empty tenant
    # -----------------------------------------------------------------------

    def test_verify_chain_empty_tenant_is_valid(self, db_session):
        """A tenant with no events has a trivially valid chain of length 0."""
        from shared.cte_persistence import CTEPersistence

        result = CTEPersistence(db_session).verify_chain(_fresh_tenant())

        assert result.valid is True
        assert result.chain_length == 0
        assert result.errors == []

    # -----------------------------------------------------------------------
    # 6. Idempotency
    # -----------------------------------------------------------------------

    def test_idempotent_ingestion_stores_only_once(self, db_session):
        """
        Ingesting the same event twice must succeed both times but only
        write one record. The second call returns idempotent=True with the
        same event_id as the first.
        """
        from shared.cte_persistence import CTEPersistence

        tenant_id = _fresh_tenant()
        p = CTEPersistence(db_session)
        kwargs = dict(
            tenant_id=tenant_id, event_type="harvesting",
            traceability_lot_code="IDEM-001", product_description="Kale",
            quantity=300.0, unit_of_measure="cases",
            event_timestamp="2026-03-05T00:00:00+00:00", source="e2e_test",
            kdes={"harvest_date": "2026-03-05"},
        )

        r1 = p.store_event(**kwargs)
        db_session.commit()

        r2 = p.store_event(**kwargs)
        db_session.commit()

        assert r1.idempotent is False
        assert r2.idempotent is True
        assert r1.event_id == r2.event_id
        assert r1.sha256_hash == r2.sha256_hash

        # Chain should have exactly one entry for this tenant
        chain = p.verify_chain(tenant_id)
        assert chain.chain_length == 1

    # -----------------------------------------------------------------------
    # 7. Multi-tenant isolation
    # -----------------------------------------------------------------------

    def test_multi_tenant_isolation(self, db_session):
        """
        Events written by tenant A must be invisible to tenant B queries,
        even when querying the same TLC.
        """
        from shared.cte_persistence import CTEPersistence

        tenant_a, tenant_b = _fresh_tenant(), _fresh_tenant()
        p = CTEPersistence(db_session)
        shared_tlc = "CROSS-TENANT-001"

        p.store_event(
            tenant_id=tenant_a, event_type="harvesting",
            traceability_lot_code=shared_tlc, product_description="Cilantro",
            quantity=100.0, unit_of_measure="bunches",
            event_timestamp="2026-03-01T00:00:00+00:00", source="e2e_test",
            kdes={"harvest_date": "2026-03-01"},
        )
        db_session.commit()

        # Tenant B should see nothing for this TLC
        events_b = p.query_events_by_tlc(tenant_b, shared_tlc)
        assert len(events_b) == 0, "Tenant B must not see Tenant A's events"

        # Tenant A should see their own event
        events_a = p.query_events_by_tlc(tenant_a, shared_tlc)
        assert len(events_a) == 1

    # -----------------------------------------------------------------------
    # 8. query_events_by_tlc — ordering and KDE population
    # -----------------------------------------------------------------------

    def test_query_events_by_tlc_returns_chronological_order_with_kdes(self, db_session):
        """
        query_events_by_tlc must return events in ascending event_timestamp
        order with KDEs populated.
        """
        from shared.cte_persistence import CTEPersistence

        tenant_id = _fresh_tenant()
        p = CTEPersistence(db_session)
        tlc = "QUERY-ORDER-001"

        # Insert in reverse order to confirm ORDER BY is doing the work
        p.store_event(
            tenant_id=tenant_id, event_type="receiving", traceability_lot_code=tlc,
            product_description="Tomatoes", quantity=100.0, unit_of_measure="cases",
            event_timestamp="2026-03-03T00:00:00+00:00", source="e2e_test",
            kdes={"receive_date": "2026-03-03", "receiving_location": "DC"},
        )
        p.store_event(
            tenant_id=tenant_id, event_type="shipping", traceability_lot_code=tlc,
            product_description="Tomatoes", quantity=100.0, unit_of_measure="cases",
            event_timestamp="2026-03-02T00:00:00+00:00", source="e2e_test",
            kdes={"ship_date": "2026-03-02", "ship_from_location": "Farm", "ship_to_location": "DC"},
        )
        p.store_event(
            tenant_id=tenant_id, event_type="harvesting", traceability_lot_code=tlc,
            product_description="Tomatoes", quantity=100.0, unit_of_measure="cases",
            event_timestamp="2026-03-01T00:00:00+00:00", source="e2e_test",
            kdes={"harvest_date": "2026-03-01"},
        )
        db_session.commit()

        events = p.query_events_by_tlc(tenant_id, tlc)

        assert len(events) == 3
        assert [e["event_type"] for e in events] == ["harvesting", "shipping", "receiving"]
        assert events[0]["kdes"]["harvest_date"] == "2026-03-01"
        assert events[1]["kdes"]["ship_from_location"] == "Farm"
        assert events[2]["kdes"]["receiving_location"] == "DC"

    # -----------------------------------------------------------------------
    # 9. FDA export CSV structure
    # -----------------------------------------------------------------------

    def test_fda_export_csv_has_correct_columns_and_data(self, db_session):
        """
        The FDA export CSV must contain all 19 required columns and
        correctly map event fields to the FDA spreadsheet layout.
        """
        from shared.cte_persistence import CTEPersistence

        tenant_id = _fresh_tenant()
        p = CTEPersistence(db_session)
        tlc = "FDA-COL-001"

        p.store_event(
            tenant_id=tenant_id, event_type="harvesting", traceability_lot_code=tlc,
            product_description="Basil", quantity=50.0, unit_of_measure="cases",
            event_timestamp="2026-03-01T00:00:00+00:00", source="e2e_test",
            location_name="Herb Farm", location_gln="0614141000009",
            kdes={"harvest_date": "2026-03-01", "tlc_source_gln": "0614141000009"},
        )
        db_session.commit()

        events = p.query_events_by_tlc(tenant_id, tlc)
        csv_content = _generate_csv(events)

        rows = list(csv.DictReader(io.StringIO(csv_content)))
        assert len(rows) == 1, "Expected exactly 1 CSV row"

        row = rows[0]
        # Check every required column exists in the output
        for col in _FDA_COLUMNS:
            assert col in row, f"Missing FDA column: {col}"

        # Spot-check specific field mappings
        assert row["Traceability Lot Code (TLC)"] == tlc
        assert row["Product Description"] == "Basil"
        assert row["Event Type (CTE)"] == "harvesting"
        assert row["Location GLN"] == "0614141000009"
        assert row["Location Name"] == "Herb Farm"
        assert row["Event Date"] == "2026-03-01"
        assert len(row["Record Hash (SHA-256)"]) == 64
        assert len(row["Chain Hash"]) == 64

    # -----------------------------------------------------------------------
    # 10. Export hash reproducibility
    # -----------------------------------------------------------------------

    def test_fda_export_hash_is_reproducible(self, db_session):
        """
        log_export() stores the export hash. Re-generating the same query
        must produce an identical CSV and therefore an identical hash.
        This proves that stored traceability data is stable and has not
        been silently mutated.
        """
        from shared.cte_persistence import CTEPersistence

        tenant_id = _fresh_tenant()
        p = CTEPersistence(db_session)
        tlc = "EXPORT-REPRO-001"

        p.store_event(
            tenant_id=tenant_id, event_type="harvesting", traceability_lot_code=tlc,
            product_description="Arugula", quantity=75.0, unit_of_measure="cases",
            event_timestamp="2026-03-01T00:00:00+00:00", source="e2e_test",
            kdes={"harvest_date": "2026-03-01"},
        )
        db_session.commit()

        # Generate and log first export
        events_v1 = p.query_events_by_tlc(tenant_id, tlc)
        csv_v1 = _generate_csv(events_v1)
        hash_v1 = hashlib.sha256(csv_v1.encode("utf-8")).hexdigest()

        export_id = p.log_export(
            tenant_id=tenant_id,
            export_hash=hash_v1,
            record_count=len(events_v1),
            query_tlc=tlc,
            generated_by="e2e_test",
        )
        db_session.commit()

        assert export_id is not None, "log_export must return an export ID"

        # Re-query and re-generate — must be identical
        events_v2 = p.query_events_by_tlc(tenant_id, tlc)
        csv_v2 = _generate_csv(events_v2)
        hash_v2 = hashlib.sha256(csv_v2.encode("utf-8")).hexdigest()

        assert hash_v1 == hash_v2, (
            "FDA export hash changed between generation and re-generation.\n"
            f"First:  {hash_v1}\nSecond: {hash_v2}"
        )

    # -----------------------------------------------------------------------
    # 11. Master E2E — full FSMA 204 chain
    # -----------------------------------------------------------------------

    def test_full_fsma_204_chain_ingest_to_export_verify(self, db_session):
        """
        MASTER E2E TEST: Complete FSMA 204 traceability workflow.

        Proves that RegEngine's core promise holds end-to-end:
        'When the FDA calls, produce records within 24 hours.'

        Full chain:
            1.  Ingest harvest → cooling → shipping → receiving (4 events)
            2.  Verify hash chain is valid and contains 4 links
            3.  Query all events by TLC — confirm chronological order
            4.  Confirm KDEs are round-tripped correctly
            5.  Generate FDA-format CSV export
            6.  Log the export with its SHA-256 hash
            7.  Re-generate the export (simulate a second FDA request)
            8.  Assert both exports are byte-for-byte identical (same hash)
            9.  Confirm row count and column layout in the CSV
        """
        from shared.cte_persistence import CTEPersistence

        tenant_id = _fresh_tenant()
        p = CTEPersistence(db_session)
        tlc = "TOM-2026-E2E-MASTER-001"

        # -------- Step 1: Ingest the supply chain --------

        r_harvest = p.store_event(
            tenant_id=tenant_id, event_type="harvesting",
            traceability_lot_code=tlc, product_description="Roma Tomatoes",
            quantity=800.0, unit_of_measure="cases",
            event_timestamp="2026-03-01T06:00:00+00:00", source="e2e_test",
            location_name="Valley Fresh Farms, Salinas CA", location_gln="0614141000001",
            kdes={
                "harvest_date": "2026-03-01",
                "field_id": "FIELD-B4",
                "harvester_name": "Valley Fresh Farms LLC",
                "tlc_source_gln": "0614141000001",
            },
        )
        r_cool = p.store_event(
            tenant_id=tenant_id, event_type="cooling",
            traceability_lot_code=tlc, product_description="Roma Tomatoes",
            quantity=800.0, unit_of_measure="cases",
            event_timestamp="2026-03-01T14:00:00+00:00", source="e2e_test",
            location_name="Valley Fresh Cooler #2", location_gln="0614141000002",
            kdes={"cooling_date": "2026-03-01", "temperature_celsius": "2.1"},
        )
        r_ship = p.store_event(
            tenant_id=tenant_id, event_type="shipping",
            traceability_lot_code=tlc, product_description="Roma Tomatoes",
            quantity=800.0, unit_of_measure="cases",
            event_timestamp="2026-03-02T07:00:00+00:00", source="e2e_test",
            location_name="Valley Fresh Farms, Salinas CA", location_gln="0614141000001",
            kdes={
                "ship_date": "2026-03-02",
                "ship_from_location": "Valley Fresh Farms, Salinas CA",
                "ship_to_location": "Metro Distribution Center, LA",
                "ship_from_gln": "0614141000001",
                "ship_to_gln": "0614141000003",
                "carrier_name": "Cold Express Logistics",
                "po_number": "PO-2026-4521",
            },
        )
        r_recv = p.store_event(
            tenant_id=tenant_id, event_type="receiving",
            traceability_lot_code=tlc, product_description="Roma Tomatoes",
            quantity=800.0, unit_of_measure="cases",
            event_timestamp="2026-03-02T18:00:00+00:00", source="e2e_test",
            location_name="Metro Distribution Center, LA", location_gln="0614141000003",
            kdes={
                "receive_date": "2026-03-02",
                "receiving_location": "Metro Distribution Center, LA",
                "immediate_previous_source": "Valley Fresh Farms, Salinas CA",
                "temperature_celsius": "3.5",
            },
        )
        db_session.commit()

        for name, r in [("harvest", r_harvest), ("cool", r_cool), ("ship", r_ship), ("recv", r_recv)]:
            assert r.success is True, f"{name} event failed: {r.errors}"
            assert r.idempotent is False

        # -------- Step 2: Verify hash chain --------

        chain = p.verify_chain(tenant_id)
        assert chain.valid is True, f"Chain invalid after ingest: {chain.errors}"
        assert chain.chain_length == 4
        assert chain.errors == []

        # -------- Step 3: Query events by TLC --------

        events = p.query_events_by_tlc(tenant_id, tlc)
        assert len(events) == 4

        event_types = [e["event_type"] for e in events]
        assert event_types == ["harvesting", "cooling", "shipping", "receiving"], (
            f"Expected chronological order, got: {event_types}"
        )

        # -------- Step 4: Verify KDE round-trip --------

        harvest_event = events[0]
        assert harvest_event["kdes"]["field_id"] == "FIELD-B4"
        assert harvest_event["kdes"]["harvester_name"] == "Valley Fresh Farms LLC"

        ship_event = events[2]
        assert ship_event["kdes"]["ship_from_location"] == "Valley Fresh Farms, Salinas CA"
        assert ship_event["kdes"]["carrier_name"] == "Cold Express Logistics"
        assert ship_event["kdes"]["po_number"] == "PO-2026-4521"

        recv_event = events[3]
        assert recv_event["kdes"]["receiving_location"] == "Metro Distribution Center, LA"
        assert recv_event["kdes"]["immediate_previous_source"] == "Valley Fresh Farms, Salinas CA"

        # -------- Step 5: Generate FDA CSV --------

        csv_v1 = _generate_csv(events)
        assert "Traceability Lot Code (TLC)" in csv_v1   # header present
        assert tlc in csv_v1                              # TLC appears in data
        assert "harvesting" in csv_v1
        assert "receiving" in csv_v1
        assert "Cold Express Logistics" in csv_v1         # carrier in shipping KDEs

        # Verify 4 data rows (+ 1 header)
        rows = list(csv.DictReader(io.StringIO(csv_v1)))
        assert len(rows) == 4

        # -------- Step 6: Log the export --------

        hash_v1 = hashlib.sha256(csv_v1.encode("utf-8")).hexdigest()
        export_id = p.log_export(
            tenant_id=tenant_id,
            export_hash=hash_v1,
            record_count=len(events),
            query_tlc=tlc,
            generated_by="e2e_test",
        )
        db_session.commit()

        assert export_id is not None

        # -------- Steps 7–8: Re-generate and compare hashes --------

        events_v2 = p.query_events_by_tlc(tenant_id, tlc)
        csv_v2 = _generate_csv(events_v2)
        hash_v2 = hashlib.sha256(csv_v2.encode("utf-8")).hexdigest()

        assert hash_v1 == hash_v2, (
            "FDA export is not reproducible — data changed between exports!\n"
            f"Export 1 hash: {hash_v1}\n"
            f"Export 2 hash: {hash_v2}\n"
            "This means the underlying traceability data is non-deterministic "
            "or has been mutated between the two queries."
        )

        # -------- Step 9: Column layout --------

        for col in _FDA_COLUMNS:
            assert col in rows[0], f"Missing required FDA column: {col}"

        # Record hashes must be present in every row
        for row in rows:
            assert len(row["Record Hash (SHA-256)"]) == 64, (
                f"Row missing Record Hash: {row['Traceability Lot Code (TLC)']}"
            )
            assert len(row["Chain Hash"]) == 64, (
                f"Row missing Chain Hash: {row['Traceability Lot Code (TLC)']}"
            )
