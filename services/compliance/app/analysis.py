from __future__ import annotations

from dataclasses import dataclass
from math import erf, log, sqrt
from statistics import mean
from typing import Dict, List, Optional, Sequence, Tuple

from app.models import DirResult, DriftResult, GroupOutcome, RegressionResult, ThresholdSimulationResult


@dataclass
class AnalysisFlags:
    regression_bias_flag: bool
    drift_flag: bool
    risk_level: str
    recommended_action: str


def calculate_dir(groups: Sequence[GroupOutcome]) -> Tuple[List[DirResult], float]:
    rates = []
    for group in groups:
        total = group.approved + group.denied
        rates.append(group.approved / total if total > 0 else 0.0)

    max_rate = max(rates) if rates else 0.0
    min_dir = 1.0
    results: List[DirResult] = []

    for group, rate in zip(groups, rates):
        ratio = rate / max_rate if max_rate > 0 else 0.0
        min_dir = min(min_dir, ratio)
        results.append(
            DirResult(
                group_name=group.name,
                approval_rate=round(rate, 4),
                disparate_impact_ratio=round(ratio, 4),
                flagged=ratio < 0.80,
            )
        )

    if not results:
        min_dir = 0.0

    return results, min_dir


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def regression_proxy(groups: Sequence[GroupOutcome]) -> RegressionResult:
    """Proxy fairness regression using two-proportion significance + log-odds.

    This is a lightweight MVP approximation when full row-level covariates are not
    provided in API input. It still gives a statistically interpretable signal.
    """
    if len(groups) < 2:
        return RegressionResult(
            coefficient=0.0,
            p_value=1.0,
            statistically_significant=False,
            methodology="Insufficient groups for proxy regression",
        )

    rates = []
    for group in groups:
        total = group.approved + group.denied
        rate = group.approved / total if total > 0 else 0.0
        rates.append((group, rate, total))

    worst, _, n_worst = min(rates, key=lambda item: item[1])
    best, _, n_best = max(rates, key=lambda item: item[1])

    p_worst = worst.approved / n_worst if n_worst > 0 else 0.0
    p_best = best.approved / n_best if n_best > 0 else 0.0

    pooled_num = worst.approved + best.approved
    pooled_den = n_worst + n_best
    pooled = pooled_num / pooled_den if pooled_den > 0 else 0.0

    standard_error = sqrt(max(pooled * (1.0 - pooled) * ((1.0 / max(n_worst, 1)) + (1.0 / max(n_best, 1))), 1e-12))
    z_score = (p_best - p_worst) / standard_error if standard_error > 0 else 0.0
    p_value = max(0.0, min(1.0, 2.0 * (1.0 - _normal_cdf(abs(z_score)))))

    odds_best = (best.approved + 0.5) / (best.denied + 0.5)
    odds_worst = (worst.approved + 0.5) / (worst.denied + 0.5)
    coefficient = log(odds_worst / odds_best)

    return RegressionResult(
        coefficient=round(coefficient, 4),
        p_value=round(p_value, 6),
        statistically_significant=(p_value < 0.05),
        methodology=(
            "Two-proportion z-test + log-odds proxy for protected-class marginal effect "
            "(row-level covariates not provided)"
        ),
    )


def threshold_sensitivity(min_dir: float) -> List[ThresholdSimulationResult]:
    simulations: List[ThresholdSimulationResult] = []
    for delta in (-10, -5, 5, 10):
        projected = min(1.25, max(0.0, min_dir + (-delta * 0.01)))
        if projected < 0.75:
            band = "red"
        elif projected < 0.80:
            band = "yellow"
        else:
            band = "green"
        simulations.append(
            ThresholdSimulationResult(
                threshold_delta_percent=delta,
                projected_dir=round(projected, 4),
                risk_band=band,
            )
        )
    return simulations


def _ks_statistic(sample_a: Sequence[float], sample_b: Sequence[float]) -> float:
    values = sorted(set(sample_a) | set(sample_b))
    if not values:
        return 0.0

    best_gap = 0.0
    len_a = len(sample_a)
    len_b = len(sample_b)

    for value in values:
        cdf_a = sum(1 for item in sample_a if item <= value) / max(len_a, 1)
        cdf_b = sum(1 for item in sample_b if item <= value) / max(len_b, 1)
        best_gap = max(best_gap, abs(cdf_a - cdf_b))

    return best_gap


def drift_detection(historical_approval_rates: Optional[Dict[str, List[float]]]) -> List[DriftResult]:
    if not historical_approval_rates:
        return []

    results: List[DriftResult] = []
    for group, rates in historical_approval_rates.items():
        if len(rates) < 3:
            continue

        clean_rates = [min(1.0, max(0.0, float(rate))) for rate in rates]
        midpoint = max(1, len(clean_rates) // 2)
        baseline_window = clean_rates[:midpoint]
        recent_window = clean_rates[midpoint:]
        current_rate = clean_rates[-1]
        baseline_rate = mean(clean_rates[:-1])

        ks_stat = _ks_statistic(baseline_window, recent_window)
        shifted = abs(current_rate - baseline_rate)
        flagged = ks_stat > 0.20 or shifted > 0.10

        results.append(
            DriftResult(
                protected_group=group,
                baseline_rate=round(baseline_rate, 4),
                current_rate=round(current_rate, 4),
                ks_statistic=round(ks_stat, 4),
                flagged=flagged,
            )
        )

    return results


def classify_risk(
    min_dir: float,
    regression: Optional[RegressionResult],
    drift_results: Sequence[DriftResult],
) -> AnalysisFlags:
    regression_flag = bool(regression and regression.statistically_significant)
    drift_flag = any(result.flagged for result in drift_results)

    if min_dir < 0.70 or (regression_flag and drift_flag):
        return AnalysisFlags(
            regression_bias_flag=regression_flag,
            drift_flag=drift_flag,
            risk_level="high",
            recommended_action="Escalate to fair lending review committee and pause threshold changes.",
        )
    if min_dir < 0.80 or regression_flag or drift_flag:
        return AnalysisFlags(
            regression_bias_flag=regression_flag,
            drift_flag=drift_flag,
            risk_level="medium",
            recommended_action="Review threshold sensitivity and execute targeted remediation plan.",
        )
    return AnalysisFlags(
        regression_bias_flag=regression_flag,
        drift_flag=drift_flag,
        risk_level="low",
        recommended_action="Maintain monitoring cadence and preserve evidence artifacts.",
    )


def exposure_score(
    min_dir: float,
    regression_result: Optional[RegressionResult],
    drift_results: Sequence[DriftResult],
    recency_days: int,
) -> float:
    dir_component = max(0.0, min(100.0, ((0.80 - min_dir) / 0.80) * 100.0))

    regression_component = 0.0
    if regression_result and regression_result.statistically_significant:
        regression_component = max(0.0, min(100.0, (1.0 - (regression_result.p_value / 0.05)) * 100.0))

    drift_component = 0.0
    if drift_results:
        worst_ks = max(result.ks_statistic for result in drift_results)
        if any(result.flagged for result in drift_results):
            drift_component = max(0.0, min(100.0, worst_ks * 100.0))

    if recency_days <= 30:
        recency_component = 0.0
    elif recency_days <= 60:
        recency_component = 50.0
    else:
        recency_component = 100.0

    score = (
        0.40 * dir_component
        + 0.30 * regression_component
        + 0.20 * drift_component
        + 0.10 * recency_component
    )
    return round(max(0.0, min(100.0, score)), 2)
