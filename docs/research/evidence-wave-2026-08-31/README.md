# RegEngine evidence wave — 2026-08-31

Scope: a bounded research and engineering cycle for RegEngine's FSMA traceability
spine. Experimental analysis, not a production-readiness certification or a change
to the canonical product contract. The initial request was a continuation; the
user subsequently supplied `Operation_Deep_Market_Lab_Master_Prompt.docx` and
explicitly requested applying it to this repository. The complete document was
read and incorporated without modifying the attachment.

Baseline: `41aa11c5`, branch `codex/evidence-wave-20260831`. The wave was created
in an isolated worktree. Its application changes were subsequently reconciled in
a later integration pass, so this report preserves baseline observations and
labels post-integration reruns separately. No deployment, purchase, customer
contact, credential access, database mutation, or recurring automation is
authorized by this report or was needed for this wave.

## Decision frame and organization

- First principle: an operator must turn actual supplier records into complete,
  tenant-scoped, accurately described evidence at a sustainable cost.
- Non-negotiables: tenant authority, provenance, truthful claims, reproducible
  observations, and preservation of existing work.
- Drop the assumptions that agent consensus proves demand, a hash proves source
  truth, a green subset proves completeness, or a subscription pays for any volume.
- Smallest useful path: reproduce a pilot-blocking defect, fix its owner, measure
  synthetic economics, and specify the real-data experiment internal reasoning
  cannot replace.
- Escalation signal: fixing a finding requires a billing decision, schema migration,
  production access, or a new trust/authentication contract. Record that decision
  explicitly; do not silently change it during research.

The executive council is a decision function, not new application infrastructure:
root integrates evidence; economics tests viability; security challenges trust;
QA replicates; market checks external evidence; independent judgment challenges
the thesis. Six bounded lanes use the existing planner, implementer, and
security_review roles. No middle-management agents or legacy swarm runtime were
needed. Frontend implementation and public-claim review are separate from QA.

The master prompt's ten council responsibilities are assigned rather than turned
into ten idle managers: root owns Research Director and Synthesis; backend owns
Engineering; model_review owns Mathematics; economics owns Economics; market owns
Market; independent unknowns owns Product and Design; QA owns Experimental;
security owns Adversarial. Distribution and design comparisons were added when
the complete prompt arrived. Independent replication found actual errors and
triggered repairs, not just additional agreement.

## Current-state map

| Surface | Current checked-in evidence | Limit of the observation |
| --- | --- | --- |
| Runtime | [server/main.py](../../../server/main.py) mounts webhook, CSV, Inflow, proof and FDA routers; most are conditional on router flags. | Deployment and enabled flags were not inspected. |
| Intake | [csv_templates.py](../../../services/ingestion/app/csv_templates.py) normalizes CSV into webhook ingest events; [webhook_router_v2 routes](../../../services/ingestion/app/webhook_router_v2/routes.py) handle persistence/rule evaluation. | Not a real supplier ingestion observation. |
| Validation | [enforcement.py](../../../services/shared/rules/enforcement.py) has off/cte_only/all modes and a manifest of participating routes. | The default is off; no-verdict is not rejection. Universal blocking cannot be inferred. |
| Evidence store | [canonical ownership](../../../CANONICAL_OWNERSHIP.md) names traceability_events; [legacy persistence](../../../services/shared/cte_persistence/core.py) explicitly documents surviving dual-write callers and divergent idempotency keys. | Canonical-to-export reconciliation remains an experiment, not a proved invariant. |
| Exports | [FDA router](../../../services/ingestion/app/fda_export/router.py), [public verifier](../../../frontend/public/sdk/verify_chain.py), and synthetic downloadable bundles. | Consistency, provenance, completeness, legal sufficiency and source accuracy are different claims. |
| Operator loop | [first-pilot playbook](../../runbooks/first_pilot_session.md) and [OKR](../../decisions/2026-05-13-okr.md) target observed pilot ingestion. | An old target or playbook is not evidence the session happened. |
| Demand | [GTM draft](../fsma-204-go-to-market-2026-05.md), [pilot tracker](../pilot-outreach-tracker.csv), [pricing draft](../../decisions/2026-05-13-pilot-pricing.md). | Do not convert personas, composite quotations or a prospect list into customer evidence. |
| Prior work | Earlier task “Design quantum management system” completed an isolated gate patch and reported 244 focused tests. | Different base and unintegrated patch; those passes are not counted as this wave's tests. |

