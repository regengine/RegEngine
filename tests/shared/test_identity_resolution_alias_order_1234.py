"""Regression tests for #1234 — ``find_entity_by_alias`` stable ordering.

Before: the SELECT in ``find_entity_by_alias`` had no ORDER BY clause.
When multiple canonical entities shared the same (alias_type, alias_value)
— which can happen before an auto-merge has been run — Postgres returned
rows in whatever order the planner picked. That order changed with
query plans, ANALYZE runs, or index churn, so callers that took
``results[0]`` got non-deterministic merges across otherwise identical
re-runs of the same ingestion.

After: ``find_entity_by_alias`` now emits
``ORDER BY ce.confidence_score DESC, ce.created_at ASC, ce.entity_id ASC``
— highest-confidence canonical first; oldest wins on ties; entity_id is
the UUID-PK stable tiebreak.

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


# Three entities sharing the same alias, with different confidence_score and
# created_at values. HIGH_CONF is the established canonical; MID and LOW are
# the kind of duplicate rows that #1193 will eventually auto-merge away.
HIGH_CONF_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"  # confidence 0.95, oldest
MID_CONF_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"   # confidence 0.80, middle
LOW_CONF_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"   # confidence 0.50, newest


def _row(entity_id: str, alias_id: str, confidence_score: float) -> Tuple[Any, ...]:
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
        confidence_score,     # ce.confidence_score
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
    # Ordered per the new CONTRACT: confidence_score DESC, created_at ASC,
    # entity_id ASC. Postgres enforces this from the SQL clause; here we feed
    # back rows already in that order to validate the Python caller does not
    # scramble them.
    return [
        _row(HIGH_CONF_ID, "alias-high", 0.95),
        _row(MID_CONF_ID, "alias-mid", 0.80),
        _row(LOW_CONF_ID, "alias-low", 0.50),
    ]


class TestFindEntityByAliasOrderBy:
    def test_sql_has_deterministic_order_by(self, ordered_rows):
        sess = _OrderedAliasSession(ordered_rows)
        svc = IdentityResolutionService(sess)
        svc.find_entity_by_alias(TENANT, ALIAS_TYPE, ALIAS_VALUE)

        # The SQL must name a stable ordering. Whitespace-tolerant check so
        # incidental formatting changes don't flap this test.
        normalized = re.sub(r"\s+", " ", sess.last_sql).lower()
        assert "order by" in normalized, (
            "find_entity_by_alias must emit ORDER BY — see #1234"
        )
        assert "ce.confidence_score desc" in normalized, (
            "ORDER BY must lead with ce.confidence_score DESC (higher quality wins)"
        )
        assert "ce.created_at asc" in normalized, (
            "ORDER BY must include ce.created_at ASC (oldest wins on ties)"
        )
        assert "ce.entity_id asc" in normalized, (
            "ORDER BY must include ce.entity_id ASC as stable UUID tiebreak"
        )
        # confidence_score must precede created_at which must precede entity_id.
        idx_conf = normalized.index("ce.confidence_score desc")
        idx_created = normalized.index("ce.created_at asc")
        idx_id = normalized.index("ce.entity_id asc")
        assert idx_conf < idx_created < idx_id, (
            "ORDER BY column priority must be: confidence_score DESC, created_at ASC, entity_id ASC"
        )

    def test_repeated_calls_return_same_first_entity(self, ordered_rows):
        """Multiple calls must produce an identical top result (N=10).

        Mirrors the real-world hazard: an ingestion pipeline that reruns
        after an ANALYZE and suddenly merges into a different canonical.
        """
        sess = _OrderedAliasSession(ordered_rows)
        svc = IdentityResolutionService(sess)

        first_results: List[str] = []
        for _ in range(10):
            results = svc.find_entity_by_alias(TENANT, ALIAS_TYPE, ALIAS_VALUE)
            assert len(results) == 3, "all three matching entities should return"
            first_results.append(results[0]["entity_id"])

        assert len(set(first_results)) == 1, (
            f"non-deterministic top result across 10 calls: {first_results}"
        )
        assert first_results[0] == HIGH_CONF_ID, (
            "highest-confidence canonical entity must win — a lower-confidence "
            "duplicate must not clobber an established canonical"
        )

    def test_full_ordering_preserved(self, ordered_rows):
        """Every row's position must match the DB-provided order."""
        sess = _OrderedAliasSession(ordered_rows)
        svc = IdentityResolutionService(sess)
        results = svc.find_entity_by_alias(TENANT, ALIAS_TYPE, ALIAS_VALUE)

        assert [r["entity_id"] for r in results] == [
            HIGH_CONF_ID,
            MID_CONF_ID,
            LOW_CONF_ID,
        ]

    def test_confidence_scores_in_results(self, ordered_rows):
        """Confidence scores must be surfaced in the returned dicts."""
        sess = _OrderedAliasSession(ordered_rows)
        svc = IdentityResolutionService(sess)
        results = svc.find_entity_by_alias(TENANT, ALIAS_TYPE, ALIAS_VALUE)

        assert results[0]["confidence_score"] == pytest.approx(0.95)
        assert results[1]["confidence_score"] == pytest.approx(0.80)
        assert results[2]["confidence_score"] == pytest.approx(0.50)
