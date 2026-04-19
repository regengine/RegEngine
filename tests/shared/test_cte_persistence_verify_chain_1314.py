"""
Regression tests for #1314 — ``CTEPersistence.verify_chain`` used to
read ``fsma.hash_chain`` in isolation and never cross-checked
``fsma.cte_events``. Two classes of real regression slipped past it:

  * **Orphan chain rows** (#1307-class): a ``hash_chain`` row whose
    ``cte_event_id`` no longer joins to ``fsma.cte_events`` still
    passed verification with ``valid=True``.
  * **Missing chain rows**: if a CTE event's chain insert silently
    failed, the chain had no entry for it — but ``verify_chain`` only
    iterated the chain rows it *did* see, so the missing event was
    invisible. FDA export's ``X-Chain-Integrity: VERIFIED`` header would
    falsely claim full coverage.

The fix adds a LEFT JOIN to ``fsma.cte_events`` inside ``verify_chain``
and cross-checks ``count(chain) == count(events WHERE NOT rejected)``,
reporting the missing IDs. The ``ChainVerification`` DTO gains
``orphan_chain_rows``, ``missing_chain_rows``, and
``cte_events_count`` so callers can react without string-parsing
``errors``.

Tests drive the writer with a mocked session — no Postgres.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

import pytest

from shared.cte_persistence.core import CTEPersistence
from shared.cte_persistence.hashing import compute_chain_hash


# ---------------------------------------------------------------------------
# Minimal scripted session that serves verify_chain's two queries
# ---------------------------------------------------------------------------


class _ScriptedResult:
    def __init__(self, rows: List[Tuple[Any, ...]]):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _ChainSession:
    """Scripted session: feed the LEFT-JOIN chain rows, the event count
    scalar, and the missing-event-ids list.

    Chain rows shape (matches what verify_chain selects):
      (sequence_num, event_hash, previous_chain_hash, chain_hash,
       cte_event_id, matched_event_id)

    ``matched_event_id`` is ``None`` to simulate an orphan row.
    """

    def __init__(
        self,
        chain_rows: List[Tuple[Any, ...]] | None = None,
        event_count: int = 0,
        missing_ids: List[str] | None = None,
    ):
        self.chain_rows = chain_rows or []
        self.event_count = event_count
        self.missing_ids = missing_ids or []
        self.calls: List[str] = []

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append(sql)
        if "LEFT JOIN fsma.cte_events" in sql and "ORDER BY hc.sequence_num" in sql:
            return _ScriptedResult(self.chain_rows)
        if "COUNT(*)" in sql and "validation_status != 'rejected'" in sql:
            return _ScriptedResult([(self.event_count,)])
        if "LEFT JOIN fsma.hash_chain" in sql and "hc.id IS NULL" in sql:
            return _ScriptedResult([(i,) for i in self.missing_ids])
        return _ScriptedResult([])


def _chain_row(seq: int, event_hash: str, prev: str | None, chain: str,
               cte_id: str, matched: str | None) -> Tuple:
    return (seq, event_hash, prev, chain, cte_id, matched)


def _well_formed_chain(n: int) -> Tuple[List[Tuple], List[str]]:
    """Build a well-formed chain of length n with matching event ids."""
    rows = []
    event_ids = []
    prev = None
    for i in range(1, n + 1):
        event_hash = f"eh-{i:02d}"
        chain_hash = compute_chain_hash(event_hash, prev)
        cte_id = f"evt-{i:02d}"
        rows.append(_chain_row(i, event_hash, prev, chain_hash, cte_id, cte_id))
        event_ids.append(cte_id)
        prev = chain_hash
    return rows, event_ids


# ---------------------------------------------------------------------------
# #1314 — orphan chain rows must fail verification
# ---------------------------------------------------------------------------


class TestOrphanChainRowsFailVerification_Issue1314:
    def test_single_orphan_flips_valid_to_false(self):
        rows, _ = _well_formed_chain(3)
        # Orphan the middle row (matched_event_id=None).
        seq_num, evh, prev, ch, cte_id, _ = rows[1]
        rows[1] = (seq_num, evh, prev, ch, cte_id, None)
        session = _ChainSession(chain_rows=rows, event_count=3, missing_ids=[])

        result = CTEPersistence(session).verify_chain("tenant-1")

        assert result.valid is False
        assert result.orphan_chain_rows == [2]
        assert any("Orphan chain row at seq=2" in e for e in result.errors)
        # The other two rows are still good — length unchanged.
        assert result.chain_length == 3

    def test_multiple_orphans_all_listed(self):
        rows, _ = _well_formed_chain(5)
        # Orphan seq 1 and seq 4.
        for idx in (0, 3):
            seq_num, evh, prev, ch, cte_id, _ = rows[idx]
            rows[idx] = (seq_num, evh, prev, ch, cte_id, None)
        session = _ChainSession(chain_rows=rows, event_count=5, missing_ids=[])

        result = CTEPersistence(session).verify_chain("tenant-1")

        assert result.valid is False
        assert result.orphan_chain_rows == [1, 4]

    def test_no_orphans_list_is_empty_on_clean_chain(self):
        rows, _ = _well_formed_chain(3)
        session = _ChainSession(chain_rows=rows, event_count=3, missing_ids=[])

        result = CTEPersistence(session).verify_chain("tenant-1")

        assert result.valid is True
        assert result.orphan_chain_rows == []
        assert result.missing_chain_rows == []


# ---------------------------------------------------------------------------
# #1314 — missing chain rows (events without chain entries) must fail
# ---------------------------------------------------------------------------


class TestMissingChainRowsFailVerification_Issue1314:
    def test_event_without_chain_row_is_flagged(self):
        """3 events in cte_events, 2 in hash_chain — the 3rd event's
        chain insert failed. Before the fix, verify_chain looked at
        those 2 chain rows, found them internally consistent, and
        reported valid=True. After the fix, the count mismatch + the
        LEFT-JOIN-from-events query surface the 3rd event as missing."""
        rows, _ = _well_formed_chain(2)
        session = _ChainSession(
            chain_rows=rows,
            event_count=3,
            missing_ids=["evt-03"],
        )

        result = CTEPersistence(session).verify_chain("tenant-1")

        assert result.valid is False
        assert result.missing_chain_rows == ["evt-03"]
        assert result.cte_events_count == 3
        assert any("event(s) have no chain entry" in e for e in result.errors)

    def test_multiple_missing_events_all_listed(self):
        rows, _ = _well_formed_chain(1)
        session = _ChainSession(
            chain_rows=rows,
            event_count=4,
            missing_ids=["evt-02", "evt-03", "evt-04"],
        )
        result = CTEPersistence(session).verify_chain("tenant-1")
        assert result.valid is False
        assert result.missing_chain_rows == ["evt-02", "evt-03", "evt-04"]

    def test_count_match_but_chain_empty_and_events_zero_is_valid(self):
        """The legitimate empty case: no events, no chain. Must stay
        valid — this is the new-tenant state, not a break."""
        session = _ChainSession(chain_rows=[], event_count=0, missing_ids=[])
        result = CTEPersistence(session).verify_chain("tenant-1")
        assert result.valid is True
        assert result.chain_length == 0
        assert result.cte_events_count == 0
        assert result.missing_chain_rows == []

    def test_empty_chain_with_events_is_invalid(self):
        """Chain is empty but events exist → every event is missing
        its chain row. This was the #1314 silent-pass case."""
        session = _ChainSession(
            chain_rows=[],
            event_count=2,
            missing_ids=["evt-01", "evt-02"],
        )
        result = CTEPersistence(session).verify_chain("tenant-1")
        assert result.valid is False
        assert result.missing_chain_rows == ["evt-01", "evt-02"]