`CURRENT_SYSTEM_MAP.md`, requested by AGENTS, is absent at root. Its
[archived copy](../../_archive/CURRENT_SYSTEM_MAP.md) explicitly disclaims current
authority. README and current code took precedence. The MVP spec marks much of its
graph/Kafka material legacy. No archived implementation was copied into this work.

## Uncertainty and assumption ledger

Priority is decision impact divided by effort, expressed ordinally because actual
probabilities and dollar information values are unknown. U01–U17 are independent
questions, not seventeen mandates to build features.

| ID | Assumption to test | Why it changes the decision | Cheapest falsifier / owner |
| --- | --- | --- | --- |
| U01 | A buyer will pay for this workflow now. | Determines whether more product investment is justified. | Priced offer to a qualified budget owner; market. |
| U02 | A real supplier file can complete intake through export. | A demo can conceal the primary adoption blocker. | One observed sanitized file exercise; frontend + QA. |
| U03 | Export verification detects the relevant forms of alteration. | Determines what can safely be promised to an auditor. | Modify content, chain, and manifest independently; security + QA. |
| U04 | Green readiness represents all expected records. | Missing records can produce a misleadingly clean subset. | Reconcile source counts/lots against accepted, rejected, and exported records; QA. |
| U05 | Every relevant path enforces the intended commit policy. | Product prose currently implies more than route-specific policy proves. | Negative matrix by route and enforcement mode; security. |
| U06 | Dual-write and export queries agree. | A accepted record may not be represented consistently downstream. | Transaction-level failure/retry/reconciliation exercise in disposable PostgreSQL; backend. |
| U07 | The offer, checkout and entitlement are one contract. | Paid onboarding risks wrong expectations or rejected purchases. | Trace each advertised plan through both billing surfaces; economics. |
| U08 | Extra accepted events have nonnegative marginal contribution. | Unlimited usage can turn growth into cash loss. | Cost sensitivity including remediation and retention; economics. |
| U09 | Remediation effort is sufficiently low. | Founder/operator time may dominate compute. | Time a real file with zero mid-session rescue; product. |
| U10 | Volume limits preserve completeness and offer fit. | Batch/export thresholds change the workflow abruptly. | Boundary tests at 500/501 and 10,000/10,001; QA. |
| U11 | Realized price supports acquisition and onboarding. | Positive gross margin need not repay acquisition work. | Price commitment plus timed onboarding, not interest survey; market + economics. |
| U12 | Adoption can occur before cash/time exhaustion. | Delayed free pilots consume runway. | Conditional cash timeline with actual cash and labor inputs; economics. |
| U13 | Customers can recover evidence after outage/cancellation. | Evidence custody may outlast a subscription. | Export/recovery exercise across inactive entitlement and unavailable provider; security. |
| U14 | Corrections preserve both historical truth and current exports. | Real users make mistakes in immutable records. | Amend a mistaken lot and reconcile superseded/current results; QA. |
| U15 | Suppliers have authority and incentive to fix data. | The buyer may not control upstream data quality. | Observe one buyer-supplier correction handoff; product. |
| U16 | Regulatory timing and alternatives create present urgency. | A deadline alone does not prove a buying window. | Primary-source check and buyer's existing ERP/spreadsheet comparison; market. |
| U17 | Reliability and support survive a correlated incident. | Average monthly cost conceals peak demand and common failures. | Tabletop recall + provider outage + support surge; independent judgment. |

## Evidence semantics and claim graph

Reality Levels are scoped to the claim: L0 idea, L1 logical/source reasoning,
L2 mathematics, L3 simulation, L4 consistency with relevant historical data, L5 controlled
experiment, L6 realistic sandbox, L7 limited real use, L8 repeated real use,
L9 economically meaningful scale. Reading code is not L7 production evidence.
Public primary sources can establish their own statements; they cannot establish
RegEngine's customer demand. Synthetic local tests reach L5 only for the tested
software behavior, never for willingness to pay or production reliability.

