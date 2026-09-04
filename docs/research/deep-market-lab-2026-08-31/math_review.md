# Independent economics verification

**Status: arithmetic and simulation mechanics pass; business calibration is not verified.** This is a docs-only sensitivity experiment. The inputs are invented hypotheses, not measured RegEngine costs, demand, cash reserves, or forecasts. No production application module, customer dataset, credential, billing system, or network service was used in this review.

Reviewed [simulate_economics.py](simulate_economics.py), [economics_inputs.json](economics_inputs.json), and [economics_results.json](economics_results.json). The independent checks are in [verify_economics.py](verify_economics.py).

## Corrections made during review

1. The original `mean_worst_5_percent` always selected the lowest values. That direction is adverse for contribution or terminal cash, but favorable for required capital and delivery hours. The simulation owner replaced it with explicit `mean_bottom_5_percent` and `mean_top_5_percent` and regenerated results. Use the **upper tail for cost, capital, and workload**, and the **lower tail for contribution/cash**.
2. Output labels originally hardcoded a 12-month acquisition allocation and month-24 censoring even though the horizons were configurable. The owner made those keys generic and added explicit `amortization_months` and `runway_horizon_months` metadata. Default numerical results did not change.

## Independently checked base calculation

| Monthly base calculation | Amount |
|---|---:|
| Hypothetical subscription revenue | $499.00 |
| Payments: $499 × 3.6% + $0.30 | $18.264 |
| Events: 50,000 × $0.0002 | $10.00 |
| Direct account cost | $50.00 |
| Imputed support: four hours × $50 | $200.00 |
| Modeled risk allowance | $15.00 |
| Service contribution | **$205.736 / 41.23%** |
| Acquisition plus onboarding: $1,000 + 12 hours × $50 | $1,600.00 once |
| Twelve-month allocation of that acquisition/onboarding cost | $133.333/month |
| Contribution after allocation | **$72.403/month** |

The resulting `ceil($300 / $72.403) = 5` accounts cover only the model's shared overhead after its imputed support and acquisition allocation. **Five accounts do not establish founder-sustainable cash break-even or business profitability.** Founder draw is correctly absent from this accounting calculation; adding the full draw on top of imputed founder delivery labor would mix accounting bases and could double-count that labor. Founder coding, administration, and other unallocated labor still matter.

The simple no-churn acquisition payback is `$1,600 / $205.736 = 7.78` paid service months. It excludes the free-access period, churn, payment delays, and time to acquisition. The support allowance for a 70% service contribution margin is **1.13 hours/account/month** under the remaining base costs; at four hours, the base misses that margin.

## Cash and paired-simulation checks

The cash model charges cash acquisition when an account is won. Founder service work within capacity is covered by the explicit $3,000 monthly founder draw; it is not separately charged at the imputed unit-economics hourly rate. Outsourced delivery above capacity is charged as cash expense. Onboarding adds delivery workload immediately, including for free accounts.

Capital required is the maximum cumulative month-end operating deficit over the modeled horizon. A path fails on the **first negative balance after adding its initial capital**. Later hypothetical recovery does not reverse that failure. Exact zero counts as no failure; the model adds no safety buffer. Terminal operating cash is calculated even after a path's first failure only to evaluate the amount of hypothetical financing required; it is not an investable survivor return.

The same seed and random demand/churn/incident outcomes are reused across free-access options. Account counts and workload therefore match, while billing timing differs. The test verifies that longer free access cannot improve the cash path under the configured prices and fee schedule. This comparison assumes that offer terms do not change acquisition, conversion, support, or retention.

At each price, account Monte Carlo uses the same cost draws. Moving from $499 to $999 therefore raises every contribution result by exactly `$500 × (1 − 3.6%) = $482`. Identical variances across those prices are expected from that construction. These are price sensitivities conditional on unchanged customers and costs, **not evidence that customers will accept a higher price**.

With seed `2040831`, 10,000 draws, 12-month acquisition allocation, and a 24-month runway horizon, the saved JSON reproduces exactly as parsed JSON using Python 3.12.2:

