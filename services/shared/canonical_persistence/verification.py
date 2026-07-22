"""Canonical hash-chain verification (#2506).

The legacy verifier ``CTEPersistence.verify_chain`` LEFT JOINs
``fsma.hash_chain`` to the *legacy* ``fsma.cte_events`` table. The
canonical writer keys every ``hash_chain`` row to
``traceability_events.event_id`` and only writes a matching
``cte_events`` row when ``dual_write=True``. So for canonical-only
tenants (the default of the canonical / auditor / webhook-compat
routers) the legacy verifier flags every chain row orphaned and returns
``valid=False`` — a false "integrity failed" on the regulator-facing
export.

This module verifies the chain against the canonical store of record:

  * LEFT JOINs ``fsma.hash_chain`` to ``fsma.traceability_events`` on
    ``event_id = hash_chain.cte_event_id`` (tenant-scoped).
  * Recomputes each event hash from the canonical row content (matching
    ``TraceabilityEvent.compute_sha256_hash``) and compares it to the
    stored ``hash_chain.event_hash`` — so tampering with a
    ``traceability_events`` field WITHOUT updating ``sha256_hash`` is
    caught.
  * Recomputes ``chain_hash`` via ``compute_chain_hash`` and checks
    sequence continuity + ``previous_chain_hash`` linkage.
  * Flags orphan chain rows against ``traceability_events``.

EPCIS / ``skip_chain_write=True`` events intentionally have NO chain
row. They are therefore NOT cross-counted as "missing": the canonical
verifier reports ``events_without_chain_row`` for visibility but does
NOT flip ``valid`` on that count alone, because canonical-only mode
legitimately leaves some events unchained. A break in the rows that DO
exist (orphan / tamper / linkage) still flips ``valid=False``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.cte_persistence import compute_chain_hash
from sqlalchemy import text

# ---------------------------------------------------------------------------
# WS-1b (#1335): flag for cutting chain-verification READERS over to the
# canonical store. Consumers (compliance_score, FDA export handlers) only
# consume ``.valid``/``.errors``, which both ChainVerification (legacy) and
# CanonicalChainVerification expose — so the cutover is duck-type safe.
# Default OFF; flipping is a release/soak decision
# (docs/persistence/dual-write-cutover.md). The chain-verification JOB
# (chain_verification_job.py) deliberately keeps walking BOTH stores until
# WS-1d (#2506) and does not use this flag.
# ---------------------------------------------------------------------------

CHAIN_VERIFY_READ_CANONICAL_ENV = "CHAIN_VERIFY_READ_CANONICAL"


def chain_verify_reads_canonical() -> bool:
    """Are chain-verification read paths flagged onto the canonical store?"""
    import os

    return os.getenv(CHAIN_VERIFY_READ_CANONICAL_ENV, "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class CanonicalChainVerification:
    """Result of verifying a tenant's canonical hash chain.

    ``store`` records which table the verifier walked so callers /
    exports can surface what the proof actually covered.
    """

    __slots__ = (
        "valid",
        "chain_length",
        "errors",
        "checked_at",
        "orphan_chain_rows",
        "tamper_rows",
        "traceability_events_count",
        "events_without_chain_row",
        "store",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))


def _recompute_event_sha256(
    event_id: str,
    event_type: str,
    traceability_lot_code: str,
    product_reference: Optional[str],
    quantity: Any,
    unit_of_measure: str,
    from_facility_reference: Optional[str],
    to_facility_reference: Optional[str],
    event_timestamp: Any,
    kdes: Dict[str, Any],
) -> str:
    """Recompute a canonical event's ``sha256_hash`` from row content.

    MUST stay byte-for-byte identical to
    ``TraceabilityEvent.compute_sha256_hash`` (canonical_event.py). A
    drift-guard unit test asserts equality against the production method.
    """
    ts = event_timestamp.isoformat() if hasattr(event_timestamp, "isoformat") else str(event_timestamp)
    canonical = "|".join(
        [
            str(event_id),
            event_type,
            traceability_lot_code,
            product_reference or "",
            str(quantity),
            unit_of_measure,
            from_facility_reference or "",
            to_facility_reference or "",
            ts,
            json.dumps(kdes, sort_keys=True, default=str),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CanonicalChainVerificationMixin:
    """Chain verification against ``fsma.traceability_events`` — mixed
    into :class:`writer.CanonicalEventStore`."""

    def verify_chain_canonical(self, tenant_id: str) -> CanonicalChainVerification:
        """Verify a tenant's hash chain against the canonical store.

        See module docstring for the join / recompute / EPCIS-exclusion
        contract.
        """
        checked_at = datetime.now(timezone.utc).isoformat()

        rows = self.session.execute(
            text("""
                SELECT hc.sequence_num, hc.event_hash,
                       hc.previous_chain_hash, hc.chain_hash,
                       hc.cte_event_id,
                       te.event_id AS matched_event_id,
                       te.event_type, te.traceability_lot_code,
                       te.product_reference, te.quantity, te.unit_of_measure,
                       te.from_facility_reference, te.to_facility_reference,
                       te.event_timestamp, te.kdes
                FROM fsma.hash_chain hc
                LEFT JOIN fsma.traceability_events te
                    ON te.event_id = hc.cte_event_id
                   AND te.tenant_id = hc.tenant_id
                WHERE hc.tenant_id = :tid
                ORDER BY hc.sequence_num ASC
            """),
            {"tid": tenant_id},
        ).fetchall()

        # Non-rejected canonical events (the universe that COULD be chained).
        count_row = self.session.execute(
            text("""
                SELECT COUNT(*)
                FROM fsma.traceability_events
                WHERE tenant_id = :tid
                  AND status != 'rejected'
            """),
            {"tid": tenant_id},
        ).fetchone()
        events_count = int(count_row[0]) if count_row else 0

        errors: List[str] = []
        orphan_chain_rows: List[int] = []
        tamper_rows: List[int] = []

        for i, row in enumerate(rows):
            seq = row[0]
            event_hash = row[1]
            stored_prev = row[2]
            stored_chain = row[3]
            cte_event_id = row[4]
            matched_event_id = row[5]

            # Sequence continuity.
            expected_seq = i + 1
            if seq != expected_seq:
                errors.append(f"Sequence gap: expected {expected_seq}, got {seq}")

            # previous_chain_hash linkage.
            if i == 0:
                if stored_prev is not None:
                    errors.append(f"Genesis entry (seq={seq}) has non-null previous_chain_hash")
            else:
                expected_prev = rows[i - 1][3]
                if stored_prev != expected_prev:
                    errors.append(
                        f"Chain break at seq={seq}: stored prev "
                        f"{str(stored_prev)[:16]}... != expected {str(expected_prev)[:16]}..."
                    )

            # chain_hash recompute.
            recomputed_chain = compute_chain_hash(event_hash, stored_prev)
            if recomputed_chain != stored_chain:
                errors.append(
                    f"Tamper detected at seq={seq}: recomputed chain_hash "
                    f"{recomputed_chain[:16]}... != stored {str(stored_chain)[:16]}..."
                )
                if int(seq) not in tamper_rows:
                    tamper_rows.append(int(seq))

            # Orphan: chain row references an event_id with no canonical row.
            if matched_event_id is None:
                orphan_chain_rows.append(int(seq))
                errors.append(
                    f"Orphan chain row at seq={seq}: cte_event_id={cte_event_id} "
                    f"has no matching fsma.traceability_events row"
                )
                continue

            # Event-hash recompute from canonical content — catches a field
            # mutation that did NOT also rewrite sha256_hash/event_hash.
            recomputed_event = _recompute_event_sha256(
                event_id=cte_event_id,
                event_type=row[6],
                traceability_lot_code=row[7],
                product_reference=row[8],
                quantity=row[9],
                unit_of_measure=row[10],
                from_facility_reference=row[11],
                to_facility_reference=row[12],
                event_timestamp=row[13],
                kdes=row[14] if isinstance(row[14], dict) else json.loads(row[14] or "{}"),
            )
            if recomputed_event != event_hash:
                if int(seq) not in tamper_rows:
                    tamper_rows.append(int(seq))
                errors.append(
                    f"Event tamper at seq={seq}: recomputed event_hash "
                    f"{recomputed_event[:16]}... != stored {str(event_hash)[:16]}..."
                )

        # EPCIS / skip_chain_write events legitimately have no chain row, so
        # a positive (events_count - len(rows)) is reported but does NOT, on
        # its own, flip valid. Only integrity breaks in the existing rows do.
        events_without_chain_row = max(events_count - len(rows), 0)

        valid = len(errors) == 0 and not orphan_chain_rows and not tamper_rows

        return CanonicalChainVerification(
            valid=valid,
            chain_length=len(rows),
            errors=errors,
            checked_at=checked_at,
            orphan_chain_rows=orphan_chain_rows,
            tamper_rows=tamper_rows,
            traceability_events_count=events_count,
            events_without_chain_row=events_without_chain_row,
            store="traceability_events",
        )
