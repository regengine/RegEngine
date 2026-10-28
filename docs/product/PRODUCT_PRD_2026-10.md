# RegEngine Product PRD, October 2026

Date: 2026-10-27. Status: draft v1 for founder review. Product status: Beta, pre-revenue. Owner: founder / product.
Supersedes for product scope: `PRODUCT_OVERVIEW.md` and `PRODUCT_ROADMAP.md` (2026-04-30). Does not replace `PRODUCTION_REMEDIATION_PRD_2026-05-01.md`, which is a fix program; its six open questions are carried into section 9.
Verification basis. Code and surface claims were checked against `server/main.py`, `server/router_policy.py`, `PRODUCTION_SURFACE.md`, `frontend/src/lib/capabilities.ts` and Linear project P-SEL-2 as of 2026-10-27. Market, customer, pilot and compliance-scope claims come from the repository documents cited inline (`POSITIONING.md`, the May 2026 go-to-market research, the proof checklist, `docs/specs/FSMA_204_MVP_SPEC.md`, the 2026-10-27 plan note) and are those documents' claims, not verified facts about customers. Jev answers and the Q1 dates are planning inputs. Any other claim is marked "not verified".

## 1. Problem statement

FSMA 204 (21 CFR Part 1 Subpart S) requires firms that handle Food Traceability List foods to keep key data elements for each critical tracking event and to hand FDA an electronic sortable spreadsheet within 24 hours of a request. The compliance date was January 20, 2026; FDA has said it will not enforce before July 20, 2028 (copy corrected in PRs 3667 and 3670). Supplier data does not arrive in that shape: it comes as CSVs, spreadsheets, PDFs and emails with missing lot codes, locations and dates. The person who receives the request is a QA or food safety manager with no engineering support, and the cost of not solving it is a failed records request, a stalled recall, or a lost retail account that demands traceability data.

## 2. Ideal customer

Source: `docs/product/POSITIONING.md` (2026-05-06), `docs/research/fsma-204-go-to-market-2026-05.md` section 2 (four-agent ICP consensus), `docs/research/outreach-top-10-2026-05-14.md`.

| ICP | Who | Size | Buyer and champion | Named prospects |
| --- | --- | --- | --- | --- |
| 1 (primary) | Mid-market fresh-cut processor, QA manager or director of food safety | $20M to $120M revenue | Owner, COO or CFO signs; QA manager champions | 7 Salinas and Watsonville processors in the top-10 list |
| 2 | First land-based receiver or small importer (finfish, tropical fruit) | $5M to $50M | Owner or VP operations | 3 named in the top-10 list |

Data shape in both: supplier CSV, ERP export, spreadsheet or email-derived file, incomplete enough to create fix work. The proof checklist names the first measured claim to earn: "RegEngine improves supplier-data readiness before evidence commit" (`docs/product/DESIGN_PARTNER_PROOF_CHECKLIST.md`). Outreach state: 5 InMails sent 2026-05-23, honorarium retracted 2026-05-26, no session recorded in the repo. Active trackers live in `sales/local/` (git-ignored); the templates are in `sales/`.

## 3. Goals

1. One design partner runs one real supplier feed through preflight, closes at least one fix item, and verifies one export package.
2. One paid pilot agreement signed and its first payment received (a paid Stripe checkout or a paid invoice, section 8) by 2027-01-31 (Q1, decided 2026-10-27). A signed but unpaid agreement does not meet this goal.
3. Every public and signed-in claim matches the capabilities registry, so a prospect never finds a dead end during a session.
4. The signed-in app works end to end for an owner account on real data with no invented sample data.

## 4. What is built today

Production mounts the exact allowlist `PRODUCTION_ENABLED_ROUTERS` in `server/router_policy.py` (25 routers); a missing, extra or unknown name aborts startup. Feature-gated routers omitted from the allowlist return 404 in production; the always-mounted base (core ingest, webhook, status, health, readiness, metrics, scheduler status) is not gated by the allowlist. Line numbers below are the `_router_enabled` guards in `server/main.py`. Mounted in production does not mean live: only CSV upload and the JSON events API are live. Every other customer-facing surface below is Beta or Preview, and EPCIS export stays Preview.

