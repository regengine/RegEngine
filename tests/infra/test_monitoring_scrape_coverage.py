"""Regression tests for monitoring scrape coverage.

The defect: infra/monitoring/prometheus.yml carried a kubernetes-nodes
scrape job using Kubernetes service discovery even though no Prometheus,
node exporter, or related RBAC exists in this tree, and
infra/monitoring/alert_rules.yml carried Kafka, node exporter, and
Postgres exporter alert rules with no scrape job producing those metrics.
Those rules could never have data and only suggested coverage that was
not there. The fix removes the dangling scrape job and prunes the rules
whose metrics have no producer. These tests fail on the old configs.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROM_PATH = REPO_ROOT / "infra" / "monitoring" / "prometheus.yml"
RULES_PATH = REPO_ROOT / "infra" / "monitoring" / "alert_rules.yml"

# Metric families that need exporters with no deployment or scrape job in
# this tree: the Kafka exporter, the node exporter, and the postgres
# exporter. Alert rules referencing them can never have data.
UNSCRAPED_METRIC_PREFIXES = ("kafka_", "node_", "pg_")

# PromQL keywords and functions that look like metric names to a naive
# regex but are not series selectors.
_PROMQL_KEYWORDS = frozenset(
    {
        "and",
        "by",
        "without",
        "on",
        "ignoring",
        "group_left",
        "group_right",
        "bool",
        "or",
        "unless",
    }
)


def _load_prometheus_config():
    return yaml.safe_load(PROM_PATH.read_text())


def _load_rule_groups():
    return yaml.safe_load(RULES_PATH.read_text())["groups"]


def _metric_names_in_expr(expr: str) -> set[str]:
    """Return candidate metric names referenced by a PromQL expression."""
    names = set()
    for match in re.finditer(r"[a-zA-Z_:][a-zA-Z0-9_:]*", expr):
        name = match.group(0)
        if name in _PROMQL_KEYWORDS:
            continue
        # Skip function calls: histogram_quantile(, rate(, sum by ...
        rest = expr[match.end() :].lstrip()
        if rest.startswith("("):
            continue
        # Skip label names inside braces: {job="..."} or {mode="idle"}.
        before = expr[: match.start()].rstrip()
        if before.endswith("{") or before.endswith(","):
            continue
        names.add(name)
    return names


def _all_rule_exprs() -> list[tuple[str, str]]:
    exprs = []
    for group in _load_rule_groups():
        for rule in group.get("rules", []):
            if "expr" in rule:
                exprs.append((rule.get("alert", "<recording>"), str(rule["expr"])))
    return exprs


def test_no_kubernetes_sd_without_in_cluster_prometheus():
    """Scrape jobs must not use Kubernetes SD: no Prometheus runs in-cluster."""
    config = _load_prometheus_config()
    for job in config.get("scrape_configs", []):
        assert "kubernetes_sd_configs" not in job, (
            f"job {job.get('job_name')!r} uses kubernetes_sd_configs but no "
            "Prometheus, RBAC, or node exporter exists in this tree"
        )


def test_alert_rules_reference_only_scraped_metrics():
    """Every alert expr must use metrics a configured scrape job can produce."""
    failures = []
    for alert, expr in _all_rule_exprs():
        for name in sorted(_metric_names_in_expr(expr)):
            if name.startswith(UNSCRAPED_METRIC_PREFIXES):
                failures.append(f"{alert}: {name}")
    assert not failures, (
        "alert rules reference metrics with no scrape job producing them "
        f"(missing Kafka/node/postgres exporters): {failures}"
    )


def test_rule_files_reference_resolves():
    """Every rule file listed by prometheus.yml must exist on disk."""
    config = _load_prometheus_config()
    for rule_file in config.get("rule_files", []):
        resolved = (PROM_PATH.parent / rule_file).resolve()
        assert resolved.is_file(), f"rule file {rule_file!r} does not exist"
