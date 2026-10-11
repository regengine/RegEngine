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
``{placeholder}`` segments keep a marker so their shape survives, but a
predicate that only exists inside an optional builder (for example
``WHERE true {tenant_filter}``) still does NOT count. Sites that are
scoped at runtime through such builders are recorded in the allowlist
with a reason instead of passing silently. A mere mention of
``tenant_id`` is not a predicate: comments, string literals, SELECT-list
columns, SET targets, and join conditions between two columns never count.
Each tenant label (Cypher) and each tenant table (SQL) needs its own real
comparison, either a ``WHERE`` comparison against a bind parameter or a
``tenant_id`` entry in that node's ``MATCH``/``MERGE`` property map.

Scope: services/, server/ and regengine/ are scanned. Skipped: tests and
fixtures (they contain intentional shims), migrations/alembic, and
operator scripts/ directories (offline tooling that runs with full DB
access, for example the tenant-collision inventory).

Allowlist: .semgrep/tenant-scope-allowlist.yml lists the global catalog
labels and tables plus every baselined site, each with a reason and a
``qhash`` pinning the exact query text that was reviewed. A finding whose
(file, scope, rule, target, qhash) matches a baseline entry passes; any
other finding fails the run. Fixing a baselined site should remove its
entry. Stale entries (a baseline row no live query matches) fail the run
so a fixed site cannot silently suppress a later regression at the same
key.

Exit codes: 0 when no new violations and no stale entries, 1 on new
violations or stale entries, 2 on config or usage errors (including a
missing or malformed allowlist, a missing scan root, an unreadable file,
or an unparseable file, none of which must ever silently pass).
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

# One node pattern: the text between a single pair of parentheses holds
# the alias, the colon-separated labels, and the optional property map.
NODE_CHUNK_RE = re.compile(r"\(([^()]*)\)")
# Every label on a node, including backtick-quoted labels and labels in
# second or later position (``(n:Obligation:Lot)``, ``(n:`Lot`)``). The
# colon must open the pattern, follow the alias, or follow another label,
# so bind parameters (``IN :critical``), comparisons (``= :tid``), and map
# keys (``{tlc: $tlc}``, read from the map separately) never count.
NODE_ALIAS_RE = re.compile(r"^\s*(\w+)\s*(?::|\{|$)")
_LABEL_COLON_RE = re.compile(r":\s*`?([A-Za-z_]\w*)`?")
_LABEL_BEFORE_RE = re.compile(r"(?:^|[(|:,`\w])$")
# Keywords that precede a colon bind parameter, never a node label
# (``WHERE x IN :list`` is not a node with label ``list``).
_LABEL_SKIP_WORDS = frozenset(
    {
        "IN",
        "AND",
        "OR",
        "NOT",
        "WHERE",
        "SET",
        "BY",
        "FROM",
        "SELECT",
        "VALUES",
        "LIKE",
        "ILIKE",
        "BETWEEN",
        "EXISTS",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "AS",
        "ON",
        "USING",
        "LIMIT",
        "OFFSET",
        "RETURN",
        "WITH",
        "MATCH",
        "MERGE",
        "OPTIONAL",
        "UNWIND",
        "CREATE",
        "DELETE",
        "REMOVE",
        "FOREACH",
        "UNION",
        "DISTINCT",
        "TRUE",
        "FALSE",
        "NULL",
    }
)


def _chunk_labels(chunk: str) -> set[str]:
    """Labels of one node pattern, excluding bind parameters and map keys
    (maps are stripped by the caller before this runs)."""
    labels: set[str] = set()
    for match in _LABEL_COLON_RE.finditer(chunk):
        before = chunk[: match.start()].rstrip()
        word = re.search(r"(\w+)$", before)
        if word and word.group(1).upper() in _LABEL_SKIP_WORDS:
            continue
        if not _LABEL_BEFORE_RE.search(before):
            continue
        labels.add(match.group(1))
    return labels


