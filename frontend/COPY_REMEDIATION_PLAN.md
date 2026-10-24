# Copy Remediation Plan

> Date: 2026-08-02. Executes every item in [COPY_AUDIT.md](COPY_AUDIT.md).
> Facts below were verified against the backend, the repo, and the FDA/Federal
> Register on 2026-08-02 — plan items cite them instead of guessing.

## Verified facts (use these, not the old copy)

| Question | Answer | Evidence |
|---|---|---|
| Rule count | **36 rules = 33 stateless + 3 cross-event** (sandbox adds 4 demo rules → 40) | `services/shared/rules/seeds.py` (`FSMA_RULE_SEEDS`); `tests/test_rules_engine.py:263` asserts 36 |
| Canonical copy | "36 FSMA 204 validation rules (33 stateless + 3 cross-event)" | — |
| Tenant DB | **Railway Postgres**. Supabase = developer-portal auth/keys, pre-sales lead capture, legacy session validation only | `runbooks/supabase-anon-lead-capture-lockdown.sql:1-4`; `docs/engineering/AI_ENGINEERING_STANDARDS.md:44` |
| FDA posture (as of 2026-08-02) | Congress (Continuing Appropriations Act of 2026, Nov 2025) directed FDA not to enforce before **July 20, 2028**; FDA states it will comply. The Aug 2025 compliance-date-extension rule is **still only proposed** — don't say the date "was extended" as settled fact. Requirements unchanged; Feb 2026 Q&A guidance + cottage-cheese exemption finalized Feb 20, 2026 | fda.gov FSMA 204 rule page; federalregister.gov 2025-14967, 2026-03362 |
| Canonical framing sentence | "FDA has been directed by Congress not to enforce the Food Traceability Rule before July 20, 2028, and has stated it intends to comply — the requirements are unchanged, only enforcement moved." | — |
| Calendly | **Live** (200, real booking page) — no fix needed | fetched 2026-08-02 |
| IR procedure | **Exists** — `docs/operations/INCIDENT_RESPONSE.md` (current, matches prod topology). DPA claim is literally true. But 4 IR docs exist and disagree (two reference fictional roles / retired k8s) | see PR-6 |
| Secret rotation | Policy on paper (90-day in `docs/internal/SECRETS.md`), but zero evidence of recurring execution; March 2026 closeout checklist all unchecked | needs D9 |
| accept-invite backend | **Already passwordless** — `AcceptInviteRequest` = `{token, name}` only; the frontend's password is silently discarded | `services/admin/app/invite_routes.py:396`, `schemas.py:157` |
| API key reality | Prefix `rge_live_<token>.<secret>`; rotation exists in store but revokes old key immediately (no grace) and has no HTTP endpoint; scopes real but vocabulary is `records.read`, `webhooks.ingest`, `fda.export`, etc. (of the six documented scopes only records.read exists); no test env; no key-count limit; default rate limit 60/min per key, no plan tiers; no uptime endpoint | api_key_store.py, authz.py, routes.py |
| Webhooks | Inbound ingestion real (`POST /api/v1/webhooks`, Idempotency-Key **required**, dedupe-replay semantics, 24h Redis TTL + DB unique index). Outbound machinery exists but only emits hallucination-review events; documented event types have no emitters and no subscription API | webhook_router_v2/, webhook_outbox.py |

## Phase 0 — Founder decisions (blocking; answer these first)

Each has a recommended default. Reply "defaults" to accept all, or override per item.

- **D1. Legal entity (blocks PR-6) — RESOLVED per SEL-317.** Entity confirmed:
  RegEngine LLC (California single-member LLC). Terms, DPA, LICENSE, footer,
  READMEs, and the design-partner template now say "RegEngine LLC".
  `pyproject.toml` uses `admin@regengine.io` (wrong domain — still open).
- **D2. Support response promise.** Status page says "first response within
  24 hours"; LeadGate says founder reviews "within 24 hours"; retailer
  assessment promises "&lt; 24hr turnaround"; trust pages say no windows are
  promised. *Default: drop all hour-counts → "typically within one business
  day", and make trust pages the source of truth.*
