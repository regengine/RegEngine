# Economics: contribution, support capacity, and cash exposure

**Verdict: economic viability is UNKNOWN.** The reproducible model finds conditions under which the proposed price can work and conditions under which additional customers increase losses. It does not estimate which conditions RegEngine will actually encounter. All amounts are USD. Research date: August 31, 2026.

The meaningful units are **paying organization-month**, **new customer onboarding**, **accepted CTE event**, **retained evidence-year**, and **completed operator outcome**. An event counter is not a measure of customer value. One million events at one customer is not one million paying users.

## What is observed and what is assumed

Inspected [public pricing](../../../frontend/src/app/pricing/page.tsx) advertises Base partner pricing of $499 monthly, or $425 monthly equivalent billed annually. Inspected [billing definitions](../../../services/ingestion/app/stripe_billing/plans.py) instead list Growth at $999 monthly and Scale at $1,999. The [May pilot decision](../../decisions/2026-05-13-pilot-pricing.md) contains a free-pilot/free-year offer. These are conflicting proposals/configuration, not verified receipts or willingness to pay. The model compares $499/$999/$1,999 without selecting a new price or modifying any commitment. See [product contract findings](product.md).

[Stripe's US Billing price page](https://stripe.com/billing/pricing), accessed August 31, lists 0.7% of Billing volume, and separately 2.9% plus $0.30 for a successful card charge. The model combines those into 3.6% plus $0.30 for monthly domestic-card billing. Actual negotiated rates, tax products, international cards, disputes, bank payments, and annual payment timing are not modeled. Direct pricing-page requests redirected to other country pages; the US Billing page explicitly showed the values used here.

Infrastructure has usage and capacity costs, not a fixed universal price per event. [Railway](https://railway.com/pricing) lists a $20 Pro minimum including usage, with CPU, memory, storage and network metering; [Vercel](https://vercel.com/pricing) lists Pro at $20/month plus applicable usage. Those published rates do not reveal RegEngine's actual bill. The model's $300/month overhead and per-event charges are **stress assumptions**, not estimates derived from those prices. No production bills, token usage, cloud configuration, account balance, paid customers, or actual founder compensation were accessed.

Every input is preserved in [economics_inputs.json](economics_inputs.json). In particular, labor at $50/hour, 12-month amortization, conversion, churn, incidents and $3,000 monthly founder draw are invented sensitivity inputs. The founder's actual finances remain unknown.

## Derivation and four scenarios

For monthly price `P`, events `V`, cost per event `c`, direct account service cost `D`, support hours `h`, hourly labor value `w`, and risk allowance `R`:

```text
fees(P) = 0.036 P + 0.30                         (P > 0)
service contribution = P - fees(P) - Vc - D - hw - R
allocated contribution = service contribution - (CAC + onboarding_hours*w)/12
overhead-only break-even = ceil(300 / allocated contribution), if positive
simple acquisition payback = (CAC + onboarding_hours*w)/service contribution
```

This is a defined contribution view, not GAAP profit. The imputed support labor is an economic cost even when the founder is unpaid. Acquisition amortization is a management allocation, not cash timing. Fixed engineering, administration, taxes and full incident liability are outside this unit calculation. A negative support budget means the margin target is infeasible even with zero support.

| Scenario | Price / events per month | Support hours | Service contribution | After onboarding/CAC allocation | Payback, no churn |
|---|---:|---:|---:|---:|---:|
| Optimistic | $999 / 5,000 | 1 | $882.49 (88.3%) | $824.15 | 0.79 months |
| Base | $499 / 50,000 | 4 | $205.74 (41.2%) | $72.40 | 7.78 months |
| Pessimistic | $499 / 250,000 | 12 | -$569.26 | -$944.26 | Never under these constants |
| Catastrophic | $499 / 1,000,000 | 40 | -$5,219.26 | -$5,969.26 | Never under these constants |

Other costs also vary between these scenarios; the table is not a causal experiment isolating price. Exact components are in the input JSON. No probability is assigned to these four states.

**Numerical check of the base case:** fees are $18.264; event processing is $10; direct service is $50; support is $200; risk allowance is $15. Subtracting $293.264 from $499 leaves $205.736. $1,000 CAC plus 12 onboarding hours at $50 is $1,600, or $133.333/month over twelve months. Residual is $72.4027. Five accounts cover only the assumed $300 shared overhead on that allocation: **this does not mean five customers support the founder or fund the company**.

For 70% service margin under base non-support costs:

```text
h_max = (0.30*499 - 18.264 - 10 - 50 - 15)/50 = 1.12872 hours/month
```

The four-hour base exceeds that budget. The result excludes acquisition recovery, so the complete economic envelope is tighter. This conditional threshold is more useful than an unsupported claim that hosting will be cheap. A measured low-support workflow or accepted higher price would falsify the pessimistic concern; actual delivery exceeding this envelope would falsify the intended margin.

## Monte Carlo: sensitivity, not forecast

[simulate_economics.py](simulate_economics.py) runs 10,000 seeded account draws using lognormal volume, cost and support distributions; support grows with volume to the power 0.2. An assumed 5% stress branch increases support fourfold, event costs fivefold and adds a loss. Extra capacity costs step up above each assumed 250,000-event block. CAC is triangular between $200 and $4,000 with mode $1,000. These choices deliberately expose skew, dependence and step costs; they are **not fitted distributions**.

The same draws are used at each price. This isolates price arithmetic; it does **not** model the lower conversion or higher expectations that a higher price might cause.

| Monthly price | Mean allocated contribution | Median | P5 | P95 | Fraction negative in assumed draws |
|---|---:|---:|---:|---:|---:|
| $499 | -$97.52 | $34.79 | -$886.30 | $254.18 | 43.49% |
| $999 | $384.48 | $516.79 | -$404.30 | $736.18 | 10.37% |
| $1,999 | $1,348.48 | $1,480.79 | $559.70 | $1,700.18 | 2.34% |

At $499, the average of the bottom 5% is -$1,721.54. A positive median coexists with a negative mean because the assumed costly cases are severe. The [full results](economics_results.json) include mean, median, variance, P5/P25/P75/P95, upper/lower tail averages and negative fractions. Tail direction matters: low contribution is adverse, while high capital requirements are adverse. Independent review caught an initial generic “worst tail” label; the artifact now stores both tails explicitly.

**Reality Level 2:** formulas and their arithmetic. **Level 3:** hypothetical stochastic outcomes. **UNKNOWN:** real contribution, acquisition distribution, causal effect of price, lifetime value and business failure probability. Another random seed does not replace real data. Independence review of the code is not independent evidence for the economic assumptions.

## Cash survival and free-access obligations

A separate 24-month path model uses 12 qualified opportunities/month, 12% win probability, 2% monthly churn, $499 monthly receipts after a free period, $60 direct cash cost/customer/month, $200 cash acquisition cost/win and $3,300 fixed monthly cash outflow including the assumed founder draw. Delivery uses 12 onboarding hours/win plus four support hours/customer/month. Work beyond 80 delivery hours/month is assumed purchasable at $50/hour. Sales time and development/admin capacity remain additional constraints. A 1.5% monthly common incident branch reduces receipts and raises churn/costs.

The unit model's $1,000 CAC and this path model's $200 cash CAC are **different hypotheses**, not a reconciled accounting forecast. Founder delivery within capacity is not charged again at an imputed hourly rate because the cash model already includes the draw. Hiring available help at a known rate is itself unverified.

| Free service from onboarding | Median minimum capital over 24 months | P95 capital | Mean highest-cost 5% capital | Failure fraction with assumed $25,000 initial cash |
|---|---:|---:|---:|---:|
| 2 months | $20,262 | $30,010 | $33,601 | 18.58% of simulated paths |
| 12 months | $88,405 | $108,341 | $114,381 | 100% of simulated paths |

For $25,000 capital, median first shortfall is month 10 among failing two-month paths, and month 7 among twelve-month paths. No-failure paths are censored at month 24; they are not infinitely surviving businesses. A post-GA free-year commitment may start later than this model and cost more. Existing customer promises, if any, must be honored; this analysis does not revoke them.

Capital required is `max(0, -min(cumulative monthly cash flows))`. The simulation continues the unfinanced cash path after a shortfall only to calculate required financing, never to treat insolvency as reversible. End-of-horizon cash is labeled accordingly. Month-end netting omits within-month liquidity needs, and exact zero counts as survival without a safety buffer. The runway uses fixed account service costs rather than importing all account Monte Carlo tail risks. This illustrates why positive account contribution does not establish survival. **These are conditional stress fractions, not estimates of RegEngine's chance of failure.**

## Scaling economics and the millionth unit

At flat subscription revenue, one more event inside the same allowance adds zero revenue and generally some processing, storage or remediation cost. With public Base overage of $0.002/event, marginal contribution is `0.002 - incremental total cost`; it can be negative even before support. New tenants also bring onboarding and support, so scaling accounts and scaling events are different experiments.

Economies may come from reusable mappings, batching and amortizing shared overhead. Diseconomies come from long retained history, concentrated tenant locks, complete-history verification, capacity steps, support queues and simultaneous recalls. The [scaling review](scaling.md) derives six volume levels without pretending to benchmark the millionth event. At one million events/day, average traffic is only 11.57 events/second, but two years at an assumed 8 KiB/event is approximately 5,569 GiB before backups and other amplification. Observed throughput, bytes/event and marginal cloud costs are unknown.

The millionth event is **not proven better or worse** than the first in total economics. It may have lower marginal compute cost while generating negative marginal contribution; an account's accumulated history may make exports more expensive. Do not offer unlimited service, lifetime price guarantees or an SLA without a measured envelope.

## Verification, unknowns and next experiment

Run from repo root:

```sh
.venv/bin/python3 docs/research/deep-market-lab-2026-08-31/simulate_economics.py
.venv/bin/python3 docs/research/deep-market-lab-2026-08-31/verify_economics.py
```

[Independent math review](math_review.md) documents boundary tests and reproducibility. The script uses standard-library Python, no network, production imports, credentials or new dependencies. Generated JSON is checked in with the hypotheses for review, not promoted into business telemetry.

**Next experiment:** time one authorized operator file, classify rejected/missing records, measure founder and customer minutes separately, record actual provider resource deltas, and obtain a buyer-accepted bounded offer. Repeat on another file and operator. Stop broad economic modeling until those observations can replace the dominant assumptions. Expected liability, tax treatment, cash balances, support willingness, lifetime value, cancellation custody and price elasticity remain unknown; they can materially overturn this model.
