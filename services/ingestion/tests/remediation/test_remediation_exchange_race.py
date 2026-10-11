"""Single-use remediation exchange must survive a race (audit medium 5).

``exchange_for_session`` used to check ``exchange_count`` in Python and then
run an UPDATE with no count guard, so two requests that both read
``exchange_count = 0`` could each mint a session. The UPDATE now carries
``exchange_count < :max_exchanges`` and the zero-rowcount path denies, which
makes the loser's exchange fail even with a stale pre-read.

These tests run against a fake session that behaves like Postgres: the UPDATE
only guards what its WHERE clause says. On the old code the second exchange
with a stale read succeeds and both tests fail; on the fixed code both pass.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(service_dir))

import app.remediation.tokens as tokens


class _Result:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _RaceDb:
    """Fake session emulating the remediation_tokens row under contention.

    Like Postgres, the UPDATE atomically guards only what its WHERE clause
    states: when the statement carries the ``exchange_count <`` predicate the
    second concurrent exchange matches zero rows, otherwise both succeed.
    """

    def __init__(self):
        self.count = 0
        self.statements = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append((sql, dict(params or {})))
        assert "UPDATE fsma.remediation_tokens" in sql
        assert "exchange_count = exchange_count + 1" in sql
        if "exchange_count <" in sql:
            limit = (params or {}).get("max_exchanges", tokens.MAX_EXCHANGES)
            if self.count >= limit:
                return _Result(0)
        self.count += 1
        return _Result(1)


def _token_row(exchange_count: int = 0) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "case_id": str(uuid.uuid4()),
        "exchange_count": exchange_count,
    }


@pytest.fixture()
def no_side_effects(monkeypatch):
    monkeypatch.setattr(tokens, "audit_event", lambda *a, **k: None)
    monkeypatch.setattr(tokens, "set_tenant_guc", lambda *a, **k: None)


def test_second_exchange_with_stale_read_fails(no_side_effects):
    """Two requests that both pre-read exchange_count = 0: only one wins."""
    db = _RaceDb()
    stale = _token_row(exchange_count=0)

    first = tokens.exchange_for_session(db, dict(stale))
    assert first["session_token"]

    with pytest.raises(HTTPException) as exc_info:
        tokens.exchange_for_session(db, dict(stale))
    assert exc_info.value.status_code == 400
    assert db.count == 1


def test_update_carries_count_guard(no_side_effects):
    """The UPDATE itself must bound the counter, not just the Python check."""
    db = _RaceDb()
    tokens.exchange_for_session(db, _token_row(exchange_count=0))
    sql, params = db.statements[-1]
    assert "exchange_count <" in sql
    assert params["max_exchanges"] == tokens.MAX_EXCHANGES


def test_fresh_second_exchange_still_denied(no_side_effects):
    """Sequential reuse with a fresh read keeps failing uniformly."""
    db = _RaceDb()
    tokens.exchange_for_session(db, _token_row(exchange_count=0))
    with pytest.raises(HTTPException) as exc_info:
        tokens.exchange_for_session(db, _token_row(exchange_count=1))
    assert exc_info.value.status_code == 400
