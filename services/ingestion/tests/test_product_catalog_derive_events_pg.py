"""Product catalog must derive from canonical events — live Postgres.

``product_catalog._db_get_catalog`` falls back to
``_derive_products_from_events`` when ``fsma.products`` is empty for a
tenant, so the catalog is not blank. That fallback aggregated
``MAX(event_time)`` / ``MIN(event_time)``, but ``fsma.traceability_events``
has no ``event_time`` column — the timestamp column is ``event_timestamp``.
Postgres raised ``UndefinedColumn`` (SQLSTATE 42703), the function caught
``SQLAlchemyError`` and returned ``[]``, and the fallback never produced a
single product.

The unit tests in ``test_product_catalog_1342.py`` run against a fake
session that never parses the SQL, so they passed throughout. This module
runs the real statement against a real cluster at alembic head.

Skips cleanly when no migrated Postgres is reachable, except under
``REGENGINE_REQUIRE_DB=1`` where an unreachable database fails rather than
skipping (#2530).
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from shared.db_url import sync_postgres_url

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

DSN = os.environ.get(
    "REMEDIATION_TEST_SUPERUSER_DSN",
    "postgresql://regengine:regengine@localhost:55432/regengine",  # pragma: allowlist secret — throwaway scratch-DB role
)

PRODUCT = "Romaine Hearts"
EVENT_TIMESTAMP = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)


def _schema_ready(dsn: str) -> bool:
    """True when a migrated database carrying the event store and catalog is up."""
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(sync_postgres_url(dsn), pool_pre_ping=True)
        with engine.connect() as conn:
            found = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'fsma' "
                    "AND table_name IN ('traceability_events', 'products')"
                )
            ).scalar()
        engine.dispose()
        return found == 2
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
def seeded_tenant():
    """Insert one event for a fresh tenant with no ``fsma.products`` rows, then clean up."""
    from sqlalchemy import create_engine, text

    engine = create_engine(sync_postgres_url(DSN))
    tenant_id = str(uuid.uuid4())

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fsma.traceability_events
                    (tenant_id, source_system, event_type, event_timestamp,
                     product_reference, traceability_lot_code, quantity, unit_of_measure)
                VALUES (:tid, 'pytest', 'receiving', :ts,
                        :product, 'DERIVE-LOT-001', 1, 'kg')
                """
            ),
            {"tid": tenant_id, "ts": EVENT_TIMESTAMP, "product": PRODUCT},
        )

    try:
        yield engine, tenant_id
    finally:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))  # v141 append-only
            conn.execute(
                text("DELETE FROM fsma.traceability_events WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        engine.dispose()


def test_empty_products_table_derives_catalog_from_events(seeded_tenant, monkeypatch):
    """One event, no ``fsma.products`` rows: the catalog is that one derived product.

    Asserting on the timestamps as well as the count is what pins the
    column: both come from ``event_timestamp``, and a wrong column name
    fails the whole statement rather than just those two fields.
    """
    from app import product_catalog as pc
    from sqlalchemy.orm import sessionmaker

    engine, tenant_id = seeded_tenant
    monkeypatch.setattr(pc, "get_db_safe", sessionmaker(bind=engine))

    products = pc._db_get_catalog(tenant_id)

    assert products is not None, "catalog read failed outright"
    assert [p.name for p in products] == [PRODUCT]
    assert products[0].cte_count == 1
    assert datetime.fromisoformat(products[0].last_cte) == EVENT_TIMESTAMP
    assert datetime.fromisoformat(products[0].created_at) == EVENT_TIMESTAMP
