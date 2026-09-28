"""Tests for the static FSMA rule-catalog audit."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

from shared.rules.seeds import FSMA_RULE_SEEDS

_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "audit_fsma_rule_catalog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_fsma_rule_catalog", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_builtin_catalog_passes_and_classifies_citations():
    mod = _load_module()

    report = mod.build_report(FSMA_RULE_SEEDS)

    assert report["status"] == "pass"
    assert report["findings"] == []
    assert "It does not verify runtime enforcement mode or deployed behavior." in report["limitations"]
    assert report["summary"] == {
        "total_rules": 37,
        "legal_requirements": 28,
        "operational_controls": 8,
        "industry_standards": 1,
        "unclassified_citations": 0,
        "supported_evaluators": 37,
    }
    assert set(report["cte_coverage"]) == mod.REQUIRED_CTE_TYPES
    assert all(count > 0 for count in report["cte_coverage"].values())


def test_catalog_fails_for_unknown_evaluator_and_missing_evidence_fields():
    mod = _load_module()
    rules = deepcopy(FSMA_RULE_SEEDS)
    rules[0]["evaluation_logic"]["type"] = "not_implemented"
    rules[0]["citation_reference"] = ""
    rules[0]["remediation_suggestion"] = ""

    report = mod.build_report(rules)

    assert report["status"] == "fail"
    finding_codes = {finding["code"] for finding in report["findings"]}
    assert finding_codes == {
        "missing_citation",
        "missing_remediation",
        "unsupported_evaluator",
    }
    first_rule = report["rules"][0]
    assert first_rule["evaluator_supported"] is False
    assert first_rule["citation_class"] == "unclassified"


def test_catalog_fails_when_a_required_cte_type_has_no_rule():
    mod = _load_module()
    rules = [
        deepcopy(rule)
        for rule in FSMA_RULE_SEEDS
        if rule.get("applicability_conditions", {}).get("cte_types")
        and "transformation" not in rule["applicability_conditions"]["cte_types"]
    ]

    report = mod.build_report(rules)

    assert report["status"] == "fail"
    assert report["cte_coverage"]["transformation"] == 0
    assert any(
        finding["code"] == "missing_cte_coverage" and finding["cte_type"] == "transformation"
        for finding in report["findings"]
    )


def test_catalog_fails_for_unknown_cte_type():
    mod = _load_module()
    rules = deepcopy(FSMA_RULE_SEEDS)
    rules[0]["applicability_conditions"]["cte_types"] = ["recieving"]

    report = mod.build_report(rules)

    assert report["status"] == "fail"
    assert any(
        finding["code"] == "unknown_cte_type" and finding["cte_type"] == "recieving" for finding in report["findings"]
    )


def test_catalog_accepts_explicit_all_cte_type():
    mod = _load_module()
    rules = deepcopy(FSMA_RULE_SEEDS)
    rules[0]["applicability_conditions"]["cte_types"] = ["all"]

    report = mod.build_report(rules)

    assert report["status"] == "pass"
    assert all(count > 0 for count in report["cte_coverage"].values())


def test_catalog_fails_for_invalid_severity_and_duplicate_title():
    mod = _load_module()
    rules = deepcopy(FSMA_RULE_SEEDS)
    rules[0]["severity"] = "critcal"
    rules[1]["title"] = rules[0]["title"]

    report = mod.build_report(rules)

    assert report["status"] == "fail"
    assert {finding["code"] for finding in report["findings"]} == {
        "duplicate_title",
        "invalid_severity",
    }


def test_cli_writes_deterministic_json_and_markdown(tmp_path):
    mod = _load_module()
    json_out = tmp_path / "catalog.json"
    markdown_out = tmp_path / "catalog.md"

    assert mod.main(["--json-out", str(json_out), "--markdown-out", str(markdown_out)]) == 0
    first_json = json_out.read_text(encoding="utf-8")
    first_markdown = markdown_out.read_text(encoding="utf-8")

    assert mod.main(["--json-out", str(json_out), "--markdown-out", str(markdown_out)]) == 0
    assert json_out.read_text(encoding="utf-8") == first_json
    assert markdown_out.read_text(encoding="utf-8") == first_markdown
    assert json.loads(first_json)["status"] == "pass"
    assert "# FSMA 204 Rule Catalog Audit" in first_markdown
    assert "It does not verify the legal accuracy or completeness of citations." in first_markdown
    assert "Legal requirement" in first_markdown


def test_committed_artifacts_are_current():
    mod = _load_module()

    assert mod.main(["--check"]) == 0


def test_check_mode_detects_stale_artifacts_without_rewriting(tmp_path):
    mod = _load_module()
    json_out = tmp_path / "catalog.json"
    markdown_out = tmp_path / "catalog.md"
    json_out.write_text("stale\n", encoding="utf-8")
    markdown_out.write_text("stale\n", encoding="utf-8")

    assert (
        mod.main(
            [
                "--check",
                "--json-out",
                str(json_out),
                "--markdown-out",
                str(markdown_out),
            ]
        )
        == 1
    )
    assert json_out.read_text(encoding="utf-8") == "stale\n"
    assert markdown_out.read_text(encoding="utf-8") == "stale\n"
