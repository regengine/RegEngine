"""In-memory Neo4j double that *executes* the FSMA graph queries.

Why this exists
---------------
The graph service's trace queries are direction-sensitive: ``PRODUCED`` and
``CONSUMED`` are persisted **event -> lot** by ``FSMARelationships``
(``services/graph/app/models/fsma_nodes.py``), so a traversal that walks them
the other way silently returns nothing — or, worse, returns *downstream*
nodes while claiming to be an upstream trace.

Every pre-existing test for these queries either mocks ``session.run`` with an
empty result and asserts on the **Cypher string**, or feeds hand-written
records straight back to the parser. Neither can see a direction error. This
double closes that gap without a Neo4j server: it holds a small property graph
and evaluates the specific query shapes the tracer / data-quality modules
emit, honouring the direction written in the Cypher.

Two properties make the resulting tests meaningful rather than circular:

1. Edges are created by :meth:`FakeGraph.apply_writer`, which *parses the
   repository's own* ``FSMARelationships`` MERGE template. The fixture graph
   therefore points the way production writes it, not the way a test author
   assumed it points.
2. Traversal direction is read out of the query text under test. Flip an
   arrow (or a ``startNode``/``endNode``) in the tracer and this double walks
   the other way, so a "fix" applied backwards fails the test instead of
   passing it.

Supported query shapes (deliberately narrow — this is a test double, not a
Cypher implementation):

* ``MATCH path = (start:Label {prop: $param})<rel*lo..hi>(end)`` variable-length
  traversal, with the ``ALL(n IN nodes(path) WHERE n.tenant_id = $tenant_id)``
  guard and the ``CASE type(...) WHEN ... THEN startNode/endNode ...``
  per-relationship direction predicate.
* Fixed-length chain ``MATCH``/``OPTIONAL MATCH`` clauses with
  ``var.prop = $param`` / ``var.prop IN $param`` predicates and a
  ``RETURN [DISTINCT] properties(var) AS name, ...`` projection.

Anything else evaluates to an empty result rather than raising, so a query
this double does not model degrades to "no rows" instead of a false pass.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = ["FakeGraph", "FakeNeo4jClient"]


# ---------------------------------------------------------------------------
# Cypher fragment parsing
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"//[^\n]*")

# A node token: (var:Label {prop: $param, prop2: $param2})  — all parts optional
_NODE_RE = re.compile(r"\(\s*(?P<var>\w*)\s*(?::(?P<label>\w+))?\s*(?:\{(?P<props>[^}]*)\})?\s*\)")

# A relationship token: -[:A|B]->  /  <-[:A]-  /  -[:A|B*1..20]-
_REL_RE = re.compile(r"(?P<lhs><-|-)\[\s*:(?P<types>[A-Z_|]+)(?:\*(?P<lo>\d+)\.\.(?P<hi>\d+))?\s*\](?P<rhs>->|-)")

# Tokenizer that walks a pattern left-to-right.
_TOKEN_RE = re.compile(
    r"(?P<node>\(\s*\w*(?::\w+)?(?:\s*\{[^}]*\})?\s*\))"
    r"|(?P<rel>(?:<-|-)\[\s*:[A-Z_|]+(?:\*\d+\.\.\d+)?\s*\](?:->|-))"
)

_PROP_PAIR_RE = re.compile(r"(\w+)\s*:\s*\$(\w+)")

# WHERE predicates this double understands.
_EQ_PRED_RE = re.compile(r"(\w+)\.(\w+)\s*=\s*\$(\w+)")
_IN_PRED_RE = re.compile(r"(\w+)\.(\w+)\s+IN\s+\$(\w+)")

# Per-relationship direction predicate, e.g.
#   WHEN 'PRODUCED' THEN endNode(relationships(path)[idx]) = nodes(path)[idx]
#   ELSE            startNode(relationships(path)[idx]) = nodes(path)[idx]
# endNode == the node we are standing on  -> the edge points *at* us  -> inbound
# startNode == the node we are standing on -> the edge points *away*  -> outbound
_WHEN_DIR_RE = re.compile(r"WHEN\s+'(?P<type>\w+)'\s+THEN\s+(?P<fn>startNode|endNode)\s*\(")
_ELSE_DIR_RE = re.compile(r"ELSE\s+(?P<fn>startNode|endNode)\s*\(")

_FN_TO_DIRECTION = {"endNode": "in", "startNode": "out"}

_PROJECTION_RE = re.compile(r"properties\(\s*(\w+)\s*\)\s+(?:AS|as)\s+(\w+)")

_MATCH_CLAUSE_RE = re.compile(r"^\s*(?P<optional>OPTIONAL\s+)?MATCH\s+(?P<pattern>.+)$", re.IGNORECASE)


def _strip_comments(query: str) -> str:
    return _COMMENT_RE.sub("", query)


def _parse_props(body: Optional[str]) -> Dict[str, str]:
    """``"tlc: $tlc, tenant_id: $tenant_id"`` -> ``{"tlc": "tlc", ...}``."""
    if not body:
        return {}
    return {prop: param for prop, param in _PROP_PAIR_RE.findall(body)}


def _tokenize_pattern(pattern: str) -> List[Tuple[str, str]]:
    """Split a Cypher pattern into ordered ``("node"|"rel", text)`` tokens."""
    tokens: List[Tuple[str, str]] = []
    for m in _TOKEN_RE.finditer(pattern):
        kind = "node" if m.group("node") else "rel"
        tokens.append((kind, m.group(kind)))
    return tokens


def _parse_rel(token: str) -> Dict[str, Any]:
    m = _REL_RE.match(token)
    assert m is not None, f"unparsable relationship token: {token!r}"
    lhs, rhs = m.group("lhs"), m.group("rhs")
    if lhs == "<-" and rhs == "-":
        direction = "in"
    elif lhs == "-" and rhs == "->":
        direction = "out"
    else:
        direction = "any"
    return {
        "types": set(m.group("types").split("|")),
        "direction": direction,
        "lo": int(m.group("lo")) if m.group("lo") else 1,
        "hi": int(m.group("hi")) if m.group("hi") else 1,
    }


def _parse_node(token: str) -> Dict[str, Any]:
    m = _NODE_RE.match(token)
    assert m is not None, f"unparsable node token: {token!r}"
    return {
        "var": m.group("var") or "",
        "label": m.group("label"),
        "props": _parse_props(m.group("props")),
    }


# ---------------------------------------------------------------------------
# The graph itself
# ---------------------------------------------------------------------------


class FakeGraph:
    """A tiny labelled property graph with directed, typed relationships."""

    def __init__(self) -> None:
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Tuple[str, str, str]] = []  # (rel_type, src_key, dst_key)

    # -- construction -------------------------------------------------------

    def add_node(self, key: str, labels: Sequence[str], **props: Any) -> str:
        self.nodes[key] = {"labels": list(labels), "props": dict(props)}
        return key

    def add_edge(self, rel_type: str, src_key: str, dst_key: str) -> None:
        edge = (rel_type, src_key, dst_key)
        if edge not in self.edges:
            self.edges.append(edge)

    def apply_writer(self, template: str, **params: Any) -> None:
        """Create an edge by interpreting a ``FSMARelationships`` MERGE template.

        The template supplies both the node lookups and the arrow direction, so
        the fixture graph is wired exactly the way production persists it. If a
        ``MATCH`` cannot be resolved the MERGE is a no-op, mirroring Neo4j.
        """
        text = _strip_comments(template)
        bindings: Dict[str, str] = {}
        for raw in re.findall(r"MATCH\s*(\([^)]*\))", text):
            spec = _parse_node(raw)
            key = self._find_node(spec, params)
            if key is None:
                return  # MATCH found nothing -> MERGE never runs
            bindings[spec["var"]] = key

        merge = re.search(r"MERGE\s*\(\s*(\w+)\s*\)-\[\s*:(\w+)\s*\]->\(\s*(\w+)\s*\)", text)
        assert merge is not None, f"apply_writer only handles `MERGE (a)-[:T]->(b)`; got: {template!r}"
        src_var, rel_type, dst_var = merge.group(1), merge.group(2), merge.group(3)
        if src_var in bindings and dst_var in bindings:
            self.add_edge(rel_type, bindings[src_var], bindings[dst_var])

    # -- lookup helpers -----------------------------------------------------

    def _matches(self, key: str, spec: Dict[str, Any], params: Dict[str, Any]) -> bool:
        node = self.nodes[key]
        if spec["label"] and spec["label"] not in node["labels"]:
            return False
        for prop, param in spec["props"].items():
            if node["props"].get(prop) != params.get(param):
                return False
        return True

    def _find_node(self, spec: Dict[str, Any], params: Dict[str, Any]) -> Optional[str]:
        for key in self.nodes:
            if self._matches(key, spec, params):
                return key
        return None

    def _candidates(self, spec: Dict[str, Any], params: Dict[str, Any]) -> List[str]:
        return [key for key in self.nodes if self._matches(key, spec, params)]

    def _neighbours(self, key: str, types: Iterable[str], direction: str) -> List[str]:
        out: List[str] = []
        wanted = set(types)
        for rel_type, src, dst in self.edges:
            if rel_type not in wanted:
                continue
            if src == key and direction in ("out", "any"):
                out.append(dst)
            elif dst == key and direction in ("in", "any"):
                out.append(src)
        return out

    # -- query execution ----------------------------------------------------

    def execute(self, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = _strip_comments(query)
        if re.search(r"MATCH\s+path\s*=", text):
            return self._execute_path_query(text, params)
        return self._execute_chain_query(text, params)

    # variable-length ``MATCH path = ...``
    def _execute_path_query(self, text: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        pattern_m = re.search(r"MATCH\s+path\s*=\s*([^\n]+)", text)
        if not pattern_m:
            return []
        tokens = _tokenize_pattern(pattern_m.group(1))
        if len(tokens) < 3:
            return []

        start_spec = _parse_node(tokens[0][1])
        rel = _parse_rel(tokens[1][1])

        # Per-relationship direction overrides, read out of the CASE predicate.
        dirmap: Dict[str, str] = {t: rel["direction"] for t in rel["types"]}
        if rel["direction"] == "any":
            for m in _WHEN_DIR_RE.finditer(text):
                dirmap[m.group("type")] = _FN_TO_DIRECTION[m.group("fn")]
            else_m = _ELSE_DIR_RE.search(text)
            if else_m:
                fallback = _FN_TO_DIRECTION[else_m.group("fn")]
                named = {m.group("type") for m in _WHEN_DIR_RE.finditer(text)}
                for rel_type in rel["types"] - named:
                    dirmap[rel_type] = fallback

        tenant = params.get("tenant_id")
        enforce_tenant = "n.tenant_id = $tenant_id" in text

        start_key = self._find_node(start_spec, params)
        if start_key is None:
            return []
        if enforce_tenant and self.nodes[start_key]["props"].get("tenant_id") != tenant:
            return []

        paths = self._expand(start_key, rel["types"], dirmap, rel["hi"])
        records: List[Dict[str, Any]] = []
        for path in paths:
            if len(path) - 1 < rel["lo"]:
                continue
            if enforce_tenant and any(self.nodes[k]["props"].get("tenant_id") != tenant for k in path):
                continue
            hop_count = len(path) - 1
            for key in dict.fromkeys(path):
                node = self.nodes[key]
                records.append(
                    {
                        "labels": list(node["labels"]),
                        "props": dict(node["props"]),
                        "hop_count": hop_count,
                    }
                )
        records.sort(key=lambda r: r["hop_count"])
        return records

    def _expand(
        self,
        start_key: str,
        types: Iterable[str],
        dirmap: Dict[str, str],
        max_len: int,
    ) -> List[List[str]]:
        """Enumerate acyclic paths from ``start_key`` honouring ``dirmap``."""
        wanted = set(types)
        found: List[List[str]] = []
        stack: List[List[str]] = [[start_key]]
        while stack:
            path = stack.pop()
            if len(path) - 1 >= max_len:
                continue
            cur = path[-1]
            for rel_type, src, dst in self.edges:
                if rel_type not in wanted:
                    continue
                mode = dirmap.get(rel_type, "any")
                nxt = None
                if src == cur and mode in ("out", "any"):
                    nxt = dst
                elif dst == cur and mode in ("in", "any"):
                    nxt = src
                if nxt is None or nxt in path:
                    continue
                extended = path + [nxt]
                found.append(extended)
                stack.append(extended)
        return found

    # fixed-length ``MATCH`` / ``OPTIONAL MATCH`` chains
    def _execute_chain_query(self, text: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        clauses: List[Tuple[bool, str]] = []
        for line in text.splitlines():
            m = _MATCH_CLAUSE_RE.match(line)
            if m and "(" in m.group("pattern"):
                clauses.append((bool(m.group("optional")), m.group("pattern").strip()))
        if not clauses:
            return []

        projection = _PROJECTION_RE.findall(text)
        if not projection:
            return []

        rows: List[Dict[str, Optional[str]]] = [{}]
        for optional, pattern in clauses:
            rows = self._extend_bindings(rows, pattern, params, optional)
            if not rows:
                return []

        rows = [r for r in rows if self._where_holds(r, text, params)]

        records: List[Dict[str, Any]] = []
        seen: List[Dict[str, Any]] = []
        for row in rows:
            record: Dict[str, Any] = {}
            for var, alias in projection:
                key = row.get(var)
                record[alias] = dict(self.nodes[key]["props"]) if key else None
            if "DISTINCT" in text.upper() and record in seen:
                continue
            seen.append(record)
            records.append(record)
        return records

    def _extend_bindings(
        self,
        rows: List[Dict[str, Optional[str]]],
        pattern: str,
        params: Dict[str, Any],
        optional: bool,
    ) -> List[Dict[str, Optional[str]]]:
        tokens = _tokenize_pattern(pattern)
        if not tokens:
            return rows
        specs = [_parse_node(t) for kind, t in tokens if kind == "node"]
        rels = [_parse_rel(t) for kind, t in tokens if kind == "rel"]

        extended: List[Dict[str, Optional[str]]] = []
        for row in rows:
            matches = self._walk_chain(row, specs, rels, params, 0, dict(row))
            if matches:
                extended.extend(matches)
            elif optional:
                blank = dict(row)
                for spec in specs:
                    blank.setdefault(spec["var"], None)
                extended.append(blank)
        return extended

    def _walk_chain(
        self,
        row: Dict[str, Optional[str]],
        specs: List[Dict[str, Any]],
        rels: List[Dict[str, Any]],
        params: Dict[str, Any],
        index: int,
        acc: Dict[str, Optional[str]],
    ) -> List[Dict[str, Optional[str]]]:
        spec = specs[index]
        var = spec["var"]

        if index == 0:
            bound = acc.get(var)
            candidates = [bound] if bound else self._candidates(spec, params)
        else:
            prev_key = acc[specs[index - 1]["var"]]
            rel = rels[index - 1]
            assert prev_key is not None
            candidates = [
                k for k in self._neighbours(prev_key, rel["types"], rel["direction"]) if self._matches(k, spec, params)
            ]

        results: List[Dict[str, Optional[str]]] = []
        for key in candidates:
            if key is None:
                continue
            if var in acc and acc[var] not in (None, key):
                continue
            nxt = dict(acc)
            nxt[var] = key
            if index + 1 == len(specs):
                results.append(nxt)
            else:
                results.extend(self._walk_chain(row, specs, rels, params, index + 1, nxt))
        return results

    def _where_holds(self, row: Dict[str, Optional[str]], text: str, params: Dict[str, Any]) -> bool:
        for var, prop, param in _EQ_PRED_RE.findall(text):
            key = row.get(var)
            if key is None:
                continue
            if self.nodes[key]["props"].get(prop) != params.get(param):
                return False
        for var, prop, param in _IN_PRED_RE.findall(text):
            key = row.get(var)
            if key is None:
                continue
            if self.nodes[key]["props"].get(prop) not in (params.get(param) or []):
                return False
        return True


# ---------------------------------------------------------------------------
# Neo4j driver surface
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, records: List[Dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self):
        async def _gen():
            for record in self._records:
                yield record

        return _gen()


class _Session:
    def __init__(self, graph: FakeGraph, calls: List[Tuple[str, Dict[str, Any]]]) -> None:
        self._graph = graph
        self._calls = calls

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def run(self, query: str, **params: Any) -> _Result:
        self._calls.append((query, params))
        return _Result(self._graph.execute(query, params))


class FakeNeo4jClient:
    """Stands in for ``Neo4jClient`` — ``session()`` returns an async CM."""

    def __init__(self, graph: FakeGraph) -> None:
        self._graph = graph
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def session(self, **_kwargs: Any) -> _Session:
        return _Session(self._graph, self.calls)

    async def close(self) -> None:
        return None

    async def __aenter__(self) -> "FakeNeo4jClient":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    @property
    def queries(self) -> List[str]:
        return [q for q, _ in self.calls]
