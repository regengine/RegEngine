"""Cypher tenant-scope proof for every read query in services/graph.

This suite proves that each Cypher query which reads tenant data carries a
tenant predicate, so one tenant can never read another tenant's rows through
the graph layer. It has two halves:

1. Static scan (no Neo4j needed). Every triple-quoted Cypher literal under
   ``services/graph/app`` is extracted with ``ast`` and checked:
   every node with a tenant-owned label must be tenant scoped, either
   inline (``{tenant_id: $tenant_id}``), by alias predicate
   (``alias.tenant_id = $tenant_id`` before the RETURN clause), or by the
   variable-length path guard (``ALL(n IN nodes(path) ...)``). The
   fail-open ``$tenant_id IS NULL OR ...`` shim is rejected everywhere.
2. Runtime capture. Queries composed at runtime (f-strings, depth
   interpolation) cannot be judged from source text, so these tests invoke
   the real functions with mocked sessions and run the same checker over
   the composed Cypher.

Out of scope for this suite, by design:

* Write templates (any literal containing MERGE or CREATE). They are
  covered by the per-module regression tests instead.
* Global catalog reads (Obligation, Provision, Concept, Jurisdiction and
  the Document rows served from the separate global database). These carry
  no tenant rows by design and are listed in CATALOG_ALLOWLIST with the
  reason for each entry.
* Dynamically composed queries are listed in DYNAMIC_INVENTORY. Each entry
  names how it is covered (runtime test in this file, or catalog).

When a check below fails on current code it is marked
``xfail(strict=True)`` naming the bug, so the suite stays green while the
bug is open and starts failing (XPASS) the moment someone fixes the query,
which forces removal of the mark. Product files named in the task are not
edited here.
"""

from __future__ import annotations

import ast
import re
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

TENANT_A = "11111111-1111-1111-1111-111111111111"

# Labels whose nodes carry tenant rows (composite uniqueness constraints
# pair the business key with tenant_id, so two tenants can share the key).
REQUIRING_LABELS = frozenset(
    {
        "Lot",
        "TraceEvent",
        "Facility",
        "FoodItem",
        "RegulatoryFact",
        "TenantControl",
        "CustomerProduct",
        "ControlMapping",
        "Evidence",
        "Control",
        "TenantOverlay",
        "Tenant",
        "Document",
        "RegulationOverride",
    }
)

# Labels treated as global catalog: they never require a tenant predicate on
# their own. A query that touches only these labels is a catalog read.
# (Obligation, Section, Regulation and Citation are shared regulatory
# content; Provision, Concept and Jurisdiction live in the global database.)
CATALOG_LABELS = frozenset(
    {
        "Obligation",
        "Section",
        "Regulation",
        "Citation",
        "Provision",
        "Concept",
        "Jurisdiction",
        "GlobalJurisdiction",
    }
)

FAILOPEN_SHIM = "$tenant_id IS NULL"

NODE_RE = re.compile(r"\(\s*([A-Za-z_]\w*)\s*:((?:\s*:\s*[A-Za-z_]\w*|\s*[A-Za-z_]\w*)+)")
ANON_NODE_RE = re.compile(r"\(\s*:\s*([A-Za-z_]\w*)")
GUARD_RE = re.compile(r"ALL\s*\([^()]*?nodes\s*\(\s*\w+\s*\)[^()]*?tenant_id")
PATH_ASSIGN_RE = re.compile(r"(\w+)\s*=\s*\(")
CLAUSE_RE = re.compile(r"\b(WHERE|WITH|UNWIND|RETURN|ORDER|LIMIT|SKIP|OPTIONAL|MATCH|CALL|USING)\b")
ALIAS_PRED_RE_TEMPLATE = r"(?<![\w$]){alias}\.tenant_id"


class QueryScopeError(AssertionError):
    """Raised when a Cypher read is not tenant scoped."""


def _flatten(query: str) -> str:
    """Strip ``//`` comments and collapse whitespace for stable matching."""
    no_comments = re.sub(r"//[^\n]*", "", query)
    return " ".join(no_comments.split())


