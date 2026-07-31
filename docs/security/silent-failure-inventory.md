# Silent-failure inventory — failure paths that degrade to permissive

> Produced by the 2026-07-31 remediation sweep (Phase 2). Method: six
> parallel subsystem audits (compliance scoring, rules engine, billing
> gates & rate limits, tenant context/RLS plumbing, scheduler & probes,
> FDA export & chain verification), followed by an adversarial
> verification pass on every high-severity finding — each was
> independently re-checked against the code with instructions to refute
> it. Findings that failed verification are listed with their refutation
> rather than dropped.
>
> Pattern class (the v104 / #2662 / #2689 shape): a DB error, empty
> read, missing signal, timeout, or caught exception degrades to an
> ALLOW / PASS / assumed default / silent skip instead of failing
> closed.
>
> **Severity definition** — high: affects compliance verdicts, tenant
> isolation, billing/entitlement gates, or evidence integrity. medium:
> operational correctness with plausible product impact. low:
> logging/observability only.
>
> **Disposition** — `FIXED (this PR)`: fail-closed fix shipped in this
> branch with regression tests. `issue`: filed for follow-up (medium/low
> are deliberately not fixed in this PR, per the remediation brief) —
> filed as #2694 (compliance scoring), #2695 (rules engine), #2696
> (tenant context/RLS), #2697 (scheduler & probes), #2698 (export/chain).
> `documented-intentional`: the permissive degrade is deliberate and
> documented; citation given. `refuted`: the adversarial pass showed the
> degrade does not occur as reported.

## Severity-high findings

| Path | Failure mode | Degrade behavior (pre-fix) | Verdict | Disposition |
| --- | --- | --- | --- | --- |
| `services/shared/rules/enforcement.py:75` `current_mode` | `RULES_ENGINE_ENFORCE` set to an unrecognized value (`true`, `on`, `cte-only`, …) | Enforcement silently ran in OFF mode with **zero logging** — no event rejected, and `handle_preeval_exception`'s fail-closed 500 path also disabled. The #2662 shape: operator believes enforcement is on; engine enforces nothing. | CONFIRMED | **FIXED (this PR)**: present-but-invalid value fails closed to `all` with a once-per-value error log; empty/unset still means `off`. |
| `services/shared/canonical_persistence/verification.py:277` `verify_chain_canonical` | Empty read: zero `fsma.hash_chain` rows while non-rejected canonical events exist (RLS deny-all, deleted rows — indistinguishable from chain-less ingestion) | `valid=True` after walking **zero rows**; FDA export rendered `X-Chain-Integrity: VERIFIED`. The legacy verifier fails closed on exactly this case (#1314); the canonical rewrite dropped the guard. | CONFIRMED | **FIXED (this PR)**: degenerate case returns `valid=False` + `no_chain_evidence=True` with an explicit *not-a-tamper-verdict* error. Mixed tenants with some chain rows are unaffected; EPCIS-only tenants now honestly report "no chain evidence" instead of a VERIFIED claim backed by nothing. |
| `services/ingestion/app/fda_export_service.py:595` `_build_chain_verification_payload` | Chain verification `valid=False` co-occurring with events missing row/chain hashes | Headline `verification_status` overwritten UNVERIFIED → **PARTIAL**; the package README instructs consumers to accept VERIFIED *or* PARTIAL, so the artifact's own instructions accepted the masked status. | CONFIRMED | **FIXED (this PR)**: PARTIAL only ever downgrades a VERIFIED chain. |
| `services/shared/cte_persistence/queries.py:118` (+ batch twin `:371`) `_expand_tlcs_via_transformation_links` | `OperationalError` (transient connectivity blip) or non-missing-table `ProgrammingError` (e.g. permission denied) during recursive TLC traversal | Returned `[seed_tlc]` — the FDA trace/recall scope silently truncated to the seed lot while the export rendered 200-complete. The docstring documented the unreachable-DB carve-out, in tension with its own #1322 rationale; trigger window is a mid-export blip (narrow but real). | CONFIRMED | **FIXED (this PR)**: fallback narrowed to missing-table only (pg 42P01 / sqlite "no such table" — the fresh-DB bootstrap case); every other SQL error re-raises. Also resolves the medium sibling (broad `ProgrammingError` catch at `:100`). |
| `services/ingestion/app/compliance_score.py:327` `_query_scoring_data` | Chain verification crashes (ImportError / OperationalError / ProgrammingError) | `chain_verified=None` → gap-detection fallback awarded up to **90 points** + 30-point export credit; a tampered-but-contiguous chain scored 90 and the TAMPER branch never fired. | CONFIRMED | **FIXED (this PR)**: `chain_verification_error` flag poisons the dimension (0 points, honest detail) and denies export chain credit. |
| `services/ingestion/app/compliance_score.py:291` `_query_scoring_data` | DB error reading `fsma.compliance_alerts` | `open_obligation_alerts=0` → the **+20 zero-alert bonus**: a failed read strictly *increased* the compliance grade and hid open chain-break incidents. | CONFIRMED | **FIXED (this PR)**: `obligation_data_error` flag poisons the obligation dimension. |
| `services/ingestion/app/compliance_score.py:274` `_query_scoring_data` | DB error reading `obligations`/`obligation_cte_rules` | Counts zeroed → flat 50-point "rules not loaded" default rolled into the A–F grade. | CONFIRMED | **FIXED (this PR)**: same `obligation_data_error` flag. Residual (see issues): an RLS deny-all **empty read** (0 rows, no exception) still routes to the 50-point unseeded branch — read failure and unseeded tenant are indistinguishable without a policy probe. |
| `services/compliance/app/routes.py:734` `fsma_audit_spreadsheet` | Upstream returns `has_more=true` with missing `next_cursor` or an empty page | Pagination loop broke and the accumulated **partial** event list rendered into the official FDA 204 CSV with no marker — contradicting the handler's own no-silent-truncation contract. Trigger requires a malformed graph upstream (in-repo upstream can't produce it; env-configured upstreams can). | CONFIRMED (weakest trigger likelihood of the set) | **FIXED (this PR)**: malformed pagination aborts 502 with correlation id, matching the handler's other malformed-upstream cases. |
| `services/admin/app/database.py:187` `_reset_tenant_guc_on_checkout` | Exception while clearing `app.tenant_id` on pool checkout | Warned and handed the pooled connection out anyway — **carrying the previous tenant's session-scoped GUC**, so RLS reads ran under the wrong tenant on exactly the error path of the #1381 isolation mitigation. Narrow window (pool_pre_ping runs first), but the class is tenant isolation. | CONFIRMED | **FIXED (this PR)**: raises `DisconnectionError` so the pool discards the connection and retries checkout on a fresh one. |
| `services/scheduler/service.py:473` `_process_new_items` (recall ack) | Per-item compliance-alert failures / webhook failures acked anyway in pg mode | — | REFUTED as reported: (a) the #2689 follow-up in this PR withholds acks per failed `source_id` (constructor failure withholds all); (b) webhook per-URL failures are dead-lettered to the durable outbox and drained by `webhook_outbox_drain` — acking despite webhook failure is DLQ-backed by design; (c) payload-construction errors propagate (ValidationError not in the catch tuple). | **FIXED (this PR)** for (a) — the mandated #2689 follow-up; (b)/(c) fail closed already. |
| `services/scheduler/app/compliance_integration.py:147` `_find_matching_tenants` | DB error on the Tier-1 lot-code query | Reported as "silently degrades to Tier-2/3 keyword matching + permanent ack". | REFUTED: the handler never rolls back, so the very next Tier-2/3 query on the same session raises (`PendingRollbackError`), propagates to the per-item handler, and the item's ack is withheld — net behavior is loud failure + retry. A future forced-RLS deny would be a silent zero-row read, which the class docstring (lines 39–46) pre-documents as requiring a maintenance-role exemption. | refuted (downgraded to low; no change) |
| `services/shared/database.py:176` `check_rls_posture` | Probe exception during the boot-time RLS posture check | Returns `"unknown"` and boot proceeds — even under `REGENGINE_REQUIRE_RLS_ENFORCEMENT=1`, silently bypassing the one-way boot guard. | DOWNGRADED high → medium by the adversarial pass: the probe only *detects* posture; a failed probe blinds the detector but does not alter RLS enforcement, and the realistic trigger (transient boot-time blip) does not coincide with the misconfiguration the guard exists to catch. | issue (fail-closed under REQUIRE=1: retry then abort boot) |
| `services/shared/rules/enforcement.py:93` `should_reject` | Zero applicable rules / unclassifiable event → no-verdict → accept, in every enforcement mode | An unseeded tenant under `RULES_ENGINE_ENFORCE=all` has every event accepted. | CONFIRMED mechanically, but **documented-intentional**: module docstring (#1346/#1347) — "blocking an event on non-evaluation would silently break ingestion for tenants without seeded rules and for non-FTL products". | documented-intentional (revisit at enforcement GA; see issues) |

## Medium / low findings

Grouped by subsystem. None are fixed in this PR (per the brief); each
group is filed as a GitHub issue linked in the PR.

### Compliance scoring (`services/ingestion/app/compliance_score.py`, `services/compliance/app/routes.py`)

| Path | Sev | Behavior | Disposition |
| --- | --- | --- | --- |
| `compliance_score.py:307` (FTL category count) | M | DB error → `ftl_category_count=0` → 50-point assumed default for product coverage | issue |
| `compliance_score.py:900` `get_pending_reviews` | M | Any exception → HTTP 200 with `pending_reviews: 0` — dashboard shows nothing awaiting review | issue |
| `compliance_score.py` obligation empty-read ambiguity | M | RLS deny-all empty read (no exception) is indistinguishable from an unseeded tenant → 50-point branch | issue (needs a distinguishing signal, e.g. seeded-marker or policy probe) |
| `routes.py:504` `validate_compliance` | M | Caller omits config → 200 `valid=true`, `rules_evaluated=0` | documented-intentional (advisory endpoint; response carries `rules_evaluated`) |

### Rules engine (`services/shared/rules/`)

| Path | Sev | Behavior | Disposition |
| --- | --- | --- | --- |
| `engine.py:787` `_batch_persist_evaluations` | M | Failed 100-row chunk logged and skipped — accepted events with no evaluation record (audit-trail gap) | issue |
| `engine.py:704` `_persist_evaluations` | M | Savepoint rollback swallows persist failure after accept | documented-intentional (comment on the savepoint contract); listed in the same issue for durability follow-up |
| `rejection_audit.py:128` `record_rejection` | M | Durable rejection-audit row dropped on DB error (error log + Sentry; reject decision itself stands) | documented-intentional |
| `enforcement.py:135` `handle_preeval_exception` (OFF mode) | M | Pre-eval crash → warn + accept in OFF mode | documented-intentional (docstring: OFF is log-and-accept by contract; enforcement modes fail closed with 500) |
| `evaluators/relational.py:458,486` mass-balance | M | UOM mix without container weights, or zero input events → `warn`, not `fail` | documented-intentional (warn-tier design; revisit when mass-balance goes critical-blocking) |
| `evaluators/relational.py:156` temporal order | L | Unknown event_type → `skip` | documented-intentional |

### Tenant context / RLS plumbing (`services/shared/`, `services/admin/app/`)

| Path | Sev | Behavior | Disposition |
| --- | --- | --- | --- |
| `shared/database.py:176` `check_rls_posture` | M (downgraded from H) | Probe error → `"unknown"` → boot proceeds under `REGENGINE_REQUIRE_RLS_ENFORCEMENT=1` | issue (retry-then-abort under REQUIRE=1) |
| `admin/app/dependencies.py:326` stale-context clear | M | #1383 hygiene clear failure silently `pass`es — not even a log | issue |
| `shared/middleware/tenant_context.py:170` | M | Malformed tenant claim in a *validated* JWT → warning + treated as absent claim | issue |
| `admin/app/database.py:303` `get_tenant_session` | L | Falsy tenant_id → yields session with no GUC instead of raising | issue |
| `shared/tenant_context.py:452,650` slug-tenant GUC skips | M | Non-UUID tenant id → RLS GUC backstop silently absent | documented-intentional (slug tolerance, #2458 / begin-hook `skipped_non_uuid` metric; fail-hard predicate remains the enforcement layer) |
| `shared/tenant_context.py:247,274` claim collection | L | Exceptions reading query params / body → claim treated as absent (409 defense-in-depth check skipped) | issue |
| `shared/middleware/tenant_context.py:139`, `shared/tenant_context.py:558` | L | Exempt-path extraction errors → `tenant_id=None`; RLS-GUC metric counter failures swallowed | documented-intentional |

### Scheduler & probes (`services/scheduler/`, `server/main.py`)

| Path | Sev | Behavior | Disposition |
| --- | --- | --- | --- |
| `server/main.py:1062` readiness scheduler check | M | Embedded-scheduler daemon thread dying after a successful start is never detected — `/readiness` reports `ok` forever | issue |
| `service.py:854` `run_fsma_nightly_sync` (also `:748` drain) | M | Job catches all exceptions and returns → APScheduler records EVENT_JOB_EXECUTED (success); #1144 listener never fires | issue |
| `notifications.py:424` outbox rewrite | M | Corrupt JSONL line skipped, then the file is rewritten from parsed entries only — the corrupt entry is permanently destroyed | issue |
| `kafka_producer.py:273` `_send` | M | Returns True on local enqueue; async delivery failure + swallowed flush error → items acked (kafka backbone only, non-default) | issue |
| `service.py:388` FSMA graph emission | M | fsma emission failures / transform exceptions never gate the ack | issue |
| `scrapers/fda_warning_letters.py:96` | M | RSS 404 + zero scrape results → `success=True, items_found=0`; coverage can be dead indefinitely with no alarm (feeds known bot-blocked) | issue |
| `scrapers/fda_recalls.py:137` | L | Row missing `recall_number` dropped with no log | issue |
| `graph/audit_buffer_reconciler.py:406`, `notifications.py:402`, `service.py:672`, `service.py:340`, `server/main.py:980,1058`, `app/metrics.py:120` | M/L | Reconciler-tick swallow, outbox-append OSError, unset outbox path, pg-mode kafka skip, readiness degraded-200 for Redis/Neo4j/worker-start, metrics no-op without prometheus_client | documented-intentional (in-code comments; README documents the readiness degrade contract; outbox-path warning at boot) |

### FDA export & chain verification (`services/ingestion/app/fda_export*`, `services/shared/`)

| Path | Sev | Behavior | Disposition |
| --- | --- | --- | --- |
| `fda_export_service.py:518` `_build_completeness_summary` | M | Events whose type isn't a `WebhookCTEType` member are assumed fully covered (`ratio 1.0`) — an export where nothing was checked reports 100% KDE coverage | issue |
| `cte_persistence/verification.py:250` `verify_chain_merkle` | M | Empty chain read → `MerkleVerification(valid=True, chain_length=0)` surfaced verbatim by the export routes | issue (canonical twin fixed in this PR; legacy Merkle path needs the same guard or retirement at WS-1d) |
| `cte_persistence/queries.py:100` broad `ProgrammingError` catch | M | — | **FIXED (this PR)** as part of the `:118` fix (narrowed to missing-table) |

### Billing gates & rate limits

The first-pass auditor for this dimension stalled; a re-run auditor's
findings are recorded below.

<!-- GATES-SECTION -->

## Cross-cutting observations

1. **The inflating-degrade subclass is the dangerous one.** Most
   degrades push scores/status *down* or merely lose observability; the
   fixed set contains every case found where a failure pushed a
   compliance verdict or evidence claim *up* (zero-alert bonus, 90-point
   chain fallback, VERIFIED-on-empty-chain, UNVERIFIED→PARTIAL).
2. **"Read failed" vs "legitimately empty" is a recurring ambiguity**
   (obligation rules, chain rows, warning-letter feeds). Where the store
   keeps no distinguishing marker, this PR fails the *claim* closed and
   says so explicitly rather than inventing a tamper verdict.
3. **The adversarial pass earned its cost**: 2 of 13 high findings were
   refuted outright and 1 was downgraded — all three would otherwise
   have produced unnecessary (and in one case behavior-changing) "fixes".