# An unresolvable dynamic fragment (an f-string hole or ``%s`` the gate
# cannot see through) keeps this marker, so a comparison against the
# tenant bind still shows its shape instead of vanishing.
DYNAMIC_HOLE = "__DYNAMIC__"
CYPHER_RE = re.compile(r"\bMATCH\b|\bMERGE\b", re.IGNORECASE)
SQL_LIKE_RE = re.compile(
    r"\bSELECT\b.*\bFROM\b|\bUPDATE\b.*\bSET\b|\bDELETE\s+FROM\b|\bINSERT\s+INTO\b",
    re.IGNORECASE | re.DOTALL,
)
# The fail-open shape: a null tenant matching every row. Parentheses may
# sit between NULL and OR (``($tenant_id IS NULL) OR ...``), and
# ``coalesce($tenant_id, <row>.tenant_id)`` degrades to the same thing
# when the parameter is null.
SHIM_RE = re.compile(
    r"\$?tenant_id\s+IS\s+NULL\s*\)?\s*OR\b"
    r"|\bOR\s*\(?\s*\$?tenant_id\s+IS\s+NULL"
    r"|coalesce\s*\(\s*\$?tenant_id\s*,",
    re.IGNORECASE,
)
# A real tenant comparison: ``tenant_id`` or ``org_id`` compared with ``=``
# to something that is not another column (bind parameters, literals, and
# expressions such as ``CAST(:tid AS uuid)`` count; a join condition such
# as ``a.tenant_id = b.tenant_id`` does not constrain any tenant). The
# comparison must sit in a WHERE clause or a node property map; SELECT
# lists, comments, string literals, and SET targets never count.
TENANT_CMP_RE = re.compile(
    r"(?<![\w$])(?:(\w+)\s*\.\s*)?(tenant_id|org_id)\s*=\s*(?!\w+\s*\.\s*\w)(?=\S)",
    re.IGNORECASE,
)
# Tenant-suffixed columns (``receiver_tenant_id``) only constrain the row
# when the value is the tenant bind, so ``not_tenant_id = 1`` still fails.
TENANT_SUFFIX_CMP_RE = re.compile(
    r"(?<![\w$])(?:(\w+)\s*\.\s*)?\w[\w$]*(tenant_id|org_id)\s*=\s*"
    r"(?=(?:__DYNAMIC__|%s|[:$][^\s,;)]*ten[^\s,;)]*|[:$][^\s,;)]*org[^\s,;)]*|[:$]tid\b))(?=\S)",
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
# Comments and quoted literals are noise: a predicate mention inside them
# constrains nothing.
_STRING_RE = re.compile(r"'(?:[^'\\]|\\.|'')*'|\"(?:[^\"\\]|\\.)*\"")
_LINE_COMMENT_RE = re.compile(r"--[^\n]*|//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# SET targets never count as predicates (``SET tenant_id = :t`` still
# writes every row the WHERE clause selects).
_SET_CLAUSE_RE = re.compile(
    r"\bSET\b.*?(?=\b(?:MATCH|MERGE|OPTIONAL|WHERE|RETURN|WITH|DELETE|REMOVE|CREATE|ON)\b|$)",
    re.IGNORECASE | re.DOTALL,
)
# WHERE clause terminators for both SQL and Cypher.
_WHERE_END_RE = re.compile(
    r"\b(?:GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|OFFSET|RETURNING|UNION|EXCEPT|INTERSECT"
    r"|RETURN|WITH|MATCH|MERGE|OPTIONAL|UNWIND|DELETE|REMOVE|CREATE|SET|SKIP)\b|;",
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
    qhash: str = ""

    def key(self) -> tuple[str, str, str, str]:
        return (self.file, self.scope, self.rule, self.target)


@dataclass(frozen=True)
class BaselineEntry:
    file: str
    scope: str
    rule: str
    target: str
    reason: str
    qhash: str = ""


def query_hash(resolved: str) -> str:
    """Stable id for one query text, so a baseline row pins the reviewed
    query instead of every future query at the same key."""
    import hashlib

    normalized = " ".join(resolved.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def entry_covers(entry: BaselineEntry, violation: Violation) -> bool:
    """Whether a baseline entry suppresses a finding.

    The (file, scope, rule, target) key must match, and when the entry
    carries a qhash the query text must match too, so one reviewed query
    never hides a different query added later at the same site. Entries
    without a qhash keep the old key-only behavior.
    """
    if (entry.file, entry.scope, entry.rule, entry.target) != violation.key():
        return False
    return not entry.qhash or entry.qhash == violation.qhash


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
        qhash = str(item.get("qhash") or "")
        if qhash and not re.fullmatch(r"[0-9a-f]{16}", qhash):
            raise ConfigError(f"allowlist baseline[{i}] has a malformed qhash: {qhash!r}")
        entries.append(
            BaselineEntry(
                file=str(item["file"]),
                scope=str(item["scope"]),
                rule=str(item["rule"]),
                target=str(item["target"]),
                reason=str(item["reason"]),
                qhash=qhash,
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
            # In an f-string the literal pieces and the interpolations are
            # separate AST nodes, so literal Cypher maps written with
            # doubled braces (``{{tenant_id: $tenant_id}}``) are real text
            # and must survive, while each ``{name}`` hole resolves from
            # the assigns map (a module-level predicate constant inlines
            # here; an unresolvable builder stays blank and never counts).
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value.replace("{{", "{").replace("}}", "}"))
                elif isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name):
                    resolved = self.assigns.get(value.value.id)
                    parts.append(resolved if isinstance(resolved, str) else DYNAMIC_HOLE)
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


def _iter_scope_statements(node: ast.AST) -> list[ast.stmt]:
    """Statements of one function body in source order, without descending
    into nested functions, classes, or lambdas (their assignments belong to
    a different scope)."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return list(node.body)
    return [node] if isinstance(node, ast.stmt) else []


def _walk_ordered(stmts: list[ast.stmt]) -> list[ast.stmt]:
    """Depth-first statement walk in source order, skipping nested scopes."""
    ordered: list[ast.stmt] = []
    for stmt in stmts:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        ordered.append(stmt)
        for child in ast.iter_child_nodes(stmt):
            if isinstance(child, ast.stmt):
                ordered.extend(_walk_ordered([child]))
    return ordered


def _bind_name(stmt: ast.stmt, assigns: dict[str, str | None]) -> None:
    targets: list[ast.AST] = []
    value: ast.AST | None = None
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        targets = list(stmt.targets)
        value = stmt.value
    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        targets = [stmt.target]
        value = stmt.value
    if value is None or not targets:
        return
    target = targets[0]
    if isinstance(target, ast.Name) and _is_string_expr(value):
        # The last assignment in source order wins, resolved against the
        # names bound so far, so a reassignment to an unscoped fragment is
        # what the query actually carries.
        assigns[target.id] = QueryResolver(assigns).resolve(value)


def _function_assigns(func: ast.AST, outer: dict[str, str | None]) -> dict[str, str | None]:
    """Names bound to strings inside one function, layered over module names."""
    assigns: dict[str, str | None] = {**outer}
    for stmt in _walk_ordered(_iter_scope_statements(func)):
        _bind_name(stmt, assigns)
    return assigns


def strip_noise(text: str) -> str:
    """Remove quoted literals and comments so a mention inside them never
    counts as a predicate."""
    text = _STRING_RE.sub(" ", text)
    text = _BLOCK_COMMENT_RE.sub(" ", text)
    return _LINE_COMMENT_RE.sub(" ", text)


def where_segment(text: str) -> str:
    """The WHERE clause tail of a SQL query, cut before the next clause
    keyword. Only comparisons inside it can constrain rows. (Cypher
    comparisons are read over the whole SET-stripped text so predicates
    inside EXISTS subqueries still count.)"""
    match = re.search(r"\bWHERE\b", text, re.IGNORECASE)
    if not match:
        return ""
    tail = text[match.end() :]
    end = _WHERE_END_RE.search(tail)
    return tail[: end.start()] if end else tail


def _clean_ref(ref: str) -> str:
    return ref.strip().strip("(),;").split("(")[0]


def _split_top_level(text: str) -> list[str]:
    """Split a FROM clause on commas, ignoring commas inside parentheses
    (function argument lists must stay whole)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _from_items(text: str) -> list[str]:
    """Every table item of each FROM clause, splitting comma-separated
    lists (``FROM fsma.a o, fsma.b e``) instead of reading only the first
    table."""
    items: list[str] = []
    for match in re.finditer(
        r"\bFROM\b(.*?)(?=\bWHERE\b|\bGROUP\b|\bORDER\b|\bLIMIT\b"
        r"|\bJOIN\b|\bHAVING\b|;|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        for part in _split_top_level(match.group(1)):
            part = part.strip()
            if part.strip("(),;"):
                # Full comma part (not just the first token): aliases live
                # here, and a trailing open paren marks a set-returning
                # function call, which the caller handles separately.
                items.append(part)
    return items


def _is_function_call(text: str, match_end: int) -> bool:
    """Whether a FROM/JOIN table reference opens an argument list, making
    it a set-returning function call rather than a plain table."""
    return text[match_end:].lstrip().startswith("(")


def _function_args_mention_tenant(text: str, match_end: int) -> bool:
    """Whether a function call's argument list carries the tenant bind."""
    tail = text[match_end:].lstrip()
    if not tail.startswith("("):
        return False
    depth = 0
    for i, char in enumerate(tail[:400]):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                args = tail[1:i]
                return bool(re.search(r"(?i)tenant|\borg\b|(?<=[:$])tid\b", args))
    return False


def _sql_tables_and_aliases(text: str, global_tables: set[str], known_tenant_tables: set[str]) -> dict[str, set[str]]:
    """Tenant tables touched by a SQL statement, each mapped to the aliases
    that may refer to it (explicit aliases plus the bare table name).
    Unqualified names count only when they name a known tenant table, so an
    unqualified read of a tenant table under a bare ``search_path`` cannot
    hide behind the missing schema prefix. A set-returning function call
    (``FROM fsma.roster_for(:tid)``) counts as scoped when its arguments
    carry the tenant bind; otherwise it is reported under its own name so
    the owning team records why the function is safe."""
    lowered_global = {g.lower() for g in global_tables}
    tables: dict[str, set[str]] = {}

    def add(ref: str, alias: str | None, func_scoped: bool = False) -> None:
        ref = _clean_ref(ref)
        if "." in ref:
            schema, table = ref.split(".", 1)
            if schema.lower() != "fsma" or table.lower() in lowered_global:
                return
            key = f"fsma.{table}"
        else:
            if ref.lower() in lowered_global or ref.lower() not in known_tenant_tables:
                return
            table = ref
            key = f"fsma.{table}"
        if not table:
            return
        if func_scoped:
            return
        aliases = tables.setdefault(key, set())
        aliases.add(table.lower())
        aliases.add(key.lower())
        if alias:
            aliases.add(alias.lower())

    for item in _from_items(text):
        parts = item.split()
        if not parts:
            continue
        if "(" in parts[0]:
            name = _clean_ref(parts[0].split("(")[0])
            if not name or name.upper() == "SELECT":
                continue
            if DYNAMIC_HOLE in name:
                # A call through an unresolvable name (``FROM fsma.{fn}()``)
                # cannot be judged statically; the old gate passed it too.
                # Recorded as a scanner limitation, not a finding.
                continue
            if _function_args_mention_tenant(item, item.index("(")):
                continue
            add(name, None)
            continue
        add(parts[0], parts[-1] if len(parts) > 1 and parts[-1].lower() != "as" else None)
        if len(parts) > 2 and parts[-2].lower() == "as":
            add(parts[0], parts[-1])
    for match in TABLE_REF_RE.finditer(text):
        groups = match.groups()
        ref = next(g for g in groups if g)
        group_index = next(i for i, g in enumerate(groups) if g)
        if DYNAMIC_HOLE in ref:
            # Unresolvable table or function name: nothing static to judge.
            continue
        if group_index == 0 and _is_function_call(text, match.end()):
            if _function_args_mention_tenant(text, match.end()):
                continue
        add(ref, None)
        upper = match.group(0).upper()
        if upper.startswith("JOIN"):
            tail = text[match.end() :]
            alias_match = re.match(r"\s+(?:AS\s+)?([A-Za-z_]\w*)", tail, re.IGNORECASE)
            if alias_match and alias_match.group(1).upper() not in (
                "ON",
                "INNER",
                "LEFT",
                "RIGHT",
                "FULL",
                "CROSS",
                "WHERE",
            ):
                add(ref, alias_match.group(1))
    return tables


def _node_patterns(text: str) -> list[tuple[str | None, set[str], str]]:
    """(alias, labels, map-text) for every Cypher node pattern."""
    patterns: list[tuple[str | None, set[str], str]] = []
    for chunk_match in NODE_CHUNK_RE.finditer(text):
        chunk = chunk_match.group(1)
        alias_match = NODE_ALIAS_RE.match(chunk)
        alias = alias_match.group(1) if alias_match else None
        brace = chunk.find("{")
        map_text = chunk[brace:] if brace >= 0 else ""
        # Labels come from outside the property map, so map keys never
        # read as labels.
        labels = _chunk_labels(chunk if brace < 0 else chunk[:brace])
        patterns.append((alias, labels, map_text))
    return patterns


def _merge_patterns(text: str) -> list[tuple[str | None, set[str], str]]:
    """Node patterns of MERGE clauses only. A MERGE key without tenant_id
    creates or matches rows across tenants no matter what a later SET or a
    sibling MATCH constrains, so MERGE labels are scoped by their map alone."""
    patterns: list[tuple[str | None, set[str], str]] = []
    for match in re.finditer(r"\bMERGE\b", text, re.IGNORECASE):
        tail = text[match.end() :]
        head = re.split(
            r"\b(?:MATCH|WHERE|RETURN|WITH|SET|DELETE|REMOVE|CREATE|ON|UNWIND|OPTIONAL)\b",
            tail,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        for chunk_match in NODE_CHUNK_RE.finditer(head):
            chunk = chunk_match.group(1)
            alias_match = NODE_ALIAS_RE.match(chunk)
            brace = chunk.find("{")
            patterns.append(
                (
                    alias_match.group(1) if alias_match else None,
                    _chunk_labels(chunk if brace < 0 else chunk[:brace]),
                    chunk[brace:] if brace >= 0 else "",
                )
            )
    return patterns


def analyze_text(
    text: str,
    global_tables: set[str],
    catalog_labels: set[str] | frozenset = frozenset(),
    known_tenant_tables: set[str] | frozenset = frozenset(),
) -> list[tuple[str, str]]:
    """Return (rule, target) pairs for one resolved query string."""
    findings: list[tuple[str, str]] = []
    clean = strip_noise(text)
    # The null-safe Postgres equality constrains exactly like ``=``.
    clean = re.sub(r"\bIS\s+NOT\s+DISTINCT\s+FROM\b", "=", clean, flags=re.IGNORECASE)
    # Labels that live in the shared global catalog by design need no
    # tenant predicate. Labels in TENANT_LABELS stay fail-closed even when
    # they also appear in the catalog mapping (Document, Provision).
    exempt = {label for label in catalog_labels} - set(TENANT_LABELS)
    lowered_known = {t.lower() for t in known_tenant_tables}

    if SHIM_RE.search(clean):
        patterns = _node_patterns(clean)
        alias_labels: dict[str, set[str]] = {}
        for alias, labels, _ in patterns:
            if alias:
                alias_labels.setdefault(alias.lower(), set()).update(labels)
        shim_aliases = set(
            m.group(1).lower()
            for m in re.finditer(r"(?<![\w$])(\w+)\s*\.\s*\$?tenant_id\s+IS\s+NULL", clean, re.IGNORECASE)
        )
        param_shim = re.search(
            r"(?<![\w$({\]])\$tenant_id\s+IS\s+NULL"
            r"|coalesce\s*\(\s*\$?tenant_id\s*,",
            clean,
            re.IGNORECASE,
        )
        catalog_shim = (
            bool(shim_aliases)
            and not param_shim
            and all(
                alias in alias_labels and alias_labels[alias] and alias_labels[alias] <= exempt
                for alias in shim_aliases
            )
        )
        # A shim on a global-catalog alias (``(o.tenant_id IS NULL ...`` on
        # an Obligation node) is the catalog design, not a fail-open tenant
        # read. Anything else, including a bare shim constant with no node
        # pattern to attribute, stays flagged.
        if not catalog_shim:
            touched = sorted({label for _, labels, _ in patterns for label in labels})
            findings.append(("tenant-failopen-shim", ",".join(touched) or "query"))

    if CYPHER_RE.search(clean):
        # SET clauses are stripped first (a later ``SET l.tenant_id`` never
        # scopes), but every other clause counts, so predicates inside
        # EXISTS subqueries still scope their node.
        no_set = _SET_CLAUSE_RE.sub(" ", clean)
        scoped_text = no_set + " " + " ".join(map_text for _, _, map_text in _node_patterns(no_set))
        comparisons = [(m.group(1) or "").lower() for m in TENANT_CMP_RE.finditer(scoped_text)]
        comparisons += [(m.group(1) or "").lower() for m in TENANT_SUFFIX_CMP_RE.finditer(scoped_text)]
        hole_scoped = bool(HOLE_TENANT_CMP_RE.search(scoped_text))
        qualified = {alias for alias in comparisons if alias}
        unqualified = any(not alias for alias in comparisons)
        patterns = _node_patterns(no_set)
        alias_labels: dict[str, set[str]] = {}
        for alias, labels, _ in patterns:
            if alias:
                alias_labels.setdefault(alias.lower(), set()).update(labels)
        # A comparison on an alias bound to a different node never scopes
        # this label; only an unqualified comparison or one on an
        # undeclared alias (``te.tenant_id`` on ``FROM fsma.cte_events``)
        # falls through to the single-label case below.
        fallback = unqualified or any(alias not in alias_labels for alias in qualified)
        merged: set[str] = set()
        for _, labels, map_text in _merge_patterns(clean):
            if not (MAP_TENANT_RE.search(map_text) or MAP_TENANT_VALUE_RE.search(map_text)):
                merged.update(labels)
        tenant_labels = sorted({label for _, labels, _ in patterns for label in labels} & set(TENANT_LABELS) - exempt)
        single = len(tenant_labels) == 1
        unscoped: list[str] = []
        for label in tenant_labels:
            if label in merged:
                unscoped.append(label)
                continue
            label_aliases = {a for a, labs in alias_labels.items() if label in labs}
            map_scoped = any(
                label in labels and (MAP_TENANT_RE.search(map_text) or MAP_TENANT_VALUE_RE.search(map_text))
                for _, labels, map_text in patterns
            )
            # A comparison on the label's own alias scopes it; with a
            # single tenant label an unqualified or undeclared-alias
            # comparison (or a dynamic hole compared against the tenant
            # bind) constrains that node.
            where_scoped = bool(label_aliases & qualified) or (single and (fallback or hole_scoped))
            if not (map_scoped or where_scoped):
                unscoped.append(label)
        if unscoped:
            rule = (
                "cypher-merge-without-tenant"
                if any(label in merged for label in unscoped)
                else "cypher-match-without-tenant"
            )
            findings.append((rule, ",".join(sorted(unscoped))))

    if SQL_LIKE_RE.search(clean):
        tables = _sql_tables_and_aliases(clean, global_tables, lowered_known)
        if tables:
            # INSERT carries no WHERE clause; the tenant column in the
            # column list or VALUES is the scoping evidence the gate can
            # see, so a mention there counts (SELECT/UPDATE/DELETE need a
            # real WHERE comparison below). The ON CONFLICT upsert tail is
            # not a second statement.
            statement = re.sub(r"(?i)\bON\s+CONFLICT\b.*", " ", clean)
            is_insert_only = bool(re.search(r"\bINSERT\s+INTO\b", statement, re.IGNORECASE))
            is_insert_only = is_insert_only and not re.search(
                r"\b(?:SELECT\b.*\bFROM\b|(?<!DO\s)(?<!DO\t)UPDATE\b.*\bSET\b|\bDELETE\s+FROM\b)",
                statement,
                re.IGNORECASE | re.DOTALL,
            )
            if is_insert_only:
                if not re.search(r"(?<![\w$])[\w$]*(tenant_id|org_id)\b", statement, re.IGNORECASE):
                    findings.append(("sql-without-tenant-predicate", ",".join(sorted(tables))))
                return findings
            where = where_segment(_SET_CLAUSE_RE.sub(" ", clean))
            comparisons = [(m.group(1) or "").lower() for m in TENANT_CMP_RE.finditer(where)]
            comparisons += [(m.group(1) or "").lower() for m in TENANT_SUFFIX_CMP_RE.finditer(where)]
            hole_scoped = bool(HOLE_TENANT_CMP_RE.search(where))
            qualified = {alias for alias in comparisons if alias}
            unqualified = any(not alias for alias in comparisons)
            bound = set()
            for aliases in tables.values():
                bound.update(aliases)
            fallback = unqualified or any(alias not in bound for alias in qualified)
            # A qualified comparison scopes its own table; with a single
            # tenant table an unqualified or undeclared-alias comparison
            # (``te.tenant_id = :tid`` on ``FROM fsma.cte_events``, or a
            # dynamic column compared against the tenant bind) constrains
            # that table. A second table in the same statement needs its
            # own predicate.
            single = len(tables) == 1
            unscoped_tables = sorted(
                key
                for key, aliases in tables.items()
                if not (aliases & qualified or (single and (fallback or hole_scoped)))
            )
            if unscoped_tables:
                findings.append(("sql-without-tenant-predicate", ",".join(unscoped_tables)))
    return findings


def scan_file(
    path: Path,
    relpath: str,
    global_tables: set[str],
    catalog_labels: set[str] | frozenset = frozenset(),
    known_tenant_tables: set[str] | frozenset = frozenset(),
    errors: list[str] | None = None,
) -> list[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        if errors is not None:
            errors.append(f"{relpath}: cannot read ({exc})")
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        if errors is not None:
            errors.append(f"{relpath}: cannot parse ({exc})")
        return []
    module_names = _module_assigns(tree)
    violations: list[Violation] = []
    seen: set[tuple[str, str, str, str, str]] = set()
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
        for rule, target in analyze_text(resolved, global_tables, catalog_labels, known_tenant_tables):
            digest = query_hash(resolved)
            key = (relpath, scope, rule, target, digest)
            if key in seen:
                continue
            seen.add(key)
            excerpt = " ".join(resolved.strip().split())[:160]
            violations.append(Violation(relpath, lineno, scope, rule, target, excerpt, digest))
    return violations


def iter_source_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            raise ConfigError(f"scan root not found: {root}")
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if "test_" in path.name:
                continue
            files.append(path)
    return files


def collect_fsma_tables(roots: list[Path]) -> set[str]:
    """Bare table names ever read with the ``fsma.`` prefix.

    An unqualified ``FROM cte_events`` under a bare ``search_path`` is the
    same tenant table, so the gate treats those names as tenant tables too.
    """
    names: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if "test_" in path.name:
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except OSError:
                continue
            names.update(m.group(1).lower() for m in re.finditer(r"\bfsma\.([A-Za-z_]\w*)", source))
    return names


def scan_roots(
    roots: list[Path], global_tables: set[str], catalog_labels: set[str] | frozenset = frozenset()
) -> list[Violation]:
    violations: list[Violation] = []
    errors: list[str] = []
    known = collect_fsma_tables(roots) - {g.lower() for g in global_tables}
    for path in iter_source_files(roots):
        try:
            relpath = str(path.relative_to(REPO_ROOT))
        except ValueError:
            relpath = str(path)
        violations.extend(scan_file(path, relpath, global_tables, catalog_labels, known, errors))
    if errors:
        raise ConfigError("scan errors (failing closed):\n  " + "\n  ".join(errors))
    return violations


def check(roots: list[Path], allowlist_path: Path) -> tuple[list[Violation], list[BaselineEntry]]:
    catalog_labels, global_tables, baseline = load_allowlist(allowlist_path)
    violations = scan_roots(roots, global_tables, catalog_labels)
    fresh = [v for v in violations if not any(entry_covers(e, v) for e in baseline)]
    stale = [e for e in baseline if not any(entry_covers(e, v) for v in violations)]
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
    if stale:
        print("Tenant-scope query gate failed: stale baseline entries (site fixed or moved):")
        for entry in stale:
            print(f"  STALE: {entry.file} :: {entry.scope} :: {entry.rule} :: {entry.target}")
        print("Remove the entry if the site is fixed; a stale entry must never linger,")
        print("because it would silently suppress a later regression at the same key.")
    if fresh:
        print("Tenant-scope query gate failed: queries without a tenant predicate:")
        for v in fresh:
            print(f"  {v.file}:{v.line} [{v.scope}] {v.rule} target={v.target}")
            print(f"    {v.excerpt}")
        print("Add a tenant predicate, or record the site in .semgrep/tenant-scope-allowlist.yml with a reason.")
    if fresh or stale:
        return 1
    print("Tenant-scope query gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
