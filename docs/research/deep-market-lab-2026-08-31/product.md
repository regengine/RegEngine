# Product, activation, and distribution experiment lane

**Date:** 2026-08-31. **Classification:** docs-only research; no production change, deployment, prospect contact, purchase, or customer experiment performed. **Verdict:** continue a narrow, assisted data-reconciliation experiment; do not expand the dashboard or claim product-market fit. Customer archetypes, experiment thresholds, conversion assumptions, and rankings below are **HYPOTHESES**, not observed customer results.

## What the repository actually offers

The strongest proposition is an evidence layer beside the customer's ERP: expose missing traceability fields, help an operator correct them, and produce an inspectable artifact. The canonical product description says RegEngine is pre-production with no paying customers. That is a repository statement, not an independent account or revenue verification. [Canonical description](../../../docs/PRODUCT_DESCRIPTION.md#L7)

Inflow has a useful task-shaped demonstration. The dashboard accepts pasted/uploaded CSV, evaluates through the sandbox endpoint, optionally asks for authenticated readiness, and saves a Workbench run only on an explicit action. Saving checks write permission; a successful preview is not a production commit. The public workflow explicitly separates diagnosis, saved test run, import mapping, monitored feed, and production export. Its mapping/export buttons navigate to separate routes, so the code shown does not establish that the same source and corrections travel through the whole journey without re-entry. [Evaluate/save handlers](../../../frontend/src/app/tools/inflow-lab/components/DashboardInflowLab.tsx#L863), [production handoff](../../../frontend/src/app/tools/inflow-lab/components/InflowLabClient.tsx#L1973)

The authenticated onboarding route sends a user to welcome, facility creation, FTL-category checking, then dashboard. Welcome requires role, company type, and compliance status; facility creation requires name/address/ZIP. FTL completion marks onboarding complete without proving first ingest, successful correction, or export. These controls can be necessary to establish real records, but completing setup should not count as delivering value. [Redirect](../../../frontend/src/app/onboarding/page.tsx#L17), [welcome](../../../frontend/src/app/onboarding/setup/welcome/page.tsx#L52), [facility](../../../frontend/src/app/onboarding/setup/facility/page.tsx#L54), [completion](../../../frontend/src/app/onboarding/setup/ftl-check/page.tsx#L115)

Two operating instructions conflict. Inflow outreach asks for messy supplier spreadsheets, while the first-pilot playbook diverts spreadsheet-only prospects to synthetic demos unless they have API/EPCIS/EDI capability. A CSV-led product cannot learn whether CSV operators activate if recruitment excludes them. The first pilot should explicitly choose either an operator CSV task or an integrator API task; mixing them hides the source of failure. [Outreach](../../../docs/runbooks/inflow_workbench_design_partner_outreach.md#L7), [pilot qualification](../../../docs/runbooks/first_pilot_session.md#L13)

Do not equate hashes with correct source data or regulatory acceptance. A customer still needs to supply the actual missing handoff or lot information. The current UI's separation of sandbox from production is valuable trust behavior and must survive simplification.

## Commercial contract must precede a payment experiment

Three checked-in offers disagree:

| Surface | Recorded offer |
|---|---|
| May pilot decision | Free 60-day pilot, potential 12-month free access, event tiers, 10% annual discount; grandfather cutoff was August 1 |
| Pricing page | Base/Standard/Premium by facilities; partner annual equivalents $425/$549/$639 per month, monthly $499/$649/$749; Base 500 events, others described as unlimited/fair use |
| Billing plan definitions | Growth $999 monthly / $832 annual equivalent and 50,000 events; Scale $1,999 / $1,666 and 250,000 events; Enterprise custom |

Sources: [pilot terms](../../../docs/decisions/2026-05-13-pilot-pricing.md#L15), [public tiers](../../../frontend/src/app/pricing/page.tsx#L63), [billing definitions](../../../services/ingestion/app/stripe_billing/plans.py#L20).

The checkout button maps Base to Growth and Standard to Scale, defaults to annual, and deliberately sends Premium to signup without checkout. The pricing loader expects different plan IDs and field names from the inspected billing definitions. Therefore the public offer and checkout lookup are not one verified contract. Actual deployed Stripe amounts remain **not verified**; no payment was attempted. [Checkout mapping](../../../frontend/src/components/billing/PricingCheckoutButton.tsx#L11), [request](../../../frontend/src/components/billing/PricingCheckoutButton.tsx#L52), [pricing loader](../../../frontend/src/app/pricing/page.tsx#L31), [Stripe price resolution](../../../services/ingestion/app/stripe_billing/plans.py#L99)

Do not interpret checkout abandonment as unwillingness to pay until this is reconciled. The smallest prerequisite is one founder-owned offer sheet covering price, period, facilities, event allowance, support cap, pilot expiry, and cancellation, followed by a focused implementation and billing-contract test. This report does not change prices or promise a new offer.

## Design philosophy tournament — proposed, not user-tested

| Philosophy | Strongest reason to win | Main failure mode | Cheapest discriminator | Provisional rank |
|---|---|---|---|---|
| Trust/data-first professional workspace | QA lead can inspect source, missing field, owner, correction, and export consequence | Dense panels create diagnosis without completed work | Observe one lot from file to corrected result, counting navigation and help | 1 for retained operators |
| Minimalist assisted workflow | A first-time operator sees one file, one blocker, one next action | Hides evidence or makes the founder do every mapping | Existing UI plus a one-page task card; disclose assistance and time it | 1 for first activation |
| API-first infrastructure | Integrator can reuse mappings and automate recurring feeds | Technical setup excludes the user who owns the pain | One developer uses current quickstart without live coaching | 2, conditional channel |
| Consumer-style/game-style dashboard | Progress feedback may explain remaining work | Score chasing, false certainty, decorative engagement | Ask whether a simple completion checklist changes task understanding | Reject as a separate build |

The first two are compatible: a short starting path can open detailed evidence when needed. Do not implement four competing applications. Reuse the present sample, exception grouping, and separate production boundary. Any progress display should represent completed evidence tasks, never a reward for dismissing exceptions. The provisional design winner is **assisted first-use followed by a professional exception workspace**.

Measure behavior rather than visual preference. Present believable tasks without naming the button to click, observe where users fail, and record task completion/time. These choices follow the [GOV.UK moderated-testing guidance](https://www.gov.uk/service-manual/user-research/using-moderated-usability-testing) and [usability benchmarking guidance](https://www.gov.uk/service-manual/measuring-success/usability-benchmarking-a-website-or-whole-service). These sources justify the method, not a claim that RegEngine's proposed design wins.

## Customer archetype tournament — all hypotheses

| Archetype | User / likely payer | Trigger and bounded job | Disqualifier or risk | First evidence required |
|---|---|---|---|---|
| Fresh-cut processor QA lead | QA operator / operations owner | A failed trace exercise or supplier handoff; reconcile one receiving-to-shipping lot | Buyer requires an incumbent network; transformation complexity consumes support | One recent file, actual failure, access to budget owner |
| Regional distributor operations lead | Data/QA operator / operations leader | Repeated supplier-format errors; compare two feeds and correct one recurring pattern | Hundreds of supplier formats with no willingness to standardize | Two representative feeds and measured manual effort |
| Small importer or seafood receiver | Owner/operator / same person | One traceability request with missing provenance | Limited budget or a specialist incumbent already solves it | Concrete prior request and current alternative's actual cost |
| Implementation consultant/ERP integrator | Integrator / client or partner | A repeatable client mapping and evidence check | Custom consulting becomes the whole business; consultant is not end-customer demand | Two clients with the same input pattern and a named operator |

The older ICP memo explicitly describes agent-generated consensus and composite pain quotes; its revenue ranges, sales cycles, and TAM counts are not interview findings. Use it as a recruiting hypothesis bank. [Method and archetypes](../../../docs/research/fsma-204-go-to-market-2026-05.md#L15)

There is no defensible “CSV traceability is unserved” claim. Trustwell states that FoodLogiQ supports CSV import across the remaining CTE types in its June 2025 release. iFoodDS currently lists Trace Exchange Core with TraceApproved at $2,500 annually. Their existence invalidates a generic cheapest-tool thesis; comparative capability, implementation effort, and customer suitability still require testing. [Trustwell release](https://blog.trustwell.com/foodlogiq-q2-2025-release-new-tools-to-enable-traceability-supplier-relationships-and-product-specifications), [iFoodDS offer](https://supplier-trace.ifoodds.com/trace-exchange-core-with-traceapproved/)

Provisional recruiting order: an accessible processor or distributor with a current file and named pain first; a consultant only if they bring real client work. Select by evidence access and task repeatability, not the apparent precision of an invented market segment.

## Activation and repeat use

Define **activation** as: a real operator diagnoses their own authorized file, identifies a missing field correctly, obtains a valid correction, and sees the resulting persisted evidence/export in the intended environment. Record sandbox-only success separately. Define **repeat use** as a second new source batch completed within seven days, with less founder assistance. Neither a fabricated sample nor a founder-triggered recurring API job alone proves user value.

Likely bottlenecks to test are permission to share supplier data; finding the right source columns; understanding whether “ready” refers to a test or real evidence; moving between saved run, fix queue, import, and export; and obtaining the missing information from another company. More UI cannot manufacture unavailable evidence. If obtaining supplier responses dominates the time, test a manual owner/due-date checklist before building collaboration infrastructure.

The existing OKR is weekly pilots ingesting events. Its SQL counts insertion timestamps and excludes internal tenants by name prefix. This is useful activity evidence but does not verify source authenticity, distinct new business work, or completed exports. Keep the existing OKR and add a manual outcome record for each observed pilot. [OKR](../../../docs/decisions/2026-05-13-okr.md#L9), [query](../../../scripts/okr_pilots_ingesting_weekly.sql#L23)

The funnel runbook still routes success through scan and NLP-query stages. Those are not necessary steps in the stated evidence product. The generic frontend analytics wrapper tracks pricing/demo/tool events, not the full correction-to-export loop. Instrumentation elsewhere and live counts are **not verified**. For two pilots, a consented observation sheet is enough; do not add an analytics dependency. [Funnel stages](../../../docs/runbooks/design_partner_funnel_operating_rhythm.md#L5), [analytics wrapper](../../../frontend/src/lib/analytics.ts#L24)

## Demand evidence and distribution constraints

The outreach tracker contains five dated sends on May 23 and five other researched rows. Every response field is blank. This proves recorded outreach activity, not nonresponse, interviews, pilots, revenue, or retention. No completed interview synthesis or pilot-observation document was found in the targeted research/pilot filename scan; evidence outside the repository remains unknown. [Tracker](../../../docs/research/pilot-outreach-tracker.csv#L1)

The following growth paths are hypotheses, not forecasts. “Customer” means a paying organization with verified recurring use, not a signup, supplier invitation, or free pilot.

| Scale | Concrete mechanism | Founder constraint and stop condition |
|---|---|---|
| First 10 | Founder obtains permission to approach a narrow list; one-file observation, bounded pilot, buyer review, referral after a verified result | At one new pilot session weekly, ten sessions take at least ten weeks and do not imply ten wins. Track all outreach, sales, and support hours |
| First 100 | Reuse the winning input pattern; two or three implementation partners bring matching clients; publish a permissioned case result | Do not recruit partners until at least three direct customers repeat the task. At 30 support minutes/customer/week, 100 require 50 hours/week before selling |
| First 1,000 | Repeatable partner onboarding, referenceable results, documented implementation and support handled beyond the founder | At only 10 minutes/customer/week, support is about 167 hours/week; a solo operating model fails |
| First 10,000 | Distribution through ERP/industry platforms with proven economical onboarding and partner-owned first-line support | No evidence this channel exists or this narrow segment contains sufficient reachable buyers. This is a different organizational requirement, not a next-quarter target |

Use partner referrals and tightly scoped direct conversations before paid acquisition. A page download is a lead signal, not demand validation. No messages were sent and no partner commitments were made during this run.

## Fourteen-day experiment proposal

**Budget hypothesis:** ten founder hours across two weeks, zero ad spend, at most two observed sessions (one per week, consistent with the existing playbook). This is intentionally a learning test, not a statistically powered conversion study.

1. **Days 1–2, 90 minutes:** choose one CSV workflow and the offer-sheet owner; select up to six already-researched contacts for a founder-authorized approach. Do not send automatically. Prepare a consent/data-handling note and request redacted data. No live credentials are needed for recruitment.
2. **Days 3–5, two hours:** seek three short problem conversations. Ask about the last real trace request, current process, actual elapsed effort, who supplies missing fields, and who approves spend. Show no product until the problem is recorded. If nobody will describe a real event or share a permitted sample, change recruitment or pain hypothesis before coding.
3. **Days 6–7, two hours:** run one observed session on the present workflow. Capture independent task success, wrong conclusions, source mapping time, corrections, and founder interventions. Attempt actual persistence/export only in an approved isolated environment after relevant integrity gates pass; otherwise label the result sandbox-only.
4. **Days 8–11, three hours:** test one change in assistance or task wording, then a second session. Use the same task where comparable; changing both segment and UI makes interpretation weak. Request a second new batch from the first participant and record voluntary completion separately from reminders.
5. **Days 12–14, 90 minutes:** review evidence with a budget owner. After commercial terms are reconciled, ask whether they will accept a specific scoped paid continuation; record the written response and conditions. Do not treat hypothetical price enthusiasm or a free pilot as payment.

**Advance hypothesis:** two authorized real files, at least one independently completed correction-to-artifact task, one second-batch return, and one named budget owner accepting a concrete next step. **Reshape:** interest is real but every file requires bespoke founder mapping, or the buyer values a one-time exercise more than recurring monitoring. **Stop expansion:** no real file, no repeat task, or no credible buyer after the cycle. Failure is evidence about this recruitment/test, not proof that the entire market does not exist.

Highest-value unknowns are real time saved, correction accuracy, second-batch recurrence, willingness to pay for that saved work, support minutes per organization, and acceptance of the exported artifact by the intended recipient. Resolve those before feature breadth, visual redesign, or a thousand-customer architecture.

## Verification and handoff

- **Files changed:** this report only.
- **What changed:** documented source-backed workflow findings, commercial conflicts, hypotheses, and a bounded customer experiment.
- **Tests run:** `npm run test:run -- src/__tests__/pages/inflow-lab.test.tsx src/__tests__/lib/inflow-lab-exception-grouping.test.ts src/__tests__/api/inflow-lab-proxy.test.ts`; `npm run promise:audit`, from `frontend/`.
- **What passed:** 3 test files, 31 tests in 2.85 seconds; promise audit passed. Tests cover mock UI behavior, sandbox/save separation, write-permission handling, grouping, and proxy behavior.
- **What was not tested:** live signup, deployed pricing, actual charges, browser usability/accessibility, database persistence, full frontend suite/lint/build, real customer outcomes, or willingness to pay. No code changed, so no new tests were added.
- **Remaining risks:** commercial mismatch, sandbox-to-production handoff friction, synthetic/demo success mistaken for activation, founder support cost, and absent verified customer evidence.
- **Recommended next step:** reconcile one offer and observe one authorized real CSV workflow; route only its concrete blocker into implementation.
