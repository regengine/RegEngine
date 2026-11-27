"""#2506 — the only mounted tenant-chain DB verifier
(``CTEPersistence.verify_chain``) LEFT JOINs ``fsma.hash_chain`` to the
*legacy* ``fsma.cte_events`` table. The canonical writer keys every
``hash_chain`` row to ``traceability_events.event_id`` and only writes a
matching ``cte_events`` row under ``dual_write=True``. So a canonical-only
tenant (``dual_write=False`` — the default of the canonical / auditor /
webhook-compat routers) has every chain row reported orphaned and
``valid=False`` — a false "integrity failed" on the FDA-export path.

``CanonicalEventStore.verify_chain_canonical`` joins to
``fsma.traceability_events`` instead, recomputes both the event hash
(from canonical row content) and the chain hash, and flags orphans /
tamper against the canonical store.

These tests drive both verifiers with scripted sessions (no Postgres) and
assert the canonical verifier passes the exact rows the legacy verifier
flags orphaned, that field tampering is caught, and that EPCIS
``skip_chain_write`` events are not falsely counted as a break.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Tuple
from uuid import UUID

import pytest
from shared.canonical_event import CTEType, IngestionSource, TraceabilityEvent
from shared.canonical_persistence.verification import SHARED_ROW_BOUND_FROM, _recompute_event_sha256
from shared.canonical_persistence.writer import CanonicalEventStore
from shared.cte_persistence.core import CTEPersistence
from shared.cte_persistence.hashing import compute_chain_hash

# A chain row shared by both stores must carry the canonical hash when it was
# created at or after SHARED_ROW_BOUND_FROM. These two instants sit on either
# side of it.
_BEFORE_BOUNDARY = SHARED_ROW_BOUND_FROM - timedelta(days=30)
_SINCE_BOUNDARY = SHARED_ROW_BOUND_FROM + timedelta(days=1)

# ---------------------------------------------------------------------------
# Build a real canonical event + its persisted row representation
# ---------------------------------------------------------------------------


def _make_event(seq: int) -> TraceabilityEvent:
    return TraceabilityEvent(
        event_id=UUID(f"00000000-0000-0000-0000-0000000000{seq:02d}"),
        tenant_id=UUID("22222222-2222-2222-2222-222222222222"),
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType.SHIPPING,
        event_timestamp=datetime(2026, 1, 1, 0, seq, 0, tzinfo=timezone.utc),
        product_reference="Romaine Lettuce",
        traceability_lot_code=f"LOT-2026-{seq:03d}",
        quantity=seq,
        unit_of_measure="CASE",
        from_facility_reference="gln-from",
        to_facility_reference="gln-to",
        kdes={"k": seq},
    )


def _canonical_chain(n: int):
    """Return (chain_rows, events) for a well-formed canonical chain of n.

    chain_rows match the SELECT in ``verify_chain_canonical``:
      (sequence_num, event_hash, previous_chain_hash, chain_hash,
       cte_event_id, matched_event_id, event_type, tlc, product_reference,
       quantity, unit_of_measure, from_facility, to_facility,
       event_timestamp, kdes, matched_legacy_id, hashed_timestamp,
       canonical_sha256, chain_row_created_at)
    """
    rows = []
    events = []
    prev = None
    for i in range(1, n + 1):
        ev = _make_event(i)
        sha = ev.compute_sha256_hash()
        chain_hash = compute_chain_hash(sha, prev)
        rows.append(
            (
                i,
                sha,
                prev,
                chain_hash,
                str(ev.event_id),
                str(ev.event_id),  # matched_event_id (canonical row exists)
                ev.event_type.value,
                ev.traceability_lot_code,
                ev.product_reference,
                float(ev.quantity),
                ev.unit_of_measure,
                ev.from_facility_reference,
                ev.to_facility_reference,
                ev.event_timestamp,
                ev.kdes,
                None,  # matched_legacy_id — canonical-only fake rows
                None,  # hashed_timestamp (normalized_payload->>'event_timestamp'); no hint
                sha,  # canonical_sha256 (te.sha256_hash) — writer sets it equal to event_hash
                _SINCE_BOUNDARY,  # chain_row_created_at (hc.created_at)
            )
        )
        events.append(ev)
        prev = chain_hash
    return rows, events


def _shared_row(row, *, event_hash=None, created_at=_SINCE_BOUNDARY) -> list:
    """Turn a canonical-only fake row into one that both stores hold.

    ``event_hash`` replaces the chain row's digest and re-seals the chain
    hash, so the chain itself stays sound.
    """
    r = list(row)
    if event_hash is not None:
        r[1] = event_hash
        r[3] = compute_chain_hash(event_hash, r[2])
    r[15] = r[4]  # matched_legacy_id — the row exists in fsma.cte_events too
    r[18] = created_at
    return r


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _CanonicalSession:
    """Scripted session for ``verify_chain_canonical``: serves the
    traceability_events LEFT-JOIN chain query and the non-rejected count."""

    def __init__(self, chain_rows, event_count):
        self.chain_rows = chain_rows
        self.event_count = event_count

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "LEFT JOIN te" in sql:
            return _Result(self.chain_rows)
        if "COUNT(*)" in sql and "traceability_events" in sql:
            return _Result([(self.event_count,)])
        return _Result([])


class _LegacySession:
    """Scripted session for ``CTEPersistence.verify_chain`` (legacy). For a
    canonical-only tenant, the LEFT JOIN to cte_events yields NULL matches
    (orphans) and the cte_events count is 0."""

    def __init__(self, canonical_rows):
        # Reshape canonical rows into the legacy 6-col chain shape, with
        # matched_event_id=None (no cte_events row exists).
        self.chain_rows = [(r[0], r[1], r[2], r[3], r[4], None) for r in canonical_rows]

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "FROM fsma.hash_chain hc" in sql and "ORDER BY hc.sequence_num" in sql:
            return _Result(self.chain_rows)
        if "COUNT(*)" in sql and "validation_status != 'rejected'" in sql:
            return _Result([(0,)])  # canonical-only: zero cte_events rows
        if "NOT EXISTS" in sql and "FROM fsma.hash_chain hc" in sql:
            return _Result([])
        return _Result([])


# ---------------------------------------------------------------------------
# Core acceptance: canonical-only chain verifies under the canonical verifier
# but is flagged orphaned by the legacy one.
# ---------------------------------------------------------------------------


class TestCanonicalOnlyChain_Issue2506:
    def test_canonical_verifier_passes_dual_write_false_chain(self):
        rows, _ = _canonical_chain(3)
        store = CanonicalEventStore(_CanonicalSession(rows, event_count=3), dual_write=False)
        result = store.verify_chain_canonical("22222222-2222-2222-2222-222222222222")
        assert result.valid is True
        assert result.orphan_chain_rows == []
        assert result.tamper_rows == []
        assert result.chain_length == 3
        assert result.store == "traceability_events"

    def test_legacy_verifier_flags_same_rows_orphaned(self):
        rows, _ = _canonical_chain(3)
        legacy = CTEPersistence(_LegacySession(rows))
        result = legacy.verify_chain("22222222-2222-2222-2222-222222222222")
        # The exact regression: legacy walks cte_events and orphans every row.
        assert result.valid is False
        assert result.orphan_chain_rows == [1, 2, 3]


# ---------------------------------------------------------------------------
# Tamper detection: mutate a canonical field without updating sha256_hash.
# ---------------------------------------------------------------------------


class TestCanonicalTamperDetection_Issue2506:
    def test_field_mutation_without_hash_update_is_caught(self):
        rows, _ = _canonical_chain(2)
        # Tamper row 2's quantity (index 9) — sha256/event_hash unchanged.
        r = list(rows[1])
        r[9] = 999.0
        rows[1] = tuple(r)
        store = CanonicalEventStore(_CanonicalSession(rows, event_count=2), dual_write=False)
        result = store.verify_chain_canonical("22222222-2222-2222-2222-222222222222")
        assert result.valid is False
        assert 2 in result.tamper_rows
        assert any("Event tamper at seq=2" in e for e in result.errors)

    def test_chain_hash_tamper_is_caught(self):
        rows, _ = _canonical_chain(2)
        r = list(rows[1])
        r[3] = "f" * 64  # corrupt stored chain_hash
        rows[1] = tuple(r)
        store = CanonicalEventStore(_CanonicalSession(rows, event_count=2), dual_write=False)
        result = store.verify_chain_canonical("22222222-2222-2222-2222-222222222222")
        assert result.valid is False
        assert 2 in result.tamper_rows

    def test_chain_row_event_hash_reseal_is_caught(self):
        """CodeRabbit follow-up to the prod-grade run fix: rewrite a
        canonical-only row's event_hash AND a CONSISTENT chain_hash —
        linkage and chain_hash recompute both pass, and the content
        recompute never reads the chain row. The strict
        ``hc.event_hash == te.sha256_hash`` check must flag it."""
        rows, _ = _canonical_chain(2)
        r = list(rows[1])
        fake_event_hash = "e" * 64
        r[1] = fake_event_hash
        r[3] = compute_chain_hash(fake_event_hash, r[2])  # consistent re-seal
        rows[1] = tuple(r)
        store = CanonicalEventStore(_CanonicalSession(rows, event_count=2), dual_write=False)
        result = store.verify_chain_canonical("22222222-2222-2222-2222-222222222222")
        assert result.valid is False
        assert 2 in result.tamper_rows
        assert any("Chain-row tamper at seq=2" in e for e in result.errors)

    def test_legacy_matched_row_with_legacy_digest_is_not_flagged(self):
        """Webhook dual-write topology (2026-09-02 prod-grade run): the
        chain row is legacy-written, so hc.event_hash is the LEGACY digest
        — different from te.sha256_hash by design. Rows that also match
        the legacy store and were created before SHARED_ROW_BOUND_FROM
        must be exempt from the strict equality check, otherwise every
        event the webhook route ingested back then reads as tampered."""
        rows, _ = _canonical_chain(2)
        r = list(rows[1])
        legacy_digest = "a" * 64  # legacy formula output ≠ canonical sha
        r[1] = legacy_digest
        r[3] = compute_chain_hash(legacy_digest, r[2])  # legacy-written chain is internally sound
        r[15] = r[4]  # matched_legacy_id — row exists in fsma.cte_events too
        r[18] = _BEFORE_BOUNDARY  # the chain row predates the writers that hash canonical content
        rows[1] = tuple(r)
        store = CanonicalEventStore(_CanonicalSession(rows, event_count=2), dual_write=False)
        result = store.verify_chain_canonical("22222222-2222-2222-2222-222222222222")
        assert result.valid is True, result.errors
        assert result.tamper_rows == []


class TestSharedRowBinding:
    """A chain row shared by both stores binds the canonical content.

    Every current writer puts the canonical hash into a shared row, and the
    canonical writer refuses to attach a row to a chain entry that holds
    another hash. A shared row created at or after SHARED_ROW_BOUND_FROM
    that disagrees with its canonical row is therefore reported. Older rows
    keep the exemption covered by
    ``test_legacy_matched_row_with_legacy_digest_is_not_flagged``.
    """

    TENANT = "22222222-2222-2222-2222-222222222222"

    def _verify(self, rows):
        store = CanonicalEventStore(_CanonicalSession(rows, event_count=len(rows)), dual_write=False)
        return store.verify_chain_canonical(self.TENANT)

    def _assert_chain_row_tamper_at_2(self, result) -> None:
        assert result.valid is False
        assert result.tamper_rows == [2]
        assert any("Chain-row tamper at seq=2" in e for e in result.errors), result.errors

    def test_shared_row_with_matching_hashes_verifies(self):
        rows, _ = _canonical_chain(2)
        rows[1] = tuple(_shared_row(rows[1]))
        result = self._verify(rows)
        assert result.valid is True, result.errors
        assert result.tamper_rows == []

    def test_shared_row_created_since_the_boundary_must_carry_the_canonical_hash(self):
        rows, _ = _canonical_chain(2)
        rows[1] = tuple(_shared_row(rows[1], event_hash="a" * 64))
        self._assert_chain_row_tamper_at_2(self._verify(rows))

    def test_the_boundary_instant_itself_is_bound(self):
        rows, _ = _canonical_chain(2)
        rows[1] = tuple(_shared_row(rows[1], event_hash="a" * 64, created_at=SHARED_ROW_BOUND_FROM))
        self._assert_chain_row_tamper_at_2(self._verify(rows))

    def test_canonical_content_rewritten_with_its_hash_is_reported(self):
        """The rewrite the exemption used to hide: new content, a stored hash
        that matches it, and an untouched chain row."""
        rows, _ = _canonical_chain(2)
        r = _shared_row(rows[1])
        r[9] = 999.0
        r[17] = _recompute_event_sha256(
            event_id=r[4],
            event_type=r[6],
            traceability_lot_code=r[7],
            product_reference=r[8],
            quantity=r[9],
            unit_of_measure=r[10],
            from_facility_reference=r[11],
            to_facility_reference=r[12],
            event_timestamp=r[13],
            kdes=r[14],
            timestamp_hint=r[16],
        )
        rows[1] = tuple(r)
        result = self._verify(rows)
        self._assert_chain_row_tamper_at_2(result)
        # The row agrees with itself, so only the chain row can catch it.
        assert not any("Event tamper" in e for e in result.errors), result.errors

    @pytest.mark.parametrize("created_at", [None, "2026-08-01T00:00:00+00:00", 0])
    def test_shared_row_with_an_unreadable_creation_time_is_bound(self, created_at):
        rows, _ = _canonical_chain(2)
        rows[1] = tuple(_shared_row(rows[1], event_hash="a" * 64, created_at=created_at))
        self._assert_chain_row_tamper_at_2(self._verify(rows))

    def test_shared_row_from_a_result_without_the_creation_time_is_bound(self):
        rows, _ = _canonical_chain(2)
        rows[1] = tuple(_shared_row(rows[1], event_hash="a" * 64)[:18])
        self._assert_chain_row_tamper_at_2(self._verify(rows))

    @pytest.mark.parametrize(
        ("created_at", "exempt"),
        [
            (_BEFORE_BOUNDARY.replace(tzinfo=None), True),
            (_SINCE_BOUNDARY.replace(tzinfo=None), False),
        ],
    )
    def test_creation_time_without_a_zone_is_read_as_utc(self, created_at, exempt):
        rows, _ = _canonical_chain(2)
        rows[1] = tuple(_shared_row(rows[1], event_hash="a" * 64, created_at=created_at))
        result = self._verify(rows)
        if exempt:
            assert result.valid is True, result.errors
        else:
            self._assert_chain_row_tamper_at_2(result)

    def test_creation_time_in_another_zone_is_compared_as_an_instant(self):
        """One hour before the boundary, written with a +05:00 offset: the
        wall-clock reading is after the boundary, the instant is before it."""
        rows, _ = _canonical_chain(2)
        just_before = (SHARED_ROW_BOUND_FROM - timedelta(hours=1)).astimezone(timezone(timedelta(hours=5)))
        rows[1] = tuple(_shared_row(rows[1], event_hash="a" * 64, created_at=just_before))
        result = self._verify(rows)
        assert result.valid is True, result.errors


# ---------------------------------------------------------------------------
# EPCIS skip_chain_write events are NOT falsely counted as a break.
# ---------------------------------------------------------------------------


class TestEpcisSkipChainWrite_Issue2506:
    def test_unchained_events_do_not_flip_valid(self):
        """3 canonical events exist, only 2 are chained (the 3rd was written
        with skip_chain_write=True). The chain rows are internally sound, so
        the verifier stays valid=True but surfaces events_without_chain_row."""
        rows, _ = _canonical_chain(2)
        store = CanonicalEventStore(_CanonicalSession(rows, event_count=3), dual_write=False)
        result = store.verify_chain_canonical("22222222-2222-2222-2222-222222222222")
        assert result.valid is True
        assert result.events_without_chain_row == 1
        assert result.traceability_events_count == 3

    def test_empty_chain_no_events_is_valid(self):
        store = CanonicalEventStore(_CanonicalSession([], event_count=0), dual_write=False)
        result = store.verify_chain_canonical("22222222-2222-2222-2222-222222222222")
        assert result.valid is True
        assert result.chain_length == 0
        assert result.events_without_chain_row == 0
        assert result.no_chain_evidence is False

    def test_empty_chain_with_events_fails_closed(self):
        """Silent-failure sweep (#1314 canonical twin): ZERO chain rows
        while non-rejected events exist must NOT report VERIFIED — an
        unreadable (RLS-denied) or emptied chain is indistinguishable
        from chain-less ingestion, and nothing was walked."""
        store = CanonicalEventStore(_CanonicalSession([], event_count=5), dual_write=False)
        result = store.verify_chain_canonical("22222222-2222-2222-2222-222222222222")
        assert result.valid is False
        assert result.no_chain_evidence is True
        assert result.chain_length == 0
        # Explicitly a no-evidence condition, not a tamper verdict.
        assert result.tamper_rows == []
        assert any("Not a tamper verdict" in e for e in result.errors)

    def test_partial_chain_with_events_keeps_no_evidence_false(self):
        rows, _ = _canonical_chain(1)
        store = CanonicalEventStore(_CanonicalSession(rows, event_count=4), dual_write=False)
        result = store.verify_chain_canonical("22222222-2222-2222-2222-222222222222")
        assert result.valid is True
        assert result.no_chain_evidence is False


# ---------------------------------------------------------------------------
# Orphan canonical chain row (event_id with no traceability_events row).
# ---------------------------------------------------------------------------


class TestCanonicalOrphan_Issue2506:
    def test_orphan_row_flips_valid(self):
        rows, _ = _canonical_chain(2)
        # Null out matched_event_id (index 5) for row 1 → orphan.
        r = list(rows[0])
        r[5] = None
        rows[0] = tuple(r)
        store = CanonicalEventStore(_CanonicalSession(rows, event_count=2), dual_write=False)
        result = store.verify_chain_canonical("22222222-2222-2222-2222-222222222222")
        assert result.valid is False
        assert result.orphan_chain_rows == [1]
