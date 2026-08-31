# Economics evidence wave — 2026-08-31

Docs/research only. No billing, production, schema, deployment, or pricing changes. Currency is USD. Model and outputs: [economics_model.py](economics_model.py), [economics_results.json](economics_results.json).

**Decision: do not claim profitable scale or start a paid pilot from the current pricing contract without reconciliation.** The connected frontend/backend catalogs disagree, observed usage in the subscription response is hardcoded, and no actual receipts, cloud invoices, workload distribution, or measured support time were available. This does not establish that a customer was charged the wrong amount. **Reality Level 1 — logical decision from locally inspected artifacts; commercial economics UNKNOWN.**

Evidence labels below are claim-specific: **L1** logical interpretation, **L2** arithmetic, **L3** hypothetical scenario execution, **L5** controlled runtime experiment. Source checks here are classified L1; they do not establish deployed behavior, customer demand, or operational scale. No economic claim reached L7–L9.

## The units that matter

| Unit | Definition and reason | Evidence / Reality Level |
|---|---|---|
| Paid account-month | One tenant's actually earned subscription revenue, with facilities and negotiated scope recorded separately. This is the revenue unit; facilities do not independently incur invoices in the checked-out checkout code. | Subscription checkout has one price item, quantity 1: [routes.py](../../../services/ingestion/app/stripe_billing/routes.py), lines 176–183. L1 source inspection; realized price UNKNOWN. |
| Accepted CTE | One unique, persisted traceability business event, excluding duplicate requests, retries, rejected submissions and failed writes. This is the processing/evidence unit, not necessarily a billing unit. | [webhook_router_v2 routes](../../../services/ingestion/app/webhook_router_v2/routes.py), accepted counter from line 127 and response around line 496; append-only duplicate check in [core.py](../../../services/shared/cte_persistence/core.py), lines 276–300. L1 recommended measurement definition grounded in code; operational counts UNKNOWN. |
| Remediation case / minute | A defect requiring human work, with provider and customer time measured separately. Multiple cases may arise from one CTE, so a case/event ratio is not necessarily a probability. | Fix queue generation in [inflow_workbench.py](../../../services/ingestion/app/inflow_workbench.py), lines 754–791. L1 proposed measurement; measured time UNKNOWN. |
| Onboarded account | One completed initial integration, measured in human hours and cash outlay before repeat service. Avoid hiding founder implementation work inside acquisition assumptions. | L1 economic accounting recommendation; actual CAC, onboarding time and payback UNKNOWN. |

## Observed contract conflicts and missing measurements

1. **Displayed and checkout catalog values are inconsistent. L1, source inspection.** [Pricing page](../../../frontend/src/app/pricing/page.tsx), lines 63–122, contains Base / Standard / Premium partner monthly offers of $499 / $649 / $749; its annual displayed monthly equivalents are $425 / $549 / $639. Base advertises 500 CTEs/month; Standard and Premium advertise no per-CTE caps subject to fair use. The [checkout button](../../../frontend/src/components/billing/PricingCheckoutButton.tsx), lines 11–15 and 40–57, maps Base to Growth and Standard to Scale, while Premium goes to signup without Stripe checkout. The [proxy](../../../frontend/src/app/api/billing/checkout/route.ts), lines 14 and 46–53, forwards those selections to the configured ingestion backend. The [backend plans](../../../services/ingestion/app/stripe_billing/plans.py), lines 20–58, declare Growth at $999/month, 50,000 events and one facility; Scale at $1,999/month, 250,000 events and five facilities. These are source artifacts, not proof of a live offer or collected payment.

2. **Fetching the checked-in backend catalog does not reconcile the page. L1 source reasoning / untested runtime implication.** [server/main.py](../../../server/main.py), lines 355–362, mounts `/api/v1/billing` and aliases `/billing/plans` to the same list function when billing is enabled. [Backend list_plans](../../../services/ingestion/app/stripe_billing/routes.py), lines 56–75, returns `growth` / `scale` IDs and `price_monthly` fields. The page matches `base` / `standard` / `premium` IDs and expects `ga_monthly` / `partner_monthly` fields (page lines 159–173). The ID sets are disjoint in this checkout, so the matching branch preserves static tiers for that response. Actual environment URLs, enabled routers, deployed revision and response payloads were not inspected.

