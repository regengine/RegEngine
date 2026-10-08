"""Tests for the tenant-scope query gate (Pattern 3 foundational fix).

Covers the scanner in scripts/security/scan_tenant_scope.py: each rule
flags its violation shape on synthetic files, allows scoped and catalog
queries, honors the allowlist, and fails loudly on bad config. A mere
mention of tenant_id (select list, comment, literal, SET target) is not a
predicate; every tenant label and table needs its own real comparison.
The live-tree gate test lives in test_tenant_scope_gate.py next to this
file, kept out of the blocking suites until the tree itself is green.
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
CATALOG_LABELS = {"Obligation", "Section", "Regulation", "Citation"}


def write_source(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def scan_text(tmp_path: Path, body: str, catalog=None, known=None) -> list:
    path = write_source(tmp_path, "sample.py", body)
    return scanner.scan_file(
        path,
        "sample.py",
        GLOBAL_TABLES,
        CATALOG_LABELS if catalog is None else catalog,
        {"cte_events", "task_queue"} if known is None else known,
    )


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
        'QUERY = "MATCH (l:Lot {tlc: $tlc, tenant_id: $tenant_id})-[:UNDERWENT]->(e:TraceEvent) WHERE e.tenant_id = $tenant_id RETURN l"\n',
    )
    assert violations == []


def test_cypher_match_scoped_on_one_label_only_flags_the_other(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "MATCH (l:Lot {tlc: $tlc, tenant_id: $tenant_id})-[:UNDERWENT]->(e:TraceEvent) RETURN l"\n',
    )
    assert [v.rule for v in violations] == ["cypher-match-without-tenant"]
    assert violations[0].target == "TraceEvent"


def test_cypher_match_predicate_on_other_node_does_not_scope(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "MATCH (e:TraceEvent) WHERE e.tenant_id = $tenant_id MATCH (l:Lot) RETURN l"\n',
    )
    assert [v.rule for v in violations] == ["cypher-match-without-tenant"]
    assert violations[0].target == "Lot"


def test_select_list_mention_is_not_a_predicate(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "SELECT tenant_id, id FROM fsma.cte_events"\n')
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    violations = scan_text(tmp_path, 'QUERY = "MATCH (l:Lot) RETURN l.tenant_id"\n')
    assert [v.rule for v in violations] == ["cypher-match-without-tenant"]


def test_comment_mention_is_not_a_predicate(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "SELECT * FROM fsma.cte_events -- filter tenant_id in the app"\n',
    )
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    violations = scan_text(
        tmp_path,
        'QUERY = "DELETE FROM fsma.cte_events WHERE id = :id /* tenant_id */"\n',
    )
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]


def test_string_literal_mention_is_not_a_predicate(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        "QUERY = \"SELECT * FROM fsma.cte_events WHERE label = 'not_a_tenant_id'\"\n",
    )
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]


def test_set_target_is_not_a_predicate(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "UPDATE fsma.cte_events SET tenant_id = :t WHERE id = :id"\n',
    )
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    violations = scan_text(
        tmp_path,
        'QUERY = "MERGE (l:Lot {tlc: $tlc}) SET l.tenant_id = $tenant_id"\n',
    )
    assert [v.rule for v in violations] == ["cypher-merge-without-tenant"]
    assert violations[0].target == "Lot"


def test_bind_value_without_tenant_column_is_not_a_predicate(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "SELECT * FROM fsma.cte_events WHERE quantity = :tid"\n')
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    violations = scan_text(tmp_path, 'QUERY = "SELECT * FROM fsma.cte_events WHERE l.not_tenant_id = 1"\n')
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]


def test_join_condition_between_columns_is_not_a_predicate(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "SELECT * FROM fsma.cte_events e JOIN fsma.cte_kdes k ON k.tenant_id = e.tenant_id"\n',
    )
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    assert violations[0].target == "fsma.cte_events,fsma.cte_kdes"


def test_parenthesized_shim_is_flagged(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "MATCH (e:TraceEvent) WHERE ($tenant_id IS NULL) OR e.tenant_id = $tenant_id RETURN e"\n',
    )
    assert [v.rule for v in violations] == ["tenant-failopen-shim"]


def test_coalesce_shim_is_flagged(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "MATCH (e:TraceEvent) WHERE e.tenant_id = coalesce($tenant_id, e.tenant_id) RETURN e"\n',
    )
    assert [v.rule for v in violations] == ["tenant-failopen-shim"]


def test_catalog_alias_shim_passes(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "MATCH (o:Obligation {id: $id}) WHERE (o.tenant_id IS NULL OR o.tenant_id = $tenant_id) RETURN o"\n',
    )
    assert violations == []


def test_comma_from_list_checks_every_table(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "SELECT * FROM fsma.obligations o, fsma.cte_events e WHERE o.id = e.obligation_id"\n',
    )
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    assert violations[0].target == "fsma.cte_events"
    violations = scan_text(
        tmp_path,
        'QUERY = "SELECT * FROM fsma.cte_events e, fsma.task_queue q WHERE e.tenant_id = :t AND q.tenant_id = :t"\n',
    )
    assert violations == []
    violations = scan_text(
        tmp_path,
        'QUERY = "SELECT * FROM fsma.cte_events e, fsma.task_queue q WHERE e.tenant_id = :t"\n',
    )
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    assert violations[0].target == "fsma.task_queue"


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


def test_second_position_and_backtick_labels_are_checked(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "MATCH (n:Obligation:Lot) RETURN n"\n')
    assert [v.rule for v in violations] == ["cypher-match-without-tenant"]
    assert violations[0].target == "Lot"
    violations = scan_text(tmp_path, 'QUERY = "MATCH (n:`Lot`) RETURN n"\n')
    assert [v.rule for v in violations] == ["cypher-match-without-tenant"]
    assert violations[0].target == "Lot"


def test_catalog_mapping_exempts_only_catalog_labels(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "MATCH (o:Obligation), (l:Lot) WHERE o.tenant_id = $tenant_id RETURN l"\n',
    )
    assert [v.rule for v in violations] == ["cypher-match-without-tenant"]
    assert violations[0].target == "Lot"
    # Document stays fail-closed: it is a tenant label even though the
    # allowlist also lists it as catalog (global reads are baselined).
    violations = scan_text(
        tmp_path,
        'QUERY = "MATCH (d:Document {hash: $h}) RETURN d"\n',
        catalog={"Document", "Obligation"},
    )
    assert [v.rule for v in violations] == ["cypher-match-without-tenant"]


def test_unqualified_tenant_table_is_checked(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "SELECT * FROM cte_events WHERE event_type = :t"\n')
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    assert violations[0].target == "fsma.cte_events"
    violations = scan_text(tmp_path, 'QUERY = "SELECT * FROM cte_events WHERE tenant_id = :t"\n')
    assert violations == []
    violations = scan_text(tmp_path, 'QUERY = "SELECT * FROM alembic_version WHERE version_num = :v"\n')
    assert violations == []


def test_insert_and_delete_cases(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "INSERT INTO fsma.task_queue (id, status) VALUES (:a, :b)"\n')
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    violations = scan_text(
        tmp_path,
        'QUERY = "INSERT INTO fsma.task_queue (id, tenant_id) VALUES (:a, :t)"\n',
    )
    assert violations == []
    violations = scan_text(tmp_path, 'QUERY = "DELETE FROM fsma.cte_events WHERE id = :id"\n')
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]
    violations = scan_text(tmp_path, 'QUERY = "DELETE FROM fsma.cte_events WHERE tenant_id = :t AND id = :id"\n')
    assert violations == []


def test_null_safe_equality_counts_as_predicate(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "SELECT id FROM fsma.task_queue WHERE tenant_id IS NOT DISTINCT FROM :tenant_id"\n',
    )
    assert violations == []


def test_tenant_suffixed_column_with_tenant_bind_passes(tmp_path: Path):
    violations = scan_text(
        tmp_path,
        'QUERY = "UPDATE fsma.exchange_packages SET status = :s WHERE receiver_tenant_id = :receiver_tenant_id"\n',
        known=set(),
    )
    assert violations == []


def test_tenant_function_with_tenant_argument_passes(tmp_path: Path):
    violations = scan_text(tmp_path, 'QUERY = "SELECT * FROM fsma.get_team_roster(CAST(:tid AS uuid))"\n')
    assert violations == []
    violations = scan_text(tmp_path, 'QUERY = "SELECT * FROM fsma.lookup_by_token(:link_token)"\n')
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]


def test_fstring_map_and_module_constant_resolve(tmp_path: Path):
    body = (
        '_PRED = "(o.tenant_id IS NULL OR o.tenant_id = $tenant_id)"\n'
        "def get(lot_tlc):\n"
        '    query = f"""\n'
        "        MATCH (l:Lot {{tlc: $tlc, tenant_id: $tenant_id}})-[:UNDERWENT]->(e:TraceEvent)\n"
        "        MATCH (o:Obligation)-[:GOVERNS]->(e)\n"
        "        WHERE {_PRED}\n"
        "        RETURN l\n"
        '    """\n'
        "    return query\n"
    )
    violations = scan_text(tmp_path, body)
    # The module-level shim constant is flagged on its own (fail closed:
    # a bare shim has no node pattern to attribute), and the resolved
    # query flags its unscoped TraceEvent hop.
    assert [v.rule for v in violations] == [
        "tenant-failopen-shim",
        "cypher-match-without-tenant",
    ]
    assert violations[0].scope == "_PRED"
    assert violations[1].target == "TraceEvent"
    assert violations[1].scope == "get"