### 4.1 Production routers, grouped by product stage

| Stage | Router (line) | What it does | Evidence |
| --- | --- | --- | --- |
| Ingest | `webhook` (557, always mounted) | JSON events API, `POST /api/v1/webhooks/ingest` | `services/ingestion/app/webhook_router_v2/`; registry: live |
| Ingest | `csv` (596) | Per-CTE CSV templates and `POST /api/v1/ingest/csv` | `services/ingestion/app/csv_templates.py`; registry: live |
| Ingest | `epcis_ingestion` (636) | EPCIS 2.0 events, batch, XML, validate, export under `/api/v1/epcis` | `services/ingestion/app/epcis/router.py`; registry: preview |
| Ingest | `edi` (606) | EDI import under `/api/v1/ingest/edi` | `services/ingestion/app/edi_ingestion/routes.py`; registry: off. Mounted but not claimed; see Q6 |
| Ingest | `core_ingest` (545), `status` (553) | Document, URL and regulation ingest; ingestion status | `services/ingestion/app/routes_ingest.py`, `routes_status.py`; status: Beta |
| Preflight | `inflow_workbench` (579) | Runs, readiness preview and summary, fix queue, commit gate, scenarios under `/api/v1/inflow-workbench` | `services/ingestion/app/inflow_workbench.py`; tables `fsma.inflow_workbench_*`; status: Beta |
| Validate | `rules` (743), `exceptions` (748), `score` (611), `readiness` (782), `compliance_metrics` (777), `fsma_compliance` (980) | Versioned rules engine (26 critical, 11 warning rules in services/shared/rules/seeds.py), exception queue, compliance score, readiness wizard, metrics, advisory `POST /validate` and snapshots | `services/shared/rules/`, `docs/runbooks/RULES_ENGINE_ENFORCE_ROLLOUT.md`, `services/compliance/app/`; status: Beta |
| Validate | enforcement switch | `RULES_ENGINE_ENFORCE` is `off` by default; `cte_only` and `all` exist; no-verdict events are accepted in every mode | `services/shared/rules/enforcement.py`; status: Beta |
| Persist | `canonical_records` (738) | Tenant-scoped reads over `fsma.traceability_events` | `services/ingestion/app/canonical_router.py:120`; status: Beta |
| Persist | `chain_verification` (799), `audit_export_log` (804), `sla_tracking` (809), `export_monitoring` (814) | Hash-chain verification job, export log, FDA SLA requests, export monitoring | `services/ingestion/app/` modules of the same names; status: Beta |
| Export | `fda_export` (584) | `/api/v1/fda/export`, `/export/v2`, `/export/recall`, `/export/all`, `/export/history`, `/export/verify`, Merkle root and proof, `/trace/{tlc}` | `services/ingestion/app/fda_export/router.py`; status: Beta |
| Export | `proof_verify` (589), `proof_recall` (694) | Public, unauthenticated bundle verifier; recall drill endpoint returns no data | `PRODUCTION_SURFACE.md` "Public, tenantless" section; status: Beta |
| Workflow | `request_workflow` (762), `auditor` (772), `recall` (684), `onboarding` (679), `portal` (616) | FDA request workflow, auditor review, recall report, onboarding, supplier portal | `services/ingestion/app/` modules of the same names; status: Beta |
| Commercial | `billing` (656) | Stripe checkout for plans `growth` and `scale` (aliases `base`, `standard`), a contact-only third tier, metered label events; display amounts are the hardcoded `price_monthly`/`price_annual` values in `plans.py`; `STRIPE_PRICE_*` env vars hold Stripe checkout price IDs only | `services/ingestion/app/stripe_billing/plans.py`; GET `/plans` in `stripe_billing/routes.py` `list_plans` returns those hardcoded amounts every time; pricing page (`frontend/src/app/pricing/page.tsx`) shows unavailable when the plans fetch fails or returns no usable plans, not when Stripe IDs are unset; status: Beta |
| Admin | `admin` (853) | Tenants, users, invites, API keys, passwordless OTP and passkey auth, supplier onboarding, facilities, supplier compliance (data gaps, gap time to fix, FDA records export preview), bulk upload, review queue, admin audit, tool lead capture, erasure, data export | `services/admin/app/`; `services/admin/app/supplier_compliance_routes.py`; migration v135 `data_gap_events` (PR 3572); status: Beta |
| System | `/health`, `/readiness`, `/metrics`, scheduler status (1005) | Liveness, bounded dependency readiness, metrics behind a key | `server/main.py` readiness section; status: Beta |