3. **Actual charge, billing interval and discount remain UNKNOWN.** [Price resolution](../../../services/ingestion/app/stripe_billing/plans.py), lines 99–132, uses environment-backed Stripe Price IDs. An annual request falls back to a monthly Price ID when an annual ID is absent, while returned amount metadata still uses the annual catalog number. The [checkout creation](../../../services/ingestion/app/stripe_billing/routes.py), lines 176–191, passes the Price ID to Stripe. The Price object, not the hardcoded metadata amount, governs the charge. No environment secrets, Stripe account, invoice, coupon, checkout session or production payment was read or created. **L1 risk, no demonstrated incorrect customer charge.**

4. **Subscription usage response is not economic metering evidence. L1 source inspection.** [routes.py](../../../services/ingestion/app/stripe_billing/routes.py), lines 311–320, returns `events_used=0` and `facilities_used=0` for mapped subscriptions. [Settings defaults](../../../services/ingestion/app/settings.py), lines 84–91, instead supply a default Professional plan, $499 price, and 12,847 events. Neither value is treated as observed activity. This is not an assertion that no other telemetry exists; a tenant-month reconciliation from attempted → accepted → invoiced was not found in the surfaces reviewed.

5. **Prior price/revenue statements are dated or estimates. L1, documentary evidence only.** The [2026-05-13 pricing decision](../../decisions/2026-05-13-pilot-pricing.md), lines 5, 22–27, 48 and 53–60, calls itself draft, proposes free pilot/grandfather access and placeholder tiers, and claims zero pilots as of that date. It does not establish today's customer count. [Deployment cost estimates](../../operations/DEPLOYMENT.md), lines 374–385, describe an AWS ECS/Kafka layout; [README](../../../README.md), lines 20–23 and architecture section, describes the checked-in consolidated Railway target. The old $750 estimate is not a present bill. R2 estimates in [r2_provisioning.md](../../runbooks/r2_provisioning.md), lines 77–81, are also not invoices. No external current cloud-price claims are used in this model.

## Reproducible scenario assumptions

**All model results are L3: they hold only under the stated inputs.** $649/account-month is a scenario anchor copied from the Standard partner monthly source offer, not a validated willingness to pay or billing amount. The model does not change the offer. Every other dollar cost, case ratio, workload, capacity and growth input is deliberately hypothetical, including zero-valued inputs.

| Input | Illustrative baseline | What must replace it |
|---|---:|---|
| Price / collected account count | $649 / scenario-dependent | Settled invoices net of discounts, refunds and unpaid balances |
| Accepted CTEs per account-month in balanced scale case | 5,000 | Tenant workload distribution and facilities; not a tier cap |
| Attempts per accepted CTE | 1.1 | Rejections, deduplication, retries, failed writes and replay traffic |
| Compute / inference per attempt | $0.001 / $0 | Attributed runtime and any model invoices; zero inference is a chosen scenario, not a claim about all routes |
| Infrastructure usage / data writes per attempt | $0.0002 / $0.0005 | Measured database, cache, queue, network and object operations |
| Retained storage / event-month | $0.00001 | Bytes, indices, replicas, evidence objects, backups and retention periods |
| External transaction cost per attempt | $0 | Scoped integration/data charges, if any; unknown actual |
| Payment cost | 3% + $0.30/account invoice | Negotiated processor bills; this is not a Stripe pricing claim |
| Remediation cases / accepted CTE | 1%; 5 minutes/case | Measured provider and customer work separately |
| Routine support / account | 30 minutes/month | Ticket/work-log evidence |
| Human cost / flexible capacity | $60/hour / 20 hours/month | Fully loaded cash cost and actual capacity |
| Added service worker | $7,200/month for 120 service hours | Real hiring/contractor options and lead time |
| Platform capacity | $150 base; +$120 per additional 100,000 attempts/month | Measured database and application thresholds; no capacity benchmark claimed |
| Core overhead | $12,000/month | Payroll, product engineering, administration, compliance; excludes separately counted infrastructure/platform, support, onboarding and acquisition |
| Acquisition / onboarding | $1,000 cash + 8 hours = $1,480/new account | Sales labor, elapsed sales cycle, implementation logs and cash expense; includes no inferred demand |
| Failure / fraud / legal / incident expected cost | **UNKNOWN** | Incident frequencies, conditional losses, contractual exposure, insurance; JSON leaves expected values `null` |