# ---------------------------------------------------------------------------
# #1314 — both failure modes simultaneously
# ---------------------------------------------------------------------------


class TestOrphanAndMissingTogether_Issue1314:
    def test_both_categories_reported(self):
        """A chain that has BOTH an orphan row AND a missing event —
        both must appear in the result, not just the first one found."""
        rows, _ = _well_formed_chain(2)
        # Orphan row 1
        seq_num, evh, prev, ch, cte_id, _ = rows[0]
        rows[0] = (seq_num, evh, prev, ch, cte_id, None)
        # And 3 events exist; 2 in chain, 1 missing.
        session = _ChainSession(
            chain_rows=rows,
            event_count=3,
            missing_ids=["evt-03"],
        )

        result = CTEPersistence(session).verify_chain("tenant-1")

        assert result.valid is False
        assert result.orphan_chain_rows == [1]
        assert result.missing_chain_rows == ["evt-03"]


# ---------------------------------------------------------------------------
# #1314 — ChainVerification shape is backward-compatible + structured
# ---------------------------------------------------------------------------


class TestChainVerificationShape_Issue1314:
    """Existing callers read ``.valid`` / ``.chain_length`` / ``.errors`` /
    ``.checked_at``. The new fields must NOT break them, and must be
    available for callers that want structured data instead of
    string-parsing the errors list."""

    def test_legacy_fields_still_present(self):
        rows, _ = _well_formed_chain(2)
        session = _ChainSession(chain_rows=rows, event_count=2, missing_ids=[])
        result = CTEPersistence(session).verify_chain("tenant-1")

        assert hasattr(result, "valid")
        assert hasattr(result, "chain_length")
        assert hasattr(result, "errors")
        assert hasattr(result, "checked_at")
        assert isinstance(result.valid, bool)
        assert isinstance(result.chain_length, int)
        assert isinstance(result.errors, list)
        assert isinstance(result.checked_at, str)

    def test_new_fields_present_and_typed(self):
        rows, _ = _well_formed_chain(2)
        session = _ChainSession(chain_rows=rows, event_count=2, missing_ids=[])
        result = CTEPersistence(session).verify_chain("tenant-1")

        assert hasattr(result, "orphan_chain_rows")
        assert hasattr(result, "missing_chain_rows")
        assert hasattr(result, "cte_events_count")
        assert isinstance(result.orphan_chain_rows, list)
        assert isinstance(result.missing_chain_rows, list)
        assert isinstance(result.cte_events_count, int)

    def test_rejected_events_are_not_flagged_as_missing(self):
        """A rejected CTE event is intentionally not chained. Cross-check
        logic filters by ``validation_status != 'rejected'`` — if it
        didn't, every rejected event would look like a missing chain
        entry and verify_chain would cry wolf every time validation
        rejects anything."""
        # event_count excludes rejected, missing_ids is empty → the
        # helper query returned no events needing a chain row.
        rows, _ = _well_formed_chain(2)
        session = _ChainSession(chain_rows=rows, event_count=2, missing_ids=[])
        result = CTEPersistence(session).verify_chain("tenant-1")
        assert result.valid is True
        # Ensure the COUNT query we scripted used the right filter.
        count_calls = [c for c in session.calls if "COUNT(*)" in c]
        assert count_calls, "verify_chain must issue the COUNT cross-check query"
        assert all("validation_status != 'rejected'" in c for c in count_calls)


# ---------------------------------------------------------------------------
# #1314 — tamper + orphan combinations still detected
# ---------------------------------------------------------------------------


class TestTamperStillDetected_Issue1314:
    """The #1314 fix must not weaken the existing tamper-detection
    path. A bit-flip in chain_hash must still trip .valid=False, with
    or without structural issues."""

    def test_tamper_detected_even_on_chain_with_orphan(self):
        rows, _ = _well_formed_chain(3)
        # Orphan row 2.
        s, e, p, c, cid, _ = rows[1]
        rows[1] = (s, e, p, c, cid, None)
        # Tamper row 3: flip stored chain_hash.
        s, e, p, c, cid, m = rows[2]
        rows[2] = (s, e, p, "TAMPERED", cid, m)
        session = _ChainSession(chain_rows=rows, event_count=3, missing_ids=[])

        result = CTEPersistence(session).verify_chain("tenant-1")

        assert result.valid is False
        assert result.orphan_chain_rows == [2]
        assert any("Tamper detected at seq=3" in e for e in result.errors)
