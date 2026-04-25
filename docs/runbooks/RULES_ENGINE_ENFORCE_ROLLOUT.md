# Rules Engine Enforcement — Alpha Rollout Runbook

**Feature:** Flip ``RULES_ENGINE_ENFORCE`` from ``off`` (current default) to ``cte_only`` so FSMA 204 CTE-critical rule violations reject ingestion with HTTP 422 instead of being logged in the exception queue.

**Severity if rollback needed:** SEV2 (false-positive rejections block a tenant's compliant events) / SEV1 (rollback fails or rejection logic corrupts state).

**Owner:** On-call engineer for the rollout window. Hand off to product after broadening.

**Last Updated:** 2026-04-24

---

## What this turns on

Today, every accepted ingestion event runs the rules engine, but rule failures only land in ``fsma.exception_queue`` rows — the event is persisted regardless. After the flip, **CTE-critical** rule failures cause ingestion to reject the event with:

```http
HTTP 422
Content-Type: application/json

{
  "detail": {
    "error": "rule_violation",
    "reason": "<rule_id>: <why_failed>",
    "tenant_id": "<tenant>"
  }
}
```

Affected paths (verified end-to-end by the Phase 0 test suite):

| Endpoint | File | Rejection mechanism |
|---|---|---|
| ``POST /api/v1/webhooks/ingest`` (batch happy path) | ``services/ingestion/app/webhook_router_v2.py`` | Pre-eval partition removes rejected events from ``store_events_batch``; rejected events land in ``IngestResponse.events`` with ``status="rejected"`` |
| ``POST /api/v1/webhooks/ingest`` (per-event fallback) | same | Same pre-eval gate per-event |
| EPCIS ingestion (single + atomic batch) | ``services/ingestion/app/epcis/persistence.py`` | Pre-eval gate raises ``HTTPException(422)``; caller's ``db_session.rollback()`` unwinds in-flight state. Atomic batch rolls back the whole batch (per ``#1156``) |
| Internal webhook compat (``shared.auth.require_api_key`` callers) | ``services/ingestion/app/webhook_compat.py`` | Rules eval moved before the per-event savepoint commits; rejected events have their savepoint rolled back |

What does **not** change:
- **Warning-severity** failures still produce exception-queue rows; the event is accepted (HTTP 201). Same as today.
- **No-verdict** events (no rules loaded for the tenant, non-FTL product, classification missing) accept silently. Same as today. **This is the safety valve** — tenants without seeded rules or with non-FTL products will not be blocked.
- The ``audit_logs`` hash chain is unaffected — append-only triggers in v066 already enforce immutability separately.

---

## 1. Pre-rollout checklist (do all of these)

### 1.1 Confirm the alpha tenant has seeded rules

```sql
-- Run against Railway production DB.
SELECT
  rule_id, severity, applicability_conditions->>'cte_types' AS cte_types
FROM fsma.rule_definitions
WHERE tenant_id = '<ALPHA_TENANT_UUID>'
  AND retired_date IS NULL
ORDER BY severity DESC, rule_id;
```

Expected: at least one ``severity = 'critical'`` rule whose ``cte_types`` covers the events the tenant ingests. If zero critical rules exist, the flag is a no-op for this tenant — pick a different alpha or run ``services.shared.rules.seeds.seed_rule_definitions`` against the tenant first.

### 1.2 Confirm FTL classification is reaching the engine

The rules engine only evaluates events on the FDA Food Traceability List. If the alpha tenant's events lack ``ftl_covered``, ``ftl_category``, or the inference path for these (#1346), every event gets ``no_verdict_reason="ftl_classification_missing"`` and the flag does nothing.

```sql
-- Sample 100 recent events from the alpha tenant; expect ftl_covered to be set.
SELECT
  event_type,
  COUNT(*) AS n,
  COUNT(*) FILTER (WHERE kdes ? 'ftl_covered') AS with_ftl_hint,
  COUNT(*) FILTER (WHERE kdes ? 'ftl_category') AS with_ftl_category
FROM fsma.cte_events
WHERE tenant_id = '<ALPHA_TENANT_UUID>'
  AND event_timestamp > NOW() - INTERVAL '7 days'
GROUP BY event_type;
```

If ``with_ftl_hint`` is 0 across all event types, **stop** — fix #1346 hint propagation first, then come back. Otherwise the rollout is silent and you learn nothing from it.

### 1.3 Capture a baseline

Note these numbers before flipping (record in the rollout ticket):

| Metric | Source | Why |
|---|---|---|
| Last 24h ingestion volume for alpha tenant | ``SELECT count(*) FROM fsma.cte_events WHERE tenant_id = '<ALPHA>' AND event_timestamp > NOW() - INTERVAL '24 hours'`` | Compare during rollout; sudden drop = rejections |
| Last 24h exception-queue volume | ``SELECT count(*) FROM fsma.exception_queue WHERE tenant_id = '<ALPHA>' AND created_at > NOW() - INTERVAL '24 hours'`` | Should drop after flip (rejected events don't make exception rows) |
| Current p95 ingestion latency for alpha tenant | Sentry / structured logs ``ingest_batch`` events | Track any regression — pre-eval adds work even after the [#1929](https://github.com/PetrefiedThunder/RegEngine/pull/1929) optimization |
| Last 24h ``fsma_validation_status='failed'`` count | ``SELECT count(*) FROM fsma.cte_events WHERE tenant_id = '<ALPHA>' AND fsma_validation_status = 'failed' AND event_timestamp > NOW() - INTERVAL '24 hours'`` | These are events the schema gate already failed; rules engine is a downstream gate. Use as the upper bound on expected new rejections |

### 1.4 Confirm rollback channel works

Before flipping, verify you can read back ``RULES_ENGINE_ENFORCE`` via Railway and trigger a redeploy:

```bash
railway variables  # check current value (should be unset or "off")
railway up --detach  # redeploy to confirm the pipeline works
```

If ``railway up`` is broken for any reason, fix that **first**. The whole rollout depends on a working rollback path.

### 1.5 Notify the alpha tenant

Send a 24h-advance heads-up to the alpha tenant's primary contact:

> "We're enabling FSMA 204 rule enforcement for your account on **<DATE/TIME UTC>**. Events that fail CTE-critical validation rules will return HTTP 422 with a ``rule_violation`` detail instead of being silently flagged in the exception queue. We've reviewed your seeded rules and don't expect false positives, but if you see unexpected rejections, contact <ON_CALL_CONTACT>. Rollback to silent mode is one env-var flip if needed."

Send the **specific rule IDs** the tenant has seeded (from the §1.1 query) so they know what they're being enforced against.

---

## 2. The flip

```bash
# Railway: set on the ingestion service only, not all services.
# (The flag is read by every Python process that imports
# shared.rules.enforcement, but only the ingestion service has the
# code paths that consult it. Setting it elsewhere is wasted env
# variable surface.)
railway service ingestion
railway variables set RULES_ENGINE_ENFORCE=cte_only

# Redeploy.
railway up --detach

# Tail logs for the deploy completion.
railway logs --service ingestion --tail 200
```

Wait for ``application started`` (or the equivalent ``uvicorn`` ready line). Note the deploy ID and timestamp in the rollout ticket.

**Alternative narrow target:** if you want only the alpha tenant to see enforcement (and other tenants to stay on ``off``), the flag is currently global — there is no per-tenant override. If you need per-tenant: don't ship this rollout; instead schedule the per-tenant flag work first. **Do not** try to gate via API-key scopes or middleware — the enforcement gate runs deep in the persistence path and won't see a request-level override.

---

## 3. What to watch (first 60 minutes)

Open three windows.

### 3.1 Live logs

```bash
railway logs --service ingestion --tail 500 \
  | grep -E 'rule_violation|epcis_rules_preeval_skipped|rules_preeval_skipped|canonical_write_skipped'
```

What each line means:

| Log line | Meaning | Action |
|---|---|---|
| ``rule_violation`` (in 422 response, not always logged structuredly) | A rejection happened. Expected at low volume; if alpha tenant sends only compliant events, should be near zero. | Track count. Spike > §3.4 threshold → **rollback (§4)** |
| ``epcis_rules_preeval_skipped`` / ``rules_preeval_skipped`` | Pre-eval errored; event accepted via fallback. Expected at near-zero rate. | Investigate the error. If repeated, suspect a regression in canonical normalization or rules engine. |
| ``canonical_write_skipped`` / ``canonical_write_skipped_fallback`` | Threaded canonical+rules write failed AFTER primary commit. Pre-existing failure mode, not new under enforcement. | Same response as before — log in observability tooling, don't roll back the flag for this. |

### 3.2 DB queries (every 5 min for the first hour)

```sql
-- New rejections by rule_id (last 5 min)
SELECT
  COUNT(*) AS new_in_5m
FROM fsma.cte_events
WHERE tenant_id = '<ALPHA_TENANT_UUID>'
  AND event_timestamp > NOW() - INTERVAL '5 minutes';
-- Compare against pre-flip baseline rate. Sudden drop to ~0 = mass rejection.

-- Exception queue rate (should drop, not spike — rejected events don't queue)
SELECT
  COUNT(*) AS new_in_5m
FROM fsma.exception_queue
WHERE tenant_id = '<ALPHA_TENANT_UUID>'
  AND created_at > NOW() - INTERVAL '5 minutes';
```

### 3.3 Latency

The pre-eval gate adds rule evaluation to the synchronous request path. After [#1929](https://github.com/PetrefiedThunder/RegEngine/pull/1929) the post-commit threaded block reuses the pre-computed summary, so the **net** added work is one rules eval per event (vs zero pre-flip).

Expected: p95 latency increase of **≤ 200ms** for batches of 100 events with 10 rules each. If p95 doubles or worse, suspect:
- Pre-fetch ([#1365](https://github.com/PetrefiedThunder/RegEngine/pull/1365)) regression — relational evaluators hitting the DB N times per event
- Tenant has many more rules than expected
- DB lock contention from another process

### 3.4 Rollback gates

Hard rollback (do not wait, do not investigate first — flip back, then investigate):

- Rejection rate > **5% of ingestion volume** in any 5-minute window
- Tenant ingestion volume drops by **>80%** vs the pre-flip baseline
- p95 ingestion latency exceeds **2x** baseline for >10 minutes
- Any HTTP 5xx response from ``/api/v1/webhooks/ingest`` or the EPCIS endpoint that didn't exist before the flip

Soft rollback (investigate first, decide):

- Rejection rate 1–5% of ingestion volume
- p95 latency 1.5–2x baseline
- The alpha tenant contact reports unexpected rejections

---

## 4. Rollback

Single env-var flip. **No code changes, no migration, no redeploy coordination.**

```bash
railway service ingestion
railway variables set RULES_ENGINE_ENFORCE=off
railway up --detach
```

Or unset entirely (the helper defaults to ``off`` if the var is absent):

```bash
railway variables delete RULES_ENGINE_ENFORCE
railway up --detach
```

Confirm:

```bash
railway logs --service ingestion --tail 100 | grep -i "starting\|ready"
# Then verify by tailing the ingestion path; rule_violation lines should
# stop appearing.
```

After rollback, the post-commit threaded block falls back to ``evaluate_event(persist=True)`` exactly as it did pre-flip — eval rows still get written, exception-queue rows still get created for ``compliant=False`` summaries. Bit-for-bit identical to pre-Phase-0 behavior.

---

## 5. Broaden criteria

After **48 hours** with the alpha tenant on ``cte_only``, check:

| Gate | Pass criteria | If fail |
|---|---|---|
| Rejection rate stable | < 1% of ingestion volume, no growth trend | Investigate the rejected events; iterate on rule definitions or the alpha tenant's data quality before broadening |
| No false positives reported | Alpha tenant contact has not reported any rejection of an event they consider compliant | Resolve the dispute with the rule author; broadening would multiply the disagreement |
| Latency stable | p95 within 200ms of baseline, no growth trend | Investigate which rules are slow; consider pre-fetch tuning |
| Exception queue volume | Dropped vs pre-flip (because some warnings/criticals now reject before queueing) | Expected behavior; not a fail |
| ``rules_preeval_skipped`` rate | Still near zero (< 0.1% of events) | Investigate the underlying error; broadening would amplify it |

If all gates pass, broaden to all tenants by leaving the env var as-is — the same setting applies globally. **Do not** stage the broaden as multiple tenant-specific flips; the flag is global.

If broadening reveals issues, rollback gate criteria from §3.4 still apply globally.

---

## 6. After broadening

- Update ``project_status.md`` in the project memory: enforcement is now production default.
- Open an issue to plan the **``RULES_ENGINE_ENFORCE=all``** ramp (rejects on warning-severity failures too — much more aggressive). That's a separate rollout with its own runbook.
- Consider deleting the ``off`` fallback path in 30+ days once enforcement is proven. Until then keep it: the rollback path is load-bearing.

---

## Reference

| File | What it is |
|---|---|
| ``services/shared/rules/enforcement.py`` | The flag reader + ``should_reject(summary)`` |
| ``services/shared/rules/engine.py`` | ``RulesEngine.evaluate_event`` (pre-eval) + ``persist_summary`` (post-commit fast path) |
| ``services/ingestion/app/webhook_router_v2.py`` | Webhook ingestion. ``_rules_preeval_reject`` returns ``(reject, reason, summary)``. ``_persist_canonical_and_eval`` is the threaded-block helper. |
| ``services/ingestion/app/epcis/persistence.py`` | EPCIS ingestion. Pre-eval at function-scope; threaded block uses pre-computed summary via default-kwarg capture. |
| ``services/ingestion/app/webhook_compat.py`` | Internal webhook callers. Rules eval lives in the same per-event savepoint as primary CTE write. |
| Tests pinning the contract | ``tests/shared/test_rules_enforcement.py``, ``tests/shared/test_rules_persist_summary.py``, ``services/ingestion/tests/test_webhook_router_v2_enforcement.py``, ``services/ingestion/tests/test_webhook_router_v2_canonical_helper.py``, ``services/ingestion/tests/test_webhook_compat_enforcement.py``, ``services/ingestion/tests/test_epcis_persistence_enforcement.py`` |

PRs that landed this rollout (Phase 0 #1):

- [#1905](https://github.com/PetrefiedThunder/RegEngine/pull/1905) helper + flag
- [#1907](https://github.com/PetrefiedThunder/RegEngine/pull/1907) webhook_compat wire-up
- [#1909](https://github.com/PetrefiedThunder/RegEngine/pull/1909) webhook_router_v2 wire-up
- [#1912](https://github.com/PetrefiedThunder/RegEngine/pull/1912) EPCIS wire-up
- [#1919](https://github.com/PetrefiedThunder/RegEngine/pull/1919) OFF-mode short-circuit (latency)
- [#1924](https://github.com/PetrefiedThunder/RegEngine/pull/1924) ``persist_summary`` API
- [#1926](https://github.com/PetrefiedThunder/RegEngine/pull/1926) webhook_router_v2 double-eval fix
- [#1927](https://github.com/PetrefiedThunder/RegEngine/pull/1927) EPCIS double-eval fix
- [#1929](https://github.com/PetrefiedThunder/RegEngine/pull/1929) closure extraction + tests
