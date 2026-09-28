#!/usr/bin/env python3
"""Audit the built-in FSMA 204 rule catalog and render deterministic artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))

from shared.rules.evaluators import EVALUATORS, RELATIONAL_EVALUATORS  # noqa: E402
from shared.rules.seeds import FSMA_RULE_SEEDS  # noqa: E402

DEFAULT_JSON = ROOT / "docs" / "audits" / "FSMA_RULE_CATALOG.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "audits" / "FSMA_RULE_CATALOG.md"
REQUIRED_CTE_TYPES = {
    "harvesting",
    "cooling",
    "initial_packing",
    "first_land_based_receiving",
    "shipping",
    "receiving",
    "transformation",
}
REQUIRED_RULE_FIELDS = ("title", "severity", "category", "failure_reason_template")
LIMITATIONS = (
    "This is a static structural audit of the built-in seed catalog.",
    "It does not verify the legal accuracy or completeness of citations.",
    "It does not compare seeds with rule definitions in a live database.",
    "It does not verify runtime enforcement mode or deployed behavior.",
)


def classify_citation(citation: str) -> str:
    """Separate regulatory citations from operational and industry controls."""
    normalized = citation.strip()
    if normalized.startswith("21 CFR"):
        return "legal_requirement"
    if normalized.startswith("Operational"):
        return "operational_control"
    if normalized.startswith("GS1"):
        return "industry_standard"
    return "unclassified"


def _finding(code: str, title: str, message: str, **details: str) -> dict[str, str]:
    return {"code": code, "rule_title": title, "message": message, **details}


def build_report(rules: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Build a machine-readable audit report from rule seed dictionaries."""
    findings: list[dict[str, str]] = []
    rendered_rules: list[dict[str, Any]] = []
    coverage = {cte_type: 0 for cte_type in sorted(REQUIRED_CTE_TYPES)}

    for index, rule in enumerate(rules, start=1):
        title = str(rule.get("title") or f"rule_at_index_{index}")
        for field in REQUIRED_RULE_FIELDS:
            if not rule.get(field):
                findings.append(
                    _finding("missing_required_field", title, f"Required field is empty: {field}", field=field)
                )

        citation = str(rule.get("citation_reference") or "")
        citation_class = classify_citation(citation)
        if not citation:
            findings.append(_finding("missing_citation", title, "Citation reference is required"))
        elif citation_class == "unclassified":
            findings.append(
                _finding("unclassified_citation", title, "Citation is not classified as legal, operational, or GS1")
            )

        remediation = str(rule.get("remediation_suggestion") or "")
        if not remediation:
            findings.append(_finding("missing_remediation", title, "Remediation guidance is required"))

        logic = rule.get("evaluation_logic") or {}
        evaluator_type = str(logic.get("type") or "")
        if evaluator_type in EVALUATORS:
            evaluator_kind = "stateless"
        elif evaluator_type in RELATIONAL_EVALUATORS:
            evaluator_kind = "relational"
        else:
            evaluator_kind = "unsupported"
            findings.append(
                _finding(
                    "unsupported_evaluator",
                    title,
                    f"No evaluator is registered for type: {evaluator_type or '(missing)'}",
                    evaluator_type=evaluator_type,
                )
            )

        applicability = rule.get("applicability_conditions") or {}
        configured_cte_types = list(applicability.get("cte_types") or [])
        covered_types = REQUIRED_CTE_TYPES if not configured_cte_types else set(configured_cte_types)
        for cte_type in sorted(set(configured_cte_types) - REQUIRED_CTE_TYPES):
            findings.append(
                _finding(
                    "unknown_cte_type",
                    title,
                    f"Configured CTE type is not recognized: {cte_type}",
                    cte_type=cte_type,
                )
            )
        for cte_type in covered_types & REQUIRED_CTE_TYPES:
            coverage[cte_type] += 1

        rendered_rules.append(
            {
                "position": index,
                "title": title,
                "severity": rule.get("severity"),
                "category": rule.get("category"),
                "cte_types": configured_cte_types or ["all"],
                "evaluator_type": evaluator_type,
                "evaluator_kind": evaluator_kind,
                "evaluator_supported": evaluator_kind != "unsupported",
                "citation_reference": citation,
                "citation_class": citation_class,
                "remediation_suggestion": remediation,
            }
        )

    for cte_type, count in coverage.items():
        if count == 0:
            findings.append(
                {
                    "code": "missing_cte_coverage",
                    "rule_title": "",
                    "message": f"No rule covers required CTE type: {cte_type}",
                    "cte_type": cte_type,
                }
            )

    class_counts = {
        key: sum(rule["citation_class"] == value for rule in rendered_rules)
        for key, value in (
            ("legal_requirements", "legal_requirement"),
            ("operational_controls", "operational_control"),
            ("industry_standards", "industry_standard"),
            ("unclassified_citations", "unclassified"),
        )
    }
    return {
        "schema_version": 1,
        "source": "services/shared/rules/seeds.py:FSMA_RULE_SEEDS",
        "status": "fail" if findings else "pass",
        "limitations": list(LIMITATIONS),
        "summary": {
            "total_rules": len(rendered_rules),
            **class_counts,
            "supported_evaluators": sum(rule["evaluator_supported"] for rule in rendered_rules),
        },
        "cte_coverage": coverage,
        "findings": findings,
        "rules": rendered_rules,
    }


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# FSMA 204 Rule Catalog Audit",
        "",
        f"**Structural status:** {report['status'].upper()}",
        "",
        (
            "Generated from `services/shared/rules/seeds.py:FSMA_RULE_SEEDS` with "
            "`python3 scripts/audit_fsma_rule_catalog.py`."
        ),
        "",
        "## Scope",
        "",
    ]
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Measure | Count |",
            "| --- | ---: |",
            f"| Total rules | {summary['total_rules']} |",
            f"| Legal requirement | {summary['legal_requirements']} |",
            f"| Operational control | {summary['operational_controls']} |",
            f"| Industry standard | {summary['industry_standards']} |",
            f"| Unclassified citation | {summary['unclassified_citations']} |",
            f"| Supported evaluator | {summary['supported_evaluators']} |",
            "",
            "## CTE coverage",
            "",
            "| CTE type | Rules |",
            "| --- | ---: |",
        ]
    )
    lines.extend(f"| {_cell(cte_type)} | {count} |" for cte_type, count in report["cte_coverage"].items())
    lines.extend(["", "## Findings", ""])
    if report["findings"]:
        lines.extend(
            f"- `{finding['code']}` — {_cell(finding['rule_title'] or finding.get('cte_type', 'catalog'))}: "
            f"{_cell(finding['message'])}"
            for finding in report["findings"]
        )
    else:
        lines.append("No structural catalog findings.")
    lines.extend(
        [
            "",
            "## Rules",
            "",
            "| # | Title | Severity | CTE types | Evaluator | Citation class | Citation |",
            "| ---: | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for rule in report["rules"]:
        cells = {key: _cell(value) for key, value in rule.items()}
        cells["cte_types"] = _cell(", ".join(rule["cte_types"]))
        lines.append(
            "| {position} | {title} | {severity} | {cte_types} | {evaluator_type} | "
            "{citation_class} | {citation_reference} |".format(**cells)
        )
    return "\n".join(lines) + "\n"


def _matches(path: Path, expected: str) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8") == expected


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--check", action="store_true", help="fail if committed artifacts are stale")
    args = parser.parse_args(argv)

    report = build_report(FSMA_RULE_SEEDS)
    outputs = ((args.json_out, render_json(report)), (args.markdown_out, render_markdown(report)))
    if args.check:
        stale = [str(path) for path, content in outputs if not _matches(path, content)]
        if stale:
            print("Rule catalog artifacts are stale: " + ", ".join(stale), file=sys.stderr)
            return 1
    else:
        for path, content in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"Wrote {path}")
    if report["status"] != "pass":
        print(f"Rule catalog audit failed with {len(report['findings'])} finding(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