def test_unresolvable_builder_hole_never_counts(tmp_path: Path):
    body = 'def get():\n    query = f"SELECT * FROM fsma.cte_events WHERE {where_clause}"\n    return query\n'
    violations = scan_text(tmp_path, body)
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]


def test_dynamic_column_against_tenant_bind_passes(tmp_path: Path):
    body = 'def get(col):\n    query = f"SELECT * FROM fsma.cte_events WHERE {col} = :tenant_id"\n    return query\n'
    violations = scan_text(tmp_path, body)
    assert violations == []


def test_last_assignment_wins(tmp_path: Path):
    body = (
        "def get():\n"
        '    where = "WHERE tenant_id = :tid"\n'
        '    where = "WHERE event_type = :t"\n'
        '    query = "SELECT * FROM fsma.cte_events " + where\n'
        "    return query\n"
    )
    violations = scan_text(tmp_path, body)
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]


def test_concatenated_literal_predicate_passes(tmp_path: Path):
    body = (
        "def get():\n"
        '    pred = "tenant_id = :tid"\n'
        '    where = "WHERE " + pred\n'
        '    query = "SELECT * FROM fsma.cte_events " + where\n'
        "    return query\n"
    )
    violations = scan_text(tmp_path, body)
    assert violations == []


def test_nested_function_assignments_do_not_leak(tmp_path: Path):
    body = (
        "def outer():\n"
        '    query = "SELECT * FROM fsma.cte_events WHERE event_type = :t"\n'
        "    def inner():\n"
        '        pred = "tenant_id = :tid"\n'
        "        return pred\n"
        "    return query\n"
    )
    violations = scan_text(tmp_path, body)
    assert [v.rule for v in violations] == ["sql-without-tenant-predicate"]


