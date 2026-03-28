"""
FSMA 204 Happy-Path End-to-End Test: CTE Ingestion -> Persistence -> FDA Export.

Exercises RegEngine's money path — the core value proposition that an acquirer's
engineering team needs to see proven:

    1. Food companies ingest Critical Tracking Events (CTEs) via the webhook API
    2. Events are persisted with SHA-256 hash chain integrity
    3. FDA-compliant 24-hour response packages are generated on demand

This test uses the real FastAPI app with TestClient, authenticating via the
AUTH_TEST_BYPASS_TOKEN pattern used across the codebase. It requires a live
Postgres database (via testcontainers or local Docker).

Run:
    pytest tests/test_fsma_happy_path_e2e.py -x -v

Skip if no Docker:
    pytest -m "not e2e"
"""

from __future__ import annotations

import csv
import io
import os
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Environment setup — must happen before any app imports
# ---------------------------------------------------------------------------

_BYPASS_TOKEN = "test-token-fsma-happy-path-e2e"

os.environ["REGENGINE_ENV"] = "test"
os.environ["AUTH_TEST_BYPASS_TOKEN"] = _BYPASS_TOKEN
os.environ["API_KEY"] = _BYPASS_TOKEN
# Disable Sentry in tests
os.environ.setdefault("SENTRY_DSN", "")
# Suppress noisy middleware
os.environ.setdefault("DISABLE_RATE_LIMITING", "true")

