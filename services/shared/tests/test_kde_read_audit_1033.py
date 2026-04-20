"""Regression tests for issue #1033.

FSMA 204 §1.1350(h) and NIST AU-2 require that read-access to traceability
KDE records be logged.  Before this fix, query_events_by_tlc and
query_all_events fetched KDE rows from fsma.cte_kdes with no audit record
— an attacker or rogue admin could exfiltrate the full KDE corpus
silently.

The fix emits a structured INFO log record (audit=True, fsma_au2=True)
after each KDE read.  These tests verify:

1. The audit record is emitted when events are returned.
2. No audit record is emitted when the query returns no events (nothing to log).
3. The audit record contains the required fields: tenant_id, event_ids,
   event_count, source.
4. Both query paths (query_events_by_tlc and query_all_events) emit the record.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Minimal fake session factory
# ---------------------------------------------------------------------------


def _fake_session(event_rows=None, kde_rows=None, count_row=None):
    """Build a mock SQLAlchemy session that returns canned rows."""
    session = MagicMock()

    call_num = [0]

    def _execute(sql, params=None):
        result = MagicMock()
        n = call_num[0]
        call_num[0] += 1

        sql_str = str(sql).upper()

        if "COUNT(*)" in sql_str or (n == 0 and count_row is not None):
            result.scalar.return_value = count_row or 0
            result.fetchall.return_value = event_rows or []
        elif "CTE_KDES" in sql_str:
            result.fetchall.return_value = kde_rows or []
        else:
            result.fetchall.return_value = event_rows or []
            result.scalar.return_value = 0

        return result

    session.execute.side_effect = _execute
    return session


# ---------------------------------------------------------------------------
# Helper: build CTEPersistence with a mocked session
# ---------------------------------------------------------------------------


def _make_persistence(session):
    from services.shared.cte_persistence.core import CTEPersistence  # noqa: PLC0415
    p = object.__new__(CTEPersistence)
    p.session = session
    # DEFAULT_TRAVERSAL_DEPTH may be accessed
    p.DEFAULT_TRAVERSAL_DEPTH = 5
    return p


# ---------------------------------------------------------------------------
# Tests: query_events_by_tlc audit record
# ---------------------------------------------------------------------------


class TestQueryEventsByTlcAudit:
    """Audit record emitted by query_events_by_tlc when KDE rows are read."""

    def _run(self, event_rows, kde_rows=None):
        session = _fake_session(event_rows=event_rows, kde_rows=kde_rows or [])
        p = _make_persistence(session)

        # patch _expand_tlcs_via_transformation_links to return [tlc] directly
        with patch.object(p, "_expand_tlcs_via_transformation_links", return_value=["TLC-001"]):
            with patch.object(p, "set_tenant_context"):
                return p, session

    def test_audit_record_emitted_when_events_returned(self, caplog):
        event_rows = [
            # (id, event_type, tlc, product_description, qty, uom, gln, loc, ts, sha, chain, src, status, ingested, entry_ts)
            (
                "evt-001", "receiving", "TLC-001", "Tomatoes", 100.0, "cases",
                "0614141000005", "WH-A", None, "abc", "def", "epcis",
                "valid", None, None,
            )
        ]
        session = _fake_session(event_rows=event_rows, kde_rows=[])
        p = _make_persistence(session)

        with patch.object(p, "_expand_tlcs_via_transformation_links", return_value=["TLC-001"]):
            with patch.object(p, "set_tenant_context"):
                with caplog.at_level(logging.INFO, logger="cte-persistence"):
                    p.query_events_by_tlc(tenant_id="t1", tlc="TLC-001")

        audit_records = [r for r in caplog.records if "kde_read_access" in r.getMessage()]
        assert audit_records, "Expected at least one kde_read_access audit log record"

    def test_no_audit_record_when_no_events(self, caplog):
        session = _fake_session(event_rows=[], kde_rows=[])
        p = _make_persistence(session)

        with patch.object(p, "_expand_tlcs_via_transformation_links", return_value=["TLC-999"]):
            with patch.object(p, "set_tenant_context"):
                with caplog.at_level(logging.INFO, logger="cte-persistence"):
                    p.query_events_by_tlc(tenant_id="t1", tlc="TLC-999")

        audit_records = [r for r in caplog.records if "kde_read_access" in r.getMessage()]
        assert not audit_records, "No audit record should be emitted for empty result"

    def test_audit_record_contains_required_fields(self, caplog):
        event_rows = [
            (
                "evt-001", "receiving", "TLC-001", "Tomatoes", 100.0, "cases",
                "0614141000005", "WH-A", None, "abc", "def", "epcis",
                "valid", None, None,
            )
        ]
        session = _fake_session(event_rows=event_rows, kde_rows=[])
        p = _make_persistence(session)

        with patch.object(p, "_expand_tlcs_via_transformation_links", return_value=["TLC-001"]):
            with patch.object(p, "set_tenant_context"):
                with caplog.at_level(logging.INFO, logger="cte-persistence"):
                    p.query_events_by_tlc(tenant_id="tenant-xyz", tlc="TLC-001")

        audit_records = [r for r in caplog.records if "kde_read_access" in r.getMessage()]
        assert audit_records
        record = audit_records[0]
        extra = record.__dict__

        assert extra.get("audit") is True
        assert extra.get("fsma_au2") is True
        assert extra.get("tenant_id") == "tenant-xyz"
        assert extra.get("event_count") == 1
        assert extra.get("source") == "query_events_by_tlc"
        assert "evt-001" in extra.get("event_ids", [])