### 4.2 Built but not in the production allowlist

- `remediation`: buyer manifests, release, case link revoke, outbox, metrics under `/api/v1/remediation`, plus the token-scoped supplier correction session under `/api/v1/remediation/supplier` (exchange, context, corrections, form). It is in `COMPLIANCE_ROUTERS` (disabling it in dev is a hard error) but not in `PRODUCTION_ENABLED_ROUTERS`, so production cannot mount it without a policy change (`server/router_policy.py`, `docs/engineering/ROUTER_SURFACE.md`). The frontend route `frontend/src/app/remediation` exists; whether it degrades cleanly in production: not verified. Decision 2026-10-27: promote (R4, SEL-593).
- Ops-adjacent, 404 in production: `alerts`, `supplier_mgmt`, `audit_log`, `product_catalog`, `notification_prefs`, `team_mgmt`, `settings`, `integration`, `identity`, `incidents`, `supplier_validation`, `disaster_recovery`, `email_ingest`. SEL-411 (done) removed the dashboard dead ends that pointed at some of these.
- Experimental, 404 in production: `scraping`, `discovery`, `sources`, `sandbox`, `sensitech`, `audit` (mock), `sop`, `export` (legacy), `qr_decoder`, `label_vision`, `exchange`, `recall_simulations`, `graph`, `nlp`, `agent_org`.

### 4.3 Frontend surfaces (`frontend/src/app/`)

- Public: home, trust, pricing, integrations, docs, blog, compare, case-studies, verify (public bundle verifier), free tools under `/tools` with optional email lead capture (`frontend/src/components/tools/EmailGate.tsx` always renders the tool for unverified visitors and shows an optional "Save your results" card under it; verification routes in `services/admin/app/tool_verification_routes.py`): `FREE_TOOLS` has 13 entries (`frontend/src/lib/fsma-tools-data.ts`), the landing `TOOLS` list has 6 (`frontend/src/app/tools/components/ToolsLandingClient.tsx`), and there are 24 tool pages not counting the landing page (`frontend/src/app/tools/*/page.tsx`).
- Signed in: dashboard (suppliers with data quality and gap time to fix views, export jobs, recall report, receiving, scan, team, settings), records, rules, exceptions, requests, trace, api-keys, developer portal, remediation, supplier-compliance. SEL-409 (session auth on records, rules, exceptions, requests) was fixed in PR 3476 with a regression test in PR 3620.
- Copy controls: `scripts/check_trust_safety_copy.py` in frontend CI; copy gate workflow `.github/workflows/copy-gate.yml` with `frontend/src/lib/capabilities.ts` (PR 3549, on main). Registry today: live = CSV upload, JSON events API; preview = EPCIS intake, EPCIS export; off = EDI, SFTP.
- Trust page states no SOC 2, no third-party pentest, no FDA endorsement, no availability commitment (`frontend/src/app/trust/page.tsx:100`).

### 4.4 Guarantees the product rests on