- **D3. Price presentation.** why-regengine shows $425/$549/$639 as the
  price; pricing shows GA $999/$1299/$1499 with struck partner rates;
  compare pages say "$425–$749/mo". *Default: pricing page's GA-with-
  struck-partner-rate presentation everywhere; kill bare partner prices.*
- **D4. Maturity statement.** "Pre-production" (case-studies) vs production
  plans (pricing). *Default: "in production with founding design partners;
  self-serve in staged rollout" — one sentence, used verbatim site-wide.*
- **D5. `/fsma/market` page.** Sales CRM with named real companies inside
  the user-facing app; "75+" claim over 48 entries. *Default: remove the
  route from the app entirely (keep the data file for internal use).*
- **D6. `/ingest` demo flow.** *Default: keep, but hard-label every surface
  "Simulated walkthrough — sample output", fix the CFR citation, and delete
  the printable "Integrity Status: VERIFIED" report until it renders real
  chain data.*
- **D7. Program name.** *Default: "Founding Design Partner" everywhere.*
- **D8. Org term.** workspace / organization / tenant / account all in use.
  *Default: "workspace" in all UI copy; "tenant" never user-facing.*
- **D9. DPA "rotated regularly".** *Default: soften to "stored in secret
  management systems, never in source control; rotated on schedule and on
  suspicion of exposure" — and actually run the March-2026 rotation
  checklist once so the claim is true.*
- **D10. Developer funnel.** Docs say "free developer account in minutes";
  /developers says request-gated preview. *Default: request-gated is the
  truth today — rewrite docs CTAs to "Request developer access".*

## S1 — Immediate security action (independent of copy)

`docs/operations/CREDENTIAL_ROTATION_RUNBOOK.md` (~lines 61-73) appears to
contain literal old secret values in a tracked file. Verify those secrets
were actually rotated (Railway/Vercel history), then scrub the values from
the doc (and consider whether git history needs another BFG pass). Do this
before anything ships.

## PR batches

Ordered by damage-per-hour. Each PR: branch from fresh main in an isolated
worktree (concurrent-session hazard), run `npm run promise:audit` +
frontend lint/tests before push.

### PR-1 — Ingest fake-flow honesty (~2-3h) [Tier1 #1, Tier2 #7]
- Label the demo override end-to-end: banner on `app/ingest/page.tsx` flow,
  "Simulated — sample output" chips on `NormalizedDocumentViewer` facts and
  confidence scores.
- Fix `§ 1.1330` → `§ 1.1345` (receiving) in `NormalizedDocumentViewer.tsx:29,82-83`
  and the `h-1.1330-a` highlight ids.
- Fix inflation baseline "2011" → "2020" (`NormalizedDocumentViewer.tsx:27`).
- Delete the "Integrity Status: VERIFIED" printable report + "Export Signed
  Report" button (`AnalysisResultClient.tsx:30-59,73,83-86`) — or gate it to
  real chain data if that's <1h.
- "100% unbreakable provenance linking" → "SHA-256 provenance manifests for
  every extraction" (`ingest/page.tsx:408`).
- Fix ingest self-contradictions: supported-formats list vs error help;
  "publicly accessible via URL" vs the File Upload tab (`:654,698-710`).
- Remove SEC-regulations example URL (`:46-49`) — off-vertical remnant.

### PR-2 — Passwordless invite + settings truth (~1-2h) [Tier1 #2]
Backend already accepts `{token, name}` — frontend-only:
- Strip both password fields + validation from
  `accept-invite/AcceptInviteClient.tsx`; stop sending `password`; success
  copy: "We'll email you a sign-in code — no password needed."
- `settings/page.tsx:82,87` → "Passkeys, sign-in codes, and session security".
- `settings/security/page.tsx:110-117` → positive framing; remove the
  no-op "Manage sign-in from login" button.
- Collapse bulk-upload's duplicate "Sign In to Validate" / "Create an
  Account" CTAs into one "Continue with email" (`onboarding/bulk-upload:747-752,938-943`).

### PR-3 — Fabricated-evidence sweep (~1-2h) [Tier1 #3, #5; needs D5]
Pure copy deletions/rewrites, one pass:
- "customer interviews" → "public pricing and vendor documentation"
  (`why-regengine:352`).