def _matching_paren(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise QueryScopeError(f"unbalanced parens near offset {open_idx}")


def _path_bound_aliases(flat: str) -> set[str]:
    """Aliases bound inside a ``name = (pattern)`` path assignment that is
    protected by an ALL(nodes(path)) tenant guard."""
    if not GUARD_RE.search(flat):
        return set()
    bound: set[str] = set()
    for assign in PATH_ASSIGN_RE.finditer(flat):
        rest = flat[assign.end() :]
        clause = CLAUSE_RE.search(rest)
        region = rest[: clause.start()] if clause else rest
        for node in NODE_RE.finditer(region):
            if node.group(1):
                bound.add(node.group(1))
    return bound


def assert_query_scoped(source: str, query: str) -> None:
    """Assert one Cypher read query is tenant scoped.

    Raises QueryScopeError (an AssertionError) describing the first gap.
    """
    flat = _flatten(query)
    if FAILOPEN_SHIM in flat:
        raise QueryScopeError(
            f"{source}: fail-open null-tenant shim {FAILOPEN_SHIM!r} returns "
            "every tenant's rows when the caller forgets tenant_id"
        )
    if "$tenant_id" not in flat:
        raise QueryScopeError(f"{source}: no $tenant_id parameter binding; query is unscoped")
    zone = flat.split("RETURN")[0]
    guarded = _path_bound_aliases(flat)

    occurrences: list[tuple[str, str, int]] = []
    for node in NODE_RE.finditer(flat):
        alias = node.group(1)
        labels = [part.strip(" :") for part in re.findall(r":\s*[A-Za-z_]\w*", node.group(0))]
        for label in labels:
            occurrences.append((alias, label, node.start()))
    for anon in ANON_NODE_RE.finditer(flat):
        occurrences.append(("", anon.group(1), anon.start()))

    for alias, label, start in occurrences:
        if label in CATALOG_LABELS:
            continue
        if label not in REQUIRING_LABELS:
            continue
        if alias and alias in guarded:
            continue
        try:
            close = _matching_paren(flat, start)
        except QueryScopeError:
            close = start
        if "tenant_id" in flat[start:close]:
            continue
        if alias and re.search(ALIAS_PRED_RE_TEMPLATE.format(alias=re.escape(alias)), zone):
            continue
        if not alias:
            raise QueryScopeError(f"{source}: anonymous (:{label}) node has no tenant predicate")
        raise QueryScopeError(
            f"{source}: (:{label}) aliased {alias!r} has no tenant predicate "
            "(no inline tenant_id, no alias.tenant_id predicate, no path guard)"
        )


# ── Extraction ─────────────────────────────────────────────────────────────


def _const_text(node: ast.AST) -> tuple[str, bool] | None:
    """Best-effort static text of a string expression.

    Returns (text, dynamic) where dynamic means a value is interpolated, or
    None when the expression cannot be composed statically at all.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value, False)
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        dynamic = False
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                dynamic = True
                parts.append(" ")
        return ("".join(parts), dynamic)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _const_text(node.left)
        right = _const_text(node.right)
        if left is None or right is None:
            return None
        return (left[0] + right[0], left[1] or right[1])
    return None


def _docstring_ids(tree: ast.Module) -> set[int]:
    """Ids of string constants that are docstrings (not queries)."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _enclosing_name(tree: ast.Module, target: ast.AST) -> str:
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    current = parents.get(id(target))
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parents.get(id(current))
    return "<module>"


def _extract(path: Path):
    """Return (static_literals, dynamic_sites) for one source file.

    static_literals: list of (lineno, text, enclosing function).
    dynamic_sites: list of (lineno, enclosing function) for MATCH queries
    composed at runtime (f-strings or concatenation with values).
    """
    tree = ast.parse(path.read_text())
    docstrings = _docstring_ids(tree)
    skip: set[int] = set()
    static: list[tuple[int, str, str]] = []
    dynamic: list[tuple[int, str]] = []

    def _claim(node: ast.AST) -> None:
        for child in ast.walk(node):
            skip.add(id(child))

    for node in ast.walk(tree):
        if isinstance(node, (ast.JoinedStr, ast.BinOp)):
            if id(node) in skip:
                continue
            composed = _const_text(node)
            if composed is None:
                text = "".join(
                    child.value
                    for child in ast.walk(node)
                    if isinstance(child, ast.Constant) and isinstance(child.value, str)
                )
                if "MATCH" in text or "CALL db.index" in text:
                    dynamic.append((node.lineno, _enclosing_name(tree, node)))
                    _claim(node)
            elif "MATCH" in composed[0] or "CALL db.index" in composed[0]:
                if composed[1]:
                    dynamic.append((node.lineno, _enclosing_name(tree, node)))
                else:
                    static.append((node.lineno, composed[0], _enclosing_name(tree, node)))
                _claim(node)

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip
            and id(node) not in docstrings
            and ("MATCH" in node.value or "CALL db.index" in node.value)
        ):
            static.append((node.lineno, node.value, _enclosing_name(tree, node)))
    return sorted(static), sorted(dynamic)