The baseline loss allowance is zero solely to expose pre-risk economics. A separate $100/account/month allowance and $50,000 one-off loss are stress inputs, not expected losses or probability estimates. Tax, churn, bad debt, refunds, discounts, interest and unpaid founder time are not estimated. For the scenario, human service/onboarding is paid cash; core overhead excludes that cash to prevent double counting. If customers do remediation themselves, provider cost falls but customer workload and conversion/retention effects remain to be measured.

Monthly model identities (**L2**) are:

```text
attempts = accepted_CTEs × attempts_per_accepted_CTE
human_hours = accounts × routine_support_hours + remediation_cases × minutes / 60
staff = ceil(max(0, human_hours − flexible_capacity) / staff_capacity)
support_cost = hourly_cost × (flexible_hours_used + staff × staff_capacity)
contribution = revenue − usage/payment/data/loss_allowance − support_cost
service_surplus = contribution − reserved_platform_capacity
operating_surplus = service_surplus − core_overhead
marginal_service_surplus(N) = service_surplus(N) − service_surplus(N − 1)
```

Idle reserved staff and platform capacity are intentionally charged. No smooth scaling or cost-per-event constant is assumed. Storage in the scale table is one month's retained events; the time simulation accumulates retained history. Human hours are effort, **not processing latency**. Throughput, p95/p99 latency, queueing, maximum safe tenant size and provider-imposed capacity limits are UNKNOWN.

## Scale: revenue follows accounts, not raw event count

**L3, hypothetical monthly results, rounded.** Service surplus excludes $12,000 core overhead, acquisition/onboarding, tax and unmeasured risk. Both scenarios use the same $649 price; the balanced case *assumes* another paying account for every 5,000 events. This is an accounting contrast, not a customer acquisition model.

| Accepted CTEs/month | One account: revenue | One account: service surplus | Balanced case: assumed accounts | Balanced revenue | Balanced service surplus | Balanced human hours / reserved staff |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | $649 | $449.18 | 1 | $649 | $449.18 | 0.50 / 0 |
| 10 | $649 | $448.71 | 1 | $649 | $448.71 | 0.51 / 0 |
| 100 | $649 | $444.04 | 1 | $649 | $444.04 | 0.58 / 0 |
| 1,000 | $649 | $397.35 | 1 | $649 | $397.35 | 1.33 / 0 |
| 10,000 | $649 | −$69.57 | 2 | $1,298 | $529.66 | 9.33 / 0 |
| 100,000 | $649 | −$8,228.77 | 20 | $12,980 | $3,726.60 | 93.33 / 1 |
| 1,000,000 | $649 | −$54,200.77 | 200 | $129,800 | $63,816.00 | 933.33 / 8 |

**Does the millionth unit improve the economics?** Actual answer: UNKNOWN. In both illustrative event scenarios the millionth accepted event produces no incremental subscription revenue and reduces service surplus by $0.00188 while existing reserved labor absorbs its work. The first event in an existing paid account reduces service surplus by $0.05188 because flexible labor is paid by the hour. The millionth is less negative at this particular capacity point; both consume margin. This is not its long-run cost: labor demand rises another 0.05 minutes/event at the assumed defect ratio, and the next staffing threshold costs $7,200/month. In the separate account-growth mode, creating the first account and its first event yields $599.18 incremental service surplus against an already reserved $150 platform; that includes the first full account invoice and is not repeatable per-event revenue. A new paying account and another event from an existing account are economically different units. **L2/L3 conditional conclusion.**

