"""Regression tests for #2500 — drop the hash_chain → cte_events FK.

``fsma.hash_chain.cte_event_id`` carried a
``NOT NULL REFERENCES fsma.cte_events(id)`` FK (V002). The canonical-only
write path (``CanonicalEventStore(dual_write=False)``, used by webhook
ingestion) chains by ``traceability_events.event_id`` and never creates a
matching ``cte_events`` row, so the chain INSERT hit the FK and raised
``IntegrityError`` (rolled back as HTTP 500). Migration v090 drops that FK
(keeping ``NOT NULL``) so the canonical-only path can write its chain row.

A true FK-enforcing integration test needs live Postgres; in its absence
these tests assert the migration's intent statically and assert the
canonical-only ``persist_event`` path issues the chain INSERT (the SQL
that used to violate the FK) without requiring a ``cte_events`` row.
"""

from __future__ import annotations

import importlib.util
import os
from uuid import uuid4

from shared.canonical_persistence.writer import CanonicalEventStore

from tests.shared.test_canonical_persistence_hardening import (
    FakeSession,
    _FakeResult,
    _make_event,
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MIGRATION_PATH = os.path.join(
    _REPO_ROOT,
    "alembic",
    "versions",
    "20260629_4c5d6e7f8a9b_v090_hash_chain_drop_cte_events_fk.py",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v090_hash_chain_fk_drop", _MIGRATION_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMigrationDropsFk_Issue2500:
    def test_migration_module_loads_and_is_head_child_of_v089(self) -> None:
        mod = _load_migration()
        assert mod.revision == "4c5d6e7f8a9b"
        # Chains onto v089 (38e02636e340), the prior head.
        assert mod.down_revision == "38e02636e340"

    def test_upgrade_drops_a_cte_events_fk_on_hash_chain(self) -> None:
        sql = _read_upgrade_sql()
        # Discovers the FK on hash_chain referencing cte_events and drops it.
        assert "hash_chain" in sql
        assert "cte_events" in sql
        assert "DROP CONSTRAINT" in sql
        assert "contype = 'f'" in sql

    def test_upgrade_is_idempotent_guarded(self) -> None:
        sql = _read_upgrade_sql()
        # Only drops when the table / constraint is present.
        assert "to_regclass('fsma.hash_chain')" in sql

    def test_downgrade_readds_fk_not_valid(self) -> None:
        sql = _read_downgrade_sql()
        assert "ADD CONSTRAINT" in sql
        assert "REFERENCES fsma.cte_events(id)" in sql
        # NOT VALID so the restore does not fail on pre-existing
        # canonical-only chain rows that have no cte_events twin.
        assert "NOT VALID" in sql


def _read_upgrade_sql() -> str:
    mod = _load_migration()
    return mod._UPGRADE_SQL


def _read_downgrade_sql() -> str:
    mod = _load_migration()
    return mod._DOWNGRADE_SQL


class TestCanonicalOnlyChainWrite_Issue2500:
    def test_dual_write_false_persist_issues_guarded_chain_insert(self) -> None:
        """The canonical-only path writes a hash_chain row keyed by the
        canonical event_id with NO cte_events row in scope. With the FK
        dropped (v090) and the WHERE EXISTS guard (#2533) referencing
        traceability_events, this INSERT is the one that previously hit
        the cte_events FK. Assert it is issued and references the
        canonical table, not cte_events."""
        session = FakeSession()
        # New event: idempotency SELECT empty, chain head empty (genesis),
        # canonical INSERT returns the inserted row.
        session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        session.add_rule(
            r"INSERT INTO fsma\.traceability_events",
            _FakeResult(rows=[(str(uuid4()), "sha", "chain")]),
        )

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=False)
        store.persist_event(_make_event())

        chain_inserts = [sql for sql, _ in session.calls if "INSERT INTO fsma.hash_chain" in sql]
        assert chain_inserts, "canonical-only path must still write the chain row"
        chain_sql = chain_inserts[0]
        # Guard references the canonical table — the dropped FK pointed at
        # cte_events, which this path never populates.
        assert "FROM fsma.traceability_events" in chain_sql
        # No cte_events INSERT happened (dual_write=False).
        assert not any("INSERT INTO fsma.cte_events" in sql for sql, _ in session.calls)
