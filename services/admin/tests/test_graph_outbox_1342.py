"""Coverage sweep for ``app.graph_outbox`` — closing the last 9 missing lines.

The module already has a strong regression suite in
``test_graph_outbox.py`` (pending->drained happy path, transient reschedule,
max-attempts flip to failed, null-tenant fail-closed, reconciliation).
Those tests leave 9 lines uncovered (baseline 93%):

    * ``143``          — ``max_attempts < 1`` validation in
      ``enqueue_graph_write``. A client that passes ``max_attempts=0``
      creates a row that can never retry, which silently turns the
      outbox into a fail-once-and-lose pattern; we require a loud
      ValueError instead.
    * ``172``          — the PostgreSQL branch of ``enqueue_graph_write``.
      The existing suite only exercises the SQLite dev-fallback path;
      the Postgres path (with ``CAST(... AS JSONB)`` and the
      ``ON CONFLICT ON CONSTRAINT uq_graph_outbox_dedupe`` upsert) is
      the one that actually runs in production and was completely
      unobserved. A dialect-spoofed Mock session confirms the right
      SQL statement and bind parameters are issued.
    * ``223``          — the ``TypeError`` raised by ``_json_default``
      when a caller enqueues params holding a type it can't serialize
      (e.g. ``set``). This is the safety net that stops us from
      quietly dropping a Cypher param; the outbox must reject the
      enqueue, not round-trip a lossy payload.
    * ``339``          — ``_parse_params`` receives ``NULL`` from the
      DB column. Can happen if an ops DBA inserts / patches a row
      directly; the drainer must treat it as ``{}`` rather than
      crashing the batch.
    * ``341``          — ``_parse_params`` receives a ``dict``
      directly. This is the production Postgres-JSONB code path
      (psycopg returns JSONB as a dict, not a string). Without this
      covered, every real drain is running on an unobserved branch.
    * ``345``–``347``  — ``_parse_params`` receives a malformed JSON
      string (``json.JSONDecodeError`` at 345-346) or a non-str /
      non-dict / non-None value (``return {}`` fallthrough at 347).
      Both are the safety rails that prevent a single corrupted row
      from wedging the drainer; regression coverage makes sure neither
      raises and both collapse to ``{}``.
    * ``495``          — ``reconcile_graph_outbox`` receives an
      ``oldest_pending`` whose datetime is *naive* (no tzinfo).
      SQLite stores timestamps as naive text; the production code
      defensively attaches UTC before subtracting ``datetime.now(UTC)``
      so the health metric never throws ``TypeError: can't subtract
      offset-naive and offset-aware datetimes``.

No production code was modified. If you were hunting for a real bug
(DLQ message loss, retry tenant bleed), none was found while reading
these branches — they are all sensible defensive code that simply
hadn't been exercised yet.

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.graph_outbox import (
    GraphOutboxDrainer,
    _json_default,
    enqueue_graph_write,
    reconcile_graph_outbox,
)
from app.graph_outbox import GraphOutboxDrainer as _Drainer  # alias for _parse_params


# ---------------------------------------------------------------------------
# Fixture: same SQLite schema as the base test module
# ---------------------------------------------------------------------------


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE graph_outbox (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       TEXT NULL,
                operation       TEXT NOT NULL,
                cypher          TEXT NOT NULL,
                params          TEXT NOT NULL DEFAULT '{}',
                status          TEXT NOT NULL DEFAULT 'pending',
                attempts        INTEGER NOT NULL DEFAULT 0,
                max_attempts    INTEGER NOT NULL DEFAULT 10,
                last_error      TEXT NULL,
                enqueued_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                drained_at      TEXT NULL,
                next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                dedupe_key      TEXT NULL
            )
        """))
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = SessionLocal()
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Line 143 — max_attempts < 1 must be rejected
# ---------------------------------------------------------------------------


def test_enqueue_rejects_zero_max_attempts(session):
    """A zero/negative max_attempts creates a row that can never retry."""
    with pytest.raises(ValueError, match="max_attempts must be >= 1"):
        enqueue_graph_write(
            session,
            tenant_id=str(uuid.uuid4()),
            operation="op",
            cypher="MERGE (x:Y {tenant_id: $tenant_id})",
            params={},
            max_attempts=0,
        )


def test_enqueue_rejects_negative_max_attempts(session):
    with pytest.raises(ValueError, match="max_attempts must be >= 1"):
        enqueue_graph_write(
            session,
            tenant_id=str(uuid.uuid4()),
            operation="op",
            cypher="MERGE (x:Y {tenant_id: $tenant_id})",
            params={},
            max_attempts=-3,
        )


# ---------------------------------------------------------------------------
# Line 172 — Postgres dialect branch in enqueue_graph_write
# ---------------------------------------------------------------------------


