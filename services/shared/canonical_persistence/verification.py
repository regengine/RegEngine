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

One degenerate case fails closed (#1314, canonical twin): ZERO chain
rows while non-rejected events exist returns ``valid=False`` with
``no_chain_evidence=True`` — nothing was walked, so there is no basis
for a VERIFIED claim, and an unreadable/emptied chain is
indistinguishable from chain-less ingestion. The error text explicitly
marks this as a no-evidence condition, not a tamper verdict.
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
    """Are chain-verification read paths flagged onto the canonical store?

    Default ON since #3039 (WS-1d P3): the flag has been set in
    production since 2026-07-24 and soaked. The canonical verifier
    recomputes event digests from row *content*; the legacy verifier
    only re-links stored ``event_hash`` values, so content tampering
    that leaves ``hash_chain`` untouched passes legacy verification.
    Set ``CHAIN_VERIFY_READ_CANONICAL=0`` only as an emergency rollback.
    """
    import os

    return os.getenv(CHAIN_VERIFY_READ_CANONICAL_ENV, "1").strip().lower() in {
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
        "legacy_chain_rows",
        "store",
        "no_chain_evidence",
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
    timestamp_hint: Optional[str] = None,
) -> str:
    """Recompute a canonical event's ``sha256_hash`` from row content.

    MUST stay byte-for-byte identical to
    ``TraceabilityEvent.compute_sha256_hash`` (canonical_event.py). A
    drift-guard unit test asserts equality against the production method.
    """
    if isinstance(event_timestamp, datetime):
        # TIMESTAMPTZ preserves the instant, but the driver renders it in the
        # connection's timezone. The normalized snapshot preserves the offset
        # originally hashed. Use only that offset; never replace the authoritative
        # timestamp with the snapshot's date/time (which would conceal tampering).
        original_zone = timezone.utc
        if isinstance(timestamp_hint, str):
            try:
                original_zone = datetime.fromisoformat(timestamp_hint).tzinfo or timezone.utc
            except ValueError:
                pass
        timestamp = event_timestamp if event_timestamp.tzinfo else event_timestamp.replace(tzinfo=timezone.utc)
        ts = timestamp.astimezone(original_zone).isoformat()
    else:
        ts = str(event_timestamp)
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
                       te.event_timestamp, te.kdes,
                       ce.id AS matched_legacy_id,
                       te.normalized_payload->>'event_timestamp' AS hashed_timestamp,
                       te.sha256_hash AS canonical_sha256
                FROM fsma.hash_chain hc
                LEFT JOIN fsma.traceability_events te
                    ON te.event_id = hc.cte_event_id
                   AND te.tenant_id = hc.tenant_id
                -- Existence-only probe of the legacy store: during the WS-1
                -- dual-write window the ingest path appends TWO chain rows
                -- per event (one per store — see webhook_compat.ingest_events:
                -- legacy CTEPersistence.store_event + canonical-only
                -- CanonicalEventStore). A row is a TRUE orphan only when BOTH
                -- stores miss it — the rule chain_verification_job's
                -- _combine_results already documents and applies. No legacy
                -- business data is read (WS-1 never-do list); WS-1d removes
                -- this join with the legacy store itself.
                LEFT JOIN fsma.cte_events ce
                    ON ce.id = hc.cte_event_id
                   AND ce.tenant_id = hc.tenant_id
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
        legacy_chain_rows: List[int] = []

        for i, row in enumerate(rows):
            seq = row[0]
            event_hash = row[1]
            stored_prev = row[2]
            stored_chain = row[3]
            cte_event_id = row[4]
            matched_event_id = row[5]
            matched_legacy_id = row[15]

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
            # During the dual-write window a chain row legitimately lives in
            # only ONE store (the ingest path appends a legacy-id row and a
            # canonical-id row per event). Per the documented combine rule
            # (chain_verification_job._combine_results), a row is a TRUE
            # orphan only when BOTH stores miss it. Legacy-store rows are
            # counted, skipped for canonical content recompute (a
            # canonical-only capability), and still fully covered by the
            # store-agnostic sequence/linkage/chain_hash checks above.
            if matched_event_id is None:
                if matched_legacy_id is not None:
                    legacy_chain_rows.append(int(seq))
                    continue
                orphan_chain_rows.append(int(seq))
                errors.append(
                    f"Orphan chain row at seq={seq}: cte_event_id={cte_event_id} has no matching row in either store"
                )
                continue

            # Event-hash recompute from canonical content — catches a field
            # mutation that did NOT also rewrite sha256_hash.
            #
            # Compared against te.sha256_hash, NOT hc.event_hash: in the
            # webhook ingest topology the chain row is written by the
            # legacy store (CTEPersistence.store_events_batch), so
            # hc.event_hash is the LEGACY digest — a different formula
            # over different fields. Comparing the canonical recompute to
            # it flagged every webhook-ingested event as tampered (found
            # by the 2026-09-02 production-grade data run). For
            # canonical-written chains the two columns are equal, so this
            # comparison covers both topologies.
            canonical_sha = row[17]

            # Chain-row digest check (CodeRabbit review of the prod-grade
            # run fix): a row matching ONLY the canonical store was written
            # by CanonicalEventStore, which sets hc.event_hash =
            # te.sha256_hash by construction — any deviation is chain-row
            # tampering. Rows that ALSO match the legacy store may carry
            # the legacy digest (webhook dual-write topology), so they are
            # exempt here and covered by the recompute below.
            if matched_legacy_id is None and event_hash != canonical_sha:
                if int(seq) not in tamper_rows:
                    tamper_rows.append(int(seq))
                errors.append(
                    f"Chain-row tamper at seq={seq}: chain event_hash "
                    f"{str(event_hash)[:16]}... != canonical sha256_hash "
                    f"{str(canonical_sha)[:16]}..."
                )

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
                timestamp_hint=row[16] if len(row) > 16 else None,
            )
            if recomputed_event != canonical_sha:
                if int(seq) not in tamper_rows:
                    tamper_rows.append(int(seq))
                errors.append(
                    f"Event tamper at seq={seq}: recomputed event_hash "
                    f"{recomputed_event[:16]}... != stored {str(canonical_sha)[:16]}..."
                )

        # EPCIS / skip_chain_write events legitimately have no chain row, so
        # a positive (events_count - canonical rows) is reported but does NOT,
        # on its own, flip valid. Only integrity breaks in the existing rows
        # do. Legacy-store rows are excluded from the count — they do not
        # represent canonical events.
        events_without_chain_row = max(events_count - (len(rows) - len(legacy_chain_rows)), 0)

        # Fail closed on the degenerate case (#1314, canonical twin): ZERO
        # chain rows while non-rejected events exist. The store keeps no
        # per-event marker distinguishing skip_chain_write ingestion from an
        # unreadable (RLS-denied) or emptied chain, so "VERIFIED" here would
        # be a claim made after walking zero rows of evidence. This is NOT a
        # tamper verdict — the error text says so — but the headline must
        # not read VERIFIED. A tenant with SOME chain rows and some
        # legitimately-unchained EPCIS events is unaffected.
        no_chain_evidence = len(rows) == 0 and events_count > 0
        if no_chain_evidence:
            errors.append(
                f"No chain rows exist for tenant with {events_count} non-rejected canonical "
                "events — an unreadable or emptied chain is indistinguishable from chain-less "
                "ingestion, so chain integrity cannot be attested (nothing was walked). "
                "Not a tamper verdict; failing closed rather than reporting VERIFIED."
            )

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
            legacy_chain_rows=legacy_chain_rows,
            store="traceability_events",
            no_chain_evidence=no_chain_evidence,
        )
