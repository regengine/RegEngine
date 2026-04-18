# GitHub Issues Consolidation — 2026-04-17

**Scope:** 361 open issues (as of 2026-04-17). This document identifies exact
duplicates, tight clusters that share a single root cause, and proposes
consolidated solutions (epic / meta-issue + common fix pattern).

**Priority profile:** P0: 58, P1: 131, P2: 88, P3: 6. The heaviest themes are
tenant isolation (~70 issues), auth/session (~35), NLP pipeline (~36), and
rules/validation (~20).

---

## Delta note — 2026-04-18 (morning)

Between the audit and the next morning, four overnight fix PRs landed that
moved the "keeper" side of every duplicate pair from OPEN to CLOSED. The
surviving open siblings are each resolved by the same PR (verified by
diff-reading) even though they were not explicitly referenced in the PR
titles:

| Originally-flagged duplicate (still OPEN) | Already-shipped keeper | Fixing PR | Pending action |
|---|---|---|---|
| #1093 Neo4jClient `database=` silent override | #1229 CLOSED | #1437 `fix(graph): tenant-scope Neo4j MERGE/MATCH` | Close #1093 as completed, reference PR #1437 |
| #1124 Content-Disposition filename injection | #1283 CLOSED | #1448 `fix(compliance): FDA export hardening` | Close #1124 as completed, reference PR #1448 |
| #1213 task_processor pg_notify never LISTENs | #1185 CLOSED | #1449 `fix(scheduler): task queue + scheduler hardening` | Close #1213 as completed, reference PR #1449 |
| #1092 + #1331 GDPR erasure signature | both CLOSED | #1441 / #1453 | none — already complete |

Collateral overnight progress on the proposed epics (sampled 2026-04-18):

| Epic | Open children | Closed children | Status |
|---|---|---|---|
| EPIC-A (tenant_id trust, 16 sampled) | 8 | 8 | Half done — keep meta, scope to remaining 8 |
| EPIC-C (Neo4j MERGE, 26 sampled) | 13 | 13 | First slice (admin supplier_graph_sync) shipped by #1437; #1315 meta already exists and is still the right anchor |
| EPIC-L (FDA CSV exports, 13 sampled) | 2 | 11 | Nearly done — #1448 closed most; skip meta, just track the 2 singletons |
| EPIC-P (scheduler, 14 sampled) | 6 | 8 | Mostly done — narrow meta to the 6 remaining |

Recommendation: before creating the meta-issues listed in §2, refresh
each epic's child-issue list against current state (the lists below are
snapshots from 2026-04-17). Epics whose children are mostly closed
(EPIC-L, EPIC-P, parts of EPIC-C) should be **skipped or narrowed** rather
than filed as fresh meta-issues — the underlying work is already
shipping. The epics with the highest remaining open-child count and the
largest consolidation value are EPIC-B (RLS), EPIC-D (hash-chain),
EPIC-E (NLP), EPIC-F (rules engine), EPIC-K (admin/RBAC), and EPIC-N
(ingestion parsers). EPIC-G (retire kernel/control) is a one-PR decision
and does not need a tracking meta-issue.

## Filed meta-issues — 2026-04-18

