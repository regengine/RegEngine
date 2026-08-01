"""#2698: legacy Merkle verifier fails closed on an empty chain read.

Pre-fix, ``verify_chain_merkle`` returned ``MerkleVerification(valid=True,
chain_length=0)`` for ZERO ``fsma.hash_chain`` rows even when non-rejected
events exist — surfaced verbatim by the FDA verification routes. The
canonical verifier gained this guard in the silent-failure sweep (#1314
twin); this locks the legacy Merkle path to the same contract.

Tests drive the verifier with a scripted session — no Postgres.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from shared.cte_persistence.core import CTEPersistence


class _ScriptedResult:
    def __init__(self, rows: List[Tuple[Any, ...]]):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def scalar(self):
        return self._rows[0][0] if self._rows else None


class _MerkleSession:
    """Serves verify_chain_merkle's two queries by SQL substring."""

    def __init__(self, chain_hashes: List[str], event_count: int):
        self.chain_hashes = chain_hashes
        self.event_count = event_count
        self.calls: List[str] = []

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append(sql)
        if "SELECT event_hash" in sql and "fsma.hash_chain" in sql:
            return _ScriptedResult([(h,) for h in self.chain_hashes])
        if "COUNT(*)" in sql and "validation_status != 'rejected'" in sql:
            return _ScriptedResult([(self.event_count,)])
        raise AssertionError(f"unexpected query: {sql}")


def test_empty_chain_with_events_fails_closed() -> None:
    """Zero chain rows + non-rejected events → valid=False, no_chain_evidence."""
    session = _MerkleSession(chain_hashes=[], event_count=7)
    result = CTEPersistence(session).verify_chain_merkle("tenant-1")

    assert result.valid is False
    assert result.no_chain_evidence is True
    assert result.chain_length == 0
    assert result.errors, "must carry an explanatory error"
    # Explicitly NOT a tamper verdict.
    assert "Not a tamper verdict" in result.errors[0]
    assert "7" in result.errors[0]


def test_empty_chain_with_no_events_stays_vacuously_valid() -> None:
    """A truly empty tenant (no events at all) is legitimately chain-less."""
    session = _MerkleSession(chain_hashes=[], event_count=0)
    result = CTEPersistence(session).verify_chain_merkle("tenant-1")

    assert result.valid is True
    assert result.chain_length == 0
    assert result.errors == []
    assert not getattr(result, "no_chain_evidence", False)


def test_populated_chain_unaffected() -> None:
    """Chains with rows verify via the Merkle tree as before."""
    session = _MerkleSession(chain_hashes=["a" * 64, "b" * 64], event_count=2)
    result = CTEPersistence(session).verify_chain_merkle("tenant-1")

    assert result.valid is True
    assert result.chain_length == 2
    assert result.merkle_root is not None
    assert not getattr(result, "no_chain_evidence", False)


def test_merkle_root_handler_forwards_no_chain_evidence(monkeypatch) -> None:
    """The /export/merkle-root handler surfaces the marker (#2698)."""
    import asyncio
    import sys
    from pathlib import Path

    ingestion_dir = Path(__file__).resolve().parent.parent.parent / "services" / "ingestion"
    if str(ingestion_dir) not in sys.path:
        sys.path.insert(0, str(ingestion_dir))
    from app.fda_export import merkle as merkle_mod

    session = _MerkleSession(chain_hashes=[], event_count=3)

    import shared.database as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)
    session.close = lambda: None  # handler's finally

    body = asyncio.run(merkle_mod.get_merkle_root_handler("tenant-1"))
    assert body["valid"] is False
    assert body["no_chain_evidence"] is True