Source files, design documents and offers remain L1 implementation/business
reasoning; their existence does not promote their business claims to L4. Historical
publications support their reported dates and statements, not vendor performance.
Unknown production costs, active customers, cash reserves, conversion, failure
rates, incident losses and production throughput stay UNKNOWN.

The claim-evidence graph is represented as directed edges below. Separate claims
avoid turning a valid local observation into a broader assertion.

| Claim | Supporting/refuting evidence → current level | Decision edge |
| --- | --- | --- |
| C01: RegEngine has verified paid demand. | [Market inspection](market.md): no located payment/finished study; current reality UNKNOWN; hypothesis L0–L1. | U01/U11 → E04; do not accelerate based on this wave. |
| C02: Displayed plans and billing are a single coherent offer. | [Economics trace](economics.md): connected catalog/metadata disagreements, actual Stripe prices UNKNOWN; L1. | U07 → E06; reconcile before a paid offer. |
| C03: Public hash verification authenticates the issuer. | [Security original/altered/recomputed cases](security-results.jsonl), independently [replicated](qa-artifact-results.json); falsified L5. | U03 → correct signing copy; do not infer source truth. |
| C04: Current FDA generator packages work in advertised verifiers. | Baseline falsified by two independent probes; post-integration [security](security-results-integrated.jsonl) and [QA](qa-artifact-results-integrated.json) reruns pass the real helper's valid-chain package through both verifiers. A self-consistent `UNVERIFIED` package fails both; L5. | U02/U03 → local format mismatch and invalid-chain acceptance closed; retain internal-consistency wording and test remaining package boundaries. |
| C05: Chain-link validation rechecks stored event content. | [SQLite quantity-change probe](security.md): stored quantity changes without invalidating chain; falsified L5 in that model. | U03/U06 → content reconciliation, with historical hash formats respected. |
| C06: Selected canonical writers bind tenant context before SQL. | [QA SQL-order and invalid-tenant probes](qa.md); L5 for emitted calls only. | U06 → disposable PostgreSQL test; no RLS readiness inference. |
| C07: All focused existing tests are green. | [Raw baseline](qa-pytest-results.txt): 231 passed, five failed; falsified L5. | Preserve failures; stale SQL-spelling assertions do not establish a deployed tenant leak. |
| C08: There is no change in behavior at larger volumes. | [QA boundaries](qa.md): 500-event batch, 5,000-row PDF, 10,000-row v2/recall limits; L1/L5 by specific check. | U10/U17 → supported-volume contract; do not remove protective limits. |
| C09: Higher usage is profitable at a flat subscription price. | [Conditional model](economics.md); L2 arithmetic / L3 scenarios, actual margin UNKNOWN. | U08/U09/U12 → measure human cleanup and retained evidence costs. |
| C10: Readiness proves all source records arrived. | [Workbench source](../../../services/ingestion/app/inflow_workbench.py) scores supplied results/latest run; full ERP denominator unverified, L1. | U04 → source-omission experiment, not another scoring feature. |
| C11: CSV screens describe the synchronous API outcome. | Reproduced broken baseline; [independent final QA](qa.md) passed 35 cases after repairs; L5 for component/client behavior. | U02 → integrate the bounded fix, then test a real file end to end. |
| C12: Missing hashes cannot downgrade a failed-chain verdict. | Original [counterexample](security-results.jsonl), corrected [replication](security-results-after.jsonl), plus truth-table/ZIP tests; L5. | Preserve UNVERIFIED failure precedence; content rehash/format questions remain separate. |

Failed hypotheses were retained. Independent review also challenged the initial
economic model's first-event comparison: opening an account must not be confused
with adding the first event to an existing account. Replication results below
must use the corrected comparison.

## Experiment queue

All success/failure thresholds below are proposed decision rules, not observed
industry benchmarks. Ordinal value/cost is a prioritization judgment, not a
measured return. Runs are independent where dependencies allow.

