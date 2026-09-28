# Run Ledger Schema

The operational run ledger extends the existing `fsma.ingestion_runs` table
with append-only state receipts in `fsma.ingestion_run_receipts`.

## Receipt States

Each receipt records one state transition:

- `received`
- `validated`
- `canonicalized`
- `evidence_persisted`
- `rule_evaluated`
- `export_ready`
- `export_generated`
- `failed`
- `needs_review`

## Integrity Contract

Receipts are tenant-scoped and append-only. The database computes:

- `payload_hash`: SHA-256 over receipt `metadata`
- `previous_receipt_hash`: prior receipt hash for the same ingestion run
- `receipt_hash`: SHA-256 over receipt identity, state, linked artifact IDs,
  payload hash, and previous receipt hash

The insert trigger enforces contiguous `sequence_num` values per ingestion run
and rejects caller-provided `previous_receipt_hash` values that do not match the
current chain head. It runs with the caller's rights and serialises appends by
locking the parent `fsma.ingestion_runs` row (v126), so the runtime role needs
no UPDATE privilege on the append-only ledger.

## Evidence Links

Receipts can link a run transition to persisted spine artifacts:

- `canonical_event_id` -> `fsma.traceability_events.event_id`
- `evidence_attachment_id` -> `fsma.evidence_attachments.id`
- `rule_evaluation_id` -> `fsma.rule_evaluations.evaluation_id`
- `export_log_id` -> `fsma.fda_export_log.id`

Composite foreign keys include `tenant_id`, so a receipt cannot link to another
tenant's evidence record.

## Operator Read Model

`shared.run_ledger` exposes the read-side contract for operators and support
workflows. `fetch_ingestion_run_timeline()` returns the ingestion run summary,
ordered receipts, and `verification` metadata for the chain:

- `valid`: whether the observed receipt rows form a contiguous hash chain
- `chain_length`: number of receipts inspected
- `head_receipt_hash`: hash at the current chain head
- `errors`: read-side integrity findings, if any

The canonical records API exposes this as:

```http
GET /api/v1/records/ingestion-runs/{run_id}/timeline
```

The endpoint is read-only. It applies tenant RLS context, returns `404` when
the run is absent, and reports chain breaks in the response instead of
mutating or repairing ledger rows.

## Scope

This schema does not alter `kernel/evidence/envelope.py` and does not persist
agent artifacts. It creates the deterministic receipt ledger those later
integrations can reference.