Tenant isolation through authenticated principal state and Postgres RLS (least-privilege roles since 2026-07, `README.md` "Security And Tenant Boundaries"); schema validation before persistence; hash-chained audit and export evidence; FDA export derived only from stored tenant evidence (`PRODUCTION_SURFACE.md` "Required Guarantees"). Verified beyond that list: audit logs, the hash chain, CTE events, ingestion run receipts and correction patches carry append-only triggers (migrations v066, v078, v079, v095); rule failures on accepted events are recorded durably in the exception queue (`services/ingestion/app/webhook_router_v2/rules_eval.py`); the traceability lot code travels from the event into every export query and the `/trace/{tlc}` route (`services/ingestion/app/fda_export/queries.py`). The full KDE map, including source location and reference-document keys, travels as JSON with each exported event (`kdes` in both export readers in `queries.py`); whether the sortable spreadsheet writer maps those keys into named columns: not verified.

## 5. What is in flight

Current focus as of 2026-10-27 PT, in order: SEL-474 (end to end with real data), SEL-409, SEL-410 and SEL-414 (signed-in app fixes), SEL-487 (production deploy), and SEL-534 (passing as of about 8:52 PM PT).

Linear issues under SEL-361 in a started state on 2026-10-27 (In Review = code exists, awaiting merge or verification; In Progress = being worked):

| Issue | State | What |
| --- | --- | --- |
| SEL-474 | Current focus | End to end with real data: one real feed through ingest, preflight, validation and a verified export (R1) |
| SEL-487 | Current focus | Production deploy (R6) |
| SEL-534 | Passing | Passing as of about 8:52 PM PT on 2026-10-27 |
| SEL-409 | In Review | Owner sees "Invalid or missing API key" on records, rules, exceptions, requests (fix merged) |
| SEL-412 | In Review | Navigation: no trace view, no on-demand FDA export |
| SEL-410, SEL-414 | In Review | Error states without retry; dashboard placeholder cards and skeletons |
| SEL-406, SEL-407 | In Review | Public pages name EPCIS, EDI, SFTP as live; dashes on 40 of 65 pages |
| SEL-419 | In Review | Developer portal does not say the JSON events API is live or show keys |
| SEL-335 | In Review | Inflow Lab shared demo: contract pin drift recurrence |
| SEL-447 | In Progress | Remove remaining invented sample and demo data |
| SEL-452 | In Progress | Copy gate with capabilities registry (merged as PR 3549; issue not closed) |
| SEL-453 | In Progress | Playwright crawler with visual regression |
| SEL-454, SEL-476, SEL-465 | In Progress | Reliable previews and head-pinned checks; red preview and SHA guard fixes; workflow contract inventory |
| SEL-420 | In Progress | Local tests fail on Node 26 |
| SEL-472 | In Progress | Merge drive across 51 repos (agent operations, not product work) |

## 6. What is next for a first paying customer

### P0, the pilot cannot run without these