| Rank / ID | Question and hypothesis | Value / cost / time | Method and dependencies | Success / failure | Result → confidence update → next action |
| --- | --- | --- | --- | --- | --- |
| 1 / E01 | Does the CSV UI describe actual backend outcomes? Hypothesis: response contract matches. | High / local / under one session. | Synthetic component tests using current backend payload shape. | Exact accepted/rejected/duplicate counts and truthful zero-result states / mismatch. | Implementation and independent check in this wave. |
| 2 / E02 | What does verification actually establish? Hypothesis: claimed guarantee equals tested guarantee. | High / local / under one session. | Independent file, manifest, row-hash and chain alteration. | Documented guarantees survive / stronger claim fails. | Security and QA evidence in this wave. |
| 3 / E03 | Can event growth destroy margin? Hypothesis: flat subscription supports higher volume. | High / local / under one session. | Reproducible conditional cost model and hand checks. | Positive incremental contribution in specified envelope / negative or capacity breach. | Economics analysis in this wave; measured inputs still required. |
| 4 / E04 | Will one qualified buyer commit at a defined price? | Highest external / one founder session plus outreach time. | Existing warm contact, concrete scope/price, budget owner; founder sends, no agent contact. | Payment supports that buyer/offer only; refusal weakens that case, nonresponse is inconclusive. | NOT RUN → demand remains unknown → choose a coherent offer, then compare materially different qualified cases. |
| 5 / E05 | Does one sanitized real file produce a reconciled export? | High / 30–60 minutes observation plus safe setup. | Consented file, isolated tenant/database, known source counts, timed correction. | Every row accounted for, including explicit valid rejections; silent omissions, unauthorized access or false evidence claims are hard failures. Measure rescue time separately. | NOT RUN → end-to-end claim unverified → test CSV and distinguish unassisted from managed delivery. |
| 6 / E06 | Is the sellable billing contract coherent? | High / bounded local trace plus payment-provider test mode. | Choose one existing plan contract; no live charge. | Displayed price/period/limits equal checkout and entitlement / mismatch. | Local evidence in economics report; real checkout NOT RUN. |
| 7 / E07 | Do retries, rejection and corrections reconcile across stores? | High / disposable infrastructure / half-day estimate. | PostgreSQL migrations, tenant A/B, forced transaction failure and retry. | No cross-tenant data, duplicate counts or missing accepted exports / any violation. | NOT RUN → dual-write risk remains → next technical experiment. |
| 8 / E08 | Do 500/501-row ingest and 10,000/10,001-row export remain explicit? | Medium / local fixture plus DB / hours estimate. | Boundary fixture, complete row accounting, rejection/partition UX. | Explicit complete result or explicit refusal / silently incomplete evidence. | Limits inspected; full database boundary exercise NOT RUN. |
| 9 / E09 | Can evidence be recovered during cancellation/outage? | High / disposable environment / half-day estimate. | Inactive entitlement, backup restore, external viewer with retained artifact. | Authorized recovery and scoped guarantees / permanent loss or misleading claim. | NOT RUN → custody remains unknown. |
| 10 / E10 | Does real remediation fit the economic envelope? | High / observation alongside E05. | Record event count, failure reasons, operator minutes, retries, variable provider usage. | Measured cost below agreed price at buyer's volume / negative contribution. | NOT RUN → replace hypothetical model inputs before scale decisions. |
| Completed locally / E11 | Can a real generated package pass its intended verifier? | High / small local repair, no customer data needed. | One artifact contract; generator → SDK/API plus negative package cases. | Valid `VERIFIED`/`PARTIAL` formats pass; changed content, `UNVERIFIED` chain, manifest/chain disagreement, and undeclared/duplicate/unsafe members fail. | Integrated helper passes both verifiers → local interoperability confidence increased. Unsupported-version and malformed-manifest behavior remain follow-up work. |

