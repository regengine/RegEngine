"""Regression tests for #1234 — ``find_entity_by_alias`` stable ordering.

Before: the SELECT in ``find_entity_by_alias`` had no ORDER BY clause.
When multiple canonical entities shared the same (alias_type, alias_value)
— which can happen before an auto-merge has been run — Postgres returned
rows in whatever order the planner picked. That order changed with
query plans, ANALYZE runs, or index churn, so callers that took
``results[0]`` got non-deterministic merges across otherwise identical
re-runs of the same ingestion.

After: ``find_entity_by_alias`` now emits ``ORDER BY ce.created_at ASC,
ce.entity_id ASC`` — oldest canonical entity first, UUID as stable
tiebreak. That rule was chosen so a freshly-seen alias can never bump
an established canonical out of the top slot; ``entity_id`` handles
identical timestamps.

Scope: these tests pin the *ordering contract* only. They do not assert
anything about auto-merging duplicates — that remains #1193's territory.
``find_entity_by_alias`` still returns every matching row; it just
returns them in a predictable order.

Sessions are mocked — no real DB.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from services.shared.identity_resolution import IdentityResolutionService


TENANT = "tenant-1234"
ALIAS_TYPE = "name"
ALIAS_VALUE = "Acme Cold Storage"


# Three entities sharing the same alias, created at distinct timestamps.
# ``oldest`` is the established canonical; ``mid`` and ``newest`` are the
# kind of duplicate rows that #1193 will eventually auto-merge away.
OLDEST_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MID_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
NEWEST_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def _row(entity_id: str, alias_id: str) -> Tuple[Any, ...]:
    """Shape matches the SELECT in ``find_entity_by_alias`` exactly."""
    return (
        entity_id,            # ce.entity_id
        "facility",           # ce.entity_type
        "Acme Cold Storage",  # ce.canonical_name
        None,                 # ce.gln
        None,                 # ce.gtin
        None,                 # ce.fda_registration
        None,                 # ce.internal_id
        "unverified",         # ce.verification_status
        1.0,                  # ce.confidence_score
        True,                 # ce.is_active
        alias_id,             # ea.alias_id
        ALIAS_TYPE,           # ea.alias_type
        ALIAS_VALUE,          # ea.alias_value
        "csv",                # ea.source_system
        1.0,                  # ea.alias_confidence
    )


class _OrderedAliasSession:
    """Fake session whose fetchall result respects the SELECT's ORDER BY.

    We do not try to simulate Postgres' planner — the point of this test
    is that the *SQL text* includes a deterministic ORDER BY, and that
    the Python layer does not re-shuffle. We assert the SQL separately,
    then feed back rows already in the DB-promised order so ``results[0]``
    comparisons are meaningful.
    """

    def __init__(self, ordered_rows: List[Tuple[Any, ...]]):
        self._rows = ordered_rows
        self.last_sql: str = ""

    def execute(self, stmt, params=None):
        self.last_sql = str(stmt)
        result = MagicMock()
        result.fetchall.return_value = list(self._rows)
        return result


@pytest.fixture
def ordered_rows() -> List[Tuple[Any, ...]]:
    # Oldest first, matching the ORDER BY contract we want the SQL to
    # express. The actual determinism is enforced by Postgres from the
    # SQL clause; here we're confirming the call site doesn't scramble
    # whatever the DB returned.
    return [
        _row(OLDEST_ID, "alias-oldest"),
        _row(MID_ID, "alias-mid"),
        _row(NEWEST_ID, "alias-newest"),
    ]


class TestFindEntityByAliasOrderBy:
    def test_sql_has_deterministic_order_by(self, ordered_rows):
        sess = _OrderedAliasSession(ordered_rows)
        svc = IdentityResolutionService(sess)
        svc.find_entity_by_alias(TENANT, ALIAS_TYPE, ALIAS_VALUE)

        # The SQL must name a stable ordering — created_at first, then
        # entity_id as UUID-PK tiebreak. Whitespace-tolerant check so
        # incidental formatting changes don't flap this test.
        normalized = re.sub(r"\s+", " ", sess.last_sql).lower()
        assert "order by" in normalized, (
            "find_entity_by_alias must emit ORDER BY — see #1234"
        )
        assert "ce.created_at asc" in normalized, (
            "ORDER BY must lead with ce.created_at ASC (oldest wins)"
        )
        assert "ce.entity_id asc" in normalized, (
            "ORDER BY must include ce.entity_id ASC as stable tiebreak"
        )
        # created_at must come before entity_id — if the tiebreak is
        # listed first the oldest-wins semantics are violated.
        assert normalized.index("ce.created_at asc") < normalized.index(
            "ce.entity_id asc"
        ), "ce.created_at must precede ce.entity_id in ORDER BY"

    def test_repeated_calls_return_same_first_entity(self, ordered_rows):
        """Multiple calls must produce an identical top result.

        Mirrors the real-world hazard: an ingestion pipeline that reruns
        after an ANALYZE and suddenly merges into a different canonical.
        """
        sess = _OrderedAliasSession(ordered_rows)
        svc = IdentityResolutionService(sess)

        first_results: List[Dict[str, Any]] = []
        for _ in range(10):
            results = svc.find_entity_by_alias(TENANT, ALIAS_TYPE, ALIAS_VALUE)
            assert len(results) == 3, "all three matching entities should return"
            first_results.append(results[0]["entity_id"])

        assert len(set(first_results)) == 1, (
            f"non-deterministic top result across 10 calls: {first_results}"
        )
        assert first_results[0] == OLDEST_ID, (
            "oldest canonical entity must win — a newer duplicate must not "
            "clobber an established canonical"
        )

    def test_full_ordering_preserved(self, ordered_rows):
        """Every row's position must match the DB-provided order."""
        sess = _OrderedAliasSession(ordered_rows)
        svc = IdentityResolutionService(sess)
        results = svc.find_entity_by_alias(TENANT, ALIAS_TYPE, ALIAS_VALUE)

        assert [r["entity_id"] for r in results] == [
            OLDEST_ID,
            MID_ID,
            NEWEST_ID,
        ]