| Requirement | Acceptance criteria | Owner |
| --- | --- | --- |
| R1. One real feed through the loop (SEL-474) | Given a design partner CSV or JSON feed, when it is run through Inflow Workbench, then a readiness score, at least one fix item and a commit-gate decision are recorded with run ID; at least one fix item is closed and the re-run shows the readiness or commit outcome change; a no-verdict outcome is reported distinctly from a rule failure, with its reason; and a sortable FDA spreadsheet (the 24-hour records-request format in `docs/specs/FSMA_204_MVP_SPEC.md`) is produced from the committed records through `/api/v1/fda/export` within 24 hours of the request, preserves each traceability lot code with its source location and reference-document KDEs, and verifies with `/export/verify` or the public verifier; every validation failure on the feed is recorded in `fsma.exception_cases` as evidence whether or not the event was accepted | founder session, product |
| R2. Signed-in app truthful and working | SEL-409 verified on staging by the owner account; SEL-412 trace view and on-demand export reachable from navigation; SEL-450 EDI, SFTP and unlabeled EPCIS no longer shown as live; SEL-447 no invented data on any surface the partner sees | product, frontend |
| R3. Home page states the problem and offers a free check | Per the 2026-10-27 plan note: hook, two-sentence problem, free-check CTA first, both copy lints green, SEL-447 and SEL-406 fixed on the page; decisions D1 to D3 answered | founder, separate session |
| R4. Promote supplier remediation to production (decided 2026-10-27, SEL-593) | `remediation` enters `PRODUCTION_ENABLED_ROUTERS` only after the full Promotion Rule in `PRODUCTION_SURFACE.md`: route-security manifest; two-tenant isolation tests; contract tests that reject a malformed manifest and invalid corrections; token failure-mode tests (single-use race, expiry, replay, rate limits); and an export check proving a corrected record reaches the FDA export with its traceability lot code and source link intact. The Railway `ENABLED_ROUTERS` variable changes in the same release, staging first; correction links stay hidden until the production deploy is verified. Blocked by SEL-446 test restoration | backend |
| R5. Pilot paper | Pilot agreement and DPA (`docs/DATA_PROCESSING_AGREEMENT.md` template) ready to send; price or free-pilot terms chosen; Stripe prices set in production or invoicing done by hand (price env state: not verified) | founder |
| R6. Production deploy (SEL-487) | The current main is deployed to production; `/health` returns 200 and `GET /readiness` returns HTTP 200 with `status: "ready"` on the production domain. `degraded` fails R6: it means a check reported `error` (worker, scheduler thread, rate limiter on memory storage, Redis, or Neo4j when graph is enabled). The `not_probed` and `disabled` statuses never degrade and are acceptable | DevOps, backend |
| R7. Remove EDI from the production allowlist before the first pilot ingest (SEL-592) | `/api/v1/ingest/edi` is authenticated but persists FSMA shipping CTE events through the shared ingest path while the registry marks EDI off (`services/ingestion/app/edi_ingestion/routes.py`); drop `edi` from `PRODUCTION_ENABLED_ROUTERS` and the Railway `ENABLED_ROUTERS` variable in one release so no unadvertised input path can write evidence during the pilot | backend |

### P1, fast follows during the pilot

- EPCIS from preview to live: conformance checklist SEL-439, identifier validation SEL-429, then move the registry entry.
- Per-supplier gap time to fix in the evidence packet (data exists since PR 3572; packet template in `sales/`).
- "Check without saving" dry run on write flows (SEL-455); signed review audit trail (SEL-463).

### P2, design for, do not build

GS1 roadmap items parked under SEL-443 (labels, GDSN, Digital Link, PTI); email ingest promotion; graph and NLP promotion; any second regulatory vertical.

## 7. Non-goals for this PRD window

- EDI and SFTP intake. Registry says off; SEL-443 records the decision. Reason: no prospect has asked and the claim was removed from copy.
- SOC 2, penetration test, uptime commitments. Reason: pre-revenue; the trust page already says so.
- Label printing, RFID, GS1 Data Hub, other industries' GS1 standards. Reason: RegEngine reads codes, it does not print them (SEL-443).
- Agent orchestration tooling (SEL-472, SEL-459). Reason: not customer-facing product work; it does not belong in the product initiative.
- A patent filing. Reason: not a prerequisite for a first customer (plan note, Jev p(yes) 0.08).

## 8. Success metrics

Leading, measured per session from the Workbench and the outreach tracker (`docs/product/DESIGN_PARTNER_PROOF_CHECKLIST.md` metric table):

| Metric | Target by 2026-11-26, 30 days after the Q1 decision |
| --- | --- |
| Guided sessions completed | 3, one per design partner |
| Real or production-like feeds through Workbench | 1 per partner |
| Readiness delta on a repeated feed | positive on at least 1 feed |
| Commit-gate blocks on messy feeds | at least 1 per messy feed, with a readable reason |
| Export packages verified | 1 per partner that reaches commit |
| Time to first preflight | under 30 minutes from session start |

Lagging, the initiative's done condition:

| Metric | Target |
| --- | --- |
| Signed paid pilot | 1, by 2027-01-31 |
| First dollar of revenue | a paid Stripe checkout or a paid invoice from that pilot |
| Second session rate | 2 of 3 partners return within 30 days |
| Permission to use anonymized findings | 1 partner in writing |