def _is_write(text: str) -> bool:
    return bool(re.search(r"\b(MERGE|CREATE)\b", text))


def _collect():
    reads: list[tuple[str, int, str, str]] = []
    dynamic: list[tuple[str, int, str]] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        rel = path.relative_to(APP_ROOT).as_posix()
        static, dynamic_sites = _extract(path)
        for lineno, text, func in static:
            if _is_write(text):
                continue
            flat = _flatten(text)
            if not NODE_RE.search(flat) and not ANON_NODE_RE.search(flat) and "CALL db.index" not in flat:
                continue
            reads.append((rel, lineno, func, text))
        for lineno, func in dynamic_sites:
            dynamic.append((rel, lineno, func))
    return reads, dynamic


READ_QUERIES, DYNAMIC_SITES = _collect()


def _labels_of(text: str) -> str:
    flat = _flatten(text)
    labels = sorted({label for _, label in NODE_RE.findall(flat)} | set(ANON_NODE_RE.findall(flat)))
    return ",".join(labels) if labels else ("fulltext" if "CALL db.index" in flat else "none")


# ── Known findings and catalog exceptions ──────────────────────────────────
# Each KNOWN_GAPS entry is a real scoping gap on current code. The matching
# parametrized case is marked xfail(strict=True): it fails today, and the
# strict flag turns the suite red the moment the query is fixed, which
# forces removal of the entry. Product files are not edited by this task.


KNOWN_GAPS = [
    {
        "file": "fsma/chain_integrity.py",
        "snippet": "NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) }",
        "bug": "BUG-001 find_gaps inner Lot in the NOT EXISTS sub-query "
        "carries no tenant predicate, so a cross-tenant Lot satisfies the "
        "lot linkage and suppresses a genuine missing_lot gap (fail-open "
        "null-tenant shim removed in #3227; Lot remainder retained)",
        "fix": [
            (
                "NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) }",
                "NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) WHERE l.tenant_id = $tenant_id }",
            ),
        ],
    },
    {
        "file": "routers/lineage_traversal.py",
        "snippet": "OPTIONAL MATCH (f)-[:SUPERSEDES]->(prev:RegulatoryFact)",
        "bug": "BUG-004 LINEAGE_BY_TLC_QUERY returns prev.tlc from an unscoped "
        "OPTIONAL MATCH, and the Python invariant check only inspects the "
        "anchor fact, so a cross-tenant predecessor leaks its TLC",
        "fix": [
            (
                "OPTIONAL MATCH (f)-[:SUPERSEDES]->(prev:RegulatoryFact)",
                "OPTIONAL MATCH (f)-[:SUPERSEDES]->(prev:RegulatoryFact) WHERE prev.tenant_id = $tenant_id",
            ),
        ],
    },
    {
        "file": "fsma/data_quality.py",
        "snippet": "sum(CASE WHEN NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) }",
        "bug": "BUG-005 analyze_kde_completeness counts a cross-tenant Lot as "
        "satisfying the lot linkage, undercounting missing_lot for the caller "
        "(same NOT EXISTS shape fixed per-node in #1301 for chain_integrity)",
        "fix": [
            (
                "NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) }",
                "NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) WHERE l.tenant_id = $tenant_id }",
            ),
        ],
    },
    {
        "file": "overlay_resolver.py",
        "snippet": "OPTIONAL MATCH (product)<-[:MAPS_TO]-(control:TenantControl)",
        "bug": "BUG-006 get_regulatory_requirements anchors on a scoped product "
        "but the OPTIONAL MATCH join into TenantControl has no tenant "
        "predicate, surfacing another tenant's controls (same class as the "
        "#1278/#1289/#1294 fixes for the sibling queries in this file)",
        "fix": [
            (
                "OPTIONAL MATCH (product)<-[:MAPS_TO]-(control:TenantControl)",
                "OPTIONAL MATCH (product)<-[:MAPS_TO]-(control:TenantControl {tenant_id: $tenant_id})",
            ),
        ],
    },
]

