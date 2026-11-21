# ADR-007: Stable line identity for EDI events

**Status:** Accepted
**Date:** 2026-11-14
**Decision owner:** RegEngine engineering. Sections 2, 3 and 4 were put to the
repository owner as questions and are recorded as answered.

## Context

Both event stores deduplicate on an idempotency key that hashes every KDE
(`services/shared/cte_persistence/hashing.py`, `TraceabilityEvent.compute_idempotency_key`).
For EDI lines the KDEs include the line's position (`edi_line_index`) and three
envelope numbers (`edi_isa13`, `edi_gs_control_number`, `edi_control_number`).
Neither key covers quantity, unit or product.

Reproduced on `main` at `7472a8d7`, real route into the real key functions of
both stores, for a stored three-line document:

| Resend | Keys | Result |
| --- | --- | --- |
| A. Line 2 removed | Line 3 becomes line 2 and gets a new key | Stored twice |
| B. Line 2 quantity corrected | Unchanged | Dropped, 201, old value stands |
| C. Unchanged, new ISA13 | Every key is new | Every line stored twice |

`main` changed after this work was scoped:

- #3833 stores an interchange completely or not at all, so a partly accepted
  interchange no longer exists.
- #3840 commits a receipt in `fsma.edi_interchanges` with the events. A resend
  under the same ISA13 gets 409 for seven days, changed content included.

So A and B under the **same ISA13** were reachable only after the receipt
expires, or for an envelope with no sender or ISA13. Under a **new ISA13**,
which is what the 409 tells a partner to use, all three were live: unchanged
lines were stored again, and a corrected line landed beside the old value with
both rows active and both exported.

## Decision

### 1. Line identity

A line is the same line when these match. The list is an allowlist, read from
fields the events already carry:

| Field | Source |
| --- | --- |
| Trading partner | `edi_sender_id`, `edi_receiver_id` |
| Transaction set | `edi_transaction_set` |
| Document number | 856 BSN02, 861 BRA01, 944 W1703 (else W1705, W1704), 945 W0604 (else W0602), 850 BEG03, 810 BIG02 |
| Event | CTE type and event date (not time of day) |
| Lot | Traceability lot code, exactly as the event stores it |
| Product | GTIN, else UPC, else the product text, case and spacing folded |
| Occurrence | 1, 2, 3 among lines of the interchange that match on all of the above |

Position and the envelope numbers are not identity. Everything else is
**content**: quantity, unit, time of day, locations and every other KDE. The
envelope and position KDEs and the `X-Partner-ID` header are neither.

Four KDEs are also left out of content because they only restate what is
compared already: `event_date`, `ship_date` and `receive_date` repeat the
timestamp, and `immediate_previous_source` repeats the ship-from party. The two
856 routes name them differently, so counting them would refuse a line that was
stored through one route and sent again through the other.

A line with no sender or no document number has no identity and keeps the
behaviour it had before.

### 2. Identity lives in a registry, not in the keys

`fsma.edi_line_identities` `(tenant_id, identity_key, content_digest, event_id, stored_at)`,
Alembic v145, written in the same transaction as the events. It holds two
hashes and an event id, no business data. Per line, inside `ingest_events` and
only for the EDI routes:

- identity unknown: store as before, then register it;
- identity known, same content: nothing is written and the response reports
  the stored event;
- identity known, different content: see section 3.

**Effect on stored rows: none.** Neither key formula changes. Stored keys,
event hashes and the hash chain are untouched for old and new rows. Rows
stored before v145 are not registered and behave as they did. They can be
registered later by INSERT, without touching an event row.

The registry is read under the tenant's chain lock, the lock both stores take
on their first write, so two envelopes carrying the same line are compared one
after the other. An identity whose event no longer exists is ignored on read
and replaced on the next store.

### 3. A corrected line is refused, loudly

A line whose identity is stored with different content returns HTTP 409
`edi_line_content_conflict` before anything is written. The response names
each stored event, sets `needs_review` and carries a `rejection_id`. It never
returns stored values, because the caller may hold a write-only key. The
rejection record holds each refused line as it was submitted. Nothing
from the interchange is stored and the ISA13 stays free. The correction is
neither dropped nor applied.

The target is the amendment chain the canonical model already defines: a new
event with `supersedes_event_id`, the stored row moving `active` to
`superseded`. That is a separate change, because:

- no ingestion path sets `supersedes_event_id` today;
- `fsma.cte_events` has no status, and the v1 FDA export and recall readers
  default to it (`FDA_EXPORT_V1_READ_CANONICAL` is off), so both rows would be
  exported;
- whether a partner resend may correct evidence without review is a product
  call.

### 4. The ISA13 claim is left as it is

The step "release the claim for partly accepted interchanges" has no case
after #3833, and releasing the Redis claim would not admit a resend: the
receipt answers 409. Corrections arrive under a new ISA13.

## Alternatives considered

1. **Make the identity the idempotency key of new EDI rows.** No migration.
   Stored keys cannot be rewritten (`fsma.cte_events` is append-only since
   v107, and `idempotency_key` is not on the v141 allowlist), so old rows
   could never match the new key: they would lose the replay protection they
   have unless every write also looked up the old key, and could never gain
   the new protection. A correction would later need a second key for the
   superseding row.
2. **Supersede in this change.** Deferred for the reasons in section 3.

## Consequences

- An unchanged line is stored once, whatever envelope or position it arrives in.
- A line missing from a resend is not a retraction. Its stored event stays active.
- Two lines with the same lot and product are told apart by occurrence. If one
  of two such lines with different quantities is removed, the survivor is
  compared with the first stored line and refused as a conflict.
- A sender that reuses a document number on one day for another shipment of
  the same lot and product gets a conflict.
- A reworded free-text product description is a new identity and is stored
  again, as before.
- Content is compared as extracted. A change to how an EDI field is extracted
  makes a line stored before it conflict when sent again.
  `test_edi_line_identity.py` pins one 856 line and one 945 line as the route
  builds them, so such a change to those two sets is seen in review. The
  other four sets are not pinned.
- Refusals are all-or-nothing: one conflicting line holds back the other lines
  of that interchange.
- `POST /api/v1/ingest/edi` and `POST /api/v1/ingest/edi/document` build 856
  events separately. They must give a line the same identity and content, and
  `test_both_856_routes_describe_a_line_the_same_way` holds them to it.
- v145 must be deployed before the application, as v143 was. It follows v144
  (`d8f3a1c6b902`) in the chain, so `alembic upgrade head` applies that first.
- The registry points at `fsma.cte_events`, the id the API returns. It moves
  to the canonical table with that table's cutover (#1335).

## References

- PR 3811, #3833, #3840; `docs/engineering/TRACEABILITY_FILE_INTAKE.md`, Line identity
- `docs/engineering/SCHEMA_CHANGE_POLICY.md` sections 5.1 and 5.2
- #1335 (the two key formulas differ by design)
