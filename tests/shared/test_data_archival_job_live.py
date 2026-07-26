"""Live-DB regression: the data_archival scheduler job completes against real schema.

Prod scheduler job ``data_archival`` failed on EVERY run with
``(psycopg2.errors.UndefinedTable) relation "fsma.fda_exports" does not
exist``: the job opened with a raw-SQL DELETE on a table no alembic
migration ever created (added speculatively in the #1017 mega-commit —
raw SQL is invisible to the ORM drift gate). FDA exports are generated
on demand and streamed, never persisted server-side (only the
``fsma.fda_export_log`` metadata table exists), so the DELETE was
removed rather than the table invented.

That first failure also masked a second: the ``fsma.cte_events`` sweep
filtered on ``created_at``, a column that table has never had — its
record-creation column is ``ingested_at``.

A mocked-session test cannot catch either defect (only a real Postgres
can object to a missing relation or column), which is exactly how both
shipped. This test seeds expired + fresh rows, runs the real job body
against a live database, and asserts the job completes and archives
only the expired rows. Requires DATABASE_URL and skips without it
(same pattern as tests/shared/test_exception_queue_uuid_arrays_live.py).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from tests.migrations.rls_db import guarded_live_database_url

DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — skipping live data_archival job test",
)


def _build_scheduler_service_without_init():
    """SchedulerService with heavy collaborators mocked (same pattern as
    services/scheduler/tests/test_task_queue_retention.py) — DB access
    inside job bodies stays real."""
    from services.scheduler import service as scheduler_service

    with (
        patch.object(scheduler_service, "get_kafka_producer", return_value=MagicMock()),
        patch.object(scheduler_service, "WebhookNotifier", return_value=MagicMock()),
        patch.object(scheduler_service, "DistributedContext", return_value=MagicMock()),
        patch.object(scheduler_service, "StateManager", return_value=MagicMock()),
        patch.object(scheduler_service, "FDAImportAlertsScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "FDARecallsScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "FDAWarningLettersScraper", return_value=MagicMock()),
        patch.object(scheduler_service, "BlockingScheduler", return_value=MagicMock()),
    ):
        return scheduler_service.SchedulerService()


def test_archive_expired_records_completes_and_archives() -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(DATABASE_URL)
    tenant_id = str(uuid.uuid4())
    old_cte_id = str(uuid.uuid4())
    fresh_cte_id = str(uuid.uuid4())

    def _cte_row(row_id: str, age_interval: str) -> dict:
        return {
            "id": row_id,
            "tid": tenant_id,
            "lot": f"LOT-{row_id[:8]}",
            "sha": f"sha-{row_id[:8]}",
            "chain": f"chain-{row_id[:8]}",
            "age": age_interval,
        }

    with engine.connect() as conn:
        # Seed committed rows — the job opens its own session, so the
        # fixtures must be visible cross-connection.
        conn.execute(
            text("INSERT INTO tenants (id, name, slug) VALUES (CAST(:id AS uuid), :name, :slug)"),
            {"id": tenant_id, "name": "archival-live-test", "slug": f"archival-live-{tenant_id[:8]}"},
        )
        for row in (_cte_row(old_cte_id, "1100 days"), _cte_row(fresh_cte_id, "10 days")):
            conn.execute(
                text("""
                    INSERT INTO fsma.cte_events
                        (id, tenant_id, event_type, traceability_lot_code,
                         product_description, quantity, unit_of_measure,
                         event_timestamp, sha256_hash, chain_hash, ingested_at)
                    VALUES
                        (CAST(:id AS uuid), CAST(:tid AS uuid), 'shipping', :lot,
                         'archival live test', 1.0, 'case',
                         NOW() - CAST(:age AS interval), :sha, :chain,
                         NOW() - CAST(:age AS interval))
                """),
                row,
            )
        old_audit_id = conn.execute(
            text("""
                INSERT INTO audit.sysadmin_access_log (accessed_at, table_name, operation)
                VALUES (NOW() - INTERVAL '2600 days', 'archival_live_test', 'SELECT')
                RETURNING id
            """)
        ).scalar_one()
        fresh_audit_id = conn.execute(
            text("""
                INSERT INTO audit.sysadmin_access_log (accessed_at, table_name, operation)
                VALUES (NOW(), 'archival_live_test', 'SELECT')
                RETURNING id
            """)
        ).scalar_one()
        conn.commit()

    try:
        svc = _build_scheduler_service_without_init()
        # Before the fix this raised ProgrammingError (UndefinedTable on
        # fsma.fda_exports; UndefinedColumn on cte_events.created_at once
        # that was gone) — neither is in the job's caught-exception tuple.
        svc.archive_expired_records()

        with engine.connect() as conn:
            cte_ids = {
                str(r[0])
                for r in conn.execute(
                    text("SELECT id FROM fsma.cte_events WHERE tenant_id = CAST(:tid AS uuid)"),
                    {"tid": tenant_id},
                )
            }
            assert old_cte_id not in cte_ids, "expired CTE event (>1095 days) must be archived"
            assert fresh_cte_id in cte_ids, "fresh CTE event must be retained"

            audit_ids = {
                r[0]
                for r in conn.execute(
                    text("SELECT id FROM audit.sysadmin_access_log WHERE table_name = 'archival_live_test'")
                )
            }
            assert old_audit_id not in audit_ids, "expired sysadmin access log (>2555 days) must be archived"
            assert fresh_audit_id in audit_ids, "fresh sysadmin access log must be retained"
    finally:
        with engine.connect() as conn:
            # cte_events is append-only (v078 trigger) — cleanup needs the
            # same transaction-local break-glass GUC the job uses.
            conn.execute(text("SELECT set_config('fsma.allow_mutation', 'true', true)"))
            conn.execute(
                text("DELETE FROM fsma.cte_events WHERE tenant_id = CAST(:tid AS uuid)"),
                {"tid": tenant_id},
            )
            conn.execute(text("DELETE FROM audit.sysadmin_access_log WHERE table_name = 'archival_live_test'"))
            conn.execute(text("DELETE FROM tenants WHERE id = CAST(:tid AS uuid)"), {"tid": tenant_id})
            conn.commit()