# Reads that are catalog by design: no tenant rows exist behind them, so no
# tenant predicate is required. Each entry must still match a live query
# (test_catalog_allowlist_entries_current fails on stale entries).
CATALOG_ALLOWLIST = [
    {
        "file": "overlay_resolver.py",
        "snippet": "WHERE prov.hash IN $hashes",
        "reason": "global regulation database (separate global_db session); "
        "provisions and their documents are shared catalog content",
    },
    {
        "file": "overlay_resolver.py",
        "snippet": "MATCH (prov:Provision {hash: $hash})",
        "reason": "global regulation database (separate global_db session); "
        "provision, document, concept and jurisdiction are shared catalog",
    },
    {
        "file": "overlay_resolver.py",
        "snippet": "MATCH (prov:Provision)\n                WHERE prov.hash IN $hashes",
        "reason": "global regulation database (separate global_db session); "
        "provision lookup by hash for control details",
    },
    {
        "file": "overlay_resolver.py",
        "snippet": "MATCH (prov:Provision)-[:APPLIES_TO]->(j:Jurisdiction {name: $jurisdiction})",
        "reason": "global regulation database (separate global_db session); "
        "jurisdiction provision listing is shared catalog content",
    },
]

# Dynamically composed MATCH queries (f-strings or concatenation with runtime
# values) whose full predicate is invisible to the static scan, keyed by
# file and enclosing function with the expected site count. Disposition
# "runtime" means a runtime capture test in this file proves scoping over
# the composed Cypher (for the linker GOVERNS write template it proves the
# shared-catalog predicate instead; write templates are out of checker
# scope by design). map_requirement's 3 sites became static literals in
# #3227: the two reads now pass the static scan and the MERGE is excluded.
DYNAMIC_INVENTORY = {
    ("fsma/tracer.py", "trace_forward"): {"count": 2, "disposition": "runtime"},
    ("fsma/tracer.py", "trace_backward"): {"count": 1, "disposition": "runtime"},
    ("routers/regulations.py", "list_regulations"): {"count": 1, "disposition": "runtime"},
    ("routers/regulations.py", "get_requirement_mappings"): {"count": 1, "disposition": "runtime"},
    ("traceability_linker.py", "link_obligation_to_traceability"): {"count": 2, "disposition": "runtime"},
    ("traceability_linker.py", "get_governing_regulations"): {"count": 1, "disposition": "runtime"},
    ("traceability_linker.py", "get_impacted_lots"): {"count": 1, "disposition": "runtime"},
}


def _gap_for(rel: str, text: str):
    for gap in KNOWN_GAPS:
        if gap["file"] == rel and gap["snippet"] in text:
            return gap
    return None


def _allowlisted(rel: str, text: str) -> bool:
    return any(entry["file"] == rel and entry["snippet"] in text for entry in CATALOG_ALLOWLIST)


def _case_id(rel: str, lineno: int, text: str) -> str:
    return f"{rel}:{lineno} [{_labels_of(text)}]"


def _scan_params():
    params = []
    for rel, lineno, func, text in READ_QUERIES:
        gap = _gap_for(rel, text)
        marks: list = []
        # A known gap always wins over the catalog allowlist, so a shared
        # substring can never hide a scoping gap behind a skip.
        if gap is not None:
            marks.append(pytest.mark.xfail(strict=True, reason=gap["bug"]))
        elif _allowlisted(rel, text):
            marks.append(pytest.mark.skip(reason="global catalog read, see CATALOG_ALLOWLIST"))
        params.append(pytest.param(rel, text, marks=marks, id=_case_id(rel, lineno, text)))
    return params


def test_read_query_inventory_sane():
    """The extractor must see the real query population, or it proves nothing."""
    assert len(READ_QUERIES) >= 25, f"extractor found only {len(READ_QUERIES)} reads; check _extract"
    assert DYNAMIC_SITES, "extractor found no dynamic query sites; check _extract"


@pytest.mark.parametrize("rel,text", _scan_params())
def test_read_query_is_tenant_scoped(rel: str, text: str):
    """Every static Cypher read of tenant data carries a tenant predicate."""
    assert_query_scoped(_case_id(rel, 0, text), text)