## 9. Decisions on the six questions carried from the May remediation PRD

Christopher accepted all six recommended defaults on 2026-10-27, so each row below is the decision of record. Jev (TypeSafe, jev-1.14.0, 2026-10-27) was asked the same questions; its answer is shown with confidence. The Q1 target dates and all Jev confidence figures are planning inputs, not verified facts.

| # | Question | Decision (2026-10-27) | Jev |
| --- | --- | --- | --- |
| Q1 | Pilot date and minimum acceptance bar | Two sessions. The first guided session is preflight-only (Q4): Workbench runs, no production ingest, and `POST /commit-gate` returns `export_eligible=False` in preflight mode. The acceptance session comes after the `cte_only` switch: one real supplier feed preflighted, one fix item closed, one export package verified from committed records, inside one 60-minute session. Planning target dates (not verified): first guided session by 2026-11-30, paid pilot signed by 2027-01-31 | one_feed_loop, confidence 1.00 (planning input) |
| Q2 | Is `fsma.traceability_events` the committed canonical contract for all new FSMA evidence? | Yes for writes: new FSMA evidence goes only to `fsma.traceability_events`; the canonical API already reads it and v125 added event-level verdict columns. `fsma.cte_events` and `fsma.critical_tracking_events` become read-only retention (no new writers, columns or indexes), not frozen reads: the v1 FDA export and recall readers still default to `fsma.cte_events` behind `FDA_EXPORT_V1_READ_CANONICAL` (default off, `services/ingestion/app/fda_export/queries.py`), so each export, recall, trace and verification reader is cut over only after its historical-row and canonical coverage is documented. Record this in `docs/engineering/SCHEMA_CHANGE_POLICY.md` (SEL-589) | yes, p 0.75 |
| Q3 | Which dependencies gate `/readiness` per deploy mode? | Keep the code as it is: Postgres fails readiness everywhere; Redis fails it in strict deployed runtimes because authenticated ingest already fails closed without Redis; Neo4j is probed only when graph is enabled; object storage and Stripe never gate readiness | postgres_only 0.67, postgres_redis 0.31. I disagree with Jev: a Redis-less instance would pass readiness and then 503 every ingest |
| Q4 | Rule enforcement default for pilot tenants | `off` during the first session does not protect production ingest: `should_reject()` in `services/shared/rules/enforcement.py` accepts everything when the mode is OFF, and the Workbench commit gate (`services/ingestion/app/inflow_workbench.py` POST `/commit-gate`) only returns a decision and is not checked by direct ingest. Keep the first session preflight-only (Workbench runs, no production JSON/CSV ingest), then switch to `cte_only` before the pilot's first export, after the runbook gate 1.2 passes. The switch is process-wide, so with one tenant this is the tenant's setting | cte_only 0.41, off 0.40 (confidence 0.11, a coin flip; planning input) |
| Q5 | Who owns compliance signoff for the 7 CTE/KDE maps? | Founder signs now against the rule text using `docs/specs/FSMA_204_MVP_SPEC.md` CTE and KDE sections; the first design partner's QA lead co-signs during the pilot. No consultant spend before revenue. Location of the seven map files: not verified in this pass | partner_qa 0.42, founder 0.20 |
| Q6 | Which public claims stay hidden until verified? | Everything the registry does not mark live: EPCIS stays "preview", EDI and SFTP hidden, recall drill hidden (endpoint returns no data), alerts and heartbeat hidden, supplier correction links hidden until R4 resolves, "pre-revenue" out of the hero and metadata (plan note D1). Remove `edi` from the production allowlist before the first pilot ingest (R7, SEL-592) | remove EDI router: yes, p 0.85 |

Follow-on actions these decisions create, filed as Linear stories on 2026-10-27:

