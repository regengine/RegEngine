"""SEL-599: real canonical ledger verification with schema-derived inputs.

The session only supplies rows; production recomputes all hashes and decides
validity. No VERIFIED status is mocked. ``valid`` is the verifier contract,
not a claim that a lot has a complete supply-chain history.

Cases left out
--------------
1: no per-lot harvest-through-receive completeness/status implementation exists
in CanonicalChainVerificationMixin. A complete hash ledger is tested separately
below, without claiming this satisfies the supply-chain acceptance case.
2: no CTE missing-link gap report exists here. Removing a ledger middle row is
covered, but a sequence gap does not name a missing harvest/shipping/etc. link.
3: TraceabilityEvent has supersedes_event_id (amendment), not previous_event_id.
Broken previous_chain_hash linkage is covered as the existing ledger contract.
5: canonical verification is tenant-wide, not lot-scoped. It cannot keep lot Y
VERIFIED independently of broken lot X in the same tenant.
6: EPCIS uses a separate persistence path and skip_chain_write events may have
no ledger row. No isolated round-trip harness establishes the requested lot
status contract; export code is deliberately untouched.
4 and 7: strict expected failures below demonstrate singleton acceptance and
partial ledger coverage on this checkout. No claim about another revision is
made. Removing the markers after a fix will make these normal acceptance tests.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from shared.canonical_event import CTEType, TraceabilityEvent
from shared.canonical_persistence import CanonicalEventStore
from shared.canonical_persistence.verification import _recompute_event_sha256
from shared.cte_persistence import compute_chain_hash


def _ledger():
    """Derive cardinality/types from the enum; use only opaque runtime values."""
    rows = []
    lot = str(uuid4())
    quantity = next(bound.ge for bound in TraceabilityEvent.model_fields["quantity"].metadata if hasattr(bound, "ge"))
    previous = None
    for sequence, event_type in enumerate(CTEType, start=1):
        event_id = str(uuid4())
        timestamp = datetime.now(timezone.utc)
        unit = str(uuid4())
        digest = _recompute_event_sha256(
            event_id,
            event_type.value,
            lot,
            None,
            quantity,
            unit,
            None,
            None,
            timestamp,
            {},
        )
        chain_hash = compute_chain_hash(digest, previous)
        # Exact SELECT projection of verify_chain_canonical; no legacy match.
        rows.append(
            (
                sequence,
                digest,
                previous,
                chain_hash,
                event_id,
                event_id,
                event_type.value,
                lot,
                None,
                quantity,
                unit,
                None,
                None,
                timestamp,
                {},
                None,
                timestamp.isoformat(),
                digest,
            )
        )
        previous = chain_hash
    return rows


def _verify(rows, event_count):
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = rows
    session.execute.return_value.fetchone.return_value = (event_count,)
    result = CanonicalEventStore(session, dual_write=False, meter_usage=False).verify_chain_canonical(str(uuid4()))
    # Both real queries must bind the same tenant. No external connection exists.
    bound_tenants = [call.args[1]["tid"] for call in session.execute.call_args_list]
    assert bound_tenants and all(tenant == bound_tenants[0] for tenant in bound_tenants)
    return result


def test_complete_hash_ledger_passes_integrity_walk():
    rows = _ledger()
    result = _verify(rows, len(rows))
    assert result.valid and not result.errors
    assert result.chain_length == result.traceability_events_count == len(rows)
    assert not result.events_without_chain_row


def test_removed_middle_ledger_row_reports_sequence_gap():
    rows = _ledger()
    middle = len(rows) // 2
    missing = rows[middle]
    result = _verify(rows[:middle] + rows[middle + 1 :], len(rows))
    assert not result.valid
    assert any(f"expected {missing[0]}," in error for error in result.errors)
    assert result.events_without_chain_row == len(rows) - result.chain_length


def test_dangling_previous_chain_hash_fails_integrity_walk():
    rows = _ledger()
    middle = len(rows) // 2
    broken = list(rows[middle])
    broken[2] = compute_chain_hash(str(uuid4()), None)
    # Rehash this row, so linkage itself must be checked, not only its digest.
    broken[3] = compute_chain_hash(broken[1], broken[2])
    rows[middle] = tuple(broken)
    result = _verify(rows, len(rows))
    assert not result.valid
    assert any(f"Chain break at seq={broken[0]}:" in error for error in result.errors)


def test_events_without_any_chain_evidence_fail_closed():
    rows = _ledger()
    result = _verify([], len(rows))
    assert not result.valid and result.no_chain_evidence and result.errors
    assert result.events_without_chain_row == len(rows)


@pytest.mark.xfail(strict=True, reason="SEL-599 fix not merged")
def test_single_event_is_not_verified():
    singleton = _ledger()[:1]
    result = _verify(singleton, len(singleton))
    assert not result.valid


@pytest.mark.xfail(strict=True, reason="SEL-599 fix not merged")
def test_unchained_events_prevent_full_chain_verification():
    rows = _ledger()
    # One genuine ledger prefix, with the remaining canonical events unchained.
    prefix = rows[:1]
    result = _verify(prefix, len(rows))
    assert result.events_without_chain_row == len(rows) - len(prefix)
    assert not result.valid