def test_known_gap_entries_current():
    """Every KNOWN_GAPS entry must still match a live query (no stale xfails)."""
    for gap in KNOWN_GAPS:
        matched = [
            _case_id(rel, lineno, text)
            for rel, lineno, func, text in READ_QUERIES
            if gap["file"] == rel and gap["snippet"] in text
        ]
        assert matched, f"stale KNOWN_GAPS entry, query was fixed or moved: {gap['bug']}"


def test_catalog_allowlist_entries_current():
    """Every CATALOG_ALLOWLIST entry must still match a live query."""
    for entry in CATALOG_ALLOWLIST:
        matched = [
            _case_id(rel, lineno, text)
            for rel, lineno, func, text in READ_QUERIES
            if entry["file"] == rel and entry["snippet"] in text
        ]
        assert matched, f"stale CATALOG_ALLOWLIST entry: {entry['snippet'][:60]!r}"


def test_dynamic_query_inventory():
    """Every runtime-composed MATCH query must be a known, covered site."""
    actual: dict[tuple[str, str], int] = {}
    for rel, lineno, func in DYNAMIC_SITES:
        actual[(rel, func)] = actual.get((rel, func), 0) + 1
    expected = {key: value["count"] for key, value in DYNAMIC_INVENTORY.items()}
    assert actual == expected, (
        "dynamic MATCH inventory changed; classify each new site as runtime-covered "
        f"or catalog. actual={actual} expected={expected}"
    )


@pytest.mark.parametrize("gap", KNOWN_GAPS, ids=[gap["bug"].split(" ", 1)[0] for gap in KNOWN_GAPS])
def test_checker_accepts_fixed_shape(gap):
    """The checker is not vacuous: the documented fix shape passes it."""
    literals = [text for rel, _, _, text in READ_QUERIES if gap["file"] == rel and gap["snippet"] in text]
    assert literals, f"gap entry matches nothing: {gap['bug']}"
    fixed = literals[0]
    for old, new in gap["fix"]:
        assert old in fixed, f"fix pattern no longer applies: {old!r}"
        fixed = fixed.replace(old, new)
    assert_query_scoped(f"fixed-shape {gap['bug'].split(' ', 1)[0]}", fixed)


# ── Runtime capture helpers ────────────────────────────────────────────────


class _Result:
    def __init__(self, records, single=None):
        self._records = list(records)
        self._single = single

    async def single(self):
        return self._single

    def __aiter__(self):
        async def _gen():
            for record in self._records:
                yield record

        return _gen()


class _CaptureSession:
    def __init__(self, store, single=None):
        self._store = store
        self._single = single

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query, *args, **kwargs):
        self._store.append(query)
        return _Result([], single=self._single)


def _capture_client(store, single=None):
    client = MagicMock()
    session = _CaptureSession(store, single=single)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    client.session = MagicMock(return_value=context)
    return client


class _FakeNeo4jClient:
    """Stand-in for Neo4jClient capturing session.run queries."""

    queries: list = []

    def __init__(self, *args, **kwargs):
        pass

    @staticmethod
    def get_tenant_database_name(tenant_id):
        return "neo4j"

    @staticmethod
    def get_global_database_name():
        return "global"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def session(self):
        return _CaptureSession(_FakeNeo4jClient.queries)


@pytest.fixture
def captured_queries(monkeypatch):
    _FakeNeo4jClient.queries = []
    return _FakeNeo4jClient.queries


def _match_queries(captured):
    return [query for query in captured if "MATCH" in query]


# ── Runtime tests: tracer traversals ───────────────────────────────────────


@pytest.mark.asyncio
async def test_trace_forward_composed_queries_scoped():
    """trace_forward traversal and facility queries scope every node."""
    from services.graph.app.fsma.tracer import trace_forward

    for enforce in (True, False):
        store: list = []
        await trace_forward(_capture_client(store), tlc="LOT-A", tenant_id=TENANT_A, enforce_time_arrow=enforce)
        matched = _match_queries(store)
        assert matched, "trace_forward issued no MATCH query"
        for query in matched:
            assert_query_scoped(f"trace_forward enforce_time_arrow={enforce}", query)
        traversal = [query for query in matched if "MATCH path" in query]
        assert traversal, "variable-length traversal query missing"
        assert "ALL(" in traversal[0] and "nodes(path)" in traversal[0]


