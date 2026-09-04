"""Offline sensitivity analysis. No customer data, network, or project imports.

Run with python3 simulate_economics.py. Outputs deterministic JSON next to this
file. Probabilities describe invented distributions, never company forecasts.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def quantile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    x = (len(ordered) - 1) * p
    lo, hi = math.floor(x), math.ceil(x)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (x - lo)


def describe(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "variance": statistics.pvariance(values),
        **{f"p{p}": quantile(values, p / 100) for p in (5, 25, 75, 95)},
        "mean_bottom_5_percent": statistics.mean(sorted(values)[: max(1, math.ceil(len(values) * 0.05))]),
        "mean_top_5_percent": statistics.mean(sorted(values)[-max(1, math.ceil(len(values) * 0.05)) :]),
        "negative_fraction": sum(x < 0 for x in values) / len(values),
    }


def fees(price: float, cfg: dict) -> float:
    return price * cfg["payment_percent"] + (cfg["payment_fixed_usd"] if price else 0)


def unit(s: dict, cfg: dict) -> dict:
    labor = cfg["labor_usd_hour"]
    variable = (
        fees(s["price"], cfg)
        + s["events"] * s["event_cost"]
        + s["direct_account_cost"]
        + s["support_hours"] * labor
        + s["monthly_risk_cost"]
    )
    contribution = s["price"] - variable
    acquisition = s["cac"] + s["onboarding_hours"] * labor
    after_allocation = contribution - acquisition / cfg["amortization_months"]
    fixed = cfg["fixed_cash_usd_month"]
    return {
        "revenue": s["price"],
        "variable_cost_including_imputed_support": variable,
        "service_contribution": contribution,
        "service_margin": contribution / s["price"],
        "contribution_after_onboarding_and_cac_allocation": after_allocation,
        "allocated_fixed_cost_break_even_accounts": math.ceil(fixed / after_allocation)
        if after_allocation > 0
        else None,
        "simple_payback_months_no_churn": acquisition / contribution if contribution > 0 else None,
        "support_hours_for_70_percent_service_margin": (
            0.3 * s["price"]
            - fees(s["price"], cfg)
            - s["events"] * s["event_cost"]
            - s["direct_account_cost"]
            - s["monthly_risk_cost"]
        )
        / labor,
    }


def account_draw(rng: random.Random, cfg: dict) -> dict:
    d = cfg["account_distributions"]
    events = rng.lognormvariate(math.log(d["events_lognormal_median"]), d["events_log_sigma"])
    cost = rng.lognormvariate(math.log(d["event_cost_lognormal_median"]), d["event_cost_log_sigma"])
    support = rng.lognormvariate(math.log(d["support_lognormal_median_hours"]), d["support_log_sigma"])
    support *= (events / d["events_lognormal_median"]) ** d["support_volume_elasticity"]
    stress = rng.random() < d["stress_probability"]
    if stress:
        support *= d["stress_support_multiplier"]
        cost *= d["stress_event_cost_multiplier"]
    blocks = max(0, math.ceil(events / d["extra_capacity_block_events"]) - 1)
    low, mode, high = d["cac_triangular_min_mode_max"]
    return {
        "events": events,
        "event_cost": cost,
        "support_hours": support,
        "direct_account_cost": d["direct_account_usd"] + blocks * d["extra_capacity_block_usd"],
        "onboarding_hours": d["onboarding_fixed_hours"] + d["onboarding_support_multiple"] * support,
        "monthly_risk_cost": d["monthly_risk_base_usd"] + stress * d["stress_loss_usd"],
        "cac": rng.triangular(low, high, mode),
    }


def runway_path(seed: int, free_months: int, cfg: dict) -> dict:
    """Cash excludes imputed founder labor; includes founder draw and overflow hire.

    Generate an UNFINANCED path through month 24 even after negative cash, solely
    to compute required initial capital. Insolvency is the first crossing, not
    a recoverable event; terminal net cash must not be called survivor return.
    """
    rng = random.Random(seed)
    r = cfg["runway"]
    cohorts = []
    cumulative = 0.0
    path, delivery, total_hours = [], [], []
    for month in range(1, r["months"] + 1):
        incident = rng.random() < r["monthly_incident_probability"]
        churn = min(1, r["monthly_churn"] * (r["incident_churn_multiplier"] if incident else 1))
        cohorts = [born for born in cohorts if rng.random() >= churn]
        wins = sum(rng.random() < r["win_probability"] for _ in range(r["qualified_opportunities_per_month"]))
        cohorts.extend([month] * wins)
        paid = sum(month - born >= free_months for born in cohorts)
        price = r["price"] * (1 - r["incident_revenue_haircut"] if incident else 1)
        revenue = paid * price
        service_hours = len(cohorts) * r["support_hours_per_customer_month"] + wins * r["onboarding_hours_per_win"]
        overflow = max(0, service_hours - r["founder_delivery_capacity_hours"])
        cash_cost = (
            cfg["fixed_cash_usd_month"]
            + cfg["founder_draw_usd_month"]
            + len(cohorts) * r["direct_cash_per_customer_month"]
            + wins * r["cac_cash_per_win"]
            + overflow * r["outsourced_delivery_usd_hour"]
            + paid * fees(price, cfg)
            + incident * r["incident_cash_cost"]
        )
        cumulative += revenue - cash_cost
        path.append(cumulative)
        delivery.append(service_hours)
        total_hours.append(
            min(service_hours, r["founder_delivery_capacity_hours"])
            + r["qualified_opportunities_per_month"] * r["opportunity_sales_hours"]
        )
    return {
        "unfinanced_cumulative_cash": path,
        "capital_required": max(0, -min(path)),
        "terminal_net_operating_cash": cumulative,
        "max_delivery_hours": max(delivery),
        "max_founder_delivery_plus_sales_hours": max(total_hours),
        "terminal_accounts": len(cohorts),
    }


def main() -> None:
    cfg = json.loads((ROOT / "economics_inputs.json").read_text())
    rng = random.Random(cfg["seed"])
    draws = [account_draw(rng, cfg) for _ in range(cfg["draws"])]
    account_results = {}
    for price in cfg["prices_usd_monthly"]:
        results = [unit({**d, "price": price}, cfg) for d in draws]
        account_results[str(price)] = {
            "service_contribution_usd": describe([x["service_contribution"] for x in results]),
            "after_acquisition_allocation_usd": describe(
                [x["contribution_after_onboarding_and_cac_allocation"] for x in results]
            ),
        }
    runway_results = {}
    for free in cfg["runway"]["free_months_options"]:
        paths = [runway_path(cfg["seed"] + i, free, cfg) for i in range(cfg["draws"])]
        capital_results = {}
        for capital in cfg["runway"]["capital_sensitivities_usd"]:
            failures = [
                next((m + 1 for m, cash in enumerate(p["unfinanced_cumulative_cash"]) if cash + capital < 0), None)
                for p in paths
            ]
            failed_times = [m for m in failures if m is not None]
            capital_results[str(capital)] = {
                "failure_fraction": len(failed_times) / len(paths),
                "survival_fraction": 1 - len(failed_times) / len(paths),
                "median_first_failure_month_conditional_on_failure": statistics.median(failed_times)
                if failed_times
                else None,
                "censored_no_failure_by_horizon": len(paths) - len(failed_times),
            }
        runway_results[str(free)] = {
            "capital_required_usd": describe([p["capital_required"] for p in paths]),
            "terminal_net_operating_cash_usd_assuming_financing_continues": describe(
                [p["terminal_net_operating_cash"] for p in paths]
            ),
            "max_delivery_hours": describe([p["max_delivery_hours"] for p in paths]),
            "max_founder_delivery_plus_sales_hours": describe(
                [p["max_founder_delivery_plus_sales_hours"] for p in paths]
            ),
            "terminal_accounts": describe([p["terminal_accounts"] for p in paths]),
            "capital_sensitivity": capital_results,
        }
    sensitivity = {}
    for price in cfg["prices_usd_monthly"]:
        for hours in [1, 4, 12]:
            sensitivity[f"price_{price}_support_{hours}h"] = unit(
                {**cfg["scenarios"]["base"], "price": price, "support_hours": hours}, cfg
            )
    result = {
        "evidence_status": cfg["evidence_status"],
        "seed": cfg["seed"],
        "draws_per_experiment": cfg["draws"],
        "amortization_months": cfg["amortization_months"],
        "runway_horizon_months": cfg["runway"]["months"],
        "scenarios": {name: unit(s, cfg) for name, s in cfg["scenarios"].items()},
        "account_monte_carlo": account_results,
        "runway_monte_carlo_by_free_months": runway_results,
        "price_support_sensitivity": sensitivity,
        "limitations": [
            "Distributions, conversion, churn, labor, budget, cost, incident rate and capacity are invented stress assumptions.",
            "No posterior calibration or observed customer sample; reported fractions are not real-world probabilities.",
            "Account draws share volume/support and incident dependence, but not all real dependencies or tail events.",
            "Same demand distribution at different prices; price elasticity, procurement, growth and referrals not modeled.",
            "Runway assumes unlimited ability to hire overflow help at stated rate; missing expertise can make capacity infeasible.",
            "Founder draw is assumed cash need, not known finances; 80 delivery hours excludes sales, coding and administration.",
            "Annual upfront billing, taxes, refunds outside modeled shock, chargebacks, financing and legal liability are excluded.",
            "12-month free comparison starts at onboarding, not unknown GA date; a post-GA promise can cost more.",
            "Event cost and capacity blocks do not measure application throughput or cloud bills.",
            "Cash is netted monthly; intramonth liquidity is omitted and exact zero cash has no safety buffer.",
        ],
    }
    out = ROOT / "economics_results.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {out.name}: {cfg['draws']} account draws and {cfg['draws']} paired paths per free-term option.")


if __name__ == "__main__":
    main()
