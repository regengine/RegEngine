"""Regression tests for FDA export date-boundary handling (issue #1224).

``end_date`` was previously concatenated with ``"T23:59:59"`` and fed
into Postgres as a naive string; the result was interpreted per the
database-server timezone and silently dropped boundary events in
non-UTC deployments. The fix uses a strict ``<`` upper bound at the
next-day 00:00 UTC.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.fda_export.queries import (
    _end_bound_utc,
    build_recall_where_clause,
    build_v2_where_clause,
)


def test_1224_end_bound_utc_next_day_midnight():
    """``_end_bound_utc('2026-04-17')`` returns 2026-04-18T00:00:00+00:00."""
    assert _end_bound_utc("2026-04-17") == "2026-04-18T00:00:00+00:00"


def test_1224_end_bound_utc_falls_back_on_malformed_input():
    """Malformed input is passed through verbatim; upstream validation
    remains the authoritative source of 4xx responses.
    """
    assert _end_bound_utc("not-a-date") == "not-a-date"
    assert _end_bound_utc("") == ""


def test_1224_recall_where_clause_uses_strict_lt_upper_bound():
    where, params = build_recall_where_clause(
        tenant_id="00000000-0000-0000-0000-000000000111",
        product=None,
        location=None,
        tlc="TLC-001",
        event_type=None,
        start_date="2026-04-01",
        end_date="2026-04-17",
    )
    # Old behavior: ``e.event_timestamp <= :end`` with ``end_date + 'T23:59:59'``.
    # New behavior: strict ``<`` with a next-day UTC datetime.
    assert "e.event_timestamp < :end" in where
    assert params["end"] == "2026-04-18T00:00:00+00:00"
    assert params["start"] == "2026-04-01"


def test_1224_v2_where_clause_uses_strict_lt_upper_bound():
    where, params = build_v2_where_clause(
        tenant_id="00000000-0000-0000-0000-000000000111",
        tlc=None,
        event_type=None,
        start_date="2026-04-01",
        end_date="2026-04-17",
    )
    assert "e.event_timestamp < :end" in where
    assert params["end"] == "2026-04-18T00:00:00+00:00"