- "Why teams switch/use both" → "Why you might choose…" (3 compare pages).
- about.tsx customer-track-record lines (`:210,219-221`) → design-partner
  framing.
- walkthrough "real FDA records request" → "illustrative" (`:121`).
- OG metadata "48-hour speed to compliance" → "first export in days" (`why-regengine:24`).
- proof retailer-names claim (`proof/page.tsx:50`) → unnamed "several major
  buyers — confirm your retailer's onboarding tests"; metadata "three real
  artifacts" → "three verifiable sample artifacts" (`:8`).
- supplier-compliance asserted-buyer badge + "already enforcing" hero/header
  (`:86,95,119`) → signaling/question framing.
- FTL checker "retailers are already requiring traceability NOW"
  (`FTLCheckerClient:1067`) → announced-programs framing.
- `/fsma/market`: execute D5 (default: remove route; delete "75+ companies
  we have identified" and named-company market-share claims from any
  surviving surface).

### PR-4 — Regulatory accuracy (~2-3h) [Tier1 #4, Tier2 #6]
- Sync `components/fsma/readiness-assessment.tsx:42-49` categories to the
  FTL checker's correct list (`FTLCheckerClient.tsx:94-379`); drop
  spices/nuts/RTE-bakery/concentrates/duck-eggs draft-era entries.
- Create ONE exported constant with the canonical FDA framing sentence
  (verified above) + the date, e.g. `src/lib/fsma-enforcement.ts`; replace:
  dashboard "FDA deadline: July 2028" (`dashboard/page.tsx:504`),
  "Compliance Deadline" countdowns (`fsma/assessment:14-18,56-60`,
  `fsma/market:49-50` if page survives), blog deadline phrasing
  (`food-traceability-software:56`). Do NOT claim the compliance date "was
  extended" — the extension rule is still proposed; cite the congressional
  non-enforcement directive.
- Optional (worth it): note the Feb 2026 cottage-cheese exemption in the
  FTL checker's dairy handling.
- Fix non-CTE sample event types: `transport`/`quality_check`
  (`tools/export:14-23,587`), `CREATION` (`DataImportClient:66`) → real CTE
  names; mid-market blog: one sentence distinguishing org-program timeline
  (18-24 mo) from tool onboarding.

### PR-5 — Compliance-verdict language + audit-log integrity (~2-3h) [Tier1 #6, Tier4 actor]
- "FSMA 204 Compliant — meets current FDA requirements" → readiness framing
  (`dashboard/compliance:90-91`).
- Remove "Compliant with 21 CFR Part 11 … SOX" + "Tamper-proof" badge
  (`audit-log:496,233`) → "designed to support Part 11-style record
  controls".
- **Code:** stop injecting synthetic client-side rows into the audit log
  (`audit-log:139-159`) and remove the decorative "Chain Verified" stat, or
  bind it to the real verification endpoint.
- recall-report "ready to respond to a 24-hour FDA records request" (`:457`)
  → drill-results framing.
- bulk-upload "compliance score" → "data completeness" (`:788`).
- **Code:** replace hardcoded `'dashboard_user'` actor with the session
  user's identity in exceptions/requests resolutions
  (`exceptions:256-275`, `requests:255-312`, `requests/[id]:319-336`).
- portal "verified and recorded" → "validated and recorded" (`portal/[portalId]:287`).

### PR-6 — Legal/trust truth batch (~3-4h) [Tier1 #7, #8; Tier2 #3, #12; needs D1, D2, D9]
- Entity unification per D1 across: Terms contact/governing-law block, DPA
  §processor + contact, marketing footer ©, LICENSE, CONTRIBUTING, service
  READMEs, `pyproject.toml` author email (`admin@regengine.io` →
  `regengine.co`).