@pytest.mark.asyncio
async def test_trace_backward_composed_queries_scoped():
    """trace_backward traversal and facility queries scope every node."""
    from services.graph.app.fsma.tracer import trace_backward

    store: list = []
    await trace_backward(_capture_client(store), tlc="LOT-A", tenant_id=TENANT_A)
    matched = _match_queries(store)
    assert matched, "trace_backward issued no MATCH query"
    for query in matched:
        assert_query_scoped("trace_backward", query)


# ── Runtime tests: regulations router ──────────────────────────────────────


@pytest.mark.asyncio
async def test_list_regulations_composed_query_scoped(captured_queries, monkeypatch):
    """list_regulations composes the tenant predicate into the WHERE clause."""
    from services.graph.app.routers import regulations as regulations_router

    monkeypatch.setattr(regulations_router, "Neo4jClient", _FakeNeo4jClient)
    await regulations_router.list_regulations(
        jurisdiction=None, skip=0, limit=50, api_key=object(), tenant_id=uuid.UUID(TENANT_A)
    )
    matched = _match_queries(captured_queries)
    assert matched, "list_regulations issued no MATCH query"
    for query in matched:
        assert_query_scoped("list_regulations", query)
    assert "r.tenant_id = $tenant_id" in matched[0]


@pytest.mark.asyncio
async def test_requirement_mappings_composed_scopes_obligations(captured_queries, monkeypatch):
    """Obligation mapping reads are tenant filtered on both ends."""
    from services.graph.app.routers import regulations as regulations_router

    monkeypatch.setattr(regulations_router, "Neo4jClient", _FakeNeo4jClient)
    await regulations_router.get_requirement_mappings(
        obligation_id=None, regulation=None, skip=0, limit=50, api_key=object(), tenant_id=uuid.UUID(TENANT_A)
    )
    matched = _match_queries(captured_queries)
    assert matched, "get_requirement_mappings issued no MATCH query"
    assert "o1.tenant_id = $tenant_id" in matched[0]
    assert "o2.tenant_id = $tenant_id" in matched[0]


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="BUG-007 get_requirement_mappings scopes o1/o2 but not the joined "
    "s1/s2 Sections, so a cross-tenant REQUIRES edge leaks the other "
    "tenant's regulation name into the mapping rows",
)
async def test_requirement_mappings_composed_scopes_sections(captured_queries, monkeypatch):
    """Joined Section nodes in the mappings query must be tenant filtered."""
    from services.graph.app.routers import regulations as regulations_router

    monkeypatch.setattr(regulations_router, "Neo4jClient", _FakeNeo4jClient)
    await regulations_router.get_requirement_mappings(
        obligation_id=None, regulation=None, skip=0, limit=50, api_key=object(), tenant_id=uuid.UUID(TENANT_A)
    )
    matched = _match_queries(captured_queries)
    assert matched, "get_requirement_mappings issued no MATCH query"
    assert "s1.tenant_id = $tenant_id" in matched[0]
    assert "s2.tenant_id = $tenant_id" in matched[0]


# ── Runtime tests: overlay writer listings ──────────────────────────────────


@pytest.mark.asyncio
async def test_overlay_writer_list_queries_scoped(monkeypatch):
    """list_controls and list_products compose tenant-scoped MATCH queries."""
    from services.graph.app import overlay_writer as overlay_writer_module

    writer = overlay_writer_module.OverlayWriter.__new__(overlay_writer_module.OverlayWriter)
    writer.tenant_id = uuid.UUID(TENANT_A)
    writer.db_name = "neo4j"

    _FakeNeo4jClient.queries = []
    result = _Result([], single={"total": 0})

    async def run_with_count(query, *args, **kwargs):
        _FakeNeo4jClient.queries.append(query)
        return result

    session = _CaptureSession(_FakeNeo4jClient.queries)
    session.run = run_with_count  # type: ignore[method-assign]

    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    fake_client = MagicMock()
    fake_client.session = MagicMock(return_value=context)
    fake_client.close = AsyncMock()
    monkeypatch.setattr(overlay_writer_module, "Neo4jClient", lambda database=None: fake_client)

    await writer.list_controls()
    await writer.list_controls(framework="NIST CSF")
    await writer.list_products()
    await writer.list_products(product_type="TRADING")

    matched = _match_queries(_FakeNeo4jClient.queries)
    assert len(matched) == 8, f"expected 8 listing queries, got {len(matched)}"
    for query in matched:
        assert_query_scoped("overlay_writer listing", query)