def test_enqueue_uses_postgres_upsert_sql_when_dialect_is_postgresql():
    """The production Postgres path issues the CAST(... AS JSONB) upsert.

    We can't spin up Postgres in a unit test; instead, we fake the
    ``session.bind.dialect.name`` the module inspects at line 168-169
    and assert that a) ``session.execute`` is called exactly once, and
    b) the rendered SQL contains the Postgres-only ``CAST ... AS JSONB``
    and ``ON CONFLICT ON CONSTRAINT`` clauses.
    """
    fake_dialect = SimpleNamespace(name="postgresql")
    fake_bind = SimpleNamespace(dialect=fake_dialect)
    session = MagicMock(spec=Session)
    session.bind = fake_bind

    tenant = str(uuid.uuid4())
    enqueue_graph_write(
        session,
        tenant_id=tenant,
        operation="invite_created",
        cypher="MERGE (x:Y {tenant_id: $tenant_id}) SET x.id = $invite_id",
        params={"invite_id": "i1"},
        dedupe_key="d1",
        max_attempts=5,
    )

    assert session.execute.call_count == 1
    call = session.execute.call_args
    # The first positional arg is the TextClause; compare its rendered SQL.
    sql_clause = call.args[0]
    rendered = str(sql_clause)
    assert "CAST(:params AS JSONB)" in rendered
    assert "ON CONFLICT ON CONSTRAINT uq_graph_outbox_dedupe" in rendered
    assert "DO NOTHING" in rendered

    # The bind parameters must match what the caller passed, and params
    # must be serialized to JSON (the Postgres branch passes a JSON
    # string bound to a JSONB column).
    binds = call.args[1]
    assert binds["tenant_id"] == tenant
    assert binds["operation"] == "invite_created"
    assert binds["dedupe_key"] == "d1"
    assert binds["max_attempts"] == 5
    assert json.loads(binds["params"]) == {"invite_id": "i1"}
    # ``now`` is injected by the module; assert only that it's tz-aware UTC
    # (the field that keeps ``graph_sync_lag_seconds`` well-defined).
    assert isinstance(binds["now"], datetime)
    assert binds["now"].tzinfo is not None


# ---------------------------------------------------------------------------
# Line 223 — _json_default raises TypeError for non-serializable types
# ---------------------------------------------------------------------------


def test_json_default_raises_on_unserializable_type():
    """A caller that smuggles ``set`` / ``bytes`` / ... into params must
    get a loud TypeError at enqueue time, not a silent payload loss."""
    with pytest.raises(TypeError, match="not JSON serializable: set"):
        _json_default({1, 2, 3})


def test_enqueue_rejects_unserializable_param_values(session):
    """The TypeError propagates out of ``enqueue_graph_write`` so the
    caller's transaction can be rolled back cleanly."""
    with pytest.raises(TypeError, match="not JSON serializable"):
        enqueue_graph_write(
            session,
            tenant_id=str(uuid.uuid4()),
            operation="op",
            cypher="MERGE (x:Y {tenant_id: $tenant_id})",
            params={"broken": {1, 2}},  # set is not JSON-serializable
        )


# ---------------------------------------------------------------------------
# Lines 339 / 341 / 345-347 — _parse_params branches
# ---------------------------------------------------------------------------


def test_parse_params_handles_none():
    """A NULL params column (e.g. from a hand-patched row) must coerce
    to ``{}``, not crash the drainer's batch."""
    assert _Drainer._parse_params(None) == {}


def test_parse_params_passes_through_dict():
    """Postgres JSONB is handed back as a dict by psycopg. The drainer
    must accept it as-is without round-tripping through json.loads."""
    source = {"invite_id": "i1", "nested": {"k": 1}}
    result = _Drainer._parse_params(source)
    assert result == source
    # Identity passthrough — no unnecessary copy.
    assert result is source


def test_parse_params_handles_valid_json_string():
    """SQLite (and any driver that returns JSONB as text) must parse cleanly."""
    assert _Drainer._parse_params('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parse_params_handles_malformed_json_string():
    """A corrupted row must not wedge the drainer — the parser returns
    an empty dict and the row drains against an empty param set. The
    Cypher itself fails closed if it references a missing parameter."""
    assert _Drainer._parse_params("{not valid json") == {}


def test_parse_params_returns_empty_for_unexpected_type():
    """Fallthrough: anything that isn't None / dict / str (e.g. a list
    or an int sneaking in through a buggy migration) collapses to
    ``{}`` rather than raising in the hot path."""
    assert _Drainer._parse_params(12345) == {}
    assert _Drainer._parse_params([1, 2, 3]) == {}


# ---------------------------------------------------------------------------
# Line 495 — reconcile_graph_outbox attaches UTC to naive oldest_pending
# ---------------------------------------------------------------------------


def test_reconcile_attaches_utc_to_naive_oldest_pending(session):
    """SQLite returns TEXT timestamps; after fromisoformat() parses a
    value that lacks an explicit offset, the resulting datetime is
    naive and subtracting ``datetime.now(timezone.utc)`` from it would
    raise ``TypeError: can't subtract offset-naive and offset-aware
    datetimes``. The module defensively replaces tzinfo with UTC so
    the drift metric always resolves to a finite number of seconds.
    """
    t = str(uuid.uuid4())
    # Deliberately write a *naive* ISO string (no "+00:00" suffix) so
    # that fromisoformat() produces a naive datetime and line 494-495
    # executes.
    naive_old = (datetime.utcnow() - timedelta(seconds=90)).replace(microsecond=0)
    naive_iso = naive_old.isoformat()  # "2026-04-20T10:00:00" — no tz.
    assert "+" not in naive_iso and "Z" not in naive_iso

    session.execute(
        text("""
            INSERT INTO graph_outbox (tenant_id, operation, cypher, params,
                                      status, enqueued_at, next_attempt_at)
            VALUES (:t, 'op', 'MERGE (x:Y {tenant_id: $tenant_id})', '{}',
                    'pending', :old, :old)
        """),
        {"t": t, "old": naive_iso},
    )
    session.commit()

    health = reconcile_graph_outbox(session)
    assert health.pending_count == 1
    # The key assertion: the naive-datetime path produced a real,
    # finite, plausibly-aged number instead of raising TypeError.
    assert health.oldest_pending_age_seconds is not None
    assert 60 < health.oldest_pending_age_seconds < 300


# Tracks GitHub issue #1342.