| Epic | Meta-issue | Open children at filing |
|---|---|---|
| EPIC-B Postgres RLS fail-open | [#1456](https://github.com/PetrefiedThunder/RegEngine/issues/1456) | 7 |
| EPIC-D Hash-chain appender + idempotency | [#1457](https://github.com/PetrefiedThunder/RegEngine/issues/1457) | 6 |
| EPIC-E NLP extractor — adopt FSMAExtractor | [#1458](https://github.com/PetrefiedThunder/RegEngine/issues/1458) | 6 |
| EPIC-F Rules engine — fail-closed + validator correctness | [#1459](https://github.com/PetrefiedThunder/RegEngine/issues/1459) | 8 |
| EPIC-K Admin RBAC + error hygiene + audit integrity | [#1460](https://github.com/PetrefiedThunder/RegEngine/issues/1460) | 7 |
| EPIC-N Ingestion parsers — ParseResult + webhook hardening | [#1461](https://github.com/PetrefiedThunder/RegEngine/issues/1461) | 14 |

Duplicate residuals closed: #1093, #1124, #1213 (as completed with PR
references to #1437 / #1448 / #1449 respectively).

## 0. Exact duplicates — close one of each pair

| Keep | Close as dup | Reason |
|---|---|---|
| [#1331](https://github.com/PetrefiedThunder/RegEngine/issues/1331) | [#1092](https://github.com/PetrefiedThunder/RegEngine/issues/1092) | Same `anonymize_audit_logs` wrong-signature bug. #1331 is superset (also covers missing tenant filter in soft_delete). |
| [#1229](https://github.com/PetrefiedThunder/RegEngine/issues/1229) | [#1093](https://github.com/PetrefiedThunder/RegEngine/issues/1093) | Same `Neo4jClient(database=…)` silent-override bug. #1229 is the SEC-CRIT tracker. |
| [#1213](https://github.com/PetrefiedThunder/RegEngine/issues/1213) | [#1185](https://github.com/PetrefiedThunder/RegEngine/issues/1185) | Same `pg_notify`/worker-never-LISTENs bug, two vantage points. Keep the one with 2s-latency framing. |
| [#1283](https://github.com/PetrefiedThunder/RegEngine/issues/1283) | [#1124](https://github.com/PetrefiedThunder/RegEngine/issues/1124) | Same Content-Disposition filename + date-range injection. #1283 covers the full route. |
| [#1185](https://github.com/PetrefiedThunder/RegEngine/issues/1185) + [#1213](https://github.com/PetrefiedThunder/RegEngine/issues/1213) | (see above) | pick #1213 to keep. |

**Action:** close 4 issues as duplicates, retaining the superset ticket.

---

## 1. Meta-issues already filed — keep as consolidation anchors

Four umbrella issues already exist and should remain the authoritative
trackers. New consolidation meta-issues (§2) follow the same pattern.

| # | Title | Children |
|---|---|---|
| [#1098](https://github.com/PetrefiedThunder/RegEngine/issues/1098) | [EPIC] GDPR user data rights | #1092, #1094, #1095, #1331, #1385, #1399, #1412 |
| [#1099](https://github.com/PetrefiedThunder/RegEngine/issues/1099) | [EPIC] Tenant-isolation strategy review | RLS + Neo4j sub-issues |
| [#1100](https://github.com/PetrefiedThunder/RegEngine/issues/1100) | auth [tracker] Supabase dual-auth coupling | #1072, #1073, #1075, #1086, #1087, #1088, #1089, #1090, #1401, #1403 |
| [#1101](https://github.com/PetrefiedThunder/RegEngine/issues/1101) | auth [tracker] token-revocation posture | #1039, #1069, #1071, #1349, #1375, #1380 |
| [#1315](https://github.com/PetrefiedThunder/RegEngine/issues/1315) | [SEC-META] Graph service security audit | #1229, #1236, #1242, #1244, #1250, #1256, #1261, #1268, #1270, #1273, #1278, #1284, #1289, #1294, #1298, #1301, #1304 |

---

## 2. Proposed new consolidation meta-issues (12 epics)

Each epic below replaces a tight cluster of duplicate-root-cause issues.
Child issues stay open (they track concrete code locations) but are
re-scoped under the meta so they ship together behind one fix.

### EPIC-A: "Client-supplied tenant_id" trust pattern — 17 issues

**Root cause (single):** multiple code paths accept `tenant_id` from an
attacker-controllable source (request body, URL path, query string, Kafka
payload, Supabase `user_metadata`, or string fallback) with no cross-check
against the authenticated session. This is the same bug pattern repeated
across every service.

**Children (17):**
- Kafka: [#1078](https://github.com/PetrefiedThunder/RegEngine/issues/1078), [#1176](https://github.com/PetrefiedThunder/RegEngine/issues/1176), [#1122](https://github.com/PetrefiedThunder/RegEngine/issues/1122), [#1388](https://github.com/PetrefiedThunder/RegEngine/issues/1388)
- Query param / URL path: [#1146](https://github.com/PetrefiedThunder/RegEngine/issues/1146), [#1148](https://github.com/PetrefiedThunder/RegEngine/issues/1148), [#1244](https://github.com/PetrefiedThunder/RegEngine/issues/1244), [#1268](https://github.com/PetrefiedThunder/RegEngine/issues/1268), [#1328](https://github.com/PetrefiedThunder/RegEngine/issues/1328), [#1106](https://github.com/PetrefiedThunder/RegEngine/issues/1106)
- Body / metadata: [#1184](https://github.com/PetrefiedThunder/RegEngine/issues/1184), [#1230](https://github.com/PetrefiedThunder/RegEngine/issues/1230), [#1344](https://github.com/PetrefiedThunder/RegEngine/issues/1344), [#1345](https://github.com/PetrefiedThunder/RegEngine/issues/1345)
- Fallback: [#1068](https://github.com/PetrefiedThunder/RegEngine/issues/1068), [#1268](https://github.com/PetrefiedThunder/RegEngine/issues/1268), [#1391](https://github.com/PetrefiedThunder/RegEngine/issues/1391)

**Consolidated solution:**
1. Introduce a single `resolve_tenant_context(request)` helper in
   `services/shared/auth/tenant_context.py` that pulls `tenant_id` **only**
   from the JWT `tenant_id` claim (or API-key server-side row). Remove all
   other code paths.
2. Replace every `_resolve_tenant` / ad-hoc `api_key.get('tenant_id', ...)`
   with a call to this helper. Add a pyre/semgrep rule that flags any
   `request.query_params.get("tenant_id")`, `body.tenant_id`,
   `user_metadata["tenant_id"]`, or hardcoded fallback string.
3. For Kafka, sign envelope headers with HMAC at produce time and verify
   at consume time; reject if `envelope.tenant_id != signed_headers.tenant_id`.
4. For demo/system reset, require `X-Sysadmin-Key` + explicit
   `target_tenant_id` body param (no silent default).

**Effort:** ~3-5 days (one sprint). One PR per service keeps blast radius small.

---

### EPIC-B: RLS fail-open / policy consistency — 10 issues

**Root cause:** Postgres RLS policies rely on `app.tenant_id` being set, but
several tables either have nullable `tenant_id`, no `FORCE RLS`, a fallback
`'default' UUID` path, or policies that contradict each other between
migrations.

**Children (10):** [#1091](https://github.com/PetrefiedThunder/RegEngine/issues/1091), [#1096](https://github.com/PetrefiedThunder/RegEngine/issues/1096), [#1204](https://github.com/PetrefiedThunder/RegEngine/issues/1204), [#1217](https://github.com/PetrefiedThunder/RegEngine/issues/1217), [#1265](https://github.com/PetrefiedThunder/RegEngine/issues/1265), [#1271](https://github.com/PetrefiedThunder/RegEngine/issues/1271), [#1281](https://github.com/PetrefiedThunder/RegEngine/issues/1281), [#1287](https://github.com/PetrefiedThunder/RegEngine/issues/1287), [#1321](https://github.com/PetrefiedThunder/RegEngine/issues/1321), [#1381](https://github.com/PetrefiedThunder/RegEngine/issues/1381)

**Consolidated solution:**
1. Write a single migration (`v057_rls_hardening.py`) that:
   - Adds `NOT NULL` to `tenant_id` on `fsma_audit_trail`, `task_queue`,
     `fda_sla_requests`, `chain_verification_log`.
   - Adds `FORCE ROW LEVEL SECURITY` to all 4 tables in #1281.
   - Replaces every `OR current_setting('app.tenant_id', true) = ''` with a
     hard fail; removes `'default'` UUID fallback in #1091.
   - Installs `SET search_path = fsma, pg_catalog` on every
     `SECURITY DEFINER` function (#1096).
2. Install a SQLAlchemy `after_connect` event that calls
   `set_tenant_context()` with the current request's tenant or aborts the
   checkout. Kills #1265, #1321, #1381, #1204.
3. Add a CI test that asserts every `fsma.*` and `admin.*` table has
   `FORCE RLS` and a non-nullable `tenant_id`.

**Effort:** ~2 days + migration review.

---

### EPIC-C: Neo4j tenant-scoping & MERGE hygiene — 19 issues

**Root cause:** Neo4j writes use `MERGE (n:Label {id: $id})` with no
`tenant_id` predicate. Any tenant can overwrite another tenant's nodes by
reusing an id. The `Neo4jClient(database=…)` arg is also silently ignored
(#1229). These are the same design bug repeated on every MERGE.

**Children (19):** already under meta [#1315](https://github.com/PetrefiedThunder/RegEngine/issues/1315) plus [#1352](https://github.com/PetrefiedThunder/RegEngine/issues/1352), [#1355](https://github.com/PetrefiedThunder/RegEngine/issues/1355), [#1393](https://github.com/PetrefiedThunder/RegEngine/issues/1393), [#1394](https://github.com/PetrefiedThunder/RegEngine/issues/1394), [#1395](https://github.com/PetrefiedThunder/RegEngine/issues/1395), [#1396](https://github.com/PetrefiedThunder/RegEngine/issues/1396), [#1397](https://github.com/PetrefiedThunder/RegEngine/issues/1397), [#1412](https://github.com/PetrefiedThunder/RegEngine/issues/1412), [#1413](https://github.com/PetrefiedThunder/RegEngine/issues/1413).

**Consolidated solution:**
1. **Composite key everywhere.** Change every `MERGE (n:X {id: $id})` to
   `MERGE (n:X {tenant_id: $tenant_id, id: $id})`. One PR per node-label
   family. Introduce a `CypherBuilder` helper that refuses to emit
   tenant-less MERGE for any label in a predefined set.
2. **Per-request Cypher scoping middleware** — inject `tenant_id` as a
   required parameter into every query; reject any query string that
   doesn't reference it (runtime check).
3. **Fix `Neo4jClient.database=`** to actually pass through (removes the
   silent-override from #1229) OR delete the arg and document single-DB
   mode. Pick one.
4. **Outbox for graph writes** (#1378, #1398, #1411): introduce
   `fsma.graph_outbox` table; canonical writer publishes to it; a single
   worker drains to Neo4j with idempotency on `(tenant_id, event_id)`.
5. **Tenant erasure** (#1412) runs a `MATCH (n {tenant_id: $t}) DETACH
   DELETE n` job inside the existing GDPR erasure flow.

**Effort:** ~1 sprint for (1)-(3), +3 days for outbox (4).

---

### EPIC-D: Hash-chain / idempotency race conditions — 12 issues

**Root cause:** Multiple persistence modules (`canonical_persistence`,
`cte_persistence`, `review`, `task_queue`) each roll their own idempotency
and hash-chain logic. All fail under concurrency for the same reason: the
`SELECT … FOR UPDATE LIMIT 1` locks the returned row, not the "next slot,"
and the companion `ON CONFLICT` guard is missing on the chain table.

**Children (12):** [#1074](https://github.com/PetrefiedThunder/RegEngine/issues/1074), [#1164](https://github.com/PetrefiedThunder/RegEngine/issues/1164), [#1190](https://github.com/PetrefiedThunder/RegEngine/issues/1190), [#1248](https://github.com/PetrefiedThunder/RegEngine/issues/1248), [#1251](https://github.com/PetrefiedThunder/RegEngine/issues/1251), [#1252](https://github.com/PetrefiedThunder/RegEngine/issues/1252), [#1262](https://github.com/PetrefiedThunder/RegEngine/issues/1262), [#1266](https://github.com/PetrefiedThunder/RegEngine/issues/1266), [#1307](https://github.com/PetrefiedThunder/RegEngine/issues/1307), [#1313](https://github.com/PetrefiedThunder/RegEngine/issues/1313), [#1332](https://github.com/PetrefiedThunder/RegEngine/issues/1332), [#1335](https://github.com/PetrefiedThunder/RegEngine/issues/1335).

**Consolidated solution:**
1. Extract one `HashChainAppender` class in
   `services/shared/hash_chain/appender.py`. Implements the canonical
   "advisory-lock on `(tenant_id, chain_name)` + INSERT with
   `ON CONFLICT (tenant_id, sequence_num) DO NOTHING`" pattern. Idempotent,
   race-safe.
2. Replace the three separate chain writers in `canonical_persistence`,
   `cte_persistence`, and `review/audit_logs` with this class. Kill the
   LEGACY `core.py` dual-write (#1335) — route webhook + EPCIS through the
   canonical writer only.
3. Add `idempotency_key` UNIQUE across `(tenant_id, key)` on
   `fsma.task_queue`, `fsma.review_items`, `fsma.cte_events`. Fixes
   #1164, #1211, #1248, #1237.
4. Add the `default=str` fix in `compute_idempotency_key` once (#1313) —
   import it from `shared/hash_chain/idempotency.py`.

**Effort:** ~1 sprint (design doc + refactor + migration).

---

### EPIC-E: NLP pipeline — dead code + prompt injection + gating bypass — 17 issues

**Root cause:** The NLP service has three parallel extractor implementations
(regex `extract_entities`, `FSMAExtractor`, `LLMGenerativeExtractor`). Only
the regex one is wired in prod. The "FSMA" gating, confidence tiers, FTL
scoping, and audit trails all live on the unreachable paths. The LLM
paths also merge system+user prompts and interpolate user data.

**Children (17):**
- Dead-code / unreachable: [#1118](https://github.com/PetrefiedThunder/RegEngine/issues/1118), [#1194](https://github.com/PetrefiedThunder/RegEngine/issues/1194), [#1218](https://github.com/PetrefiedThunder/RegEngine/issues/1218), [#1258](https://github.com/PetrefiedThunder/RegEngine/issues/1258), [#1260](https://github.com/PetrefiedThunder/RegEngine/issues/1260), [#1368](https://github.com/PetrefiedThunder/RegEngine/issues/1368)
- Prompt injection: [#1064](https://github.com/PetrefiedThunder/RegEngine/issues/1064), [#1121](https://github.com/PetrefiedThunder/RegEngine/issues/1121), [#1226](https://github.com/PetrefiedThunder/RegEngine/issues/1226), [#1238](https://github.com/PetrefiedThunder/RegEngine/issues/1238), [#1246](https://github.com/PetrefiedThunder/RegEngine/issues/1246), [#1253](https://github.com/PetrefiedThunder/RegEngine/issues/1253)
- Extraction correctness: [#1103](https://github.com/PetrefiedThunder/RegEngine/issues/1103), [#1104](https://github.com/PetrefiedThunder/RegEngine/issues/1104), [#1116](https://github.com/PetrefiedThunder/RegEngine/issues/1116), [#1123](https://github.com/PetrefiedThunder/RegEngine/issues/1123), [#1129](https://github.com/PetrefiedThunder/RegEngine/issues/1129)

**Consolidated solution:**
1. **Adopt-or-kill decision** — decide whether `FSMAExtractor` +
   `LLMGenerativeExtractor` become the production path (and delete the
   legacy regex `extract_entities` + `nlp.extracted` topic) or whether they
   get deleted. Default recommendation: adopt, delete regex path. Closes
   #1194, #1218, #1258, #1260, #1368, #1118.
2. **LLM hardening** (single commit): role-separated messages on every
   path (Vertex, Ollama, OpenAI), static system prompt, user content
   wrapped in `<document>…</document>` delimiters, Pydantic
   `extra="forbid"`, ASCII/regex output validation. Closes #1064, #1121,
   #1226, #1238, #1246, #1253, #1280, #1238.
3. **CTE + FTL coverage** — add extractors for HARVESTING / COOLING /
   INITIAL_PACKING / FIRST_LAND_BASED_RECEIVER; emit RECEIVING alongside
   SHIPPING for BOL docs; preserve TLC verbatim (no GTIN prepending);
   quantity+UoM as an inseparable pair. Closes #1103, #1104, #1123, #1129.
4. **FTL scoping at the extractor** (#1116) — reuse the validator's FTL
   list (shared module) so extractor and compliance agree.

**Effort:** ~2 sprints. (1) + (2) are a single PR, (3) + (4) are
feature-flagged rollout.

---

### EPIC-F: Rules engine — correctness + tenant safety — 13 issues

**Root cause:** The rules engine silently reports `compliant=True` when
rules are empty, when evaluators crash, when non-FTL foods are scanned,
and when UoM conversion fails. Several validators (GLN, quantity, regex)
have off-by-one correctness bugs. The `/validate` endpoint is orphaned.

**Children (13):** [#1102](https://github.com/PetrefiedThunder/RegEngine/issues/1102), [#1203](https://github.com/PetrefiedThunder/RegEngine/issues/1203), [#1344](https://github.com/PetrefiedThunder/RegEngine/issues/1344), [#1346](https://github.com/PetrefiedThunder/RegEngine/issues/1346), [#1347](https://github.com/PetrefiedThunder/RegEngine/issues/1347), [#1354](https://github.com/PetrefiedThunder/RegEngine/issues/1354), [#1356](https://github.com/PetrefiedThunder/RegEngine/issues/1356), [#1357](https://github.com/PetrefiedThunder/RegEngine/issues/1357), [#1358](https://github.com/PetrefiedThunder/RegEngine/issues/1358), [#1362](https://github.com/PetrefiedThunder/RegEngine/issues/1362), [#1363](https://github.com/PetrefiedThunder/RegEngine/issues/1363), [#1364](https://github.com/PetrefiedThunder/RegEngine/issues/1364), [#1371](https://github.com/PetrefiedThunder/RegEngine/issues/1371).

**Consolidated solution:**
1. **Fail-closed semantics** — empty rule set, evaluator crash, missing
   tenant_id, or zero-row evaluation all flip status to `FAILED` with a
   specific error code (`E_NO_RULES`, `E_EVALUATOR_CRASH`, `E_NO_TENANT`).
   Closes #1347, #1354, #1344.
2. **FTL gate** — before evaluation, look up the input's FDA FTL
   classification; if NOT on the list, return `NOT_APPLICABLE` (not
   `COMPLIANT`). Closes #1346 + #1102, #1116.
3. **UoM + validator fixes** (one module): add temperature conversion,
   per-product container factors (not global 24/case), GLN mod-10 check,
   quantity-AND-UoM check, regex timeout via
   `concurrent.futures` ReDoS harness. Closes #1357, #1358, #1362, #1363,
   #1364, #1356.
4. **Wire `/validate`** — React `Validator` page posts to it + server
   calls it during ingestion. Kills #1203.
5. **Redis-pubsub rule-cache invalidation** (#1371) — admin edits
   broadcast, workers subscribe.

**Effort:** ~1 sprint.

---

### EPIC-G: Kernel/Control/Obligation stack — orphaned + broken — 15 issues

**Root cause:** The `services/kernel/control/{compiler,codegen}` and
`services/kernel/obligation/{routes,engine,evaluator,regulation_loader}`
stacks are not called by any production code. The CLI entry point points
at a non-existent module (#1309). Several functions crash at import. The
codegen has a code-injection vulnerability (#1285). This is a full
adopt-or-retire decision.

**Children (15):** [#1275](https://github.com/PetrefiedThunder/RegEngine/issues/1275), [#1285](https://github.com/PetrefiedThunder/RegEngine/issues/1285), [#1295](https://github.com/PetrefiedThunder/RegEngine/issues/1295), [#1302](https://github.com/PetrefiedThunder/RegEngine/issues/1302), [#1305](https://github.com/PetrefiedThunder/RegEngine/issues/1305), [#1309](https://github.com/PetrefiedThunder/RegEngine/issues/1309), [#1310](https://github.com/PetrefiedThunder/RegEngine/issues/1310), [#1319](https://github.com/PetrefiedThunder/RegEngine/issues/1319), [#1326](https://github.com/PetrefiedThunder/RegEngine/issues/1326), [#1330](https://github.com/PetrefiedThunder/RegEngine/issues/1330), [#1339](https://github.com/PetrefiedThunder/RegEngine/issues/1339), [#1343](https://github.com/PetrefiedThunder/RegEngine/issues/1343), [#1351](https://github.com/PetrefiedThunder/RegEngine/issues/1351), [#1359](https://github.com/PetrefiedThunder/RegEngine/issues/1359), [#1366](https://github.com/PetrefiedThunder/RegEngine/issues/1366).

**Consolidated solution:**
- **Default recommendation: RETIRE.** The live compiler/engine path is in
  `services/compliance/app/validator.py`. Delete
  `services/kernel/control/` and `services/kernel/obligation/` in full,
  point the CLI (#1309) at the real validator, close all 15 issues.
- **Alternative (adopt):** fix the 8 blocker bugs (#1275, #1285, #1295,
  #1302, #1305, #1319, #1326, #1343), then wire the compiler into
  ingestion behind a feature flag. Minimum ~2 sprints of work for
  functionality already provided by the compliance validator.

**Effort:** 1-2 days to retire; 2 sprints to adopt. **Ship the retire PR
before investor demo** — reviewers otherwise hit this code first.

---

### EPIC-H: Event backbone unification — Kafka vs pg_notify split-brain — 16 issues

**Root cause:** Two different event transports run concurrently: Kafka
(inbound) + Postgres `task_queue` (outbound) + `pg_notify` trigger that
nobody LISTENs on. Every consumer has its own retry, DLQ, health check,
correlation-id handling.

**Children (16):**
- Split-brain: [#1159](https://github.com/PetrefiedThunder/RegEngine/issues/1159), [#1185](https://github.com/PetrefiedThunder/RegEngine/issues/1185), [#1213](https://github.com/PetrefiedThunder/RegEngine/issues/1213), [#1240](https://github.com/PetrefiedThunder/RegEngine/issues/1240)
- Retry / DLQ / backoff: [#1181](https://github.com/PetrefiedThunder/RegEngine/issues/1181), [#1192](https://github.com/PetrefiedThunder/RegEngine/issues/1192), [#1201](https://github.com/PetrefiedThunder/RegEngine/issues/1201), [#1220](https://github.com/PetrefiedThunder/RegEngine/issues/1220), [#1228](https://github.com/PetrefiedThunder/RegEngine/issues/1228), [#1241](https://github.com/PetrefiedThunder/RegEngine/issues/1241)
- Hygiene: [#1164](https://github.com/PetrefiedThunder/RegEngine/issues/1164), [#1166](https://github.com/PetrefiedThunder/RegEngine/issues/1166), [#1172](https://github.com/PetrefiedThunder/RegEngine/issues/1172), [#1199](https://github.com/PetrefiedThunder/RegEngine/issues/1199), [#1216](https://github.com/PetrefiedThunder/RegEngine/issues/1216), [#1225](https://github.com/PetrefiedThunder/RegEngine/issues/1225), [#1231](https://github.com/PetrefiedThunder/RegEngine/issues/1231), [#1382](https://github.com/PetrefiedThunder/RegEngine/issues/1382)

**Consolidated solution:**
1. **Pick one transport.** Align with target-architecture memo (PostgreSQL
   over Kafka). Retire Kafka consumers in NLP/graph/review/admin; route
   through `fsma.task_queue` with LISTEN/NOTIFY. Closes #1159, #1240.
2. **Shared consumer base class** in
   `services/shared/task_queue/worker.py` — exp-backoff retry, DLQ write,
   bounded `_retry_counts` (TTLCache), graceful-shutdown drain (SIGTERM),
   heartbeat on long-running handlers, HTTP `/health` endpoint, retention
   policy. Every service consumer subclasses. Closes #1166, #1172, #1181,
   #1201, #1220, #1225, #1228, #1231, #1241, #1382.
3. **Generic DLQ replay CLI** — `regengine dlq replay --queue=X --from=…`.
   Closes #1192.
4. **Inbound validation** on every topic — Pydantic model +
   schema-version field (#1197). Closes #1216.

**Effort:** ~2 sprints. Biggest win: deletes ~500 LOC of retry/DLQ
duplication.

---

### EPIC-I: Observability — correlation-id + metrics + tracing — 7 issues

**Root cause:** `CorrelationIdMiddleware` was added but commented out in
admin (#1316); structlog isn't wired to it (#1317); Kafka headers don't
carry it (#1318); Sentry scope doesn't include tenant or correlation
(#1320); there's no `/metrics` endpoint on 4 services (#1325); no OTel
auto-instrumentation (#1327); APScheduler loses it on dispatch (#1329).
Every symptom fixes the same way.

**Children (7):** [#1316](https://github.com/PetrefiedThunder/RegEngine/issues/1316), [#1317](https://github.com/PetrefiedThunder/RegEngine/issues/1317), [#1318](https://github.com/PetrefiedThunder/RegEngine/issues/1318), [#1320](https://github.com/PetrefiedThunder/RegEngine/issues/1320), [#1325](https://github.com/PetrefiedThunder/RegEngine/issues/1325), [#1327](https://github.com/PetrefiedThunder/RegEngine/issues/1327), [#1329](https://github.com/PetrefiedThunder/RegEngine/issues/1329).

**Consolidated solution:**
1. Enable `CorrelationIdMiddleware` on all FastAPI apps; bind to
   structlog `contextvars`; propagate in Kafka headers
   (`X-Correlation-Id`); propagate into APScheduler via `contextvars.copy_context()`.
2. Add `/metrics` prom endpoint via `prometheus-fastapi-instrumentator`
   to admin, compliance, nlp, ingestion.
3. Enable OTel auto-instrumentation for SQLAlchemy, httpx, aiokafka.
4. Extend Sentry `BeforeSend` to set `tenant_id` + `correlation_id` tags.

**Effort:** ~1 week. Small PR, high auditor-friendly optics.

---

### EPIC-J: Test coverage gaps — 11 issues

**Root cause:** Coverage thresholds (30-42%) are set below integration
coverage; many shared libs (auth.py, canonical_event.py), routes
(~2,500 LOC of admin), and consumers have zero dedicated tests.

**Children (11):** [#1130](https://github.com/PetrefiedThunder/RegEngine/issues/1130), [#1131](https://github.com/PetrefiedThunder/RegEngine/issues/1131), [#1132](https://github.com/PetrefiedThunder/RegEngine/issues/1132), [#1133](https://github.com/PetrefiedThunder/RegEngine/issues/1133), [#1134](https://github.com/PetrefiedThunder/RegEngine/issues/1134), [#1235](https://github.com/PetrefiedThunder/RegEngine/issues/1235), [#1300](https://github.com/PetrefiedThunder/RegEngine/issues/1300), [#1333](https://github.com/PetrefiedThunder/RegEngine/issues/1333), [#1336](https://github.com/PetrefiedThunder/RegEngine/issues/1336), [#1338](https://github.com/PetrefiedThunder/RegEngine/issues/1338), [#1341](https://github.com/PetrefiedThunder/RegEngine/issues/1341), [#1342](https://github.com/PetrefiedThunder/RegEngine/issues/1342), [#1348](https://github.com/PetrefiedThunder/RegEngine/issues/1348), [#1350](https://github.com/PetrefiedThunder/RegEngine/issues/1350), [#1353](https://github.com/PetrefiedThunder/RegEngine/issues/1353), [#1373](https://github.com/PetrefiedThunder/RegEngine/issues/1373).

**Consolidated solution:**
1. **Raise coverage floor to 70%** in one PR per service (#1348) —
   include integration tests in the coverage gate.
2. **Fixtures + golden-path tests** for the top gaps: auth_routes (#1333),
   admin routes (#1341), ingestion routers (#1342), identity_resolution
   (#1235), canonical_persistence (#1300), cte_persistence (#1336),
   shared libs (#1338).
3. **Fuzz/property-based harness** (Hypothesis) for the canonical event
   parser and rules engine (#1353).
4. **Remove time.sleep() / session-scoped http_client** antipattern
   (#1350).

**Effort:** rolling — one service per sprint until floor holds.

---

### EPIC-K: Admin / RBAC hardening — 14 issues

**Root cause:** Admin service grew organically; tenant-id and
permission checks are inconsistent, error strings leak, MFA secrets
aren't encrypted, `/health` goes through audit middleware.

**Children (14):** [#1079](https://github.com/PetrefiedThunder/RegEngine/issues/1079), [#1083](https://github.com/PetrefiedThunder/RegEngine/issues/1083), [#1376](https://github.com/PetrefiedThunder/RegEngine/issues/1376), [#1383](https://github.com/PetrefiedThunder/RegEngine/issues/1383), [#1384](https://github.com/PetrefiedThunder/RegEngine/issues/1384), [#1385](https://github.com/PetrefiedThunder/RegEngine/issues/1385), [#1386](https://github.com/PetrefiedThunder/RegEngine/issues/1386), [#1387](https://github.com/PetrefiedThunder/RegEngine/issues/1387), [#1392](https://github.com/PetrefiedThunder/RegEngine/issues/1392), [#1399](https://github.com/PetrefiedThunder/RegEngine/issues/1399), [#1405](https://github.com/PetrefiedThunder/RegEngine/issues/1405), [#1406](https://github.com/PetrefiedThunder/RegEngine/issues/1406), [#1407](https://github.com/PetrefiedThunder/RegEngine/issues/1407), [#1414](https://github.com/PetrefiedThunder/RegEngine/issues/1414), [#1415](https://github.com/PetrefiedThunder/RegEngine/issues/1415).

**Consolidated solution:**
1. **Generic exception handler** that strips `str(exc)` to a code
   (#1079) + add a `safe_error_code` enum.
2. **Fernet-encrypt `mfa_secret`** (#1376) — migration + wrapper.
3. **Role-change semantic invariant**: every role write is `SELECT FOR
   UPDATE` on `memberships` + assert `COUNT(Owners) >= 1` after the change
   or ROLLBACK. (#1083, #1387, #1406)
4. **RBAC helper `require_permission(perm, tenant_id)`** used on every
   write route; reject any route that takes a `user_id` from the request
   body. (#1384, #1386, #1407)
5. **Tenant-scope audit middleware** — skip `/health`, `/docs`,
   `/metrics`; strip `X-Forwarded-For` in favor of trusted proxy header.
   (#1414)
6. **Audit integrity** — include `actor_id, actor_email, severity,
   endpoint` in the hash input (#1415). One-shot migration to recompute
   existing chains.

**Effort:** ~1.5 sprints.

---

### EPIC-L: FDA CSV / spreadsheet export hardening — 10 issues

**Root cause:** Two separate CSV export codepaths
(`services/ingestion/app/fda_export_service.py` and
`services/compliance/app/fsma_spreadsheet.py`) share the same bug class —
no formula-prefix escaping, no Content-Disposition sanitization, no date
validation, no PII redaction, silent truncation, "success" on empty
results, end_date-only exports enabling full-tenant dumps.

**Children (10):** [#1038](https://github.com/PetrefiedThunder/RegEngine/issues/1038), [#1081](https://github.com/PetrefiedThunder/RegEngine/issues/1081), [#1108](https://github.com/PetrefiedThunder/RegEngine/issues/1108), [#1109](https://github.com/PetrefiedThunder/RegEngine/issues/1109), [#1205](https://github.com/PetrefiedThunder/RegEngine/issues/1205), [#1209](https://github.com/PetrefiedThunder/RegEngine/issues/1209), [#1219](https://github.com/PetrefiedThunder/RegEngine/issues/1219), [#1222](https://github.com/PetrefiedThunder/RegEngine/issues/1222), [#1224](https://github.com/PetrefiedThunder/RegEngine/issues/1224), [#1272](https://github.com/PetrefiedThunder/RegEngine/issues/1272), [#1283](https://github.com/PetrefiedThunder/RegEngine/issues/1283), [#1291](https://github.com/PetrefiedThunder/RegEngine/issues/1291), [#1328](https://github.com/PetrefiedThunder/RegEngine/issues/1328).

**Consolidated solution:**
1. **Extract `services/shared/fda_export/` module.** Provides:
   - `safe_cell(value: Any) -> str` — escape `=+-@\t\r` (CSV injection).
   - `safe_filename(prefix, start, end) -> str` — ASCII only, no `"`, `/`,
     `\\n`, `\\r`.
   - `validate_export_window(start, end)` — require both dates, max 90-day
     span, parsed as UTC.
   - `redact_pii(row)` — swap supplier-contact names/addresses with
     hashed placeholders unless caller has `fda_export.full_pii` scope.
   - `pagination(batch_size=500)` — stream paginated rows (removes
     #1038 silent truncation).
2. Route both export paths through this module. One PR per service.
3. Refuse to return 200+spreadsheet when `events=[]` (return 404).
   Closes #1291.
4. Log `user_id`, `ip`, `row_count`, `start`, `end`, `hash(rows)` to
   audit chain synchronously; fail export if audit fails (#1215, #1205).
5. Close #1328 with EPIC-A (drop URL tenant_id; use JWT claim).

**Effort:** ~1 sprint. High auditor signal.

---

### EPIC-M: Migrations / alembic baseline — 7 issues

**Root cause:** `alembic upgrade head` on a fresh DB fails because the
baseline references deleted `/migrations/*.sql` files; migration filenames
sort lexicographically wrong; revision IDs are hand-crafted hex
(collision risk); v051/v056 redo work; v056 drops a policy it just
created; downgrade destroys prod.

**Children (7):** [#1187](https://github.com/PetrefiedThunder/RegEngine/issues/1187), [#1227](https://github.com/PetrefiedThunder/RegEngine/issues/1227), [#1247](https://github.com/PetrefiedThunder/RegEngine/issues/1247), [#1257](https://github.com/PetrefiedThunder/RegEngine/issues/1257), [#1264](https://github.com/PetrefiedThunder/RegEngine/issues/1264), [#1296](https://github.com/PetrefiedThunder/RegEngine/issues/1296), [#1303](https://github.com/PetrefiedThunder/RegEngine/issues/1303).

**Consolidated solution:**
1. **Squash v043-v056** into `v043_baseline_consolidated.py` — one
   self-contained migration. Inline the deleted `.sql` files as Python
   strings. Closes #1187, #1227, #1247, #1257.
2. **Rename migrations** to `NNNN_description.py` (zero-padded index) —
   kills the date-sort ambiguity (#1303).
3. **Auto-generated revision IDs** via `alembic revision --autogenerate`
   — stop hand-writing hex (#1296).
4. **Guard `downgrade(base)`** — refuse if
   `os.environ["ENVIRONMENT"] == "production"` unless
   `ALEMBIC_ALLOW_DESTRUCTIVE=1`. (#1264)

**Effort:** ~3 days (requires staging-DB migration rehearsal).

---

### EPIC-N: Ingestion parsers (EPCIS + EDI + webhooks) — 19 issues

**Root cause:** EDI, EPCIS, and webhook parsers share the same
anti-patterns: validation failures persist records anyway, invalid
dates fall back to `now()`, character-encoding errors silently drop,
no HMAC/idempotency/replay guards on webhooks.

**Children (19):**
- EPCIS: [#1146](https://github.com/PetrefiedThunder/RegEngine/issues/1146), [#1148](https://github.com/PetrefiedThunder/RegEngine/issues/1148), [#1151](https://github.com/PetrefiedThunder/RegEngine/issues/1151), [#1153](https://github.com/PetrefiedThunder/RegEngine/issues/1153), [#1156](https://github.com/PetrefiedThunder/RegEngine/issues/1156), [#1249](https://github.com/PetrefiedThunder/RegEngine/issues/1249)
- EDI: [#1160](https://github.com/PetrefiedThunder/RegEngine/issues/1160), [#1165](https://github.com/PetrefiedThunder/RegEngine/issues/1165), [#1167](https://github.com/PetrefiedThunder/RegEngine/issues/1167), [#1170](https://github.com/PetrefiedThunder/RegEngine/issues/1170), [#1171](https://github.com/PetrefiedThunder/RegEngine/issues/1171), [#1174](https://github.com/PetrefiedThunder/RegEngine/issues/1174)
- Webhooks: [#1232](https://github.com/PetrefiedThunder/RegEngine/issues/1232), [#1237](https://github.com/PetrefiedThunder/RegEngine/issues/1237), [#1243](https://github.com/PetrefiedThunder/RegEngine/issues/1243), [#1245](https://github.com/PetrefiedThunder/RegEngine/issues/1245), [#1248](https://github.com/PetrefiedThunder/RegEngine/issues/1248)
- Persistence: [#1239](https://github.com/PetrefiedThunder/RegEngine/issues/1239), [#1259](https://github.com/PetrefiedThunder/RegEngine/issues/1259), [#1267](https://github.com/PetrefiedThunder/RegEngine/issues/1267)

**Consolidated solution:**
1. **Contract**: every parser returns
   `ParseResult(events: list, errors: list, rejected: bool)`.
   `rejected=True` means **persistence is skipped** (no partial state).
   Closes #1151, #1156, #1174, #1239, #1249, #1259.
2. **Transactional batch insert** — all-or-nothing per file (#1156).
3. **Webhook middleware** — HMAC verification (#1243),
   `IdempotencyMiddleware` wired on `webhook_router_v2/ingest` (#1232),
   tenant-scoped idempotency cache (#1237), timestamp replay window ≤5min
   (#1245).
4. **EDI hygiene** — parse GS segment (#1160), dedupe ISA13 (#1165),
   reject YYMMDD without century (#1167), `errors='strict'` on UTF-8
   (#1170), segment-count cap (#1171).
5. **EPCIS hygiene** — unmapped bizStep → reject (not silent 'receiving')
   (#1153); delete in-memory fallback store (move to Postgres-only)
   (#1148).
6. **Replace FastAPI `BackgroundTasks`** in the ingest hot path with
   `task_queue` (#1267) — durable across deploys.

**Effort:** ~2 sprints; biggest unblock for FSMA compliance claims.

---

### EPIC-O: Supply-chain & CI — 9 issues

**Children (9):** [#1137](https://github.com/PetrefiedThunder/RegEngine/issues/1137), [#1139](https://github.com/PetrefiedThunder/RegEngine/issues/1139), [#1141](https://github.com/PetrefiedThunder/RegEngine/issues/1141), [#1143](https://github.com/PetrefiedThunder/RegEngine/issues/1143), [#1145](https://github.com/PetrefiedThunder/RegEngine/issues/1145), [#1149](https://github.com/PetrefiedThunder/RegEngine/issues/1149), [#1155](https://github.com/PetrefiedThunder/RegEngine/issues/1155), [#1157](https://github.com/PetrefiedThunder/RegEngine/issues/1157), [#1161](https://github.com/PetrefiedThunder/RegEngine/issues/1161), [#1169](https://github.com/PetrefiedThunder/RegEngine/issues/1169), [#1173](https://github.com/PetrefiedThunder/RegEngine/issues/1173), [#1178](https://github.com/PetrefiedThunder/RegEngine/issues/1178).

**Consolidated solution:** one cross-cutting PR `chore(ci): baseline
supply-chain posture` that:
1. Adds `.dockerignore` (#1143).
2. Converts every Python Dockerfile to multi-stage (builder vs runtime)
   and drops gcc/libpq-dev from the runtime image (#1149, #1155).
3. Adds `permissions: {contents: read}` block to all workflows (#1145).
4. Pins base images + actions to SHA (#1137), ships uv lockfiles
   (#1139).
5. Generates SBOM + cosign signatures (#1169).
6. Moves detect-secrets into a required CI job (#1173), gates Semgrep
   findings (#1157), narrows Gitleaks allowlist (#1161).
7. Splits Dependabot into `security`, `patches`, `grouped-minor` groups
   (#1178).
8. Fixes `kernel/reporting/Dockerfile` to install the correct
   requirements file (#1141).

**Effort:** ~1 week. Low risk.

---

### EPIC-P: Scheduler reliability — 13 issues

**Children (13):** [#1063](https://github.com/PetrefiedThunder/RegEngine/issues/1063), [#1135](https://github.com/PetrefiedThunder/RegEngine/issues/1135), [#1136](https://github.com/PetrefiedThunder/RegEngine/issues/1136), [#1138](https://github.com/PetrefiedThunder/RegEngine/issues/1138), [#1140](https://github.com/PetrefiedThunder/RegEngine/issues/1140), [#1142](https://github.com/PetrefiedThunder/RegEngine/issues/1142), [#1144](https://github.com/PetrefiedThunder/RegEngine/issues/1144), [#1147](https://github.com/PetrefiedThunder/RegEngine/issues/1147), [#1150](https://github.com/PetrefiedThunder/RegEngine/issues/1150), [#1154](https://github.com/PetrefiedThunder/RegEngine/issues/1154), [#1158](https://github.com/PetrefiedThunder/RegEngine/issues/1158), [#1162](https://github.com/PetrefiedThunder/RegEngine/issues/1162), [#1255](https://github.com/PetrefiedThunder/RegEngine/issues/1255), [#1084](https://github.com/PetrefiedThunder/RegEngine/issues/1084).

**Consolidated solution:**
1. **Decide: adopt or retire nightly FSMA sync.** If retire, delete
   (#1135 + #1162). If adopt, wire it and fix the empty API key
   (#1063).
2. **Unified scheduler driver** — SIGTERM handler with job drain
   (#1255); heartbeat on distributed lock (#1142); misfire alerting
   (#1144); exponential-backoff HTTP retry on all outbound calls
   (#1138, #1147, #1150); SSRF guard + body cap on webhook delivery
   (#1084).
3. **FDA scraper resilience** — schema-validation on parsed HTML rather
   than regex silence (#1140); record-only dedup hash (no title/summary)
   (#1158); fixture tests (#1154).
4. **Kafka emission** — write-ahead to `task_queue` before marking seen
   (#1136, #1147).

**Effort:** ~1 sprint.

---

## 3. Remaining singletons (not in any epic)

Items that don't naturally group but need individual fixes:

| Theme | Issues |
|---|---|
| Billing / Stripe | [#1076](https://github.com/PetrefiedThunder/RegEngine/issues/1076), [#1182](https://github.com/PetrefiedThunder/RegEngine/issues/1182), [#1184](https://github.com/PetrefiedThunder/RegEngine/issues/1184), [#1186](https://github.com/PetrefiedThunder/RegEngine/issues/1186), [#1189](https://github.com/PetrefiedThunder/RegEngine/issues/1189), [#1196](https://github.com/PetrefiedThunder/RegEngine/issues/1196), [#1198](https://github.com/PetrefiedThunder/RegEngine/issues/1198), [#1243](https://github.com/PetrefiedThunder/RegEngine/issues/1243) (note #1184 → EPIC-A, #1243 → EPIC-N). Recommend a small **EPIC-Q Stripe-webhook hardening** for the rest. |
| Review / hallucination triage | [#1360](https://github.com/PetrefiedThunder/RegEngine/issues/1360), [#1361](https://github.com/PetrefiedThunder/RegEngine/issues/1361), [#1367](https://github.com/PetrefiedThunder/RegEngine/issues/1367), [#1369](https://github.com/PetrefiedThunder/RegEngine/issues/1369), [#1388](https://github.com/PetrefiedThunder/RegEngine/issues/1388), [#1389](https://github.com/PetrefiedThunder/RegEngine/issues/1389), [#1390](https://github.com/PetrefiedThunder/RegEngine/issues/1390), [#1408](https://github.com/PetrefiedThunder/RegEngine/issues/1408), [#1409](https://github.com/PetrefiedThunder/RegEngine/issues/1409). Recommend **EPIC-R Review service — identity + tenant scope + audit chain** (all 9 land together). |
| Identity resolution | [#1175](https://github.com/PetrefiedThunder/RegEngine/issues/1175), [#1177](https://github.com/PetrefiedThunder/RegEngine/issues/1177), [#1179](https://github.com/PetrefiedThunder/RegEngine/issues/1179), [#1190](https://github.com/PetrefiedThunder/RegEngine/issues/1190), [#1191](https://github.com/PetrefiedThunder/RegEngine/issues/1191), [#1193](https://github.com/PetrefiedThunder/RegEngine/issues/1193), [#1195](https://github.com/PetrefiedThunder/RegEngine/issues/1195), [#1207](https://github.com/PetrefiedThunder/RegEngine/issues/1207), [#1208](https://github.com/PetrefiedThunder/RegEngine/issues/1208), [#1211](https://github.com/PetrefiedThunder/RegEngine/issues/1211), [#1212](https://github.com/PetrefiedThunder/RegEngine/issues/1212), [#1233](https://github.com/PetrefiedThunder/RegEngine/issues/1233), [#1234](https://github.com/PetrefiedThunder/RegEngine/issues/1234). Recommend **EPIC-S Identity-resolution correctness + tenant-safe aliasing** (13 items). |
| Frontend | [#1067](https://github.com/PetrefiedThunder/RegEngine/issues/1067), [#1097](https://github.com/PetrefiedThunder/RegEngine/issues/1097), [#1152](https://github.com/PetrefiedThunder/RegEngine/issues/1152), [#1163](https://github.com/PetrefiedThunder/RegEngine/issues/1163), [#1168](https://github.com/PetrefiedThunder/RegEngine/issues/1168), [#1180](https://github.com/PetrefiedThunder/RegEngine/issues/1180), [#1183](https://github.com/PetrefiedThunder/RegEngine/issues/1183), [#1188](https://github.com/PetrefiedThunder/RegEngine/issues/1188), [#1200](https://github.com/PetrefiedThunder/RegEngine/issues/1200), [#1214](https://github.com/PetrefiedThunder/RegEngine/issues/1214), [#1221](https://github.com/PetrefiedThunder/RegEngine/issues/1221). Recommend **EPIC-T Frontend hardening + dead-code sweep**. |
| Canonical persistence (non-race) | [#1197](https://github.com/PetrefiedThunder/RegEngine/issues/1197), [#1263](https://github.com/PetrefiedThunder/RegEngine/issues/1263), [#1276](https://github.com/PetrefiedThunder/RegEngine/issues/1276), [#1277](https://github.com/PetrefiedThunder/RegEngine/issues/1277), [#1279](https://github.com/PetrefiedThunder/RegEngine/issues/1279), [#1282](https://github.com/PetrefiedThunder/RegEngine/issues/1282), [#1290](https://github.com/PetrefiedThunder/RegEngine/issues/1290), [#1292](https://github.com/PetrefiedThunder/RegEngine/issues/1292), [#1293](https://github.com/PetrefiedThunder/RegEngine/issues/1293), [#1297](https://github.com/PetrefiedThunder/RegEngine/issues/1297). Fold into EPIC-D's module refactor. |
| CTE persistence (non-race) | [#1308](https://github.com/PetrefiedThunder/RegEngine/issues/1308), [#1311](https://github.com/PetrefiedThunder/RegEngine/issues/1311), [#1312](https://github.com/PetrefiedThunder/RegEngine/issues/1312), [#1314](https://github.com/PetrefiedThunder/RegEngine/issues/1314), [#1322](https://github.com/PetrefiedThunder/RegEngine/issues/1322), [#1323](https://github.com/PetrefiedThunder/RegEngine/issues/1323), [#1324](https://github.com/PetrefiedThunder/RegEngine/issues/1324), [#1334](https://github.com/PetrefiedThunder/RegEngine/issues/1334). Fold into EPIC-D's `HashChainAppender` extraction. |
| NLP correctness (remaining) | [#1029](https://github.com/PetrefiedThunder/RegEngine/issues/1029), [#1085](https://github.com/PetrefiedThunder/RegEngine/issues/1085), [#1115](https://github.com/PetrefiedThunder/RegEngine/issues/1115), [#1117](https://github.com/PetrefiedThunder/RegEngine/issues/1117), [#1119](https://github.com/PetrefiedThunder/RegEngine/issues/1119), [#1120](https://github.com/PetrefiedThunder/RegEngine/issues/1120), [#1126](https://github.com/PetrefiedThunder/RegEngine/issues/1126), [#1127](https://github.com/PetrefiedThunder/RegEngine/issues/1127), [#1128](https://github.com/PetrefiedThunder/RegEngine/issues/1128), [#1202](https://github.com/PetrefiedThunder/RegEngine/issues/1202), [#1206](https://github.com/PetrefiedThunder/RegEngine/issues/1206), [#1269](https://github.com/PetrefiedThunder/RegEngine/issues/1269), [#1274](https://github.com/PetrefiedThunder/RegEngine/issues/1274), [#1280](https://github.com/PetrefiedThunder/RegEngine/issues/1280), [#1286](https://github.com/PetrefiedThunder/RegEngine/issues/1286), [#1288](https://github.com/PetrefiedThunder/RegEngine/issues/1288), [#1299](https://github.com/PetrefiedThunder/RegEngine/issues/1299), [#1370](https://github.com/PetrefiedThunder/RegEngine/issues/1370). Fold into EPIC-E. |
| Compliance (remaining) | [#1107](https://github.com/PetrefiedThunder/RegEngine/issues/1107), [#1110](https://github.com/PetrefiedThunder/RegEngine/issues/1110), [#1111](https://github.com/PetrefiedThunder/RegEngine/issues/1111), [#1112](https://github.com/PetrefiedThunder/RegEngine/issues/1112), [#1113](https://github.com/PetrefiedThunder/RegEngine/issues/1113), [#1114](https://github.com/PetrefiedThunder/RegEngine/issues/1114), [#1125](https://github.com/PetrefiedThunder/RegEngine/issues/1125), [#1215](https://github.com/PetrefiedThunder/RegEngine/issues/1215), [#1223](https://github.com/PetrefiedThunder/RegEngine/issues/1223). Fold into EPIC-L. |
| Auth non-revocation | [#1041](https://github.com/PetrefiedThunder/RegEngine/issues/1041), [#1060](https://github.com/PetrefiedThunder/RegEngine/issues/1060), [#1061](https://github.com/PetrefiedThunder/RegEngine/issues/1061), [#1065](https://github.com/PetrefiedThunder/RegEngine/issues/1065), [#1070](https://github.com/PetrefiedThunder/RegEngine/issues/1070), [#1082](https://github.com/PetrefiedThunder/RegEngine/issues/1082), [#1337](https://github.com/PetrefiedThunder/RegEngine/issues/1337), [#1340](https://github.com/PetrefiedThunder/RegEngine/issues/1340), [#1374](https://github.com/PetrefiedThunder/RegEngine/issues/1374), [#1377](https://github.com/PetrefiedThunder/RegEngine/issues/1377), [#1400](https://github.com/PetrefiedThunder/RegEngine/issues/1400), [#1402](https://github.com/PetrefiedThunder/RegEngine/issues/1402), [#1404](https://github.com/PetrefiedThunder/RegEngine/issues/1404). Fold into [#1100](https://github.com/PetrefiedThunder/RegEngine/issues/1100) / [#1101](https://github.com/PetrefiedThunder/RegEngine/issues/1101) trackers. |
| GDPR (remaining) | [#1094](https://github.com/PetrefiedThunder/RegEngine/issues/1094), [#1095](https://github.com/PetrefiedThunder/RegEngine/issues/1095). Fold into [#1098](https://github.com/PetrefiedThunder/RegEngine/issues/1098). |
| Infra / gateway | [#1062](https://github.com/PetrefiedThunder/RegEngine/issues/1062), [#1066](https://github.com/PetrefiedThunder/RegEngine/issues/1066), [#1033](https://github.com/PetrefiedThunder/RegEngine/issues/1033), [#1039](https://github.com/PetrefiedThunder/RegEngine/issues/1039), [#1073](https://github.com/PetrefiedThunder/RegEngine/issues/1073), [#1378](https://github.com/PetrefiedThunder/RegEngine/issues/1378), [#1410](https://github.com/PetrefiedThunder/RegEngine/issues/1410), [#1411](https://github.com/PetrefiedThunder/RegEngine/issues/1411). Case-by-case. |

---

## 4. Recommended execution order

Order optimized for **investor-demo readiness first, then auditor-readiness**,
based on ship-sequence preference (security before cosmetic):

| Sprint | Epic(s) | Rationale |
|---|---|---|
| 1 | EPIC-A (tenant_id trust) + EPIC-B (RLS) | Closes ~25 P0/P1 items; single "tenant boundary is honored" story for security review. |
| 2 | EPIC-C (Neo4j) + EPIC-D (hash-chain) | Closes full Graph audit #1315 + FSMA data-integrity. |
| 3 | EPIC-L (FDA exports) + EPIC-N (ingestion parsers) | FSMA compliance story end-to-end. |
| 4 | EPIC-E (NLP pipeline) | Unblocks extraction accuracy claims. |
| 5 | EPIC-F (rules) + EPIC-H (event backbone) | Correctness + reliability. |
| 6 | EPIC-G (retire kernel) + EPIC-M (alembic) | Remove landmines. |
| 7 | EPIC-I (observability) + EPIC-O (supply-chain) | Auditor-grade posture. |
| 8 | EPIC-J (tests) + EPIC-K (admin/RBAC) + remaining singletons | Long-tail. |

---

## 5. Summary stats

| Count | Category |
|---|---|
| 361 | Total open issues |
| 4 | True duplicates to close |
| 16 | Consolidation epics proposed (A-T) |
| ~220 | Issues consolidated into those 16 epics |
| ~80 | Issues already under existing 5 meta-issues (#1098, #1099, #1100, #1101, #1315) |
| ~55 | Singletons / case-by-case |

**Net:** ~95% of open issues fall into ~20 work streams with shared
solutions. Every P0 is either a meta-tracker child or a singleton fix
touching fewer than 3 files.