- DPA solo-founder honesty: personnel/least-privilege (`dpa:96`) →
  founder-operator wording; "rotated regularly" per D9 (`:91`); keep IR
  claim (it's true) but consolidate the four IR docs into
  `docs/operations/INCIDENT_RESPONSE.md` and delete/mark the k8s-legacy and
  fictional-roles versions; SCC "execution package" (`:496-497`) →
  "executed as part of contracting where required".
- Status page 24h promise per D2 (`status:54`); LeadGate + AssessmentForm +
  FounderCredibility hour-counts per D2.
- Privacy TL;DR "never sell" → CCPA-scoped wording (`privacy:189-191`);
  keep 30-day notice only if honored (default: "reasonable advance notice").
- Terms: refund carve-out for termination-for-breach (`TermsClient:112`);
  delete the "(ironic, we know)" joke (`:95`).
- Trust infra truth: `trust/architecture:51` → "PostgreSQL on Railway";
  rewrite Supabase entry in `lib/trust-subprocessors.ts` to the verified
  description (developer-portal auth/keys + lead capture + legacy session
  path; core tenant data on Railway PG); kill "graph database" claim
  (`docs/fsma-204:371`) and message-bus "rolling out" line (`:423`).

### PR-7 — API docs truth pass (~3-4h) [Tier1 #9; Tier2 #9, #10, #11; needs D10]
- One exported `API_BASE` with the real host; replace `your-preview-host`
  in `docs/page.tsx:53`, `developers:60`, `connectors/inflow-lab:23`,
  `portal/codegen:22`.
- Authentication docs (`docs/authentication:68-91`): cut 24h rotation
  grace, `rge_test_`, 5-keys-per-env; document reality — `rge_live_`
  prefix, create/revoke lifecycle, scopes from the real vocabulary
  (`records.read`, `webhooks.ingest`, `fda.export`, …; note `:`/`.`
  equivalence).
- Playground/codegen: remove `uptime_percent: 99.95` + "SLA Dashboard"
  endpoint (the real `/sla/dashboard` is FDA 24-hour records-request
  tracking — rename it there to avoid the collision); regrade `B+` samples
  to gap-indicated shape (also `ApiReferenceClient:284`); fix
  `app.regengine.com` → `regengine.co` (`playground:135`).
- ApiReferenceClient: strip internal ports + pre-pivot services
  (`/checklists`, `/industries`, ingestion-of-documents), remove
  "Growth (500/min), Scale (1,000/min)" tier box (`:617`) — real story:
  per-key limits (default 60/min) with headers, matching
  `docs/rate-limits`; fix `?industry=food?limit=20` (`:577-580`); fix
  `www.regengine.co` badge (`:525`); errors page: drop `/industries` row +
  unverified 50MB limit (`docs/errors:45-46`).
- Idempotency-Key: document the truth (required on `POST /api/v1/webhooks`,
  dedupe-replay with 24h TTL, optional elsewhere) and add the header to
  every webhook-ingest sample (docs home, fsma-204, walkthrough,
  developers, codegen).
- Webhooks story: rename inbound as "Webhook ingestion" everywhere;
  docs-home card + portal checklist/quick-links stop implying live outbound
  events; keep /docs/webhooks "Roadmap" badge as canonical
  (`customer-readiness.ts:292-299` wording aligned).
- Funnel per D10: docs-home "free developer account… Get API Key" →
  "Request developer access" (`docs:485,491`).
- Quickstart timing: pick "5 min" (drop "60 seconds", `docs:99`).
- Cut OKR bullet (`docs/walkthrough:248`) and the "Decision posture" memo
  card (`connectors/inflow-lab:190-193`).
- **File separately (product bug, not copy):** the developer portal mints
  `rge_test_` keys into a Supabase table no backend reads — those keys can
  never authenticate. Either wire portal keys to the real key store or
  label the portal sandbox-only.

### PR-8 — Dead CTAs and dead-ends (~half day) [Tier3]
- `/#sandbox` links (demo:237, compare×3, fsma-204/[cte]:497) → `/ingest`.
  The `/sandbox` route and SharedSandboxResult were deleted in #3557.
- Wire or remove each dead button: kde-checker Print/CSV Template/Explore
  (wire Print to `window.print()`, CSV to a real template file, else
  remove); sop-generator Download PDF/Print; tlc-validator Schedule a Demo
  (→ Calendly, it's live) + Download Standard (wire a real doc or cut the
  gate promise); recall-readiness "Book a Compliance Audit" → "Book a call"
  (no audit service exists); fsma/assessment FTL/Reference buttons (→
  `/tools/ftl-checker`, `/docs/fsma-204`) + "Start Drill" →
  `/tools/drill-simulator`; fsma/integration "Map Your Columns" (→
  `/tools/data-import`) and "Try Web Entry" mislink; identity
  Match/Distinct (wire to handler or remove); roi-calculator "Book a
  20-minute call" → Calendly link.
- Dashboard: "Disable in Settings" sandbox banner → point at `/ingest`
  ("Connect real data to exit sample mode"); scan-history + compliance
  "Ingest Data" CTAs → `/ingest` when Field Capture disabled; remove
  "Coming in v1.1" tooltips and link the real export pages
  (`compliance:604-613`, `audit-log:229`).
- api-console: bind "Live" badge to `/health` or remove (`:180-185`); fix
  "view details and test it" empty-state vs disabled "Try it out" (`:375-409`).
- Homepage "15-min call" vs contact "30 minutes" → pick one (match the
  Calendly event).

### PR-9 — Claim reconciliation to pricing truth (~half day) [Tier2 #1, #2, #4, #5, #8, #13; needs D3, D4, D7]
- Compare pages: self-serve signup / free sandbox / free API rows →
  pricing's "staged rollout" truth; fix `reositrak` key typo; drop
  Walmart/Kroger trademark footnote or the claim it annotates.
- why-regengine: "Free API access across all plans" → contracted-workspace
  truth; "Month-to-month… cancel anytime" + "Volume discounts for 10+
  facilities" → delete (no such terms); price block per D3; scale
  "1 to 1000" vs "1 to 10,000" → pick one; "Sign up in minutes" → D10
  framing; Trustwell-vs-foodlogiq key mismatch in the comparison data.
- retailer-readiness: PricingSection "month-to-month" + "based on company
  size" (field literally holds facility counts) → facility-based framing;
  IntegrationsGrid → "Data in via API, CSV, webhook — ERP integrations
  scoped per engagement" (drop the SAP/NetSuite/QuickBooks/Shopify logo
  implication); reconsider TraceLink (pharma vendor) in the competitor set.
