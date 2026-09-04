# Dual-write retirement — read-path cutover inventory (WS-1, #1335)

> Status date: 2026-07-14 (WS-1b increment 2). Update this table in every WS-1 PR.

Two write paths persist traceability events with **different
idempotency-key formulas**: the legacy `CTEPersistence` mixins
(`services/shared/cte_persistence/` → `fsma.cte_events`/`fsma.cte_kdes`)
and the canonical writer
(`services/shared/canonical_persistence/writer.py` →
`fsma.traceability_events`). The only cross-store join key is
`sha256_hash`. The retirement sequence is:

1. **Freeze** *(done — WS-1a)*: `tests/invariants/test_dual_write_parity.py`
   runs in CI (repo-root-suite) — a real `dual_write=True` ingest must
   produce both rows with matching `sha256_hash`, and no `cte_events` row
   may lack a canonical twin (#1277 directionality).
2. **Cut reads over** consumer-by-consumer (table below), each behind an
   env flag with a one-release soak, verified by golden comparison
   (legacy read vs canonical read byte-identical on the seeded corpus).
3. **Backfill** legacy rows missing from canonical (join `sha256_hash`),
   then run the full chain-verification suite against canonical only.
4. **Retire writes**: drop `dual_write` from `CanonicalEventStore`,
   read-only trigger on the legacy tables for one release, then archive.
   Delete `DUAL_WRITE_RECONCILIATION_NEEDED` and retire
   `scripts/validate_data_integrity.py`'s reconciliation check from the
   ops runbook.

## Read-path inventory

Verified by grep + manual read on 2026-07-14. "Canonical" means
`fsma.traceability_events` (+ `fsma.hash_chain`); "legacy" means
`fsma.cte_events` / `fsma.cte_kdes`.

| Consumer | Module | Reads today | Cutover action | Status |
|---|---|---|---|---|
| FDA CSV export **v1** | `services/ingestion/app/fda_export/{queries,recall}.py` | **canonical in production** (`FDA_EXPORT_V1_READ_CANONICAL=1` set on Railway 2026-07-17; both stores were empty at flip, parity-checked); code default still legacy | Golden suite (`tests/invariants/test_fda_export_v1_golden.py`) proves legacy ≡ canonical byte-identical on the dual-written corpus across 7 filter combinations. Soak one release, then make canonical the code default | 🟨 flag ON in prod (2026-07-17); soaking, then default flip |
| FDA CSV export **v2** | `services/shared/workflows/export_output.py` | canonical | none — already canonical (preferred format) | ✅ canonical |
| Merkle proof / chain verification (canonical) | `services/shared/canonical_persistence/verification.py` (`verify_chain_canonical`, #2506) | canonical + an **existence-only** probe of `cte_events` for orphan classification (2026-07-24): the real ingest route (`webhook_compat.ingest_events` = legacy `store_event` **+** canonical-only store) appends TWO chain rows per event, so the verifier applies the combine rule — a row is a TRUE orphan only when BOTH stores miss it. Legacy rows are reported in `legacy_chain_rows`, skipped for canonical content recompute, still covered by sequence/linkage/chain_hash checks. WS-1d removes the probe with the legacy store | none | ✅ canonical (dual-write-aware) |
| Chain verification (legacy) | `compliance_score.py` + 3 FDA export handlers (via `_verify_chain_for_export`) | **canonical by default** — flag ON in prod since 2026-07-24, code default flipped to canonical 2026-09-02 (#3039); `CHAIN_VERIFY_READ_CANONICAL=0` is the emergency rollback | Golden (`tests/invariants/test_chain_verify_golden.py`) proves both verifiers agree on dual-written data, the flag switches stores, and — the #3039 rationale — content tampering with intact `hash_chain` rows fails the canonical (default) verifier while the legacy verifier is blind to it. Corpus caveat: golden writes ONE chain row per event; `tests/shared/test_chain_verify_dual_write_live.py` covers the real two-row shape. The chain-verification *job* deliberately walks BOTH stores until WS-1d (#2506) | ✅ canonical by default (#3039) |
| Ingest workflow | `services/shared/workflows/ingest_event.py` | n/a (documents the dual **write**) | write retirement is WS-1d, not a read cutover | ⬜ WS-1d |
| Graph FSMA nodes | `services/graph/app/models/fsma_nodes.py` | none (docstring references the `cte_events` hash **convention** only) | update doc references when tables archive | ✅ no live read |
| Compliance score / snapshots | `services/compliance/`, `server/workers/` | none direct (HTTP to graph service) | none | ✅ no direct read |
| Admin routes (`supplier_onboarding`, `data_export`, `supplier_funnel`, `bulk_upload/templates`) | `services/admin/app/` | none (similarly named response fields / sheet names only) | none | ✅ no live read |
| Frontend proxies | `frontend/src/app/api/**` | none direct (proxy to backend routes above) | inherit their upstream's cutover | ✅ indirect |
| Reconciliation script | `scripts/validate_data_integrity.py` (#2521) | both (compensating control) | retire from runbooks at WS-1d acceptance | ⬜ WS-1d |

### Reading the reconciliation script's result (#2934)

Exit 0 from `scripts/validate_data_integrity.py` is evidence **only** when the
output printed a `[PASS]` line for all four named checks — Hash Chain
Continuity, Orphaned Records, Dual-Write Reconciliation, Tenant Isolation.
Record the printed check table, not just the exit status. When the script
cannot reach the database it exits `2` (or `64` when `DATABASE_URL` is unset),
prints the underlying cause and runs no check at all — that is a NO-GO for the
cutover, never a pass.

## Intentional `dual_write=False` canonical-only writers

`webhook_compat`, `epcis`, `canonical_router`, `auditor_router`,
`webhook_router_v2` already write canonical-only. Canonical rows without
legacy twins are therefore EXPECTED and are not an invariant violation
(directionality documented in the invariant test).

## Never-do list

- Never delete or truncate `fsma.cte_events`/`cte_kdes` until the FDA
  export golden diff over the real seeded corpus is byte-identical
  against canonical (plan risk note).
- Never grow the legacy read surface: new code must read
  `fsma.traceability_events`. The WS-1d CI grep gate will enforce this;
  until then this table is the review checklist.
