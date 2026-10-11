#!/usr/bin/env python3
"""Tenant-scope query gate (Pattern 3 foundational fix).

Flags Neo4j Cypher MATCH/MERGE statements that touch tenant data and raw
SQL statements against fsma tenant tables when neither carries a tenant
predicate, plus the ``$tenant_id IS NULL OR ...`` fail-open shim. This is
the blocking CI check; the semgrep rules in
.semgrep/tenant-query-scope.yaml cover the same ground for editors and
ad-hoc runs but cannot consume the allowlist below.

How it works: each Python file under the scan roots is parsed with ``ast``.
Every top-level string expression (plain constant, f-string, ``+``
concatenation, or module/function-level name bound to one of those) that
looks like a query is resolved to text and analyzed as a whole. Dynamic
``{placeholder}`` segments and unresolvable builder variables are removed
before the check, so a predicate that only exists inside an optional
builder (for example ``WHERE true {tenant_filter}``) does NOT count. Sites
that are scoped at runtime through such builders are recorded in the
allowlist with a reason instead of passing silently.

Scope: services/, server/ and regengine/ are scanned. Skipped: tests and
fixtures (they contain intentional shims), migrations/alembic, and
operator scripts/ directories (offline tooling that runs with full DB
access, for example the tenant-collision inventory).

Allowlist: .semgrep/tenant-scope-allowlist.yml lists the global catalog
labels and tables plus every baselined site, each with a reason. A finding
whose (file, scope, rule, target) matches a baseline entry passes; any
other finding fails the run. Fixing a baselined site should remove its
entry; stale entries print a warning.

Exit codes: 0 when no new violations, 1 on new violations, 2 on config
or usage errors (including a missing or malformed allowlist, which must
never silently pass).
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALLOWLIST = REPO_ROOT / ".semgrep" / "tenant-scope-allowlist.yml"
DEFAULT_SCAN_ROOTS = ("services", "server", "regengine")

SKIP_DIR_NAMES = frozenset({"tests", "migrations", "alembic", "scripts", "__pycache__", "fixtures", ".venv"})

# Neo4j labels that hold per-tenant data. Provision and Document exist in
# both the global regulatory database and per-tenant databases, so they
# are treated as tenant labels (fail closed); reads against the global
# database are baselined with a reason per site.
TENANT_LABELS = frozenset(
    {
        "Lot",
        "TLC",
        "TraceEvent",
        "Facility",
        "TenantOverlay",
        "RegulationOverride",
        "TenantControl",
        "ControlMapping",
        "CustomerProduct",
        "Control",
        "Evidence",
        "RegulatoryFact",
        "FoodItem",
        "Document",
        "Provision",
        "PendingSupplierInvite",
        "SupplierFacility",
        "SupplierContact",
        "BuyerTenant",
        "Tenant",
        "CTEEvent",
    }
)

LABEL_RE = re.compile(r"\(\s*\w*\s*:(\w+)")
CYPHER_RE = re.compile(r"\bMATCH\b|\bMERGE\b", re.IGNORECASE)
SQL_LIKE_RE = re.compile(
    r"\bSELECT\b.*\bFROM\b|\bUPDATE\b.*\bSET\b|\bDELETE\s+FROM\b|\bINSERT\s+INTO\b",
    re.IGNORECASE | re.DOTALL,
)
# The exact fail-open shape: a null tenant parameter matching every row.
SHIM_RE = re.compile(
    r"\$?tenant_id\s+IS\s+NULL\s+OR\b|\bOR\s+\$?tenant_id\s+IS\s+NULL",
    re.IGNORECASE,
)
# Predicate evidence. org_id is the established equivalent for tables
# keyed by organisation (for example fsma.compliance_alerts); bare :tid
# covers helpers that pass the tenant only as a bind parameter.
SQL_PRED_RE = re.compile(r"tenant_id|org_id|\btid\b", re.IGNORECASE)
CYPHER_PRED_RE = re.compile(r"tenant_id", re.IGNORECASE)
TABLE_REF_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.]*)\b|\bUPDATE\s+([A-Za-z_][\w.]*)\b"
    r"|\bINSERT\s+INTO\s+([A-Za-z_][\w.]*)\b|\bDELETE\s+FROM\s+([A-Za-z_][\w.]*)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    scope: str
    rule: str
    target: str
    excerpt: str

    def key(self) -> tuple[str, str, str, str]:
        return (self.file, self.scope, self.rule, self.target)


@dataclass(frozen=True)
class BaselineEntry:
    file: str
    scope: str
    rule: str
    target: str
    reason: str


def load_allowlist(path: Path) -> tuple[set[str], set[str], list[BaselineEntry]]:
    """Read global labels, global tables and baselined sites.

    Raises ConfigError when the file is missing or malformed, so a broken
    allowlist fails the gate instead of passing it.
    """
    import yaml

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"allowlist not found: {path} ({exc})") from exc
    try:
        data = yaml.safe_load(raw)
    except Exception as exc:
        raise ConfigError(f"allowlist is not valid YAML: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"allowlist must be a mapping: {path}")
    labels = data.get("global_catalog_labels") or {}
    tables = data.get("global_sql_tables") or {}
    baseline = data.get("baseline") or []
    if not isinstance(labels, dict) or not isinstance(tables, dict):
        raise ConfigError("allowlist: global_catalog_labels and global_sql_tables must be mappings")
    if not isinstance(baseline, list):
        raise ConfigError("allowlist: baseline must be a list")
    entries = []
    for i, item in enumerate(baseline):
        if not isinstance(item, dict):
            raise ConfigError(f"allowlist baseline[{i}] must be a mapping")
        missing = {"file", "scope", "rule", "target", "reason"} - set(item)
        if missing:
            raise ConfigError(f"allowlist baseline[{i}] missing keys: {sorted(missing)}")
        entries.append(
            BaselineEntry(
                file=str(item["file"]),
                scope=str(item["scope"]),
                rule=str(item["rule"]),
                target=str(item["target"]),
                reason=str(item["reason"]),
            )
        )
    return set(labels), set(tables), entries


class ConfigError(Exception):
    pass


class QueryResolver:
    """Resolve a string expression to text as far as statically possible."""

    def __init__(self, assigns: dict[str, str | None]):
        self.assigns = assigns

    def resolve(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                else:
                    parts.append(" ")
            # Literal {...} spans in an f-string are author-written text such
            # as Cypher maps, not placeholders: interpolations arrive as AST
            # nodes and are already blanked above. Stripping the literals
            # deleted real tenant predicates (for example a Lot map holding
            # tenant_id), so keep them.
            return "".join(parts)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self.resolve(node.left)
            right = self.resolve(node.right)
            if left is None and right is None:
                return None
            return (left or " ") + (right or " ")
        if isinstance(node, ast.Name):
            return self.assigns.get(node.id)
        return None


def _is_string_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_string_expr(node.left) or _is_string_expr(node.right)
    return False


def _scope_name(parents: list[ast.AST], node: ast.AST) -> str:
    funcs = [p for p in parents if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if funcs:
        inner = funcs[-1]
        classes = [p for p in parents if isinstance(p, ast.ClassDef)]
        if classes and classes[-1].lineno < inner.lineno:
            return f"{classes[-1].name}.{inner.name}"
        return inner.name
    for parent in reversed(parents):
        if isinstance(parent, ast.Assign):
            for target in parent.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    return target.id
    return "<module>"


def _iter_top_string_exprs(tree: ast.AST) -> list[tuple[ast.AST, list[ast.AST]]]:
    """Top-level string expressions with their ancestor chains.

    Fragments nested inside a larger string expression (operands of ``+``,
    literal pieces of an f-string) are skipped so a concatenated query is
    analyzed once, as a whole.
    """
    found: list[tuple[ast.AST, list[ast.AST]]] = []

    def visit(node: ast.AST, parents: list[ast.AST], inside_string: bool) -> None:
        is_str = _is_string_expr(node)
        if is_str and not inside_string and isinstance(node, (ast.Constant, ast.JoinedStr, ast.BinOp)):
            found.append((node, list(parents)))
            inside_string = True
        for child in ast.iter_child_nodes(node):
            visit(child, parents + [node], inside_string)

    visit(tree, [], False)
    return found


def _module_assigns(tree: ast.AST) -> dict[str, str | None]:
    """Names bound to strings by direct module-level assignments."""
    assigns: dict[str, str | None] = {}
    resolver = QueryResolver(assigns)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and _is_string_expr(node.value):
                assigns[target.id] = resolver.resolve(node.value)
    return assigns


def _function_assigns(func: ast.AST, outer: dict[str, str | None]) -> dict[str, str | None]:
    """Names bound to strings inside one function, layered over module names."""
    local: dict[str, str | None] = {}
    resolver = QueryResolver({**outer, **local})
    for child in ast.walk(func):
        if isinstance(child, ast.Assign) and len(child.targets) == 1:
            target = child.targets[0]
            if isinstance(target, ast.Name) and _is_string_expr(child.value):
                local.setdefault(target.id, resolver.resolve(child.value))
    return {**outer, **local}


def _tenant_tables(text: str, global_tables: set[str]) -> list[str]:
    tables: list[str] = []
    for match in TABLE_REF_RE.finditer(text):
        ref = next(g for g in match.groups() if g)
        ref = ref.strip().strip("(),;")
        if "." in ref:
            schema, table = ref.split(".", 1)
            table = table.split("(")[0]
            if schema.lower() == "fsma" and table.lower() not in {g.lower() for g in global_tables}:
                tables.append(f"fsma.{table}")
    return sorted(set(tables))


def analyze_text(text: str, global_tables: set[str]) -> list[tuple[str, str]]:
    """Return (rule, target) pairs for one resolved query string."""
    findings: list[tuple[str, str]] = []
    if SHIM_RE.search(text):
        label = sorted(set(LABEL_RE.findall(text)) & TENANT_LABELS)
        findings.append(("tenant-failopen-shim", ",".join(label) or "query"))
    if CYPHER_RE.search(text):
        labels = set(LABEL_RE.findall(text))
        touched = sorted(labels & TENANT_LABELS)
        if touched and not CYPHER_PRED_RE.search(text):
            rule = (
                "cypher-merge-without-tenant"
                if re.search(r"\bMERGE\b", text, re.IGNORECASE)
                else "cypher-match-without-tenant"
            )
            findings.append((rule, ",".join(touched)))
    if SQL_LIKE_RE.search(text):
        tables = _tenant_tables(text, global_tables)
        if tables and not SQL_PRED_RE.search(text):
            findings.append(("sql-without-tenant-predicate", ",".join(tables)))
    return findings


def scan_file(path: Path, relpath: str, global_tables: set[str]) -> list[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    module_names = _module_assigns(tree)
    violations: list[Violation] = []
    seen: set[tuple[str, str, str, str]] = set()
    for node, parents in _iter_top_string_exprs(tree):
        if isinstance(node, ast.Constant):
            # Skip docstrings (first statement of a module, class or function).
            if parents and isinstance(parents[-1], ast.Expr):
                holder = parents[-2] if len(parents) > 1 else tree
                if isinstance(holder, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if holder.body and holder.body[0] is parents[-1]:
                        continue
        funcs = [p for p in parents if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef))]
        names = _function_assigns(funcs[-1], module_names) if funcs else module_names
        resolved = QueryResolver(names).resolve(node)
        if not resolved:
            continue
        if not (CYPHER_RE.search(resolved) or SQL_LIKE_RE.search(resolved) or SHIM_RE.search(resolved)):
            continue
        scope = _scope_name(parents, node)
        lineno = getattr(node, "lineno", 1)
        for rule, target in analyze_text(resolved, global_tables):
            key = (relpath, scope, rule, target)
            if key in seen:
                continue
            seen.add(key)
            excerpt = " ".join(resolved.strip().split())[:160]
            violations.append(Violation(relpath, lineno, scope, rule, target, excerpt))
    return violations


def iter_source_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if "test_" in path.name:
                continue
            files.append(path)
    return files


def scan_roots(roots: list[Path], global_tables: set[str]) -> list[Violation]:
    violations: list[Violation] = []
    for path in iter_source_files(roots):
        try:
            relpath = str(path.relative_to(REPO_ROOT))
        except ValueError:
            relpath = str(path)
        violations.extend(scan_file(path, relpath, global_tables))
    return violations


def check(roots: list[Path], allowlist_path: Path) -> tuple[list[Violation], list[BaselineEntry]]:
    _, global_tables, baseline = load_allowlist(allowlist_path)
    allowed = {(e.file, e.scope, e.rule, e.target) for e in baseline}
    violations = scan_roots(roots, global_tables)
    fresh = [v for v in violations if v.key() not in allowed]
    matched = {v.key() for v in violations}
    stale = [e for e in baseline if (e.file, e.scope, e.rule, e.target) not in matched]
    return fresh, stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tenant-scope query gate.")
    parser.add_argument(
        "roots",
        nargs="*",
        default=[str(REPO_ROOT / r) for r in DEFAULT_SCAN_ROOTS],
        help="Directories to scan (default: services server regengine).",
    )
    parser.add_argument(
        "--allowlist",
        default=str(DEFAULT_ALLOWLIST),
        help="Path to tenant-scope-allowlist.yml.",
    )
    args = parser.parse_args(argv)
    try:
        fresh, stale = check([Path(r) for r in args.roots], Path(args.allowlist))
    except ConfigError as exc:
        print(f"tenant-scope gate misconfigured: {exc}", file=sys.stderr)
        return 2
    for entry in stale:
        print(
            f"STALE BASELINE (site fixed or moved, remove the entry): "
            f"{entry.file} :: {entry.scope} :: {entry.rule} :: {entry.target}"
        )
    if fresh:
        print("Tenant-scope query gate failed: queries without a tenant predicate:")
        for v in fresh:
            print(f"  {v.file}:{v.line} [{v.scope}] {v.rule} target={v.target}")
            print(f"    {v.excerpt}")
        print("Add a tenant predicate, or record the site in .semgrep/tenant-scope-allowlist.yml with a reason.")
        return 1
    print(f"Tenant-scope query gate passed ({len(stale)} stale baseline entries).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