E01 outcome: original UI tests reproduced 10 failures and a React rendering error;
the repaired client/screens passed 35 focused tests independently. A QA challenge
found three additional malformed-response cases; all passed after narrow guards.
E02 outcome: original issuer-authenticity, generated-package interoperability,
and failure-status claims were falsified. During integration, review also
reproduced and repaired a first-pass verifier acceptance of an invalid chain.
Copy, status precedence, the local package format, chain-artifact cross-checks,
and member coverage were repaired and rerun; issuer authenticity and
stored-content rehash findings remain open. E03 outcome: arithmetic replicated
after one first-unit baseline correction. No actual profitability claim was
promoted.

For ledger confidence/status: U01/U09/U11/U12/U15 remain UNKNOWN empirical claims;
U02 is locally repaired but end-to-end UNKNOWN; U03/U07 have high-confidence
scoped counterevidence; U04/U05/U06/U10/U13/U14/U16/U17 have inspected boundaries
or tested components but incomplete runtime/business evidence. Owners and tests
remain in the ledger above; these are not subjective success probabilities.

## Thesis history

V0 is the repository proposition: an ERP-adjacent evidence layer turns supply-chain
records into traceability exports. It is a product hypothesis, not verified demand.
V1 is a narrower validation thesis: prove one complete supplier-record-to-export
outcome, including missing records, correction and recovery, and charge only for
an explicitly defined service envelope. Why it changed: C01–C10 expose demand,
contract, integrity and cost gaps hidden by the broad evidence-layer proposition.
Expected improvement: fewer promises and a measurable delivery cost. New risks:
manual-service burden and a second vendor's integration cost. Required experiment:
E04/E05/E10 after E11. V1 remains L0–L1, not established opportunity. It does not
rewrite the canonical product description or select a new market for the founder.

Independent judgment: **MODIFY**. The proposed next investment is a supervised,
explicitly experimental workflow, not a broad launch. One actual paid outcome
with reconciled source coverage, corrected records, recovery and measured support
cost can justify CONTINUE for that offer. Independent repeated customers and
verified deployed behavior would be needed for ACCELERATE. Refusal of both managed
and self-service versions by suitable buyers should cause a specified offer or
segment to be reconsidered, not be averaged into agent optimism.

## Time, outliers and phase transitions

These are hypotheses (L1), not probability estimates. The conditional cash paths
in the economics model are L3; no empirical survival distribution was available.

| Horizon / extreme | Dominant question | Smallest test / decision |
| --- | --- | --- |
| Day 1 | Does the operator have usable source records and authority? | Real CSV including malformed rows; account for every row. |
| Day 7 | Will suppliers cooperate and repeat without founder rescue? | Observe one buyer/two-supplier correction handoff; time both work and waiting. |
| Day 30 | Do corrections propagate after an export? | Wrong shipment → export → amendment → new export; retain history and identify affected recipients. |
| Day 90 | Does accumulated history exceed one synchronous export? | For d matching events/day, 10,000 is crossed on floor(10000/d)+1 (L2); filters/snapshot completeness still unverified. |
| Year 1 | Do churn and collection delays leave unfunded custody work? | Cancellation/recovery drill plus actual storage and support ledger. |
| Year 3 | Can another operator recover evidence without founder knowledge? | Customer-held archive, provider-loss tabletop, restoration and verification exercise. |
| Zero adoption | Fixed costs continue with no revenue. | Model cash exhaustion conditionally; no invented probability of ruin. |
| Sudden large tenant / correlated recall | Per-tenant locks, >10k matching records and simultaneous support dominate averages. | Skewed-volume disposable DB test and two-customer incident tabletop; do not extrapolate formatter timings. |
| Cost explosion / platform failure | Remediation labor, retries, unavailable billing cache and retained data may combine. | Sensitivity plus recovery drill; establish a supported envelope before enterprise promises. |
| Competitor copying / cheaper compute | Existing providers can supply exports; cheaper inference need not remove supplier cleanup work. | Compare the buyer's actual alternative and measured correction minutes; no speculative moat claim. |
| Regulatory or technical change | Buying urgency and recipient formats may change independently of the app. | Recheck primary publications and one recipient's acceptance test before new commitments. |

