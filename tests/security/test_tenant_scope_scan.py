"""Tests for the tenant-scope query gate (Pattern 3 foundational fix).

Covers the scanner in scripts/security/scan_tenant_scope.py: each rule
flags its violation shape on synthetic files, allows scoped and catalog
queries, honors the allowlist, and fails loudly on bad config. The final
tests run the gate against the real tree: any new unscoped query fails.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = ROOT / "scripts/security/scan_tenant_scope.py"
spec = importlib.util.spec_from_file_location("scan_tenant_scope", SCANNER_PATH)
assert spec is not None
scanner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["scan_tenant_scope"] = scanner
spec.loader.exec_module(scanner)

ALLOWLIST_PATH = ROOT / ".semgrep" / "tenant-scope-allowlist.yml"
SEMGREP_RULES_PATH = ROOT / ".semgrep" / "tenant-query-scope.yaml"

GLOBAL_TABLES = {"rule_definitions", "obligation_cte_rules", "obligations", "food_traceability_list"}


def write_source(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def scan_text(tmp_path: Path, body: str) -> list:
    path = write_source(tmp_path, "sample.py", body)
    return scanner.scan_file(path, "sample.py", GLOBAL_TABLES)


def write_allowlist(tmp_path: Path, baseline: list) -> Path:
    path = tmp_path / "allowlist.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "global_catalog_labels": {"Obligation": "catalog"},
                "global_sql_tables": {"rule_definitions": "catalog"},
                "baseline": baseline,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_shim_is_flagged(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = """\nMATCH (e:TraceEvent)\nWHERE ($tenant_id IS NULL OR e.tenant_id = $tenant_id)\n"""\n',
    )
    assert len(violations) == 1
    assert violations[0].rule == "tenant-failopen-shim"
    assert violations[0].scope == "QUERY"


def test_shim_reversed_form_is_flagged(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "MATCH (e:TraceEvent) WHERE e.tenant_id = $tenant_id OR $tenant_id IS NULL"\n',
    )
    assert [v.rule for v in violations] == ["tenant-failopen-shim"]


def test_cypher_match_on_tenant_label_without_predicate_is_flagged(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "MATCH (l:Lot {tlc: $tlc})-[:UNDERWENT]->(e:TraceEvent) RETURN l"\n')
    assert len(violations) == 1
    assert violations[0].rule == "cypher-match-without-tenant"
    assert violations[0].target == "Lot,TraceEvent"


def test_cypher_match_with_predicate_passes(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "MATCH (l:Lot {tlc: $tlc, tenant_id: $tenant_id})-[:UNDERWENT]->(e:TraceEvent) RETURN l"\n',
    )
    assert violations == []


def test_catalog_only_query_passes(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = """\nMATCH (o:Obligation {id: $id})<-[:REQUIRES]-(s:Section)\nRETURN o.text\n"""\n',
    )
    assert violations == []


def test_merge_without_tenant_is_flagged(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "MERGE (r:RegulationOverride {override_id: $oid}) RETURN r"\n')
    assert [v.rule for v in violations] == ["cypher-merge-without-tenant"]
    assert violations[0].target == "RegulationOverride"


def test_merge_with_tenant_passes(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "MERGE (l:Lot {tlc: $tlc, tenant_id: $tenant_id}) RETURN l"\n')
    assert violations == []


def test_concatenated_scoped_query_passes_as_one(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = (\n    "MATCH path = (start:Lot {tlc: $tlc})-[:UNDERWENT*1..4]->(end)\\n"\n    "WHERE start.tenant_id = $tenant_id\\n"\n    "RETURN path\\n"\n)\n',
    )
    assert violations == []


def test_optional_builder_placeholder_does_not_count_as_scoping(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = f"""\nMATCH (o:Obligation)<-[:REQUIRES]-(s:Section)\nWHERE true {tenant_filter}\n"""\n',
    )
    # Obligation/Section are catalog labels, so nothing tenant-scoped is
    # touched here; the assertion is that a tenant-label variant IS flagged.
    assert violations == []
    violations = scan_text(
        tmp_path,
        'QUERY = f"""\nMATCH (l:Lot)<-[:UNDERWENT]-(e:TraceEvent)\nWHERE true {tenant_filter}\n"""\n',
    )
    assert [v.rule for v in violations] == ["cypher-match-without-tenant"]


def test_sql_on_tenant_table_without_predicate_is_flagged(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "SELECT * FROM fsma.cte_events WHERE event_type = :t"\n')
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    assert violations[0].target == "fsma.cte_events"


def test_sql_update_without_predicate_is_flagged(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "UPDATE fsma.task_queue SET status = :s WHERE id = :id"\n')
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]


def test_sql_with_tenant_or_org_predicate_passes(tmp_path: Path):
    for where in ("tenant_id = :tid", "org_id = CAST(:tid AS uuid)", "te.tenant_id = :tenant_id"):
        violations = scan_text(tmp_path, f'QUERY = "SELECT * FROM fsma.cte_events WHERE {where}"\n')
        assert violations == [], where


def test_sql_on_global_or_other_schema_is_ignored(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "SELECT * FROM fsma.rule_definitions WHERE title = :t"\n')
    assert violations == []
    violations = scan_text(tmp_path, 'QUERY = "SELECT * FROM information_schema.tables WHERE table_name = :t"\n')
    assert violations == []


def test_docstring_match_is_ignored(tmp_path: Path):
    violations = scan_text(tmp_path, '"""Module using MATCH (l:Lot) notes."""\nX = 1\n')
    assert violations == []


def test_baseline_suppresses_exact_key_only(tmp_path: Path):
    path = write_source(
        tmp_path,
        "sample.py",
        'QUERY = "MATCH (l:Lot {tlc: $tlc}) RETURN l"\n',
    )
    allowlist = write_allowlist(
        tmp_path,
        [
            {
                "file": str(path),
                "scope": "QUERY",
                "rule": "cypher-match-without-tenant",
                "target": "Lot",
                "reason": "test baseline",
            }
        ],
    )
    fresh, stale = scanner.check([tmp_path], allowlist)
    assert fresh == []
    assert stale == []


def test_new_violation_fails_check(tmp_path: Path):
    write_source(
        tmp_path,
        "sample.py",
        'QUERY = "MATCH (l:Lot {tlc: $tlc}) RETURN l"\n',
    )
    allowlist = write_allowlist(tmp_path, [])
    fresh, _ = scanner.check([tmp_path], allowlist)
    assert len(fresh) == 1
    assert fresh[0].rule == "cypher-match-without-tenant"


def test_violation_in_new_scope_is_not_covered_by_baseline(tmp_path: Path):
    path = write_source(
        tmp_path,
        "sample.py",
        'def other():\n    return "MATCH (l:Lot {tlc: $tlc}) RETURN l"\n',
    )
    allowlist = write_allowlist(
        tmp_path,
        [
            {
                "file": str(path),
                "scope": "QUERY",
                "rule": "cypher-match-without-tenant",
                "target": "Lot",
                "reason": "test baseline",
            }
        ],
    )
    fresh, stale = scanner.check([tmp_path], allowlist)
    assert len(fresh) == 1
    assert fresh[0].scope == "other"
    assert len(stale) == 1


def test_missing_allowlist_is_a_config_error(tmp_path: Path):
    try:
        scanner.check([tmp_path], tmp_path / "nope.yml")
    except scanner.ConfigError:
        return
    raise AssertionError("missing allowlist must raise ConfigError")


def test_malformed_baseline_entry_is_a_config_error(tmp_path: Path):
    path = tmp_path / "allowlist.yml"
    path.write_text(
        yaml.safe_dump({"global_catalog_labels": {}, "global_sql_tables": {}, "baseline": [{"file": "x"}]}),
        encoding="utf-8",
    )
    try:
        scanner.check([tmp_path], path)
    except scanner.ConfigError:
        return
    raise AssertionError("malformed baseline entry must raise ConfigError")


def test_allowlist_every_entry_has_a_reason():
    data = yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["global_catalog_labels"], "catalog labels must not be empty"
    assert data["global_sql_tables"], "global tables must not be empty"
    assert data["baseline"], "baseline must not be empty"
    for entry in data["baseline"]:
        for key in ("file", "scope", "rule", "target", "reason"):
            assert entry.get(key), f"baseline entry missing {key}: {entry}"
    labels = set(data["global_catalog_labels"])
    assert {"Obligation", "Section", "Regulation", "Citation"} <= labels


def test_semgrep_rule_file_has_expected_rules():
    data = yaml.safe_load(SEMGREP_RULES_PATH.read_text(encoding="utf-8"))
    rules = {rule["id"]: rule for rule in data["rules"]}
    assert rules["tenant-failopen-shim"]["severity"] == "ERROR"
    assert rules["cypher-match-without-tenant"]["severity"] == "WARNING"
    assert rules["cypher-merge-without-tenant"]["severity"] == "WARNING"
    assert rules["sql-on-tenant-table-without-tenant-predicate"]["severity"] == "WARNING"


def test_repo_gate_has_no_new_violations():
    fresh, _ = scanner.check([ROOT / "services", ROOT / "server", ROOT / "regengine"], ALLOWLIST_PATH)
    assert fresh == [], [f"{v.file}:{v.line} [{v.scope}] {v.rule}" for v in fresh]