| Hypothetical runway outcome | Two free months | Twelve free months |
|---|---:|---:|
| Median required initial capital | $20,262 | $88,405 |
| 95th percentile required capital | $30,010 | $108,341 |
| Mean of highest 5% of capital requirements | $33,601 | $114,381 |
| Median terminal operating cash, assuming financing continues | $17,198 | −$88,290 |
| Paths avoiding negative month-end cash with $25,000 initial capital | 8,142/10,000 | 0/10,000 |
| Paths avoiding negative month-end cash with $50,000 initial capital | 10,000/10,000 | 0/10,000 |

These fractions describe this finite hypothetical experiment. They are not RegEngine survival probabilities. Zero failures in 10,000 draws does not establish impossibility of failure. The 5th–95th percentile interval describes simulated outcomes, not a confidence interval for an estimated business parameter. Variance is population variance of the simulated sample. Tail means include `ceil(5% × draws)` observations, which is exactly 500 for the default 10,000 draws.

## Material limitations

- The unit scenario uses $1,000 acquisition cost while runway uses $200 cash acquisition per win. These are separate assumptions; they are not a reconciled company P&L. Failed sales opportunities have no separate cash acquisition charge. Founder sales hours are tracked, but their opportunity cost is not an additional cash expense.
- Twelve-month acquisition allocation is a managerial sensitivity, not a claim of GAAP treatment or a churn-adjusted lifetime value. It does not guarantee 12 paying months per acquired account.
- The runway uses fixed service costs and a separate incident process, rather than sampling the account Monte Carlo's heavy-tailed customer costs. Its capital percentiles cannot be presented as incorporating all account-level tail risk.
- Month-end netting omits expense/payment timing within the month, credit terms, working capital, bad debt, cash buffers, financing friction, and failures to collect. Actual liquidity needs can be higher.
- Overflow delivery is assumed immediately available at a fixed rate with unlimited supply. No constraint verifies qualified help, management burden, founder development time, or operational feasibility.
- Free periods begin at onboarding. A promise measured from a later GA date can produce a longer unpaid period. This test does not interpret or change commercial commitments.
- Prices come from conflicting displayed/configured repository values. Accepted pricing, actual Stripe settings, elasticity, and willingness to pay were not verified in this math review. Payment rates and cost assumptions were not independently market-validated here.
- Inputs are trusted local scenario files, not a hardened public API. Invalid/empty inputs and unsupported parameter domains were not comprehensively tested. Cross-version Python random-number reproducibility was not verified.

## Verification record

Run from the repository root:

```bash
.venv/bin/python3 docs/research/deep-market-lab-2026-08-31/verify_economics.py
```

**13/13 tests passed.** Tests cover independent base arithmetic; nonpositive contribution/payback; zero collection fees; quantiles, population variance, and tail direction; zero wins; churn zero and one; zero/one/two/four free-month timing; overflow costs; incident churn clamping, revenue haircut, fees and cash loss; founder labor versus draw; paired price and free-term semantics; first cash failure despite later recovery; exact-zero cash; horizon metadata; and full saved-result regeneration into an isolated temporary directory. No output fixture is overwritten during verification.

- **Files changed by this review:** `verify_economics.py`, `math_review.md`. The simulation owner applied the two output-label fixes described above.
- **What changed:** added independent boundary and reproducibility checks; documented arithmetic, accounting distinctions, and modeling limits.
- **Tests run / what passed:** the command above passed all 13 tests; no application dependency or external infrastructure was required.
- **What was not tested:** real customer data, production infrastructure, billing integration, actual cash balances, measured cost distributions, commercial conversion, or frontend/backend behavior.
- **Remaining risks:** uncalibrated inputs, omitted dependencies and liquidity timing, price/offer inconsistency, and treating conditional model outputs as business probabilities.
- **Recommended next step:** measure onboarding/support time and direct cash cost from a small authorized pilot, reconcile one commercial offer, then rerun these same calculations with observed ranges before making spend or funding decisions.