Cross-disciplinary collision: economics + security exposed continuing evidence
custody cost after cancellation; UX + QA exposed successful HTTP responses that
do not mean accepted records; market + infrastructure exposed cheap export-format
substitutes and expensive human remediation. These changed questions, not agent
vote counts. Where positions differ, preserve them: “hashes work” concerns internal
consistency; “proof is insufficient” concerns issuer/content truth. Both can hold.

## Selected design, architecture and business model

Best-supported architecture for this wave is the existing consolidated backend,
existing tenant resolver, current ingestion/persistence ownership and narrow
contract repairs. No evidence justified another service, AI agent runtime,
database migration, signing infrastructure, or broad rewrite. Dual-write retirement
requires reconciliation, not copying the old architecture map.

[Design comparison](design.md) evaluates customer archetypes and competing UX
approaches without invented user scores. The provisional starting surface is a
CSV outcome with explicit rejection/reconciliation details and provenance limits;
API-first is a separate integrator cohort. This is not observed usability success.
[Distribution analysis](distribution.md) distinguishes the first 10/100/1,000/10,000
paying-account targets from actual channels and attacks the proposed advantage
from incumbent, ERP and open-source perspectives.

The best business model is UNKNOWN. Account-month revenue plus an explicit
usage/support envelope is a testable candidate; a paid assisted outcome is a
competing experiment. Under the economics model's hypothetical $649 price and
5,000 events/account, first operating break-even is 46 accounts, with losses
recurring at staffing steps until 57 within the bounded search. At 5% remediation
there is no break-even through 10,000 accounts. Neither threshold is a forecast.
The millionth event in an existing account is less costly at its particular
capacity point, but still produces negative marginal contribution. Actual costs,
cash reserves, demand, risk probabilities and profitability are UNKNOWN.

## Changes and verification

All tests below are local; overlapping runs are not summed into a unique total.

| Change or check | Result | Boundary |
| --- | --- | --- |
| Shared CSV response type/client and two upload screens; three focused test files | Both screens show accepted/rejected counts, warnings and errors; zero acceptance is not success; malformed response shapes reject safely; URL job flow preserved. | No server ingest API, auth, CSRF, tenant header or persistence change. File controls now match CSV/5MB support. |
| Post-integration CSV security review | Failed API-key cookie writes stop the upload; submission waits for a successful write and suppresses duplicates. Accepted events require a nonempty ID, two 64-hex evidence hashes, and no errors. The final ten-file security selection passes 145 tests; scoped tsc/ESLint pass. | Mocked client/UI behavior, not live cookie, tenant, network, or persistence verification. |
| FDA helper status and existing helper tests | Invalid chain always UNVERIFIED; valid missing-hash case PARTIAL; valid complete case VERIFIED. Package instructions distinguish them. | Intentional correction to exported failure-status semantics; schema, tenant/auth, PII policy and billing unchanged. |
| Public proof API, SDK and wording | Claims are limited to internal consistency. FDA packages require matching chain metadata and reject failed chains, undeclared members and duplicates while preserving generic-bundle behavior. | No trusted root, issuer authentication, source-truth proof or independent persisted-chain recomputation. |
| Backend red/green | Four regression failures reproduced before fix; helper/verification/PII selection 117 passed after. | Eight truth-table cases and generated ZIP assertions; no live DB. |
| Independent security | 87 tests passed after the status fix; final reproduction passes valid generated package through SDK/API, rejects a self-consistent `UNVERIFIED` package, and retains `UNVERIFIED` precedence. | Stored-content blind spot and untrusted-manifest limits remain; no deployment verification. |
| Frontend red/green and independent QA | Original six-file selection passed 35; final ten-file security selection passed 145; current scoped tsc and changed-file eslint passed. | Components/mock HTTP, not browser/service end to end. |
| Broader baseline | 231 passed, five failed, zero skipped. Current set_config tenant-binding order independently confirmed. | Five stale SQL-text assertions retained; no PostgreSQL RLS conclusion. |
| Broad frontend lint/type check | Lint exit 0 with 62 warnings; full tsc fails unchanged dashboard-error-boundary.test.tsx:30 (TS2786). | Scoped types pass; do not label full typecheck green. |
| Python static checks | Changed backend/research Python files pass Ruff. Direct mypy on the export service reports eight preexisting FPDF annotation errors outside this diff; root config marks mypy nonblocking. Syntax checks pass research scripts and SDK. | Repo-wide mypy and remediation of the older FPDF annotations were not part of this change. |
| Economic replication | Five self-check groups plus independent 14 monthly cases, six sensitivity searches, five cash paths and 30 snapshots matched corrected output. | Conditional arithmetic/scenarios only. |
| Public sample and generated package | SDK public sample exits 0; the post-integration valid-chain generated package exits 0 with four declared hashes, Merkle root, and chain summary matching. A generated `UNVERIFIED` package exits 1. | Internal consistency only; neither passing result authenticates the issuer or proves source-data accuracy. |