- Q1: initiative I-1 target date set to 2027-01-31; first guided session due 2026-11-30.
- Q2: SEL-589, add the read-freeze on `fsma.cte_events` and `fsma.critical_tracking_events` to `docs/engineering/SCHEMA_CHANGE_POLICY.md` (E3, no feature parent).
- Q4: SEL-590, flip `RULES_ENGINE_ENFORCE` to `cte_only` before the pilot's first export, after runbook gate 1.2 passes (E1, under F4).
- Q5: SEL-591, locate the seven CTE/KDE map files and record the founder signoff against them (E3, no feature parent).
- Q6: SEL-592, PR removing `edi` from `PRODUCTION_ENABLED_ROUTERS` with the manifest, tests and the Railway `ENABLED_ROUTERS` variable changed in the same release (E1, under F1). Q3 needs no code change.

## Appendix A. Proposed Linear structure

Approved by Christopher and applied in Linear in one pass on 2026-10-27 (evening PT). Created: initiative I-1 First paying customer; projects P-SEL-5 Ingest and preflight, P-SEL-6 Supplier remediation, P-SEL-7 Evidence and export, P-SEL-8 Public site and lead capture, P-SEL-9 Production stability; feature parents SEL-570 to SEL-584 (F1 to F15 in order). All 62 issues in Appendix B were re-parented; SEL-472 and SEL-459 moved to project Other; SEL-361 moved into P-SEL-9 and left open; SEL-421 closed as Done, SEL-452 set to In Review, SEL-458 reworded. The initiative target date was set to 2027-01-31 when Q1 was decided later the same evening.

- Initiative: **First paying customer**. Target date: 2027-01-31 (Q1). Done when the lagging metrics in section 8 are met.
- Projects as epics (five), features as parent issues, stories as sub-issues. Existing SEL-361 becomes the Production stability project; its goal text moves to the project description.

| Epic (project) | Scope | Features (new parent issues) |
| --- | --- | --- |
| E1 Ingest and preflight | CSV, JSON events API, EPCIS, Inflow Workbench, rules and readiness, developer portal, GS1 backlog | F1 Intake paths match the registry; F2 EPCIS preview to live; F3 GS1 roadmap, parked; F4 Preflight safety |
| E2 Supplier remediation | Supplier data quality, gap time to fix, facilities, correction links and token sessions | F5 Supplier data quality and time to fix; F6 Correction links in production (R4) |
| E3 Evidence and export | Canonical records, FDA export, trace view, hash chain, public verifier, exception queue, review trail | F7 Trace and on-demand export in the app; F8 Review audit trail |
| E4 Public site and lead capture | Home, trust, pricing, integrations, copy gate, real-data rule on every surface a prospect sees, free tools | F9 Copy gate and registry; F10 Real data only; F11 Home page (R3, new) |
| E5 Production stability (SEL-361) | CI, previews, auth, error states, dashboards, accessibility, QA walks, Inflow Lab demo | F12 Signed-in app works for the owner; F13 CI and previews; F14 Observability and data ownership; F15 Inflow Lab shared demo |
| Outside the initiative | Agent operations items; proposed home: project Other (P-SEL-4) | none |

Status drift fixed during the move: SEL-421 closed as Done (shipped in PRs 3492 and 3615); SEL-452 set to In Review (PR 3549 merged); SEL-458 reworded to a per-PR branch of production-shaped data, since production runs on Railway Postgres and Supabase is auxiliary. SEL-458 stays open in Backlog with that wording; cancelling it is a later call if the cost is not worth it before the first paid pilot.

## Appendix B. Mapping of the 62 issues under SEL-361

Project P-SEL-2 also holds six closed issues with no parent (SEL-269, 270, 271, 317, 322, 350); they stay where they are. Closed items move with their feature so the project history stays whole.

Found during the apply pass and resolved on Christopher's second approval the same evening: 23 further children of SEL-361 sat outside project P-SEL-2. The 19 approval-queue items in project Waiting on C.Lee (for example SEL-474, SEL-249, SEL-251) stay in that project with SEL-361 removed as parent. Four engineering items moved: SEL-236 supplier portal to tenant_suppliers link (E2, F5); SEL-323 Vercel contact webhook and Sentry DSN missing (E5, F14); SEL-315 Vercel env drift and stale previews (E5, F13); SEL-15 FSMA 204 compliance sweep of 2026-04-21 (E3, no feature parent; candidate to close as superseded by this PRD). SEL-361 now has no children.