def test_plus_concat_between_named_variables(tmp_path: Path):
    body = (
        "def get():\n"
        '    head = "MATCH (l:Lot {tlc: $tlc})"\n'
        '    tail = "WHERE l.tenant_id = $tenant_id RETURN l"\n'
        "    query = head + chr(10) + tail\n"
        "    return query\n"
    )
    violations = scan_text(tmp_path, body)
    # chr(10) is not a string expression, so only the head resolves: Lot
    # without its predicate is still flagged, which is fail-closed.
    assert [v.rule for v in violations] == ["cypher-match-without-tenant"]


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


def test_baseline_qhash_pins_the_reviewed_query(tmp_path: Path):
    body_a = 'QUERY = "MATCH (l:Lot {tlc: $tlc}) RETURN l"\n'
    body_b = 'QUERY = "MATCH (l:Lot {tlc: $other}) RETURN l"\n'
    path = write_source(tmp_path, "sample.py", body_a + body_b)
    digest_a = scanner.query_hash("MATCH (l:Lot {tlc: $tlc}) RETURN l")
    digest_b = scanner.query_hash("MATCH (l:Lot {tlc: $other}) RETURN l")
    assert digest_a != digest_b
    allowlist = write_allowlist(
        tmp_path,
        [
            {
                "file": str(path),
                "scope": "QUERY",
                "rule": "cypher-match-without-tenant",
                "target": "Lot",
                "reason": "reviewed query A only",
                "qhash": digest_a,
            }
        ],
    )
    fresh, stale = scanner.check([tmp_path], allowlist)
    assert [v.qhash for v in fresh] == [digest_b]
    assert stale == []