At 5,000 events and one account, the hand calculation is: $649 revenue − $19.77 payment − $9.40 other usage/storage − $280 human time − $150 platform = **$189.83 service surplus**. Revenue/CTE is $0.1298, service cost/CTE $0.091834 and surplus/CTE $0.037966. One remediation case requires five minutes and $5 of flexible labor before idle-capacity effects. First-month service plus acquisition/onboarding requires **$1,939.17/account before collections**, excluding core overhead; including the entire one-account core budget gives $13,939.17. Simple service-surplus payback on $1,480 acquisition/onboarding is **7.80 months**, conditional on unchanged workload, complete collection, no churn and no staffing step. It is not measured CAC payback. **L2 arithmetic, not real economics.**

## Break-even, diseconomies and hidden phase transitions

**L3.** A bounded search considers 1–10,000 paid accounts at 5,000 events/account/month and recomputes staff and platform cost at each point. "No later loss" is only within this search, not a proof for unlimited scale. Break-even includes core overhead but excludes acquisition/onboarding, tax and unmeasured risk.

| Scenario change | First operating break-even accounts | No subsequent loss within search from | Operating surplus at 100 accounts |
|---|---:|---:|---:|
| Baseline | 46 | 57 | $19,233 |
| 5% remediation cases/event | Not found | Not found | −$81,567 |
| Human hourly cost doubles | 235 | 494 | −$10,767 |
| $0.05 inference / attempt | 210 | 317 | −$8,267 |
| $100 loss allowance / account-month | 54 | 83 | $9,233 |
| Scenario price halved to $324.50 | 672 | 1,034 | −$12,243.50 |

At the illustrative $649 price and 5,000 events/account, an average remediation ratio above approximately **2.36%** consumes all contribution even before platform/core costs and reserved-staff inefficiency: `(649 − 19.77 − 9.40 − 30) / (5000 × $5)`. **L2 conditional bound.** Thus a more important early measurement than cloud CPU price is who resolves a bad supplier record, how often, and how long it takes.

Relevant phase transitions are staff hiring, platform blocks, enterprise integrations/security review, large evidence history, customer concentration, bursts and mass remediation after changed rules or partner formats. The first two are represented explicitly; the others are UNKNOWN and must be measured. Viral non-paying usage, a single large flat-price tenant, or a correlated supplier-format failure can increase cost without proportional revenue. No network effects, additional capacity, or customer adoption are assumed to emerge from scale. **L1 hypotheses.**

## Time and cash survival

This is nontrading SaaS. A trading/compounding laboratory, market impact, slippage and return distributions would not match the production scope. Cash depletion, delayed collections, fixed commitments and incident exposure do apply. No loss/ruin probability can be estimated from the available evidence. **L1 scope judgment; probabilities UNKNOWN.**

**L3 conditional cash paths.** Starting cash is an invented $100,000 scenario input, not the founder's balance. Service periods are 30 days. Growth cases assume two paying accounts arrive on days 1, 31, 61, etc., all remain, and each generates 5,000 events per period. Invoices occur at period start; baseline collection delay is 30 days. Service/core costs, including hypothetical payment fees, are paid evenly each day; acquisition/onboarding is paid on arrival. This deliberately simple end-of-day ledger is not a cash-accounting forecast. Within-day cash timing, annual prepayment, financing and tax are omitted. Negative balances after the first depletion day describe an **unfunded counterfactual**, not continued feasible operation.

| Horizon | Zero adoption cash | Assumed two new accounts/period | Same growth, 90-day collection | Same growth, 5% remediation |
|---|---:|---:|---:|---:|
| Day 1 | $99,595 | $96,614 | $96,614 | $96,353 |
| Day 7 | $97,165 | $94,061 | $94,061 | $92,231 |
| Day 30 | $87,850 | $84,272 | $84,272 | $76,432 |
| Day 90 | $63,550 | $48,134 | $44,240 | $33,014 |
| Year 1 / day 365 | −$47,825 | −$77,224 | −$107,078 | −$241,144 |
| Year 3 / day 1,095 | −$343,475 | −$150,637 | −$242,795 | −$1,519,357 |
| First negative cash day | 247 | 169 | 153 | 129 |
| Minimum initial cash to fund entire modeled path | $443,475 | $288,209 | $368,710 | $1,619,357 |

