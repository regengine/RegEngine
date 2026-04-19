"""Regression tests for #1314 — ``verify_chain`` must detect orphan
chain rows and unchained events.

Before this fix, ``CTEPersistence.verify_chain`` read ``fsma.hash_chain``
alone and never joined to ``fsma.cte_events``. Two integrity gaps went
undetected:

1. **Orphan chain rows**: a row in ``hash_chain`` whose
   ``cte_event_id`` no longer matched any row in ``cte_events``
   (possible via #1307 before the batch guard landed, or via any
   future partial-insert bug). The chain still walked linearly and
   ``verify_chain`` reported ``valid=True``.

2. **Unchained events**: a non-rejected CTE event with no matching
   chain row — the chain INSERT was skipped (by an exception, a
   crashed worker, or a lost idempotency race) but the event row
   still committed. The event had no tamper protection and FDA
   export could not prove its provenance, yet ``verify_chain``
   reported ``valid=True``.

Both gaps now surface as errors in the returned
``ChainVerification.errors`` list.

Pattern: mocked SQLAlchemy ``Session`` that routes SQL to canned
responses by regex — same shape as the existing hardening suite. We
assert on the error strings (stable API) and on ``valid=True/False``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from shared.cte_persistence.core import CTEPersistence
from shared.cte_persistence.hashing import compute_chain_hash


# ---------------------------------------------------------------------------
# Fake session with per-pattern routing
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self):
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self._rules: List[Tuple[re.Pattern, Any]] = []

    def add_rule(self, pattern: str, result):
        self._rules.append((re.compile(pattern, re.IGNORECASE | re.DOTALL), result))

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, dict(params or {})))
        for pat, result in self._rules:
            if pat.search(sql):
                if callable(result):
                    return result(sql, params or {})
                return result
        return _FakeResult()

    def begin_nested(self):
        return MagicMock()


# Convenience helper: build a chain of N rows with valid hashes that
# would pass the existing tamper checks, so the only errors in the
# result come from the #1314 checks we're exercising.
def _build_valid_chain(n: int, tenant_id: str = "t-1"):
    """Return (chain_rows, fake_event_ids).

    chain_rows shape: (seq, event_hash, prev_chain_hash, chain_hash,
                       cte_event_id, joined_event_id)
    """
    rows = []
    fake_event_ids = [f"evt-{i}" for i in range(1, n + 1)]
    prev = None
    for i, eid in enumerate(fake_event_ids, start=1):
        event_hash = f"eh_{i}" * 8  # 64-hex-ish placeholder
        chain_hash = compute_chain_hash(event_hash, prev)
        # By default we set joined_event_id=eid ("found" in cte_events).
        rows.append((i, event_hash, prev, chain_hash, eid, eid))
        prev = chain_hash
    return rows, fake_event_ids


def _install_chain_and_count(sess: _FakeSession, chain_rows, event_count):
    """Wire the fake to return chain_rows for the LEFT JOIN query and
    event_count for the COUNT(*) query."""
    sess.add_rule(
        r"FROM fsma\.hash_chain hc\s+LEFT JOIN fsma\.cte_events",
        _FakeResult(rows=chain_rows),
    )
    sess.add_rule(
        r"SELECT COUNT\(\*\)\s+FROM fsma\.cte_events",
        _FakeResult(rows=[(event_count,)]),
    )


# ---------------------------------------------------------------------------
# Orphan chain row detection
# ---------------------------------------------------------------------------


class TestOrphanChainRow_Issue1314:
    def test_valid_chain_still_reports_valid(self):
        """Sanity: a healthy chain with matching event rows stays valid."""
        sess = _FakeSession()
        rows, event_ids = _build_valid_chain(3)
        _install_chain_and_count(sess, rows, event_count=3)

        result = CTEPersistence(session=sess).verify_chain("t-1")
        assert result.valid is True
        assert result.errors == []
        assert result.chain_length == 3

    def test_orphan_chain_row_detected(self):
        """A chain row whose cte_event_id points to nothing must now
        fail verification. Pre-fix, verify_chain didn't join to
        cte_events at all."""
        sess = _FakeSession()
        rows, _ = _build_valid_chain(3)
        # Mutate row 2 to simulate orphan — cte_event_id present but
        # joined_event_id is NULL (LEFT JOIN miss).
        seq, eh, prev, ch, cte_id, _joined = rows[1]
        rows[1] = (seq, eh, prev, ch, cte_id, None)
        _install_chain_and_count(sess, rows, event_count=2)  # one event missing

        result = CTEPersistence(session=sess).verify_chain("t-1")
        assert result.valid is False
        assert any("Orphan chain row at seq=2" in e for e in result.errors), (
            f"expected orphan error for seq=2; got {result.errors}"
        )
        # The offending cte_event_id must be in the error message for
        # forensics — not just "something is wrong".
        assert any("evt-2" in e for e in result.errors)

    def test_multiple_orphans_all_reported(self):
        """Each orphan should be listed separately so an operator can
        enumerate the damage without rerunning the check."""
        sess = _FakeSession()
        rows, _ = _build_valid_chain(5)
        # Orphan seq=2 and seq=4
        for idx in (1, 3):
            seq, eh, prev, ch, cte_id, _ = rows[idx]
            rows[idx] = (seq, eh, prev, ch, cte_id, None)
        _install_chain_and_count(sess, rows, event_count=3)

        result = CTEPersistence(session=sess).verify_chain("t-1")
        assert result.valid is False
        orphan_errors = [e for e in result.errors if e.startswith("Orphan chain row")]
        assert len(orphan_errors) == 2
        assert any("seq=2" in e for e in orphan_errors)
        assert any("seq=4" in e for e in orphan_errors)


# ---------------------------------------------------------------------------
# Unchained event detection
# ---------------------------------------------------------------------------


class TestUnchainedEvents_Issue1314:
    def test_unchained_event_detected_when_chain_shorter_than_events(self):
        """Event count > chain length => k events have no chain row.
        Pre-fix, verify_chain counted only the chain and missed this."""
        sess = _FakeSession()
        rows, _ = _build_valid_chain(3)
        # DB has 5 non-rejected events but only 3 chain rows.
        _install_chain_and_count(sess, rows, event_count=5)

        result = CTEPersistence(session=sess).verify_chain("t-1")
        assert result.valid is False
        assert any(
            "Unchained events: 2 non-rejected event" in e for e in result.errors
        ), f"expected unchained error; got {result.errors}"
        # The diagnostic must name both counts so an operator can
        # reason about the delta without re-querying the DB.
        assert any(
            "events=5" in e and "chain_length=3" in e for e in result.errors
        )

    def test_empty_chain_with_events_is_flagged(self):
        """An empty chain but non-zero event count is the worst case
        — every event is unchained and has zero tamper protection."""
        sess = _FakeSession()
        _install_chain_and_count(sess, chain_rows=[], event_count=4)

        result = CTEPersistence(session=sess).verify_chain("t-1")
        assert result.valid is False
        assert result.chain_length == 0
        assert any(
            "Unchained events: 4" in e for e in result.errors
        ), f"expected unchained error for 4 events; got {result.errors}"

    def test_empty_chain_with_zero_events_is_valid(self):
        """A fresh tenant (no events, no chain) is a valid state — no
        regression against the pre-fix fast path."""
        sess = _FakeSession()
        _install_chain_and_count(sess, chain_rows=[], event_count=0)

        result = CTEPersistence(session=sess).verify_chain("t-1")
        assert result.valid is True
        assert result.errors == []
        assert result.chain_length == 0

    def test_chain_equals_event_count_is_valid(self):
        """Exact parity (chain rows == non-rejected events) stays valid."""
        sess = _FakeSession()
        rows, _ = _build_valid_chain(7)
        _install_chain_and_count(sess, rows, event_count=7)

        result = CTEPersistence(session=sess).verify_chain("t-1")
        assert result.valid is True
        assert result.errors == []


# ---------------------------------------------------------------------------
# Interaction with existing tamper checks
# ---------------------------------------------------------------------------


class TestInteractionWithExistingChecks_Issue1314:
    def test_orphan_does_not_mask_tamper(self):
        """If both an orphan row AND a tampered chain_hash exist, BOTH
        must surface. Neither check should short-circuit the other."""
        sess = _FakeSession()
        rows, _ = _build_valid_chain(3)
        # Orphan seq=2
        seq, eh, prev, ch, cte_id, _ = rows[1]
        rows[1] = (seq, eh, prev, ch, cte_id, None)
        # Tamper seq=3 by swapping its stored chain_hash for garbage
        seq3, eh3, prev3, _real_ch, cte3, j3 = rows[2]
        rows[2] = (seq3, eh3, prev3, "00" * 32, cte3, j3)
        _install_chain_and_count(sess, rows, event_count=2)

        result = CTEPersistence(session=sess).verify_chain("t-1")
        assert result.valid is False
        assert any("Orphan chain row at seq=2" in e for e in result.errors)
        assert any("Tamper detected at seq=3" in e for e in result.errors)

    def test_cross_tenant_join_scoping(self):
        """The LEFT JOIN must carry ``e.tenant_id = hc.tenant_id`` so
        that a tenant-B event row never 'rescues' a tenant-A orphan.
        This is enforced in the SQL, not the result logic; we assert
        the SQL itself contains the scoped join predicate."""
        sess = _FakeSession()
        _install_chain_and_count(sess, chain_rows=[], event_count=0)

        CTEPersistence(session=sess).verify_chain("t-1")

        join_calls = [
            c for c in sess.calls if "LEFT JOIN fsma.cte_events" in c[0]
        ]
        assert join_calls, "expected a LEFT JOIN query"
        sql = join_calls[0][0]
        normalized = " ".join(sql.split())
        assert "e.tenant_id = hc.tenant_id" in normalized, (
            "LEFT JOIN must be scoped by tenant_id on both sides — "
            "otherwise cross-tenant rows could mask orphans"
        )


# ---------------------------------------------------------------------------
# Backward-compatible response shape
# ---------------------------------------------------------------------------


class TestResponseShape_Issue1314:
    def test_chain_verification_fields_preserved(self):
        """The ChainVerification dataclass must retain its existing
        fields so downstream callers don't break. The change is
        additive (more errors), not a shape change."""
        sess = _FakeSession()
        rows, _ = _build_valid_chain(2)
        _install_chain_and_count(sess, rows, event_count=2)

        result = CTEPersistence(session=sess).verify_chain("t-1")
        # These attributes are the pre-existing contract.
        assert hasattr(result, "valid")
        assert hasattr(result, "chain_length")
        assert hasattr(result, "errors")
        assert hasattr(result, "checked_at")

    def test_errors_is_empty_list_when_valid(self):
        """Callers may check ``not errors`` — preserve an empty list
        (not None) on the happy path."""
        sess = _FakeSession()
        rows, _ = _build_valid_chain(1)
        _install_chain_and_count(sess, rows, event_count=1)

        result = CTEPersistence(session=sess).verify_chain("t-1")
        assert result.errors == []