| Issue | State | Epic | Feature |
| --- | --- | --- | --- |
| SEL-419 | In Review | E1 | F1 |
| SEL-450 | Todo | E1 | F1 |
| SEL-417 | Backlog | E1 | F1 |
| SEL-439 | Backlog | E1 | F2 |
| SEL-429 | Backlog | E1 | F2 |
| SEL-443 | Backlog | E1 | F3 (decision record, stays open) |
| SEL-448 | Backlog | E1 | F3 |
| SEL-424 | Backlog | E1 | F3 |
| SEL-426 | Canceled | E1 | F3 (child of SEL-424) |
| SEL-428 | Backlog | E1 | F3 |
| SEL-445 | Backlog | E1 | F3 (child of SEL-428; printing is out per SEL-443, propose cancel) |
| SEL-444 | Canceled | E1 | F3 (child of SEL-428) |
| SEL-441 | Backlog | E1 | F3 |
| SEL-442 | Backlog | E1 | F3 |
| SEL-438 | Backlog | E1 | F3 |
| SEL-437 | Backlog | E1 | F3 |
| SEL-432 | Backlog | E1 | F3 |
| SEL-427 | Backlog | E1 | F3 |
| SEL-430 | Backlog | E1 | F3 |
| SEL-440 | Canceled | E1 | F3 |
| SEL-436 | Canceled | E1 | F3 |
| SEL-435 | Canceled | E1 | F3 |
| SEL-434 | Canceled | E1 | F3 |
| SEL-433 | Canceled | E1 | F3 |
| SEL-431 | Canceled | E1 | F3 |
| SEL-425 | Canceled | E1 | F3 |
| SEL-423 | Duplicate | E1 | F3 |
| SEL-455 | Backlog | E1 | F4 |
| SEL-457 | Backlog | E1 | F4 |
| SEL-415 | Done | E2 | F5 |
| SEL-421 | Done (closed in the apply pass) | E2 | F5 |
| SEL-446 | Backlog | E2 | F6 |
| SEL-412 | In Review | E3 | F7 |
| SEL-463 | Backlog | E3 | F8 |
| SEL-452 | In Review (set in the apply pass) | E4 | F9 |
| SEL-451 | Duplicate | E4 | F9 |
| SEL-406 | In Review | E4 | F9 |
| SEL-407 | In Review | E4 | F9 |
| SEL-447 | In Progress | E4 | F10 (Jev leaned E5 at 0.45; kept with the claims work) |
| SEL-422 | Backlog | E4 | F10 |
| SEL-409 | In Review | E5 | F12 |
| SEL-410 | In Review | E5 | F12 |
| SEL-414 | In Review | E5 | F12 |
| SEL-413 | Backlog | E5 | F12 |
| SEL-416 | Backlog | E5 | F12 |
| SEL-418 | Backlog | E5 | F12 |
| SEL-408 | Backlog | E5 | F12 |
| SEL-411 | Done | E5 | F12 |
| SEL-462 | Backlog | E5 | F12 |
| SEL-476 | In Progress | E5 | F13 |
| SEL-465 | In Progress | E5 | F13 |
| SEL-464 | Backlog | E5 | F13 |
| SEL-454 | In Progress | E5 | F13 |
| SEL-456 | Duplicate | E5 | F13 |
| SEL-453 | In Progress | E5 | F13 |
| SEL-420 | In Progress | E5 | F13 |
| SEL-458 | Backlog (reworded in the apply pass) | E5 | F13 |
| SEL-461 | Backlog | E5 | F14 |
| SEL-460 | Backlog | E5 | F14 |
| SEL-335 | In Review | E5 | F15 |
| SEL-472 | In Progress | Outside | move to project Other |
| SEL-459 | Backlog | Outside | move to project Other |
