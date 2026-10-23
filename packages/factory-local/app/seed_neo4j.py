"""Load an explicitly supplied graph into Neo4j and query buyer intent.

With no graph path, this command prints "No data yet" without connecting.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent

# Cypher cannot parameterize labels or relationship types.
NODES = {
    "bills": ("Bill", "bill_uid"),
    "versions": ("BillVersion", "version_uid"),
    "legislators": ("Legislator", "bioguide_or_os_id"),
    "committees": ("Committee", "committee_uid"),
    "corporations": ("Corporation", "domain"),
    "lobbying_firms": ("LobbyingFirm", "name"),
}
RELS = {
    "HAS_VERSION": ("Bill", "BillVersion"),
    "MORPHED_INTO": ("BillVersion", "BillVersion"),
    "SHARES_MODEL_DNA": ("Bill", "Bill"),
    "SPONSORED": ("Legislator", "Bill"),
    "CHAIRS": ("Legislator", "Committee"),
    "REFERRED_TO": ("Bill", "Committee"),
    "RETAINED": ("Corporation", "LobbyingFirm"),
    "LOBBIED_ON": ("LobbyingFirm", "Bill"),
}
KEY_OF = {label: key for label, key in NODES.values()}

MIN_PASSAGE_PROBABILITY = 0.4
INTENT_POSITIONS = ["OPPOSE", "AMEND", "MONITOR"]
BUYER_INTENT_QUERY = (
    "MATCH (c:Corporation)-[r:RETAINED]->(f:LobbyingFirm)-[:LOBBIED_ON]->(b:Bill) "
    "WHERE b.passage_probability >= $min_probability AND r.position IN $positions "
    "RETURN c.name AS corporation, f.name AS firm, b.bill_uid AS bill, "
    "b.passage_probability AS passage_probability, r.position AS position, "
    "r.spend AS spend, r.filing_id AS filing_id "
    "ORDER BY r.spend DESC, b.bill_uid"
)


def load_graph(path: Path) -> dict:
    return json.loads(path.read_text())


def create_constraints(session) -> None:
    for label, key in NODES.values():
        session.run(
            f"CREATE CONSTRAINT {label.lower()}_{key}_unique IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
        ).consume()


def seed_graph(session, graph: dict) -> None:
    for section, (label, key) in NODES.items():
        for node in graph.get(section, []):
            props = {k: v for k, v in node.items() if k != key}
            session.run(
                f"MERGE (n:{label} {{{key}: $key}}) SET n += $props",
                key=node[key],
                props=props,
            ).consume()
    for rel in graph.get("relationships", []):
        src, dst = RELS[rel["type"]]
        session.run(
            f"MATCH (a:{src} {{{KEY_OF[src]}: $src}}), (b:{dst} {{{KEY_OF[dst]}: $dst}}) "
            f"MERGE (a)-[r:{rel['type']}]->(b) SET r += $props",
            src=rel["from"],
            dst=rel["to"],
            props=rel["props"],
        ).consume()


def buyer_intent(session) -> list[dict]:
    return session.run(BUYER_INTENT_QUERY, min_probability=MIN_PASSAGE_PROBABILITY, positions=INTENT_POSITIONS).data()


def print_buyer_intent(rows: list[dict], out=None) -> None:
    out = sys.stdout if out is None else out
    if not rows:
        print("No data yet", file=out)
        return
    cols = ["corporation", "firm", "bill", "passage_probability", "position", "spend", "filing_id"]
    cells = [[str(row[c]) for c in cols] for row in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(cols)]
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)).rstrip(), file=out)
    for row in cells:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)).rstrip(), file=out)


def run(driver, graph: dict | None = None, out=None) -> list[dict]:
    if not graph or not any(graph.get(section) for section in (*NODES, "relationships")):
        print("No data yet", file=sys.stdout if out is None else out)
        return []
    with driver.session() as session:
        create_constraints(session)
        seed_graph(session, graph)
        rows = buyer_intent(session)
    print_buyer_intent(rows, out)
    return rows


def neo4j_settings() -> tuple[str, str, str]:
    auth_user, _, auth_password = os.environ.get("NEO4J_AUTH", "").partition("/")
    uri = os.environ.get("NEO4J_URI", f"bolt://localhost:{os.environ.get('FACTORY_NEO4J_BOLT_PORT', '7687')}")
    user = os.environ.get("NEO4J_USER") or auth_user or "neo4j"
    password = os.environ.get("NEO4J_PASSWORD") or auth_password
    if not password:
        raise SystemExit("set NEO4J_PASSWORD or NEO4J_AUTH in the environment")
    return uri, user, password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path)
    args = parser.parse_args(argv)
    if args.graph is None or not args.graph.is_file():
        print("No data yet")
        return 0
    graph = load_graph(args.graph)
    if not graph or not any(graph.get(section) for section in (*NODES, "relationships")):
        print("No data yet")
        return 0
    from neo4j import GraphDatabase

    uri, user, password = neo4j_settings()
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        run(driver, graph)
    return 0


if __name__ == "__main__":
    sys.exit(main())
