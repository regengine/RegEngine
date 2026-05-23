# Rules Engine Enforcement Model

Last verified: 2026-05-23

## TL;DR

Rule failures are **not universally blocking** by default. Enforcement is **per-route opt-in**: a route blocks on rule violations only if (a) `RULES_ENGINE_ENFORCE` is set to `cte_only` or `all`, AND (b) the route explicitly wires in [`should_reject()`](../../services/shared/rules/enforcement.py).

The set of "enforcement-aware" routes is small and deliberate. Adding a new one is a code change, not a config flip.

## Why per-route opt-in (not global)

Rule evaluation runs inline with the primary CTE write. A blanket "reject on violation" policy would have to also pick:

- Whether to roll back the primary write (data) and on what scope (per event, per batch).
- What HTTP status the caller gets back, and which routes care about that.
- What happens for tenants with no rules seeded (no-verdict — explicitly never a reject, even under `ALL`).

Different ingestion paths answer those differently — EPCIS XML and webhook JSON have different batch semantics; the supplier portal writes into a customer tenant where the customer has authored the rules; CSV import has its own rejection-collection contract. Hard-coding one policy in `cte_persistence` would silently break at least one of those.

So the policy lives in [`shared/rules/enforcement.py`](../../services/shared/rules/enforcement.py), and each route that wants to opt in imports `should_reject(summary)` and routes its own rejection handling.

## Enforcement modes

Set via `RULES_ENGINE_ENFORCE` (read at call time, no restart needed — flip + redeploy and the next request sees it):

| Mode | Behavior |
|---|---|
| `off` (default) | Engine runs and persists evaluation rows, but never rejects. "Log and accept." |
| `cte_only` | Reject when `summary.critical_failures` is non-empty. Warnings/info still accept. |
| `all` | Reject on any `summary.compliant is False` (including warning-only failures). |

Two invariants hold in every mode:

1. **No-verdict never rejects.** When `summary.compliant is None` (no rules seeded for the tenant, non-FTL product, evaluator skipped), the event accepts — "we didn't evaluate" is not the same as "the event violates a rule."
2. **Pre-eval crashes fail loud under enforcement.** If canonical normalization or the rules engine itself raises, `handle_preeval_exception()` surfaces an HTTP 500 + Sentry under `cte_only`/`all`. Under `off` it warns and accepts (preserves the legacy best-effort behavior). See `services/shared/rules/enforcement.py` for the funnel.

## Enforcement-aware call sites (the manifest)

The current set is tracked in code at [`ENFORCEMENT_AWARE_CALL_SITES`](../../services/shared/rules/enforcement.py):

| File | What it handles |
|---|---|
| `services/ingestion/app/webhook_compat.py` | Internal `ingest_events()` helper used by CSV import, sensitech, supplier portal, EDI ingestion |
| `services/ingestion/app/epcis/persistence.py` | EPCIS XML ingestion persistence path |
| `services/ingestion/app/webhook_router_v2.py` | `POST /api/v1/webhooks/ingest` HTTP route |

A drift test in [`services/shared/tests/test_rules_enforcement_manifest.py`](../../services/shared/tests/test_rules_enforcement_manifest.py) asserts the manifest matches the actual `should_reject()` importers. Adding a new caller without updating the manifest (or vice versa) fails CI.

## Routes that do NOT enforce (intentional)

The following CTE-writing paths intentionally do not call `should_reject()`:

- **Sandbox / inflow workbench** — used by tenants to explore canonicalization + rule evaluation interactively. Rejecting on rule violation would defeat the diagnostic purpose; the response surfaces the verdict instead.
- **Free-tier / public proof endpoints** — no tenant-scoped rules and no authoritative obligation to enforce.

If a route in this category later becomes authoritative (e.g. sandbox starts persisting to canonical), wire enforcement and add it to the manifest.

## Adding enforcement to a new route

1. After running the rules evaluation and obtaining a `summary: EvaluationSummary`, import:
   ```python
   from shared.rules.enforcement import should_reject, current_mode
   ```
2. Branch on the verdict:
   ```python
   should, reason = should_reject(summary)
   if should:
       # roll back the in-flight savepoint, emit a rejected result,
       # record a rejection-audit row via shared.rules.rejection_audit
       ...
   ```
3. Use `handle_preeval_exception(exc, where="<your_module>")` inside the canonical/rules try-block so a pre-eval crash surfaces correctly under enforcement.
4. Add the new file path to `ENFORCEMENT_AWARE_CALL_SITES` in `shared/rules/enforcement.py`.
5. The drift test will start passing again on next run.

## Related

- [`shared/rules/enforcement.py`](../../services/shared/rules/enforcement.py) — the policy module
- [`shared/rules/rejection_audit.py`](../../services/shared/rules/rejection_audit.py) — durable rejection log (persists even when the outer savepoint rolls back)
- [`CONSOLIDATION.md`](CONSOLIDATION.md) — why the routes live where they do
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — overall data flow