Exact commands and raw results: [QA](qa.md), [security](security.md),
[economics](economics.md). No dependency was installed or lockfile changed.
Root also confirmed the published changed-CSV sample exits 1, reran proof-page
ESLint after the final wording edits, validated 79 relative Markdown links and
all JSON/JSONL artifacts, and removed only the temporary dependency symlink.

Application/test files changed: [CSV type](../../../frontend/src/types/api.ts),
[client](../../../frontend/src/lib/api-client.ts),
[upload page](../../../frontend/src/app/ingest/page.tsx),
[import hub](../../../frontend/src/app/tools/data-import/components/DataImportClient.tsx),
[client tests](../../../frontend/src/__tests__/lib/api-client-review.test.ts),
[upload tests](../../../frontend/src/__tests__/pages/ingest-csv.test.tsx),
[hub tests](../../../frontend/src/__tests__/pages/data-import.test.tsx),
[FDA helper](../../../services/ingestion/app/fda_export_service.py),
[helper tests](../../../services/ingestion/tests/test_fda_export_service_1342.py),
[proof page](../../../frontend/src/app/proof/page.tsx), and
[SDK docstring](../../../frontend/public/sdk/verify_chain.py).
Research files are all under this directory. The baseline wave began isolated;
the post-integration artifacts describe the reconciled local tree. They do not
assert that anything was deployed, charged, or scheduled.

At the original closeout, another task independently wrote
`docs/research/deep-market-lab-2026-08-31/`. It is separate research output even
after integration. Do not combine its observations with this report's test
counts without inspecting scope and base revision.

## Next ten actions and resource allocation

1. Version the integrated generator/verifier contract and add explicit
   unsupported-format plus predictable malformed-manifest results; do not add
   issuer-authentication claims.
2. Reconcile one advertised plan, checkout Price, billing interval and entitlement
   in test mode; choose commercial terms before any charge.
3. Repair the five obsolete SQL-text assertions without weakening tenant/order
   checks, then test actual two-tenant PostgreSQL behavior.
4. Reconcile event content, canonical/legacy hashes, retry and export inclusion
   in a disposable database with supported historical formats.
5. Run a source-omission drill against independently known shipment totals.
6. Run correction → re-export → recipient-history reconciliation.
7. Test cancellation/provider outage and customer-independent evidence recovery.
8. Have the founder conduct the bounded buyer/current-alternative/priced-outcome
   test; no agent sends messages or initiates payment.
9. Time one consented representative supplier file through the complete supported
   workflow and replace hypothetical support/cost inputs.
10. Repeat with a materially different buyer/file; revisit verdict before broader
    scaling, mobile photo ingestion or further feature expansion.

Recommended resource order: one small local artifact-contract patch plus reviewer;
one disposable DB experiment; then one consented buyer session. No paid research,
new platform, mass outreach or large load test is justified by this evidence.

## Resource boundary

No more agent agreement can supply actual willingness to pay, real-file error
rates, cloud bills, or the founder's cash balance. Request only the smallest
resource that unlocks a decision: one observed buyer/file session and aggregate
cost inputs. If unavailable, retain the unknowns and use the synthetic model as a
sensitivity calculator. Do not spend money, collect customer data, or schedule
future work merely to keep agents active.