def test_stale_baseline_entry_fails_check(tmp_path: Path):
    write_source(
        tmp_path,
        "sample.py",
        'QUERY = "MATCH (l:Lot {tlc: $tlc, tenant_id: $tenant_id}) RETURN l"\n',
    )
    allowlist = write_allowlist(
        tmp_path,
        [
            {
                "file": "sample.py",
                "scope": "QUERY",
                "rule": "cypher-match-without-tenant",
                "target": "Lot",
                "reason": "fixed since",
            }
        ],
    )
    fresh, stale = scanner.check([tmp_path], allowlist)
    assert fresh == []
    assert len(stale) == 1


GATE_RUNS = 0


def run_gate(tmp_path: Path, body: str, baseline: list) -> int:
    import subprocess

    global GATE_RUNS
    GATE_RUNS += 1
    allowlist = write_allowlist(tmp_path, baseline)
    roots = tmp_path / f"roots{GATE_RUNS}"
    roots.mkdir()
    (roots / "sample.py").write_text(body, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCANNER_PATH), str(roots), "--allowlist", str(allowlist)],
        capture_output=True,
        text=True,
    )
    return proc.returncode


def test_main_exit_codes(tmp_path: Path):
    assert run_gate(tmp_path, "X = 1\n", []) == 0
    assert run_gate(tmp_path, 'QUERY = "MATCH (l:Lot {tlc: $tlc}) RETURN l"\n', []) == 1
    assert (
        run_gate(
            tmp_path,
            'QUERY = "MATCH (l:Lot {tlc: $tlc, tenant_id: $tenant_id}) RETURN l"\n',
            [
                {
                    "file": "sample.py",
                    "scope": "QUERY",
                    "rule": "cypher-match-without-tenant",
                    "target": "Lot",
                    "reason": "fixed since",
                }
            ],
        )
        == 1
    )


def test_main_missing_allowlist_exits_2(tmp_path: Path):
    import subprocess

    (tmp_path / "sample.py").write_text("X = 1\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCANNER_PATH), str(tmp_path), "--allowlist", str(tmp_path / "nope.yml")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


def test_missing_scan_root_is_a_config_error(tmp_path: Path):
    allowlist = write_allowlist(tmp_path, [])
    try:
        scanner.check([tmp_path / "nope"], allowlist)
    except scanner.ConfigError:
        return
    raise AssertionError("missing scan root must raise ConfigError")


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
        for key in ("file", "scope", "rule", "target", "reason", "qhash"):
            assert entry.get(key), f"baseline entry missing {key}: {entry}"
    labels = set(data["global_catalog_labels"])
    assert {"Obligation", "Section", "Regulation", "Citation"} <= labels
    assert not any(
        entry["scope"] == "find_gaps" and entry["rule"] == "tenant-failopen-shim" for entry in data["baseline"]
    ), "fixed find_gaps shim must not stay baselined"
    assert not any(entry["scope"] == "RegulationOverride.merge_cypher" for entry in data["baseline"]), (
        "fixed merge_cypher must not stay baselined"
    )


def test_semgrep_rule_file_has_expected_rules():
    data = yaml.safe_load(SEMGREP_RULES_PATH.read_text(encoding="utf-8"))
    rules = {rule["id"]: rule for rule in data["rules"]}
    assert rules["tenant-failopen-shim"]["severity"] == "ERROR"
    assert rules["cypher-match-without-tenant"]["severity"] == "WARNING"
    assert rules["cypher-merge-without-tenant"]["severity"] == "WARNING"
    assert rules["sql-on-tenant-table-without-tenant-predicate"]["severity"] == "WARNING"