Growth can initially shorten modeled survival because acquisition/onboarding and whole-worker costs precede collections. A separate hypothetical $50,000 cash loss on day 90 makes the baseline growth path first negative on day 90 and raises its required initial cash to $338,209. None of these are probabilities or predictions. Early support burden and collection timing dominate these examples; long-lived evidence storage accumulates through year 3. Churn, correlated incidents and price discounting could further change the outcome and were not fitted. **L3.**

## Highest-value next external experiment

**ECON-E1: one bounded, instrumented supplier workflow with explicit commercial terms — not yet executed. L0 hypothesis / L1 design.** First reconcile displayed price, backend plan, Stripe test Price currency/amount/interval, partner discount, facility scope and event/fair-use terms. This is a stop gate before charging a pilot; no paid offer is chosen by this report. Use synthetic Stripe test mode for the contract check. Real customer data also waits for the security/persistence gates in the main evidence report.

Then, with an authorized pilot customer and sanitized 100–500 representative rows, measure original attempts, accepted unique CTEs, repeated submissions, defects, provider minutes, customer minutes, retained bytes, export attempts and a tenant-attributed service bill. Record onboarding labor separately. Capture the agreed account price and eventual settled receipt separately from interest or signup. Keep the first observation to 90 minutes of founder time plus existing pilot infrastructure; this is a proposed attention cap, not a claim that the full workflow takes 90 minutes. No outreach, invitation, data transfer or charge was performed in this wave.

The experiment's decision value is replacing the dominant unknown labor/cost denominator while testing whether somebody accepts explicit commercial terms. Success is a reconciled price contract, reproduced accepted/exported outcome, complete time/cost ledger, and positive contribution under the observed workload with a stated incident allowance. Failure is a mismatched quote/charge, unbounded manual work, incomplete ledger or negative contribution. A settled receipt supports willingness to pay at that price for that customer only (potential L7), not broad demand. If access is unavailable, use an already authorized synthetic workbook for instrument validation and keep economics/demand UNKNOWN.

## Verification and handoff

Commands run from the isolated worktree:

```bash
python3 -B docs/research/evidence-wave-2026-08-31/economics_model.py --self-test
python3 -B docs/research/evidence-wave-2026-08-31/economics_model.py > docs/research/evidence-wave-2026-08-31/economics_results.json
python3 -m ruff check docs/research/evidence-wave-2026-08-31/economics_model.py
```

Passed five check groups: independent arithmetic for one account / 5,000 CTEs, staffing threshold, zero-adoption burn and day-247 depletion, first/millionth fixed-account events, and invalid negative/zero/fraction/NaN assumptions. A separate stdlib AST/regex check confirmed disjoint displayed/backend plan IDs, checkout mappings, backend catalog amounts and literal zero usage responses; this is an artifact check, not an HTTP/Stripe test. Python syntax and corrected marginal values in the generated JSON also passed. Ruff could not run: the available `python3` reports `No module named ruff`; no dependency was installed.

Independent reviewer `model_review` matched 14 monthly cases, all six sensitivity/break-even searches, five full cash paths and 30 snapshots using separate Fraction arithmetic and cohort-period cash sums. The review found and corrected a first-event comparison that mixed new account revenue into the fixed-account scenario; after correction, generated JSON exactly matched a fresh `report()` call and replication passed. This validates the arithmetic under assumptions (L2/L3), not those assumptions. No production test suite is required by the changed research surface; no production behavior is claimed verified by these checks.

- **Files changed:** this report, `economics_model.py`, `economics_results.json` only.
- **What changed:** added a cost ledger, deterministic scale/sensitivity model, temporal cash stress cases and a price-contract evidence map.
- **Tests run / what passed:** commands and five passing check groups above; source-contract assertions passed.
- **Not tested:** real billing, payment amount/interval, actual revenue/demand, cloud bills, production latency/load, tenant workload distribution, real support/remediation time, or calibrated tail losses.
- **Remaining risks:** unmeasured legal/incident exposure, staff lead time, acquisition/retention variability, unpaid customer labor, ambiguous commercial limits and mismatch between observed code and deployed configuration.
- **Recommended next step:** reconcile and sandbox-test the price contract, then execute ECON-E1 within existing authorization and the broader security gates; replace assumptions with measured unit costs before deciding whether to expand paid activity.