# ── Runtime tests: mapping engine required tenant ───────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant_id", [None, ""], ids=["none", "empty"])
async def test_map_requirement_empty_tenant_rejected_before_query(tenant_id):
    """map_requirement with a null/empty tenant raises before touching the session (#3227).

    Fails against the pre-#3227 shape, which built tenant-optional Cypher
    and ran it instead of raising.
    """
    mapping_engine = pytest.importorskip("services.graph.app.mapping_engine")

    engine = mapping_engine.MappingEngine.__new__(mapping_engine.MappingEngine)
    engine.driver = MagicMock()
    engine.llm = MagicMock()

    with pytest.raises(ValueError, match="tenant_id"):
        await engine.map_requirement("obligation text", tenant_id=tenant_id)
    engine.driver.session.assert_not_called()


# ── Runtime tests: traceability linker composed queries ──────────────────────
# #3220 rebuilt the linker queries as f-strings interpolating
# _OBLIGATION_TENANT_PREDICATE, so they are invisible to the static scan and
# are covered here instead (see DYNAMIC_INVENTORY). Obligation rows are
# quarantined by Decision 3: only rows stamped ``catalog = true`` by a
# catalog writer are shared, tenant-stamped rows are confined to their
# tenant, and unmarked null-tenant rows match no tenant. Each composed
# query must carry the quarantine predicate with $tenant_id bound as a
# parameter, never interpolated. Fake sessions only; no driver or network
# is touched.


class _LinkerCaptureSession:
    """Fake Neo4j session capturing composed linker queries and bindings."""

    def __init__(self, store):
        self._store = store
        self._queued: list = []

    def queue(self, rows=None, single_row=None):
        self._queued.append(_Result(list(rows or []), single=single_row))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query, **kwargs):
        self._store.append((query, kwargs))
        return self._queued.pop(0)


def _linker_with_capture(store):
    """TraceabilityLinker wired to a capturing fake session (no driver)."""
    from services.graph.app.traceability_linker import TraceabilityLinker

    linker = TraceabilityLinker.__new__(TraceabilityLinker)
    session = _LinkerCaptureSession(store)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=context)
    linker.driver = driver
    return linker, session


# Independent expectation: quarantine predicate. Literal on purpose —
# importing the product constant would mirror the implementation. There is
# deliberately no ``IS NULL`` arm: unmarked null-tenant rows must match no
# tenant, and only ``catalog = true`` rows are shared.
_EXPECTED_OBLIGATION_PREDICATE = "(o.tenant_id = $tenant_id OR o.catalog = true)"
_OBLIGATION_WHERE_RE = re.compile(r"WHERE\s*" + re.escape(_EXPECTED_OBLIGATION_PREDICATE) + r"\s*(MATCH|RETURN|MERGE)")


def _assert_obligation_predicate(source: str, query: str, kwargs: dict) -> None:
    """The exact quarantine WHERE predicate is present, bound, not interpolated."""
    flat = _flatten(query)
    assert _OBLIGATION_WHERE_RE.search(flat), (
        f"{source}: missing exact shared-catalog WHERE {_EXPECTED_OBLIGATION_PREDICATE!r} "
        f"before MATCH/RETURN/MERGE:\n{query}"
    )
    assert kwargs.get("tenant_id") == TENANT_A, f"{source}: $tenant_id not bound: {kwargs!r}"
    assert TENANT_A not in query, f"{source}: tenant value interpolated into Cypher:\n{query}"


@pytest.mark.asyncio
async def test_obligation_predicate_weakened_or_true_rejected(monkeypatch):
    """Independent check rejects a weakened OR-true catalog predicate (mutation)."""
    import services.graph.app.traceability_linker as linker_module

    monkeypatch.setattr(
        linker_module,
        "_OBLIGATION_TENANT_PREDICATE",
        "(o.tenant_id = $tenant_id OR o.catalog = true OR true)",
    )
    store: list = []
    linker, session = _linker_with_capture(store)
    session.queue(rows=[{"regulation": "FSMA", "requirement": "x", "requirement_id": "obl-9"}])
    await linker.get_governing_regulations("tlc-1", TENANT_A)
    query, kwargs = store[0]
    with pytest.raises(AssertionError):
        _assert_obligation_predicate("weakened-predicate", query, kwargs)


