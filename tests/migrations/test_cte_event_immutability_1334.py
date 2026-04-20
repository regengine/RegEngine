"""Regression tests for issue #1334.

fsma.cte_events and fsma.traceability_events are append-only ledgers.
V057 adds BEFORE UPDATE OR DELETE triggers that RAISE EXCEPTION so no
caller — regardless of privilege — can mutate a committed event row.

These tests validate the migration SQL itself (not a live DB) by parsing
the .sql file and asserting the required DDL statements are present.
A separate live-DB test suite (run against a test Postgres instance in CI)
would validate actual trigger execution; the unit tests here act as a
fast, offline gate so a future refactor can't silently strip the triggers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_FILE = Path(__file__).parent.parent.parent / "alembic" / "sql" / "V057__cte_event_immutability.sql"


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION_FILE.read_text()


class TestMigrationFileExists:
    def test_file_exists(self):
        assert MIGRATION_FILE.exists(), f"Migration file not found: {MIGRATION_FILE}"


class TestCteEventsImmutability:
    def test_trigger_function_defined(self, sql):
        assert "prevent_cte_event_mutation" in sql

    def test_trigger_created_on_cte_events(self, sql):
        assert re.search(
            r"CREATE TRIGGER\s+cte_event_immutability\s+BEFORE UPDATE OR DELETE ON fsma\.cte_events",
            sql,
            re.IGNORECASE,
        ), "Expected BEFORE UPDATE OR DELETE trigger on fsma.cte_events"

    def test_trigger_raises_exception(self, sql):
        # The function body must call RAISE EXCEPTION so UPDATE/DELETE are rejected
        assert "RAISE EXCEPTION" in sql.upper()

    def test_trigger_per_row(self, sql):
        assert re.search(r"FOR EACH ROW", sql, re.IGNORECASE)


class TestTraceabilityEventsImmutability:
    def test_trigger_function_defined(self, sql):
        assert "prevent_traceability_event_mutation" in sql

    def test_trigger_created_on_traceability_events(self, sql):
        assert re.search(
            r"CREATE TRIGGER\s+traceability_event_immutability\s+BEFORE UPDATE OR DELETE ON fsma\.traceability_events",
            sql,
            re.IGNORECASE,
        ), "Expected BEFORE UPDATE OR DELETE trigger on fsma.traceability_events"


class TestMigrationIdempotency:
    def test_drop_if_exists_before_create(self, sql):
        """Both triggers must be dropped before re-creation so the migration
        is safe to re-run (e.g., on a fresh DB after a failed run)."""
        assert sql.count("DROP TRIGGER IF EXISTS") == 2

    def test_wrapped_in_transaction(self, sql):
        assert sql.strip().startswith("BEGIN;") or "BEGIN;" in sql
        assert "COMMIT;" in sql


class TestSupersessionPattern:
    def test_sql_comment_documents_supersession_pattern(self, sql):
        """The migration comment must explain how legitimate supersession works
        so developers don't accidentally try to UPDATE rows."""
        assert "supersedes_event_id" in sql
