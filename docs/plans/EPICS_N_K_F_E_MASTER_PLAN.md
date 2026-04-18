# Epics N / K / F / E — master plan

**Scope:** The four remaining unclaimed consolidation epics from the
2026-04-17 audit. This doc scopes each into PR buckets grounded in
survey of the current code, not issue-tracker titles alone.

**Surveyed on:** 2026-04-18 (post-EPIC-B / EPIC-D work).

---

## 0. Ghost children — issues OPEN on GitHub but fixed in code

The survey surfaced an important cleanup: **seven** EPIC children that
already have fix commits on `main` but stayed OPEN because the PRs
that shipped them used range references (`#1356-#1358`) that
GitHub's issue linker doesn't parse. They should be closed with a
pointer to the fix commit before any planning work starts.

| Issue | Fix | Why it's still open |
|---|---|---|
| [#1356](https://github.com/PetrefiedThunder/RegEngine/issues/1356) temperature UoM | commit 92bc068f (PR #1455) | range ref `#1356-#1358` didn't auto-close |
| [#1357](https://github.com/PetrefiedThunder/RegEngine/issues/1357) GLN mod-10 | commit 92bc068f (PR #1455) | same |
| [#1358](https://github.com/PetrefiedThunder/RegEngine/issues/1358) quantity=0 | commit 92bc068f (PR #1455) | same |
| [#1362](https://github.com/PetrefiedThunder/RegEngine/issues/1362) regex ReDoS | commit 92bc068f (PR #1455) | range `#1362-#1365` |
| [#1363](https://github.com/PetrefiedThunder/RegEngine/issues/1363) container factor | commit 92bc068f (PR #1455) | same |
| [#1079](https://github.com/PetrefiedThunder/RegEngine/issues/1079) leaky 500s | `services/shared/error_handling.py:168-207` already returns safe message | never tracked by a PR |
| [#1407](https://github.com/PetrefiedThunder/RegEngine/issues/1407) tenant-scope on admin routes | `services/admin/app/user_routes.py:97,162` already call `TenantContext.get_tenant_context` | never tracked by a PR |
| [#1118](https://github.com/PetrefiedThunder/RegEngine/issues/1118) FSMAExtractor unreachable | `services/nlp/app/extractors/fsma_extractor.py` IS called from `consumer.py` | triage error in the audit |

Action: close each with a comment + commit SHA reference. No code
change needed.

---

## 1. EPIC-F — Rules engine fail-closed + validator correctness
**Tracker:** [#1459](https://github.com/PetrefiedThunder/RegEngine/issues/1459)
**Scope after ghost-closure:** 2 real open issues.

### Open children (corrected after reading actual issue bodies)
- **#1102** — actual title: "only RECEIVING CTE enforces KDE requirements — 6/7 CTEs accept missing fields as 'compliant'". NOT about empty rule sets (the empty-rule case was already fixed by #1347's work in `services/shared/rules/engine.py` which now returns tri-state `compliant=None` on `total_rules=0`). This issue is about the OLDER `/v1/validate` endpoint at `services/compliance/app/routes.py:192-219` which only branches on `cte_type == "RECEIVING"`, and `services/compliance/app/fsma_rules.json:307-318` which only defines `receiving_required_fields`. Needs per-CTE field maps for HARVESTING / COOLING / INITIAL_PACKING / FIRST_LAND_BASED_RECEIVING / SHIPPING / TRANSFORMATION per 21 CFR 1.1320-1.1350.
- **#1371** — `RulesEngine._rules_cache` stale-until-restart when a worker holds an engine across requests. Fix options: TTL (30-300s), `rule_definitions_version` bump, or Redis pub/sub. Blocker: depends on whether any long-lived engine instances exist — per-request instantiation in `webhook_router_v2` suggests cache is de-facto short-lived, but a grep for callers is needed during implementation.

### Plan — 1 PR (~1 day)
**`fix(compliance): per-CTE KDE enforcement + rules cache lifecycle`**
1. `services/compliance/app/fsma_rules.json` — rename `receiving_required_fields` to `cte_required_fields` keyed by CTE type. Populate all 7 CTEs per 21 CFR.
2. `services/compliance/app/routes.py:192-219` — iterate the map in the validator instead of branching on RECEIVING.
3. Grep for all `RulesEngine(` instantiation sites; if any are long-lived, add TTL cache (simplest path, no pubsub infra needed).
4. Tests: table-driven parametrize across all 7 CTE types, each with a KDE-missing payload → assert rejected.

---

## 2. EPIC-E — NLP: FSMAExtractor CTE coverage + TLC/UoM fixes
**Tracker:** [#1458](https://github.com/PetrefiedThunder/RegEngine/issues/1458)
**Scope after ghost-closure:** 5 real open issues (#1118 closes as invalid).

### Open children
- **#1103** HARVESTING CTE not extracted — `CTEType` enum at `services/nlp/app/extractors/fsma_types.py:26-29` only has SHIPPING/RECEIVING/TRANSFORMATION/CREATION.
- **#1104** INITIAL_PACKING CTE not extracted — same enum gap.
- **#1116** FTL scoping lives in validator only, extractor scans all foods.
- **#1123** TLC mutilated by GTIN prepend — `fsma_extractor.py:648-652` `_build_tlc` + `:779-782` `_extract_kdes`.
- **#1129** quantity + UoM parsed separately — `fsma_extractor.py:786-792`; `LineItem` at `fsma_types.py:64-65`.

### Plan — 1 PR (~2 days)
**`fix(nlp): FSMAExtractor CTE coverage + TLC preservation + quantity+UoM tuple`**
1. `fsma_types.py` — add `HARVESTING`, `INITIAL_PACKING`, `COOLING`, `FIRST_LAND_BASED_RECEIVING` to `CTEType`. Update `LineItem` to carry `(quantity, uom)` as an inseparable tuple.
2. `fsma_extractor.py:_extract_ctes` — add dispatch for the new CTE types. Harvesting looks for `harvest_date` + farm KDEs; initial_packing looks for `pack_date` + `harvester_business_name`.
3. `fsma_extractor.py:_build_tlc` + `_extract_kdes` — drop GTIN prepend. TLC is preserved verbatim; GTIN becomes a separate KDE.
4. `fsma_extractor.py` — consult the shared FTL list (import path TBD during implementation) and skip extraction for non-FTL food names.
5. Tests: new CTE extraction per type, TLC round-trip, quantity+UoM inseparable, FTL gate.

---

## 3. EPIC-K — Admin RBAC + error hygiene + audit integrity
**Tracker:** [#1460](https://github.com/PetrefiedThunder/RegEngine/issues/1460)
**Scope after ghost-closure:** 5 real open issues (#1079 and #1407 close).

### Open children
- **#1083** role-change race — `services/admin/app/user_routes.py:90-154` `update_user_role`. No `SELECT FOR UPDATE`.
- **#1405** audit middleware runs on `/health` and `/metrics` — `services/admin/app/audit_middleware.py:35-56`. No skip list.
- **#1406** RBAC reads `user_id` from request body — needs audit of all admin POST/PATCH routes.
- **#1414** X-Forwarded-For without trusted-proxy gating — `audit_middleware.py:48-56` `_get_client_ip`.
- **#1415** audit hash omits `actor_id, actor_email, severity, endpoint` — `services/admin/app/audit.py:compute_integrity_hash` (line 25-54) currently hashes only `prev_hash, tenant_id, timestamp, event_type, action, resource_id, metadata`.

### Plan — 1 PR (~1.5 days)
**`fix(admin): RBAC + error hygiene + audit integrity`**
1. `user_routes.py:update_user_role` — wrap the membership read + Owner-count check + write in a single transaction with `SELECT FOR UPDATE` on the membership row.
2. `audit_middleware.py` — add `EXEMPT_PATHS = {"/health", "/ready", "/metrics", "/docs", "/openapi.json"}` skip list at the top of dispatch; short-circuit.
3. `audit_middleware.py:_get_client_ip` — trust `X-Forwarded-For` only when request came through a trusted proxy (env: `TRUSTED_PROXY_CIDRS`), else use `request.client.host`. Use `ipaddress` module.
4. `audit.py:compute_integrity_hash` — extend the hash input to include `actor_id, actor_email, severity, endpoint`. One-shot migration: `v069_audit_hash_recompute.py` recomputes existing chains with the richer input (chain_hash per-row updates) so continuity holds.
5. Grep admin routes for `body.user_id` / `payload.user_id` — replace with `principal.user_id` from the authz dependency on mutation routes.
6. Tests: Owner-count invariant under concurrent writes, audit middleware skip on /health, X-Forwarded-For ignored when not-trusted, hash-chain re-verification after migration.

---

## 4. EPIC-N — Ingestion parsers + webhook hardening
**Tracker:** [#1461](https://github.com/PetrefiedThunder/RegEngine/issues/1461)
**Scope:** 14 open children. Biggest of the four. Splits into 3 PRs.

### PR-A — EPCIS parser hygiene
**Children:** #1148, #1151, #1153, #1156, #1249
**Files:** `services/ingestion/app/epcis/{xml_parser,persistence,validation,router}.py`
1. Delete in-memory fallback store (#1148) — `persistence.py:_allow_in_memory_fallback` (line 50) + `_ingest_single_event_fallback` (line 385). Postgres-only path.
2. Reject unmapped `bizStep` instead of silently mapping to 'receiving' (#1153) — `xml_parser.py` / `validation.py`.
3. Reject invalid dates instead of falling back to `now()` (#1151) — `persistence.py` normalization.
4. All-or-nothing batch insert (#1156) — wrap `_ingest_single_event_db:473` in a savepoint; rollback on any per-event failure.
5. Namespace handling hardening (#1249) — `xml_parser.py:_NS_MAP` + `_xml_local`.

### PR-B — EDI parser hygiene
**Children:** #1167, #1170, #1171, #1174
**Files:** `services/ingestion/app/edi_ingestion/{parser,routes,utils,dedup}.py`
1. YYMMDD century rejection (#1167) — `utils.py` date helpers; refuse ambiguous 2-digit years, require CCYYMMDD.
2. UTF-8 `errors='strict'` on file read (#1170) — `routes.py:read_upload_with_limit` + `parser.py:_parse_x12_segments`.
3. Segment-count cap (#1171) — `parser.py:_parse_x12_segments:12` — reject envelopes with > configurable N segments.
4. ISA13 dedup via the composite UNIQUE introduced by PR #1467 (#1174) — `routes.py:_enforce_envelope_integrity:66` + `dedup.check_and_record_interchange`.

### PR-C — Webhook HMAC + replay window + BackgroundTasks retirement
**Children:** #1243, #1245, #1259, #1267
**Files:** `services/ingestion/app/webhook_router_v2.py`, `webhook_compat.py`
1. **HMAC verification from scratch** (#1243) — new dependency `require_webhook_signature` that reads `X-RegEngine-Signature`, compares against HMAC-SHA256(secret, request_body) with `hmac.compare_digest`. Config: `WEBHOOK_HMAC_SECRET` env (per-tenant lookup for prod). Mount at `POST /ingest`.
2. **Replay window ≤ 5 minutes** (#1245) — reject events whose `timestamp` is more than 5 min older than `datetime.now(UTC)`. Uses existing IngestEvent.timestamp. Config: `WEBHOOK_REPLAY_WINDOW_SECONDS=300`.
3. **Investigate #1259** — issue body not fully scoped during survey. May fold into PR-A EPCIS persistence work depending on what it names.
4. **Retire FastAPI BackgroundTasks in ingest hot path (#1267)** — grep showed BackgroundTasks in `routes_sources.py`, `routes_discovery.py`, `routes_scraping.py` but NOT in `webhook_router_v2`. Probably already done; close as no-action if confirmed on survey of `routes_discovery.py`.

---

## 5. Recommended execution order

| Rank | Epic | Rationale |
|---|---|---|
| 1 | **Ghost closures** | Zero-risk. Closes 8 issues, cleans the tracker. |
| 2 | **EPIC-F** | Smallest (2 issues). Single clean PR. Momentum win. |
| 3 | **EPIC-E** | Single PR. FSMA compliance-relevant. |
| 4 | **EPIC-K** | Single PR. Investor-demo signal. |
| 5 | **EPIC-N PR-A** EPCIS | Kicks off the biggest epic. Closes 5 issues. |
| 6 | **EPIC-N PR-B** EDI | Follow-on. Closes 4. |
| 7 | **EPIC-N PR-C** Webhooks | Biggest new work (HMAC). Closes 3-4. |

Total: 6 PRs + 8 issue closures to close all four remaining consolidation epics. Realistic timeline: one focused sprint.

## 6. Out of scope

- Full retirement of `cte_persistence` (#1335) — multi-sprint work already tracked.
- Any per-tenant HMAC secret UI — PR-C starts with a single global secret (`WEBHOOK_HMAC_SECRET`). Per-tenant management is a separate product spike.
- Rules-engine broader refactor beyond fail-closed semantics.
