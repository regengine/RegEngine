"""Illustrative RegEngine economics, NOT measured costs, demand, or a forecast.

Stdlib only; run with python3 -B. All dollar amounts are hypothetical USD.
649 is anchored to the checked-in Standard partner monthly offer, not a receipt.
Risk allowances are scenario inputs, not calibrated expected losses. Revenue is
earned evenly; the cash model collects whole invoices after an explicit delay.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from math import ceil, isclose, isfinite


@dataclass(frozen=True)
class Inputs:
    account_month_price: float = 649.0
    events_per_account_month: int = 5000
    attempts_per_accepted_event: float = 1.1
    compute_per_attempt: float = 0.001
    inference_per_attempt: float = 0.0
    infrastructure_per_attempt: float = 0.0002
    data_write_per_attempt: float = 0.0005
    storage_per_retained_event_month: float = 0.00001
    external_transaction_per_attempt: float = 0.0
    payment_fraction: float = 0.03
    payment_per_invoice: float = 0.30
    remediation_cases_per_accepted_event: float = 0.01
    remediation_minutes_per_case: float = 5.0
    routine_support_hours_per_account: float = 0.5
    human_hour_cost: float = 60.0
    flexible_human_hours: float = 20.0
    employee_service_hours_per_month: float = 120.0
    infrastructure_base_month: float = 150.0
    attempts_per_infrastructure_block: int = 100000
    additional_infrastructure_block_month: float = 120.0
    core_overhead_month: float = 12000.0
    onboarding_hours_per_new_account: float = 8.0
    acquisition_cash_per_new_account: float = 1000.0
    loss_allowance_per_account_month: float = 0.0


def validate(p: Inputs) -> None:
    for name, value in asdict(p).items():
        if not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and nonnegative")
    for name in ("events_per_account_month", "employee_service_hours_per_month", "attempts_per_infrastructure_block"):
        if getattr(p, name) <= 0:
            raise ValueError(f"{name} must be positive")
    if p.attempts_per_accepted_event < 1 or p.payment_fraction > 1:
        raise ValueError("attempts must be >=1 and payment fraction <=1")


def monthly(events: int, accounts: int, p: Inputs, retained_events: float | None = None) -> dict:
    """Steady service month; acquisition/onboarding are separate one-time costs.

    Every account is assumed paying and active for a whole month. This is a
    scenario, not inferred demand. No customer count is inferred from real data.
    Default retained stock is one month's events; temporal model accumulates it.
    """
    validate(p)
    if events < 0 or accounts < 0 or (events > 0 and accounts == 0):
        raise ValueError("events/accounts must be nonnegative; events need account")
    retained = float(events) if retained_events is None else retained_events
    if not isfinite(retained) or retained < 0:
        raise ValueError("retained_events must be finite and nonnegative")
    attempts = events * p.attempts_per_accepted_event
    revenue = accounts * p.account_month_price
    cases = events * p.remediation_cases_per_accepted_event
    hours = accounts * p.routine_support_hours_per_account + (cases * p.remediation_minutes_per_case / 60)
    flexible_hours = min(hours, p.flexible_human_hours)
    staff = ceil(max(0, hours - flexible_hours) / p.employee_service_hours_per_month)
    human_cost = p.human_hour_cost * (flexible_hours + staff * p.employee_service_hours_per_month)
    blocks = max(1, ceil(attempts / p.attempts_per_infrastructure_block))
    variable = {
        "compute": attempts * p.compute_per_attempt,
        "inference": attempts * p.inference_per_attempt,
        "infrastructure_usage": attempts * p.infrastructure_per_attempt,
        "data_write": attempts * p.data_write_per_attempt,
        "retained_storage": retained * p.storage_per_retained_event_month,
        "external_transaction": attempts * p.external_transaction_per_attempt,
        "payment": revenue * p.payment_fraction + accounts * p.payment_per_invoice,
        "loss_allowance_not_expected_loss": accounts * p.loss_allowance_per_account_month,
    }
    contribution = revenue - sum(variable.values()) - human_cost
    platform_cost = p.infrastructure_base_month + (blocks - 1) * p.additional_infrastructure_block_month
    service_surplus = contribution - platform_cost
    operating = service_surplus - p.core_overhead_month
    service_cost = revenue - service_surplus
    out = {
        "accepted_events": events,
        "paid_accounts": accounts,
        "attempts": attempts,
        "retained_event_stock": retained,
        "revenue": revenue,
        "variable_cost_components": variable,
        "remediation_cases": cases,
        "human_hours": hours,
        "reserved_staff": staff,
        "support_cost_including_idle_capacity": human_cost,
        "reserved_human_hours": flexible_hours + staff * p.employee_service_hours_per_month,
        "infrastructure_blocks": blocks,
        "platform_capacity_cost": platform_cost,
        "contribution_before_platform_and_core": contribution,
        "service_surplus_before_core_overhead": service_surplus,
        "service_margin_before_core_overhead": service_surplus / revenue if revenue else None,
        "operating_surplus_before_tax_and_unmeasured_risk": operating,
        "total_service_cost": service_cost,
        "total_operating_cost": service_cost + p.core_overhead_month,
        "revenue_to_operating_cost": revenue / (service_cost + p.core_overhead_month)
        if service_cost + p.core_overhead_month
        else None,
        "expected_failure_cost": None,
        "expected_fraud_abuse_cost": None,
        "expected_incident_legal_risk_cost": None,
        "one_time_acquisition_and_onboarding_per_new_account": (
            p.acquisition_cash_per_new_account + p.onboarding_hours_per_new_account * p.human_hour_cost
        ),
    }
    for unit, count in (("per_accepted_event", events), ("per_account_month", accounts)):
        out[unit] = {
            "revenue": revenue / count if count else None,
            "service_cost": service_cost / count if count else None,
            "service_surplus": service_surplus / count if count else None,
            "human_hours": hours / count if count else None,
            **{name: cost / count if count else None for name, cost in variable.items()},
            "support": human_cost / count if count else None,
            "platform_capacity": platform_cost / count if count else None,
        }
    return out


def breakeven(p: Inputs, max_accounts: int = 10000) -> dict:
    """Find first operating break-even and later reversals over a bounded range."""
    first = None
    last_loss = 0
    for accounts in range(1, max_accounts + 1):
        value = monthly(accounts * p.events_per_account_month, accounts, p)
        if value["operating_surplus_before_tax_and_unmeasured_risk"] >= 0:
            first = first or accounts
        else:
            last_loss = accounts
    return {
        "first_break_even_accounts": first,
        "no_later_loss_from_accounts_within_search": last_loss + 1 if last_loss < max_accounts else None,
        "search_max_accounts": max_accounts,
        "events_per_account_month_assumption": p.events_per_account_month,
    }


def cash_path(
    p: Inputs,
    new_accounts_per_30_days: int,
    collection_delay_days: int,
    initial_cash: float = 100000,
    shock_day: int | None = None,
    shock_loss: float = 0,
) -> dict:
    """Daily cash ledger; a negative balance is infeasible without new funding.

    30-day service periods; invoices occur at period start, collection is delayed.
    All modeled ongoing costs are paid daily (including assumed human cash pay).
    No churn, bad debt, tax, funding, interest or retention deletion is assumed.
    Full path continues after insolvency solely to expose required financing.
    """
    accounts = 0
    retained = 0.0
    cash = initial_cash
    peak = cash
    minimum = cash
    drawdown = 0.0
    first_negative = None
    receivables: dict[int, float] = {}
    snapshots = []
    month_cost = None
    for day in range(1, 1096):
        if (day - 1) % 30 == 0:
            accounts += new_accounts_per_30_days
            bill = accounts * p.account_month_price
            due = day + collection_delay_days
            receivables[due] = receivables.get(due, 0) + bill
            cash -= new_accounts_per_30_days * (
                p.acquisition_cash_per_new_account + p.onboarding_hours_per_new_account * p.human_hour_cost
            )
        events = accounts * p.events_per_account_month
        retained += events / 30
        month_cost = monthly(events, accounts, p, retained_events=retained)
        cash += receivables.pop(day, 0)
        cash -= month_cost["total_operating_cost"] / 30
        if day == shock_day:
            cash -= shock_loss
        minimum = min(minimum, cash)
        peak = max(peak, cash)
        drawdown = max(drawdown, peak - cash)
        if cash < 0 and first_negative is None:
            first_negative = day
        if day in (1, 7, 30, 90, 365, 1095):
            snapshots.append(
                {
                    "day": day,
                    "paying_accounts_assumed": accounts,
                    "cash": cash,
                    "human_hours_per_month": month_cost["human_hours"],
                    "retained_events": retained,
                }
            )
    return {
        "new_accounts_per_30_days": new_accounts_per_30_days,
        "collection_delay_days": collection_delay_days,
        "initial_cash_assumption": initial_cash,
        "shock_day": shock_day,
        "shock_loss_assumption": shock_loss,
        "first_negative_cash_day": first_negative,
        "minimum_cash": minimum,
        "maximum_cash_drawdown": drawdown,
        "minimum_initial_cash_to_fund_whole_path": initial_cash - minimum if minimum < initial_cash else 0,
        "extra_capital_above_assumed_initial_cash": max(0, -minimum),
        "probability_of_ruin": None,
        "survival_probability": None,
        "snapshots": snapshots,
    }


def self_test() -> list[str]:
    p = Inputs()
    # Independent arithmetic for one account with 5,000 events (no staffing step).
    a = monthly(5000, 1, p)
    assert isclose(a["human_hours"], 14 / 3)
    assert isclose(a["support_cost_including_idle_capacity"], 280)
    assert isclose(sum(a["variable_cost_components"].values()), 29.17)
    assert isclose(a["service_surplus_before_core_overhead"], 189.83)
    # A fractional hour beyond flexible capacity requires a whole worker.
    assert monthly(0, 40, p)["reserved_staff"] == 0
    assert monthly(0, 41, p)["reserved_staff"] == 1
    # No adoption has no revenue, support or payment fees; platform still burns.
    assert monthly(0, 0, p)["total_operating_cost"] == 12150
    assert cash_path(p, 0, 0)["first_negative_cash_day"] == 247
    # Fixed-account extra events cannot produce new subscription revenue.
    first = monthly(1, 1, p)["service_surplus_before_core_overhead"]
    empty = monthly(0, 1, p)["service_surplus_before_core_overhead"]
    assert isclose(first - empty, -0.05188)
    a, b = monthly(999999, 1, p), monthly(1000000, 1, p)
    assert a["revenue"] == b["revenue"]
    assert b["service_surplus_before_core_overhead"] < a["service_surplus_before_core_overhead"]
    for bad in (
        replace(p, human_hour_cost=-1),
        replace(p, attempts_per_infrastructure_block=0),
        replace(p, payment_fraction=1.1),
        replace(p, compute_per_attempt=float("nan")),
    ):
        try:
            monthly(1, 1, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid assumption accepted")
    return [
        "one-account hand calculation",
        "staffing boundary",
        "zero-adoption burn/runway",
        "millionth fixed-account event",
        "negative/zero/fraction/NaN inputs",
    ]


def report() -> dict:
    p = Inputs()
    scales = (1, 10, 100, 1000, 10000, 100000, 1000000)
    rows = []
    for mode in ("one_account_fixed_revenue", "one_account_per_5000_events"):
        for n in scales:
            accounts = 1 if mode == "one_account_fixed_revenue" else ceil(n / p.events_per_account_month)
            row = monthly(n, accounts, p)
            previous_accounts = 1 if mode == "one_account_fixed_revenue" else ceil((n - 1) / p.events_per_account_month)
            previous = monthly(n - 1, previous_accounts, p)
            row["mode"] = mode
            row["last_event_marginal_service_surplus"] = (
                row["service_surplus_before_core_overhead"] - previous["service_surplus_before_core_overhead"]
            )
            rows.append(row)
    variants = {
        "illustrative_base": p,
        "five_percent_remediation": replace(p, remediation_cases_per_accepted_event=0.05),
        "double_human_hour_cost": replace(p, human_hour_cost=120),
        "inference_5_cents_each_attempt": replace(p, inference_per_attempt=0.05),
        "loss_allowance_100_per_account": replace(p, loss_allowance_per_account_month=100),
        "price_halved": replace(p, account_month_price=324.5),
    }
    return {
        "status": "HYPOTHETICAL: not forecast or actual unit economics",
        "economic_reality_level": 3,
        "inputs": asdict(p),
        "self_checks": self_test(),
        "scale": rows,
        "sensitivity": {
            name: {"inputs": asdict(v), "break_even": breakeven(v), "at_100_accounts": monthly(500000, 100, v)}
            for name, v in variants.items()
        },
        "time": {
            "zero_adoption": cash_path(p, 0, 0),
            "two_new_accounts_each_period": cash_path(p, 2, 30),
            "same_growth_90_day_collection": cash_path(p, 2, 90),
            "same_growth_high_remediation": cash_path(variants["five_percent_remediation"], 2, 30),
            "same_growth_50k_loss_day90": cash_path(p, 2, 30, shock_day=90, shock_loss=50000),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    print(json.dumps({"passed": self_test()} if args.self_test else report(), indent=2, allow_nan=False))
