"""Merkle validity must depend on persisted content, not self-generated proofs."""

from datetime import datetime, timezone

import pytest
from shared.canonical_persistence.verification import _recompute_event_sha256
from shared.cte_persistence import CTEPersistence, compute_chain_hash


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


@pytest.mark.parametrize("tampered", [False, True])
def test_merkle_recomputes_event_content(tampered):
    timestamp = datetime(2026, 9, 4, tzinfo=timezone.utc)
    digest = _recompute_event_sha256(
        "event-1", "receiving", "LOT-1", "Lettuce", 10, "cases", None, "Warehouse", timestamp, {}
    )
    row = [
        1,
        digest,
        None,
        compute_chain_hash(digest, None),
        "event-1",
        "event-1",
        "receiving",
        "LOT-1",
        "Lettuce",
        999 if tampered else 10,
        "cases",
        None,
        "Warehouse",
        timestamp,
        {},
        None,
    ]

    class Session:
        def execute(self, statement, params):
            assert params == {"tid": "tenant-1"}
            sql = str(statement)
            if "SELECT event_hash" in sql:
                return Result([(digest,)])
            if "SELECT hc.sequence_num" in sql:
                return Result([row])
            if "COUNT(*)" in sql:
                return Result([(1,)])
            raise AssertionError(sql)

    result = CTEPersistence(Session()).verify_chain_merkle("tenant-1")
    assert result.valid is (not tampered)
    assert result.merkle_root is not None
    if tampered:
        assert any("Event tamper" in error for error in result.errors)
