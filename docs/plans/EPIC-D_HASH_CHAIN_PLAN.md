# EPIC-D — Hash-chain appender + idempotency unification — plan

**Meta-issue:** [#1457](https://github.com/PetrefiedThunder/RegEngine/issues/1457)
**Status when plan written:** 6 open children after code survey.
**Recommendation:** ship in **three** PRs (down from the plan doc's four),
bundled security-before-refactor.

---

## 1. Key finding before coding

EPIC-D's issue list conflated two orthogonal problems:

1. **Three independent writers share the same bug family** (canonical,
   cte, admin audit).
2. **cte_persistence is labelled LEGACY but has 11+ live callers**
   (`webhook_router_v2`, `epcis/persistence`, `fda_export/*`, etc.).

Writing a single `HashChainAppender` and retrofitting everything into
one PR is too wide a blast radius. And issue **#1074** (tagged on the
epic) is actually about a bulk-upload status check-then-set race in
`services/admin/app/bulk_upload/routes.py` — not a hash-chain bug.
Moving #1074 out of EPIC-D; it belongs with admin work (EPIC-K).

After code survey, the open children group cleanly into 3 PRs:

| PR | Closes | Shape | Blast radius |
|---|---|---|---|
| PR-A | #1313, #1266, #1332 | Surgical fixes, 1-3 lines each | Low |
| PR-B | #1248 | UNIQUE constraint migration + graceful IntegrityError | Medium |
| PR-C | #1335 | Retire cte_persistence OR unify hash helpers | Large (deferred) |

#1074 — move to EPIC-K (admin/RBAC hygiene).

---

## 2. Code census — three writers found

| File | LOC | Role | Status |
|---|---|---|---|
| `services/shared/canonical_persistence/writer.py` | 835 | Canonical event + chain writer. Uses `pg_advisory_xact_lock(hashtext(tid))`. | Hardened in #1251 / #1252 / #1262. |
| `services/shared/cte_persistence/core.py` | 1,397 | LEGACY dual-write. 11+ live callers. Uses `FOR UPDATE LIMIT 1` pattern that bug-locks on zero rows. | Needs lock fix (#1332) + dedup with canonical (#1335). |
| `services/admin/app/audit.py` | 165 | Admin security audit chain (AuditLogModel). SELECT-then-INSERT via ORM, not raw SQL. | Out of scope — different table, different guarantees, low volume. |

Admin audit chain is NOT consolidated with canonical/CTE — it writes
`integrity_hash` on `audit_logs`, not `chain_hash` on `hash_chain`. No
consolidation wins; keep it separate. `admin/audit.py` is cleaner
than the other two and doesn't have the `FOR UPDATE LIMIT 1` bug.

---

## 3. PR-A: Three surgical fixes

**Scope:** each under ~30 LOC. Ship first because the fixes stand
alone and #1313 is a silent data-loss bug.

### 3a. #1313 — `compute_idempotency_key` missing `default=str`

`services/shared/cte_persistence/hashing.py:71-91`. `compute_event_hash`
at line 39 passes `default=str` to `json.dumps`; `compute_idempotency_key`
doesn't. A KDE carrying a `datetime` or `Decimal` raises `TypeError`
mid-insert, losing the event.

Fix: add `default=str` to match the event-hash formula. Add a regression
test with datetime and Decimal values in KDEs.

The issue recommends "explicit normalization" because `str(datetime)` is
locale/version-fragile. I agree — but that's a breaking change to
existing idempotency keys (silent Python upgrade would change them
anyway, so the value of stability is already illusory). Ship `default=str`
first; add explicit normalization in PR-C when we decide cte_persistence's
fate. Document the caveat.

### 3b. #1266 — `_batch_insert_canonical_events` all-or-nothing failure

`services/shared/canonical_persistence/writer.py:693-709`. Multi-row
INSERT without `ON CONFLICT`. If one row in a 50-row chunk collides on
`(tenant_id, idempotency_key)`, the whole chunk aborts — 49 good events
lost.

Fix: append `ON CONFLICT (tenant_id, idempotency_key) DO NOTHING` +
`RETURNING event_id`. Count returned rows vs input rows to identify
duplicates; log duplicates separately. Keep chain-write inside the same
transaction so chain integrity is preserved.

Must also re-check the idempotency-map for the duplicates: if we
skipped inserting because of a conflict, we still need to return the
existing row's `sha256_hash` and `chain_hash` to the caller so the
per-event result is correct.

### 3c. #1332 — `cte_persistence.core._fetch_chain_head` race on first event

`services/shared/cte_persistence/core.py:159-169,403-413`. `FOR UPDATE`
on a query that returns zero rows (first event for a tenant) locks
nothing. Two concurrent first-event writers both see `chain_head=None`
and both compute `sequence_num=1`.

Fix: take `pg_advisory_xact_lock(hashtext(tenant_id))` at the top of
each chain-growing method, mirroring `canonical_persistence.writer._acquire_chain_lock`.
Idempotent, transaction-scoped, released automatically on COMMIT /
ROLLBACK.

**Test:** simulate two concurrent first-event inserts by calling the
chain-growth path twice with a forked session; assert the second caller
blocks until the first commits, then produces sequence_num=2.

---

## 4. PR-B: UNIQUE constraint for #1248

**Scope:** one migration + a small tweak to `webhook_router_v2` and
`webhook_compat` to return 409 on `IntegrityError`.

### Issue #1248

Batch ingest dedups events with an in-memory `seen_in_batch` set
bounded to the current request. Two concurrent requests with
overlapping events both pass the in-memory check and both persist.

### Fix

Two options:

**B1. Reuse existing `(tenant_id, idempotency_key)` UNIQUE**
The CTE events table already has this constraint (see `ON CONFLICT`
pattern in `cte_persistence.core.py:319`). If `webhook_router_v2`
computes the same `idempotency_key` for duplicate events, `ON CONFLICT
DO NOTHING` already catches them — the race is just that the
in-memory set is consulted before the DB.

Fix: remove the in-memory set entirely. Let the DB adjudicate. On
`ON CONFLICT RETURNING`, collect the rows that returned zero and
re-`SELECT` the existing row's `event_id`. Return 200 + `idempotent: true`.

**B2. New `event_fingerprint` UNIQUE**
If `idempotency_key` is not computed deterministically enough for the
dedup case the issue describes (GS1-equivalent events from different
sources), add a new column `event_fingerprint` = hash of
`(tenant_id, cte_type, traceability_lot_code, event_time, location)`
with a UNIQUE index.

**Recommendation: B1 first**, since the existing idempotency_key is
already the intended dedup key and adding another column is duplicate
machinery. If B1 leaves observable duplicates in prod, escalate to B2.

### Test plan

- Integration test: fire 2 concurrent POSTs with the same payload, assert
  only one event persisted.
- Assert the second response is 200 (not 409) with `idempotent=true`.

---

## 5. PR-C: Retire cte_persistence (DEFERRED)

**Scope:** large. Not in scope for this sprint.

`services/shared/cte_persistence/core.py` is 1,397 LOC with 11+ live
callers in `services/ingestion/app/`. The migration path:

1. Add a compatibility shim in `cte_persistence/__init__.py` that
   delegates to `canonical_persistence`. Every cte-specific behavior
   (legacy idempotency key formula, cte_events vs traceability_events
   dual-write) needs a toggle.
2. Migrate callers one file at a time. Each caller's test suite stays
   green at every step.
3. Once all callers moved, delete `cte_persistence/`.

This is a ~2-sprint project, not a PR. File as a separate meta-issue
(EPIC-D2) or let target-architecture consolidation (6 services → 1
monolith) absorb it.

What we CAN do now without the big-bang retire:

- **Mark cte_persistence clearly as LEGACY** in its module docstring.
  Already done — but remove the "actively written by both webhook and
  EPCIS" line that suggests dual-write is supported long-term.
- **Unify the idempotency formula** across canonical and cte: the fix
  in PR-A (#1313 `default=str`) already does half the job. The other
  half is: same field order, same canonical delimiters. Quick audit
  of the two formulas, one-line sync.
- **Reconciliation CI job** — new test that picks 100 recent CTE
  events and asserts each has a matching `traceability_events` row with
  the same `sha256_hash`. Flag divergence.

Recommendation for this sprint: just the docstring tidy + formula audit.
Defer the reconciliation job and full retirement.

---

## 6. Out of scope for EPIC-D

- **#1074** — `POST /v1/bulk-upload/commit` check-then-set race. Not a
  hash-chain issue. Moved to EPIC-K (admin/RBAC hygiene).
- **#1335 full retirement of cte_persistence** — too large for this
  epic. PR-C captures what can be shipped now; full retirement is a
  separate meta.
- **admin/audit.py chain** — different table, different guarantees,
  low volume. No consolidation gain.

---

## 7. Execution order

| PR | Closes | Effort | Blast |
|---|---|---|---|
| PR-A surgical fixes | #1313 #1266 #1332 | ~1 day | Low |
| PR-B #1248 UNIQUE | #1248 | ~2 days | Medium (DB migration) |
| PR-C docstring + formula audit | part of #1335 | ~0.5 day | None |

Total: ~1 sprint for everything realistic; full cte_persistence retirement
is a separate piece of work.

Decision needed: **do you want PR-A shipped before EPIC-B's PR-1/PR-2
merge, or stacked after?** They don't conflict — canonical_persistence/writer.py
changes in PR-A (for #1266) don't overlap with the #1265 edit in EPIC-B's
PR-2. I'll base PR-A off `main` for independence unless you prefer
stacking.