# Ensure services/ is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _REPO_ROOT / "services"
_INGESTION_DIR = _SERVICES_DIR / "ingestion"
for p in [str(_SERVICES_DIR), str(_INGESTION_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Optional-dependency guards
# ---------------------------------------------------------------------------

try:
    from testcontainers.postgres import PostgresContainer
    _HAS_TESTCONTAINERS = True
except ImportError:
    _HAS_TESTCONTAINERS = False

try:
    import psycopg  # noqa: F401
    _HAS_PSYCOPG = True
except ImportError:
    _HAS_PSYCOPG = False

_SKIP_REASON = (
    "testcontainers[postgresql] and psycopg required "
    "(pip install testcontainers[postgresql] psycopg[binary])"
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not (_HAS_TESTCONTAINERS and _HAS_PSYCOPG),
        reason=_SKIP_REASON,
    ),
]

# ---------------------------------------------------------------------------
# Database migration helpers (from existing test patterns)
# ---------------------------------------------------------------------------

_MIGRATION_V002 = _REPO_ROOT / "migrations" / "V002__fsma_cte_persistence.sql"

_PREAMBLE_STMTS = [
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    "DO $$ BEGIN CREATE ROLE regengine; EXCEPTION WHEN duplicate_object THEN NULL; END $$",
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
    """Split a SQL file into executable statements, stripping comments."""
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
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def postgres_url():
    """
    Start a Postgres 15 container, run migrations, and yield the connection URL.
    The container is torn down after the module.
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
        db = getattr(pg, "dbname", None) or getattr(pg, "POSTGRES_DB", "test")
        user = getattr(pg, "username", None) or getattr(pg, "POSTGRES_USER", "test")
        password = getattr(pg, "password", None) or getattr(pg, "POSTGRES_PASSWORD", "test")

        url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"

        # Run migrations
        engine = create_engine(url, echo=False)
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for stmt in _PREAMBLE_STMTS:
                try:
                    conn.execute(text(stmt))
                except OperationalError as exc:
                    if "already exists" not in str(exc).lower():
                        raise
            migration_sql = _MIGRATION_V002.read_text()
            for stmt in _split_sql_statements(migration_sql):
                conn.execute(text(stmt))
        engine.dispose()

        # Point the app's shared.database at this container
        os.environ["DATABASE_URL"] = url
        os.environ["ADMIN_DATABASE_URL"] = url

        yield url


@pytest.fixture(scope="module")
def test_client(postgres_url):
    """
    Create a FastAPI TestClient from the ingestion app.

    Uses the test bypass token for authentication.
    """
    from fastapi.testclient import TestClient

    # Force re-import so the app picks up the DATABASE_URL we just set
    if "services.ingestion.main" in sys.modules:
        del sys.modules["services.ingestion.main"]
    if "main" in sys.modules:
        del sys.modules["main"]

    from main import app
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def tenant_id():
    """Unique tenant UUID for test isolation."""
    return str(uuid4())


@pytest.fixture(scope="module")
def auth_headers(tenant_id):
    """Standard headers for authenticated requests."""
    return {
        "X-RegEngine-API-Key": _BYPASS_TOKEN,
        "X-Tenant-ID": tenant_id,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Test Data: 4 CTEs covering the FSMA 204 supply chain
# ---------------------------------------------------------------------------

def _build_ingest_payload(tenant_id: str) -> dict:
    """Build a webhook payload with 4 diverse CTE types."""
    return {
        "source": "e2e_happy_path_test",
        "tenant_id": tenant_id,
        "events": [
            # 1. Shipping CTE
            {
                "cte_type": "shipping",
                "traceability_lot_code": "E2E-TOMATO-2026-001",
                "product_description": "Roma Tomatoes",
                "quantity": 500.0,
                "unit_of_measure": "cases",
                "location_name": "Valley Fresh Farms, Salinas CA",
                "timestamp": "2026-03-15T07:00:00+00:00",
                "kdes": {
                    "ship_from_location": "Valley Fresh Farms, Salinas CA",
                    "ship_to_location": "Metro Distribution Center, LA",
                    "ship_date": "2026-03-15",
                    "lot_code": "E2E-TOMATO-2026-001",
                    "quantity": 500.0,
                    "unit": "cases",
                    "reference_document": "BOL-2026-0315-001",
                    "tlc_source_reference": "Valley Fresh Farms LLC",
                },
            },
            # 2. Receiving CTE
            {
                "cte_type": "receiving",
                "traceability_lot_code": "E2E-TOMATO-2026-001",
                "product_description": "Roma Tomatoes",
                "quantity": 500.0,
                "unit_of_measure": "cases",
                "location_name": "Metro Distribution Center, LA",
                "timestamp": "2026-03-15T16:00:00+00:00",
                "kdes": {
                    "receive_location": "Metro Distribution Center, LA",
                    "receiving_location": "Metro Distribution Center, LA",
                    "receive_date": "2026-03-15",
                    "lot_code": "E2E-TOMATO-2026-001",
                    "po_number": "PO-2026-8842",
                    "immediate_previous_source": "Valley Fresh Farms, Salinas CA",
                    "reference_document": "BOL-2026-0315-001",
                    "tlc_source_reference": "Valley Fresh Farms LLC",
                },
            },
            # 3. Transformation CTE
            {
                "cte_type": "transformation",
                "traceability_lot_code": "E2E-SALSA-2026-001",
                "product_description": "Fresh Tomato Salsa",
                "quantity": 200.0,
                "unit_of_measure": "cases",
                "location_name": "Metro Foods Processing, LA",
                "timestamp": "2026-03-16T10:00:00+00:00",
                "kdes": {
                    "input_lots": ["E2E-TOMATO-2026-001"],
                    "output_lot": "E2E-SALSA-2026-001",
                    "transformation_date": "2026-03-16",
                    "location": "Metro Foods Processing, LA",
                    "location_name": "Metro Foods Processing, LA",
                    "reference_document": "BATCH-2026-0316-001",
                },
                "input_traceability_lot_codes": ["E2E-TOMATO-2026-001"],
            },
            # 4. Growing/Harvesting CTE
            {
                "cte_type": "harvesting",
                "traceability_lot_code": "E2E-TOMATO-2026-002",
                "product_description": "Cherry Tomatoes",
                "quantity": 300.0,
                "unit_of_measure": "cases",
                "location_name": "Sunny Acres Farm, Watsonville CA",
                "timestamp": "2026-03-14T06:00:00+00:00",
                "kdes": {
                    "growing_location": "Sunny Acres Farm, Watsonville CA",
                    "harvest_date": "2026-03-14",
                    "commodity": "Cherry Tomatoes",
                    "lot_code": "E2E-TOMATO-2026-002",
                    "reference_document": "HARVEST-2026-0314-001",
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# The Test
# ---------------------------------------------------------------------------

class TestFSMA204HappyPath:
    """
    FSMA 204 happy-path end-to-end test.

    Exercises the money path: CTE ingestion -> persistence -> FDA export.
    This is the test an acquirer's engineering team needs to see pass.
    """

    def test_fsma_204_cte_ingest_and_export(
        self, test_client, tenant_id, auth_headers
    ):
        """
        Full happy-path:
        1. Ingest 4 CTEs (shipping, receiving, transformation, harvesting)
        2. Verify all accepted with event IDs and hashes
        3. Export FDA sortable spreadsheet (CSV)
        4. Generate 24-hour response package (ZIP)
        """

        # ==================================================================
        # STEP 1: Ingest 4 CTEs via webhook endpoint
        # ==================================================================

        payload = _build_ingest_payload(tenant_id)

        resp = test_client.post(
            "/api/v1/webhooks/ingest",
            json=payload,
            headers=auth_headers,
        )

        assert resp.status_code == 200, (
            f"Ingest failed with {resp.status_code}: {resp.text}"
        )

        body = resp.json()

        # ==================================================================
        # STEP 2: Verify ingestion results
        # ==================================================================

        assert body["total"] == 4, f"Expected 4 events, got {body['total']}"
        assert body["accepted"] == 4, (
            f"Expected 4 accepted, got {body['accepted']}. "
            f"Rejected: {body['rejected']}. "
            f"Events: {[e for e in body['events'] if e['status'] == 'rejected']}"
        )
        assert body["rejected"] == 0

        # Every accepted event must have an event_id and sha256_hash
        for event_result in body["events"]:
            assert event_result["status"] == "accepted", (
                f"Event {event_result['traceability_lot_code']} "
                f"({event_result['cte_type']}) was rejected: "
                f"{event_result.get('errors', [])}"
            )
            assert event_result["event_id"] is not None, (
                f"Missing event_id for {event_result['cte_type']}"
            )
            assert event_result["sha256_hash"] is not None, (
                f"Missing sha256_hash for {event_result['cte_type']}"
            )
            assert len(event_result["sha256_hash"]) == 64, (
                f"sha256_hash should be 64 hex chars, got "
                f"{len(event_result['sha256_hash'])}"
            )

        # Verify we got all 4 CTE types
        cte_types = {e["cte_type"] for e in body["events"]}
        assert cte_types == {"shipping", "receiving", "transformation", "harvesting"}, (
            f"Expected all 4 CTE types, got {cte_types}"
        )

        # ==================================================================
        # STEP 3: Generate FDA sortable spreadsheet (CSV export)
        # ==================================================================

        # Export for the tomato TLC (should have shipping + receiving = 2 events)
        csv_resp = test_client.get(
            "/api/v1/fda/export",
            params={
                "tlc": "E2E-TOMATO-2026-001",
                "tenant_id": tenant_id,
                "format": "csv",
            },
            headers=auth_headers,
        )

        assert csv_resp.status_code == 200, (
            f"FDA CSV export failed with {csv_resp.status_code}: {csv_resp.text}"
        )
        assert "text/csv" in csv_resp.headers.get("content-type", ""), (
            f"Expected CSV content-type, got {csv_resp.headers.get('content-type')}"
        )

        # Parse the CSV and verify it contains our events
        csv_content = csv_resp.text
        reader = csv.DictReader(io.StringIO(csv_content))
        csv_rows = list(reader)

        assert len(csv_rows) >= 2, (
            f"Expected at least 2 CSV rows for TLC E2E-TOMATO-2026-001, "
            f"got {len(csv_rows)}"
        )

        # Verify FDA-required columns are present
        fda_required_columns = [
            "Traceability Lot Code (TLC)",
            "Product Description",
            "Quantity",
            "Unit of Measure",
            "Event Type (CTE)",
        ]
        for col in fda_required_columns:
            assert col in csv_rows[0], f"Missing FDA column: {col}"

        # Verify our TLC appears in the data
        tlc_values = [row.get("Traceability Lot Code (TLC)", "") for row in csv_rows]
        assert any("E2E-TOMATO-2026-001" in v for v in tlc_values), (
            f"TLC E2E-TOMATO-2026-001 not found in CSV export. TLCs: {tlc_values}"
        )

        # Verify export integrity headers
        assert csv_resp.headers.get("X-Export-Hash"), "Missing X-Export-Hash header"
        assert csv_resp.headers.get("X-Record-Count"), "Missing X-Record-Count header"
        assert csv_resp.headers.get("X-Chain-Integrity"), "Missing X-Chain-Integrity header"

        # ==================================================================
        # STEP 4: Generate 24-hour response package (ZIP bundle)
        # ==================================================================

        pkg_resp = test_client.get(
            "/api/v1/fda/export",
            params={
                "tlc": "E2E-TOMATO-2026-001",
                "tenant_id": tenant_id,
                "format": "package",
            },
            headers=auth_headers,
        )

        assert pkg_resp.status_code == 200, (
            f"FDA package export failed with {pkg_resp.status_code}: {pkg_resp.text}"
        )
        assert "application/zip" in pkg_resp.headers.get("content-type", ""), (
            f"Expected ZIP content-type, got {pkg_resp.headers.get('content-type')}"
        )

        # Verify ZIP is valid and contains expected files
        zip_bytes = io.BytesIO(pkg_resp.content)
        assert zipfile.is_zipfile(zip_bytes), "Response is not a valid ZIP file"

        with zipfile.ZipFile(zip_bytes) as zf:
            names = zf.namelist()
            # Package should contain at least a CSV file
            csv_files = [n for n in names if n.endswith(".csv")]
            assert len(csv_files) >= 1, (
                f"ZIP package should contain at least one CSV file. Contents: {names}"
            )

        # Verify package integrity headers
        assert pkg_resp.headers.get("X-Export-Hash"), "Missing X-Export-Hash on package"
        assert pkg_resp.headers.get("X-Package-Hash"), "Missing X-Package-Hash on package"
        assert pkg_resp.headers.get("X-Chain-Integrity"), "Missing X-Chain-Integrity header"

        # ==================================================================
        # STEP 5: Export all events for the tenant (sortable spreadsheet)
        # ==================================================================

        all_resp = test_client.get(
            "/api/v1/fda/export/all",
            params={
                "tenant_id": tenant_id,
                "format": "csv",
            },
            headers=auth_headers,
        )

        assert all_resp.status_code == 200, (
            f"FDA export/all failed with {all_resp.status_code}: {all_resp.text}"
        )

        all_csv = all_resp.text
        all_rows = list(csv.DictReader(io.StringIO(all_csv)))

        # Should contain all 4 ingested events
        assert len(all_rows) >= 4, (
            f"Expected at least 4 rows in full export, got {len(all_rows)}"
        )

        # Verify all TLCs appear
        all_tlcs = {row.get("Traceability Lot Code (TLC)", "") for row in all_rows}
        assert "E2E-TOMATO-2026-001" in all_tlcs, "Missing tomato TLC in full export"
        assert "E2E-SALSA-2026-001" in all_tlcs, "Missing salsa TLC in full export"
        assert "E2E-TOMATO-2026-002" in all_tlcs, "Missing cherry tomato TLC in full export"

        # Verify all 4 CTE types appear in the export
        export_cte_types = {row.get("Event Type (CTE)", "") for row in all_rows}
        assert "shipping" in export_cte_types, "Missing shipping CTE in export"
        assert "receiving" in export_cte_types, "Missing receiving CTE in export"
        assert "transformation" in export_cte_types, "Missing transformation CTE in export"
        assert "harvesting" in export_cte_types, "Missing harvesting CTE in export"
