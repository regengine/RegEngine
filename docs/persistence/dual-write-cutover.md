# Dual-write retirement — read-path cutover inventory (WS-1, #1335)

> Status date: 2026-07-14 (WS-1a). Update this table in every WS-1 PR.

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
| FDA CSV export **v1** | `services/shared/workflows/export_output.py` | **legacy** (`cte_events`) | Deprecate v1 or re-point at canonical behind `EXPORT_V1_READ_CANONICAL`; golden CSV byte-diff on seeded corpus before flip | ⬜ pending (WS-1b, first) |
| FDA CSV export **v2** | `services/shared/workflows/export_output.py` | canonical | none — already canonical (preferred format) | ✅ canonical |
| Merkle proof / chain verification (canonical) | `services/shared/canonical_persistence/verification.py` (`verify_chain_canonical`, #2506) | canonical | none | ✅ canonical |
| Chain verification (legacy) | `services/shared/cte_persistence/verification.py` (`verify_chain`, `verify_chain_merkle`) | **legacy** | Callers move to `verify_chain_canonical`; retire with the mixins in WS-1d | ⬜ pending (WS-1b) |
| Ingest workflow | `services/shared/workflows/ingest_event.py` | n/a (documents the dual **write**) | write retirement is WS-1d, not a read cutover | ⬜ WS-1d |
| Graph FSMA nodes | `services/graph/app/models/fsma_nodes.py` | none (docstring references the `cte_events` hash **convention** only) | update doc references when tables archive | ✅ no live read |
| Compliance score / snapshots | `services/compliance/`, `server/workers/` | none direct (HTTP to graph service) | none | ✅ no direct read |
| Admin routes (`supplier_onboarding`, `data_export`, `supplier_funnel`, `bulk_upload/templates`) | `services/admin/app/` | none (similarly named response fields / sheet names only) | none | ✅ no live read |
| Frontend proxies | `frontend/src/app/api/**` | none direct (proxy to backend routes above) | inherit their upstream's cutover | ✅ indirect |
| Reconciliation script | `scripts/validate_data_integrity.py` (#2521) | both (compensating control) | retire from runbooks at WS-1d acceptance | ⬜ WS-1d |

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
