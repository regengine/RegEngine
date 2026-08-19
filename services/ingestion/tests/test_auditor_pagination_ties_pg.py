"""Auditor event pagination must be stable across pages — live Postgres.

``/api/v1/audit/events`` paginates with ``LIMIT``/``OFFSET``. Postgres
plans each page independently, so an ``ORDER BY`` over a non-unique key
leaves tied rows in an unspecified order *per page*: the same row can be
returned twice, and another can be skipped entirely. The response carries
no gap indicator — ``total`` is ``len(events)`` for the page — so an
auditor paginating an FSMA-204 evidence set to exhaustion receives a short
set that reports itself complete.

Ties are the normal case here, not a corner:

* ``csv_templates._parse_date_flexible`` (:449) stamps every empty or
  unparseable date with the epoch sentinel ``1970-01-01T00:00:00Z`` so the
  row can still be ingested and flagged. One malformed import collapses
  every bad row onto one identical timestamp — and under ``DESC`` those
  sort onto the *final* pages, exactly where someone reading to the end
  arrives.
* ``supplier_portal`` (:539) stamps ``{ship_date}T00:00:00Z``: every
  submission sharing a ship date ties.
* ``sensitech_parser`` (:160) normalises date-only values to midnight.

The sibling unit test in ``test_auditor_router_1342.py``
(``test_order_by_carries_a_unique_tiebreaker``) asserts the SQL shape and
runs everywhere. This module proves the behaviour against a real cluster:
it is the test that would have caught the defect without knowing to look
at the ORDER BY clause.

Runs in ``backend-ci.yml``'s ``ingestion-full-suite`` job against the
alembic-head ``remediation_test`` database. Skips cleanly when no migrated
Postgres is reachable, except under ``REGENGINE_REQUIRE_DB=1`` where an
unreachable database fails rather than turning the gate green (#2530).
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

DSN = os.environ.get(
    "REMEDIATION_TEST_SUPERUSER_DSN",
    "postgresql://regengine:regengine@localhost:55432/regengine",  # pragma: allowlist secret — throwaway scratch-DB role
)

# Scale matters, and it was measured rather than guessed. Postgres plans
# each page independently; at small N it picks a plan that happens to be
# stable, so a toy fixture passes even with the defect present. Measured
# against this schema on Postgres 16, walking every page of a wholly tied
# block:
#
#     rows  page   rows never returned (no tiebreaker)
#       12     5     0   <- a toy fixture proves nothing
#       60    10     1
#      400    50     2   <- deterministic, 15/15 runs, ~0.03s
#     1000   100     3
#     5000   200    11
#
# 400 rows is both the smallest scale that reproduces on every run and an
# entirely ordinary one — a single malformed CSV import of 400 rows lands
# every row on the epoch sentinel. With the tiebreaker, loss is 0 at every
# scale above.
TIED_ROWS = 400
PAGE = 50


def _schema_ready(dsn: str) -> bool:
    """True when a migrated database carrying the canonical event store is up."""
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(dsn, pool_pre_ping=True)
        with engine.connect() as conn:
            found = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'fsma' "
                    "AND table_name IN ('traceability_events', 'rule_evaluations')"
                )
            ).scalar()
        engine.dispose()
        return found == 2
    except Exception:
        return False


_DB_READY = _schema_ready(DSN)

if not _DB_READY and os.environ.get("REGENGINE_REQUIRE_DB") == "1":
    raise RuntimeError(
        f"REGENGINE_REQUIRE_DB=1 but no migrated Postgres is reachable at {DSN!r} — refusing to skip."
    )

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _DB_READY, reason="migrated Postgres with fsma schema not available"),
]


@pytest.fixture()
def seeded_tenant():
    """Insert ``TIED_ROWS`` active events sharing one timestamp, then clean up.

    The timestamp is the epoch sentinel on purpose — that is the value the
    CSV importer actually produces for unreadable dates, and under ``DESC``
    it lands on the last pages.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(DSN)
    tenant_id = str(uuid.uuid4())
    lot_codes = [f"TIE-LOT-{index:03d}" for index in range(TIED_ROWS)]

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fsma.traceability_events
                    (tenant_id, source_system, event_type, event_timestamp,
                     traceability_lot_code, quantity, unit_of_measure)
                SELECT :tid, 'pytest', 'receiving', '1970-01-01T00:00:00Z',
                       'TIE-LOT-' || to_char(g, 'FM000'), 1, 'kg'
                FROM generate_series(0, :last) g
                """
            ),
            {"tid": tenant_id, "last": TIED_ROWS - 1},
        )

    try:
        yield engine, tenant_id, set(lot_codes)
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM fsma.traceability_events WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        engine.dispose()


def _paginate(engine, tenant_id: str) -> list[str]:
    """Read every page through the endpoint's own router, collecting lot codes."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import auditor_router
    from app.authz import IngestionPrincipal, get_ingestion_principal
    from shared.database import get_db_session

    principal = IngestionPrincipal(
        key_id="pagination-test",
        tenant_id=tenant_id,
        scopes=["audit.read"],
        auth_mode="test",
    )
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    api = FastAPI()
    api.include_router(auditor_router.router)
    api.dependency_overrides[get_ingestion_principal] = lambda: principal
    api.dependency_overrides[get_db_session] = lambda: session

    collected: list[str] = []
    try:
        client = TestClient(api)
        for offset in range(0, TIED_ROWS, PAGE):
            response = client.get(f"/api/v1/audit/events?limit={PAGE}&offset={offset}")
            assert response.status_code == 200, response.text
            collected.extend(
                event["traceability_lot_code"] for event in response.json()["events"]
            )
    finally:
        session.close()
    return collected


def test_paging_tied_timestamps_returns_every_row_exactly_once(seeded_tenant):
    """Walking every page must yield each event once — no gaps, no repeats.

    Without a unique tiebreaker this fails while the row *count* still
    looks right: a duplicate on one page pays for a row missing from
    another, so ``len(collected)`` stays at 400 and only the set is short.
    Asserting on the set is what makes the failure visible at all — and it
    is precisely why the live endpoint cannot notice its own gap.
    """
    engine, tenant_id, expected = seeded_tenant

    collected = _paginate(engine, tenant_id)

    duplicates = sorted({lot for lot in collected if collected.count(lot) > 1})
    assert not duplicates, f"lot codes returned on more than one page: {duplicates}"

    missing = sorted(expected - set(collected))
    assert not missing, (
        f"{len(missing)} of {TIED_ROWS} events were never returned by any page "
        f"— an evidence set silently short by {len(missing)}: {missing}"
    )
    assert len(collected) == TIED_ROWS
