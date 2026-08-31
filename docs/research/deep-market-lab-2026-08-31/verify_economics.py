"""Independent boundary checks for the docs-only hypothetical economics model.

Run: .venv/bin/python3 docs/research/deep-market-lab-2026-08-31/verify_economics.py
Uses only the standard library and the sibling simulation, never application code.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import random
import statistics
import tempfile
import unittest
from unittest.mock import patch

import simulate_economics as model


ROOT = Path(__file__).resolve().parent
INPUTS = json.loads((ROOT / "economics_inputs.json").read_text())


def boundary_inputs() -> dict:
    """Four months, one certain win/month, known costs, no stochastic incidents."""
    cfg = deepcopy(INPUTS)
    cfg.update(payment_percent=0, payment_fixed_usd=0,
               fixed_cash_usd_month=10, founder_draw_usd_month=20)
    cfg["runway"].update(
        months=4, price=100, qualified_opportunities_per_month=1,
        win_probability=1, monthly_churn=0, monthly_incident_probability=0,
        cac_cash_per_win=5, onboarding_hours_per_win=2,
        support_hours_per_customer_month=3, direct_cash_per_customer_month=1,
        founder_delivery_capacity_hours=4, outsourced_delivery_usd_hour=7,
        opportunity_sales_hours=1,
    )
    return cfg


class EconomicsVerification(unittest.TestCase):
    def test_base_independent_arithmetic(self):
        # 499 - (18.264 fees + 10 events + 50 direct + 200 labor + 15 risk).
        actual = model.unit(INPUTS["scenarios"]["base"], INPUTS)
        self.assertAlmostEqual(model.fees(499, INPUTS), 18.264)
        self.assertAlmostEqual(actual["variable_cost_including_imputed_support"], 293.264)
        self.assertAlmostEqual(actual["service_contribution"], 205.736)
        self.assertAlmostEqual(actual["service_margin"], 205.736 / 499)
        # $1,000 acquisition + 12 hours * $50 = $1,600, allocated over 12 months.
        self.assertAlmostEqual(
            actual["contribution_after_onboarding_and_cac_allocation"],
            205.736 - 1600 / 12,
        )
        self.assertEqual(actual["allocated_fixed_cost_break_even_accounts"], 5)
        self.assertAlmostEqual(actual["simple_payback_months_no_churn"], 1600 / 205.736)
        self.assertAlmostEqual(actual["support_hours_for_70_percent_service_margin"], 1.12872)

    def test_adverse_units_have_no_positive_payback_or_break_even(self):
        for name, contribution in (("pessimistic", -569.264), ("catastrophic", -5219.264)):
            with self.subTest(name=name):
                actual = model.unit(INPUTS["scenarios"][name], INPUTS)
                self.assertAlmostEqual(actual["service_contribution"], contribution)
                self.assertIsNone(actual["allocated_fixed_cost_break_even_accounts"])
                self.assertIsNone(actual["simple_payback_months_no_churn"])
                self.assertLess(actual["support_hours_for_70_percent_service_margin"], 0)

    def test_fees_have_no_fixed_charge_on_zero_collections(self):
        self.assertEqual(model.fees(0, INPUTS), 0)

    def test_quantiles_variance_and_tail_direction(self):
        values = [30, 0, 20, 10]
        actual = model.describe(values)
        self.assertEqual(actual["mean"], 15)
        self.assertEqual(actual["median"], 15)
        self.assertEqual(actual["variance"], 125)  # Population, not sample variance.
        self.assertEqual(actual["mean_bottom_5_percent"], 0)
        self.assertEqual(actual["mean_top_5_percent"], 30)
        self.assertNotIn("mean_worst_5_percent", actual)
        independent = statistics.quantiles(values, n=100, method="inclusive")
        for p in (5, 25, 75, 95):
            self.assertAlmostEqual(actual[f"p{p}"], independent[p - 1])
        self.assertEqual(model.quantile(values, 0), 0)
        self.assertEqual(model.quantile(values, 1), 30)
        self.assertEqual(model.describe([-1, 0, 1])["negative_fraction"], 1 / 3)

    def test_no_wins_burns_fixed_cash_and_founder_draw(self):
        cfg = boundary_inputs()
        cfg["runway"]["win_probability"] = 0
        actual = model.runway_path(1, 0, cfg)
        self.assertEqual(actual["unfinanced_cumulative_cash"], [-30, -60, -90, -120])
        self.assertEqual(actual["capital_required"], 120)
        self.assertEqual(actual["terminal_accounts"], 0)
        self.assertEqual(actual["max_delivery_hours"], 0)
        self.assertEqual(actual["max_founder_delivery_plus_sales_hours"], 1)

    def test_no_churn_and_free_month_boundaries(self):
        # Delivery hours 5,8,11,14; overflow 1,4,7,10; cash costs 43,65,87,109.
        cases = {
            0: ([57, 192, 405, 696], 0),
            1: ([-43, -8, 105, 296], 43),
            2: ([-43, -108, -95, -4], 108),
            4: ([-43, -108, -195, -304], 304),
        }
        for free, (cash, capital) in cases.items():
            with self.subTest(free_months=free):
                actual = model.runway_path(1, free, boundary_inputs())
                self.assertEqual(actual["unfinanced_cumulative_cash"], cash)
                self.assertEqual(actual["capital_required"], capital)
                self.assertEqual(actual["terminal_net_operating_cash"], cash[-1])
                self.assertEqual(actual["terminal_accounts"], 4)
                self.assertEqual(actual["max_delivery_hours"], 14)
                self.assertEqual(actual["max_founder_delivery_plus_sales_hours"], 5)

    def test_full_churn_removes_incumbents_before_new_wins(self):
        cfg = boundary_inputs()
        cfg["runway"]["monthly_churn"] = 1
        paid = model.runway_path(1, 0, cfg)
        free = model.runway_path(1, 1, cfg)
        self.assertEqual(paid["unfinanced_cumulative_cash"], [57, 114, 171, 228])
        self.assertEqual(free["unfinanced_cumulative_cash"], [-43, -86, -129, -172])
        self.assertEqual(free["terminal_accounts"], 1)

    def test_incident_churn_clamp_haircut_fee_and_cash_loss(self):
        cfg = boundary_inputs()
        cfg.update(payment_percent=0.1, payment_fixed_usd=2)
        cfg["runway"].update(monthly_incident_probability=1, monthly_churn=0.2,
                             incident_churn_multiplier=10, incident_revenue_haircut=0.5,
                             incident_cash_cost=17)
        # Every month: $50 collection - $43 service/fixed - $7 fees - $17 incident.
        actual = model.runway_path(1, 0, cfg)
        self.assertEqual(actual["unfinanced_cumulative_cash"], [-17, -34, -51, -68])
        self.assertEqual(actual["terminal_accounts"], 1)

    def test_imputed_labor_and_founder_cash_are_separate(self):
        cfg = deepcopy(INPUTS)
        cfg["founder_draw_usd_month"] += 100
        self.assertEqual(model.unit(cfg["scenarios"]["base"], cfg),
                         model.unit(INPUTS["scenarios"]["base"], INPUTS))
        baseline = model.runway_path(2, 2, INPUTS)
        changed = model.runway_path(2, 2, cfg)
        for month, (before, after) in enumerate(zip(
                baseline["unfinanced_cumulative_cash"], changed["unfinanced_cumulative_cash"]), 1):
            self.assertAlmostEqual(after - before, -100 * month)
        cfg = deepcopy(INPUTS)
        cfg["labor_usd_hour"] *= 3
        self.assertEqual(model.runway_path(2, 2, cfg), baseline)

    def test_paired_prices_are_affine_sensitivities_not_demand_estimates(self):
        rng = random.Random(INPUTS["seed"])
        for _ in range(50):
            draw = model.account_draw(rng, INPUTS)
            low = model.unit({**draw, "price": 499}, INPUTS)
            high = model.unit({**draw, "price": 999}, INPUTS)
            self.assertAlmostEqual(high["service_contribution"] - low["service_contribution"], 482)

    def test_paired_free_terms_preserve_demand_and_capacity(self):
        for i in range(64):
            short = model.runway_path(INPUTS["seed"] + i, 2, INPUTS)
            long = model.runway_path(INPUTS["seed"] + i, 12, INPUTS)
            for field in ("terminal_accounts", "max_delivery_hours",
                          "max_founder_delivery_plus_sales_hours"):
                self.assertEqual(short[field], long[field])
            self.assertGreaterEqual(long["capital_required"], short["capital_required"])
            for a, b in zip(short["unfinanced_cumulative_cash"], long["unfinanced_cumulative_cash"]):
                self.assertGreaterEqual(a + 1e-8, b)

    def run_main_in_temporary_directory(self, cfg):
        with tempfile.TemporaryDirectory(prefix="regengine-economics-qa-") as directory:
            root = Path(directory)
            (root / "economics_inputs.json").write_text(json.dumps(cfg))
            with patch.object(model, "ROOT", root), redirect_stdout(StringIO()):
                model.main()
            return json.loads((root / "economics_results.json").read_text())

    def test_failure_is_first_crossing_and_exact_zero_is_not_failure(self):
        cfg = boundary_inputs()
        cfg["draws"] = 1
        cfg["runway"].update(free_months_options=[1], capital_sensitivities_usd=[0, 42, 43, 44])
        actual = self.run_main_in_temporary_directory(cfg)
        self.assertEqual(actual["runway_horizon_months"], 4)
        self.assertEqual(actual["amortization_months"], cfg["amortization_months"])
        sensitivities = actual["runway_monte_carlo_by_free_months"]["1"]["capital_sensitivity"]
        for capital in (0, 42):
            self.assertEqual(sensitivities[str(capital)]["failure_fraction"], 1)
            self.assertEqual(sensitivities[str(capital)]["median_first_failure_month_conditional_on_failure"], 1)
        # Cash recovers later, but that cannot undo the earlier failure.
        for capital in (43, 44):
            self.assertEqual(sensitivities[str(capital)]["survival_fraction"], 1)
            self.assertEqual(sensitivities[str(capital)]["censored_no_failure_by_horizon"], 1)
            self.assertIsNone(sensitivities[str(capital)]["median_first_failure_month_conditional_on_failure"])

    def test_saved_results_reproduce_from_checked_in_inputs(self):
        saved = json.loads((ROOT / "economics_results.json").read_text())
        self.assertEqual(self.run_main_in_temporary_directory(INPUTS), saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