- Rule count → "36 FSMA 204 validation rules (33 stateless + 3
  cross-event)" in walkthrough:41, demo:233, compare/foodlogiq:15,
  tracegains:29, developers:33, rules/page.tsx:180 ("Seed Rules" copy too).
- CTE count → 7 with First Land-Based Receiving added:
  supplier-compliance:196, docs/fsma-204 guide table (:279-284).
- case-studies "pre-production" (`:658`) per D4; program name per D7
  (pricing, why-regengine:137, walkthrough:267).
- "Get compliant in minutes" (`supplier-compliance:90-91` + metadata) →
  "Start submitting traceability data in minutes".

### PR-10 — Terminology + polish sweep (~1 day) [Tier4 + Tier3 #4 quick part]
- D8 sweep: "tenant" → "workspace" in all UI strings (`settings/users:224,125`,
  `dashboard/layout:494`, etc.); one name for `/dashboard/export-jobs`
  ("FDA Export") across nav/h1/hub/quick-action; recall + issues naming
  unified; import verb "Import" with `/ingest` as the canonical entry;
  sentence-case button convention; passkey button label unified.
- TLC labels: "Locations Tracked" → "Lot codes tracked" (`suppliers:399,820`).
- Error-quality pass: replace raw `API error: ${status}` renders
  (team:163, products:271, audit-log:291, heartbeat:501,
  system-health-widget:48-51) with friendly retry copy; fix alerts
  fetch-failure alarm copy (`alerts:194`); render ack failures
  (`alerts:117-129`); add error UI to products mutations.
- Jargon: Merkle/hash-chain wording off About/footer/retailer-readiness
  (keep on /proof and /docs); "The pilot headline metric"
  (`remediation:150`); `.env` + openssl instructions out of SaaS admin UI
  (`admin:195-208`, keep for self-host docs); "High Risk Domains" label
  (`ingest/curation:297-303`); "Physics Engine Halted"
  (`KnowledgeGraphErrorBoundary:44`); controls "Frameworks" list naming
  (`controls:170-173`).
- Tools: cold-chain "Monitor/Detector" → "Simulator" (title, gate, landing
  card); TLC validator heuristics — fix `[0OI1l]` false positives and the
  `startsWith('10')` GS1 guess (`TLCValidatorClient:46,67`); "fsma-unified"
  metadata "benchmark readiness" → delete (`page.tsx:11`); ask-tool panel
  → "Endpoints this query would call".