@pytest.mark.asyncio
async def test_obligation_predicate_old_null_shim_rejected(monkeypatch):
    """The pre-quarantine null-tenant shim must fail the quarantine check.

    Decision 3 removed the ``o.tenant_id IS NULL`` arm because it showed
    every unmarked null-tenant obligation to every tenant. If that shape
    ever returns, this test goes red.
    """
    import services.graph.app.traceability_linker as linker_module

    monkeypatch.setattr(
        linker_module,
        "_OBLIGATION_TENANT_PREDICATE",
        "(o.tenant_id IS NULL OR o.tenant_id = $tenant_id)",
    )
    store: list = []
    linker, session = _linker_with_capture(store)
    session.queue(rows=[{"regulation": "FSMA", "requirement": "x", "requirement_id": "obl-9"}])
    await linker.get_governing_regulations("tlc-1", TENANT_A)
    query, kwargs = store[0]
    with pytest.raises(AssertionError):
        _assert_obligation_predicate("null-shim-predicate", query, kwargs)


@pytest.mark.asyncio
async def test_link_obligation_queries_carry_obligation_predicate():
    """link_obligation_to_traceability fetch and GOVERNS write scope the Obligation anchor (#3220)."""
    store: list = []
    linker, session = _linker_with_capture(store)
    session.queue(single_row={"text": "Cooling logs required daily", "category": "COOLING"})
    session.queue(rows=[{"event_id": "e1", "type": "COOLING"}])

    links = await linker.link_obligation_to_traceability("obl-9", TENANT_A)

    assert len(links) == 1
    assert len(store) == 2, f"expected fetch + write queries, got {len(store)}"
    for query, kwargs in store:
        _assert_obligation_predicate("link_obligation_to_traceability", query, kwargs)
    assert "e.tenant_id = $tenant_id" in store[1][0]


@pytest.mark.asyncio
async def test_get_governing_regulations_composed_obligation_predicate():
    """get_governing_regulations binds the shared-catalog predicate (#3220)."""
    store: list = []
    linker, session = _linker_with_capture(store)
    session.queue(rows=[{"regulation": "FSMA", "requirement": "Cool it", "requirement_id": "obl-9"}])

    regs = await linker.get_governing_regulations("tlc-1", TENANT_A)

    assert len(regs) == 1
    assert len(store) == 1
    query, kwargs = store[0]
    assert "MATCH" in query
    _assert_obligation_predicate("get_governing_regulations", query, kwargs)
    assert kwargs.get("tlc") == "tlc-1"


@pytest.mark.asyncio
async def test_get_governing_regulations_composed_traceevent_scoped():
    """Composed governing query must scope the joined TraceEvent (BUG-002)."""
    store: list = []
    linker, session = _linker_with_capture(store)
    session.queue(rows=[{"regulation": "FSMA", "requirement": "Cool it", "requirement_id": "obl-9"}])

    await linker.get_governing_regulations("tlc-1", TENANT_A)

    matched = [query for query, _ in store if "MATCH" in query]
    assert matched, "get_governing_regulations issued no MATCH query"
    for query in matched:
        assert_query_scoped("get_governing_regulations composed", query)


@pytest.mark.asyncio
async def test_get_impacted_lots_composed_obligation_predicate():
    """get_impacted_lots binds the shared-catalog predicate (#3220)."""
    store: list = []
    linker, session = _linker_with_capture(store)
    session.queue(rows=[{"tlc": "tlc-1", "description": "Lettuce"}])

    lots = await linker.get_impacted_lots("obl-9", TENANT_A)

    assert len(lots) == 1
    assert len(store) == 1
    query, kwargs = store[0]
    assert "MATCH" in query
    _assert_obligation_predicate("get_impacted_lots", query, kwargs)
    assert kwargs.get("id") == "obl-9"


@pytest.mark.asyncio
async def test_get_impacted_lots_composed_traceevent_scoped():
    """Composed impacted-lots query must scope the joined TraceEvent (BUG-003)."""
    store: list = []
    linker, session = _linker_with_capture(store)
    session.queue(rows=[{"tlc": "tlc-1", "description": "Lettuce"}])

    await linker.get_impacted_lots("obl-9", TENANT_A)

    matched = [query for query, _ in store if "MATCH" in query]
    assert matched, "get_impacted_lots issued no MATCH query"
    for query in matched:
        assert_query_scoped("get_impacted_lots composed", query)