- Small fixes: "systematicallly" (`RecallReadinessClient:86`); "2
  categoryies" pluralization (`FTLCheckerClient:1066`); broken
  `*-muted0/…` Tailwind classes (trust, dpa, walkthrough — grep
  `muted0`); exit-intent "No thanks, I'll risk it" → neutral dismiss;
  "$5M–$50M ARR" → "annual revenue" (`why-regengine:619`); blog index — add
  the 2 orphaned posts (`blog/page.tsx:15-72`); icon mismatches
  (Mail-for-address, Calendar-for-email); native `confirm()` dialogs →
  design-system modal (`controls:83`, `admin:89`); founder title unified
  ("Founder" — pick one, about:124 vs FounderCredibility:37);
  onboarding "add facilities in Settings" → "under Suppliers"
  (`onboarding/setup/facility:146`).

### PR-11 — Duplicate-surface consolidation (~1-2 days; schedule after the copy waves) [Tier3 #4]
Bigger UX refactor, separate from copy:
- Merge `/settings` hub into `/dashboard/settings` (one hub; fix all
  back-links that currently cross between them).
- Delete the disabled `/settings/notifications` mock; route to the live
  `/dashboard/notifications`.
- Pick one team page (`/settings/users` — API-driven) and retire
  `/dashboard/team`'s hardcoded roles; align role vocabulary.
- Reconcile api-keys stories (`/api-keys` page vs dashboard "no
  tenant-visible credentials" tab) — one story per D10.

### PR-12 — Regression-proofing (~1h; ship LAST, after PR-1..10 merge — its banned strings would flag the unfixed pages until then)
Extend `scripts/promise-audit.mjs` banned strings (keep the list small and
high-signal per its own guidance):
`your-preview-host`, `customer interviews`, `Why teams switch`,
`FSMA 204 Compliant`, `Tamper-proof`, `tamper-proof`, `Create Password`,
`/#sandbox`, `we have identified`, `uptime_percent`, `rge_test_` (docs
only), `Coming in v1.1`, `§ 1.1330` (scoped to ingest viewer), `dashboard_user`.
Re-run in CI (already
wired). Note in PROMISE_AUDIT.md that COPY_AUDIT.md is the judgment-level
companion.

## Suggested execution order

| Session | Work | Outcome |
|---|---|---|
| 1 (today) | Phase 0 answers + S1 + PR-3 + PR-12 | Worst falsifiables gone, regression net up |
| 2 | PR-1 + PR-2 | Fake-evidence flow honest; invite funnel works |
| 3 | PR-4 + PR-5 | Regulatory + compliance-verdict accuracy |
| 4 | PR-6 (after D1) + PR-7 | Legal/trust + docs match reality |
| 5 | PR-8 + PR-9 | No dead promises; one capability story |
| 6+ | PR-10, then PR-11 | Polish, then consolidation |

Every PR: isolated worktree off fresh main, `npm run promise:audit`,
lint + unit tests, then normal deploy flow. Items needing backend edits
(PR-5 actor identity, PR-7 SLA-endpoint rename) run backend tests too
(`pytest -x`, skip tests/data_integrity locally).

## Coverage check

Every COPY_AUDIT.md item maps to exactly one PR above: Tier 1 #1→PR-1,
#2→PR-2, #3→PR-3, #4→PR-4, #5→PR-3(D5), #6→PR-5, #7→PR-6, #8→PR-6(D1),
#9→PR-7. Tier 2 #1→PR-9, #2→PR-9(D3), #3→PR-6(D2), #4→PR-9, #5→PR-9+PR-7,
#6→PR-4, #7→PR-1, #8→PR-9(D4), #9→PR-7, #10→PR-7, #11→PR-7(D10), #12→PR-6,
#13→PR-8/PR-9. Tier 3 #1-3→PR-8, #4→PR-10(quick)+PR-11(full), #5→verified
live / PR-7 domain fix. Tier 4 → PR-5 (actor), PR-7 (docs bits), PR-10
(everything else). Founder-verification list → resolved facts table + D1,
D9, S1.
