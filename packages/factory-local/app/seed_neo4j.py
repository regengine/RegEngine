"""Seed Neo4j with a SAMPLE lobbying graph and print a buyer intent table.

  python app/seed_neo4j.py

*** SAMPLE DATA ***
Bill numbers, sponsors and company names are real, but every filing_id, spend,
position, passage_probability, les_score, opportunity_score and lobbying firm in
fixtures/sample_lobbying_graph.json is INVENTED. Every node and relationship this
script writes carries sample = true so it can be found and removed:
  MATCH (n {sample: true}) DETACH DELETE n

Connection: NEO4J_URI (default bolt://localhost:$FACTORY_NEO4J_BOLT_PORT, port 7687),
NEO4J_USER and NEO4J_PASSWORD, falling back to NEO4J_AUTH=user/password as set in
.env.example for docker-compose.yml. Values are read from .env when present.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent.parent
FIXTURE_PATH = PACKAGE_DIR / "fixtures" / "sample_lobbying_graph.json"
BANNER = "*** SAMPLE DATA: filing IDs, spend, positions, probabilities and scores are INVENTED ***"

# Labels and relationship types are fixed here, never taken from the fixture:
# Cypher cannot parameterize them, so only these strings reach the query text.
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


def load_sample_graph(path: Path = FIXTURE_PATH) -> dict:
    return json.loads(path.read_text())


def create_constraints(session) -> None:
    for label, key in NODES.values():
        session.run(
            f"CREATE CONSTRAINT {label.lower()}_{key}_unique IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
        ).consume()


def seed_sample_graph(session, graph: dict) -> None:
    for section, (label, key) in NODES.items():
        for node in graph[section]:
            props = {k: v for k, v in node.items() if k != key}
            session.run(
                f"MERGE (n:{label} {{{key}: $key}}) SET n += $props, n.sample = $sample",
                key=node[key], props=props, sample=True,
            ).consume()
    for rel in graph["relationships"]:
        src, dst = RELS[rel["type"]]
        session.run(
            f"MATCH (a:{src} {{{KEY_OF[src]}: $src}}), (b:{dst} {{{KEY_OF[dst]}: $dst}}) "
            f"MERGE (a)-[r:{rel['type']}]->(b) SET r += $props, r.sample = $sample",
            src=rel["from"], dst=rel["to"], props=rel["props"], sample=True,
        ).consume()


def buyer_intent(session) -> list[dict]:
    return session.run(
        BUYER_INTENT_QUERY, min_probability=MIN_PASSAGE_PROBABILITY, positions=INTENT_POSITIONS
    ).data()


def print_buyer_intent(rows: list[dict], out=None) -> None:
    out = out or sys.stdout
    cols = ["corporation", "firm", "bill", "passage_probability", "position", "spend", "filing_id"]
    cells = [[str(row[c]) for c in cols] for row in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(cols)]
    print(BANNER, file=out)
    print("Buyer intent (SAMPLE): passage_probability >= 0.4, position OPPOSE / AMEND / MONITOR", file=out)
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)).rstrip(), file=out)
    for r in cells:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip(), file=out)
    print(f"{len(rows)} rows. {BANNER}", file=out)


def run(driver, graph: dict | None = None, out=None) -> list[dict]:
    graph = graph or load_sample_graph()
    with driver.session() as session:
        create_constraints(session)
        seed_sample_graph(session, graph)
        rows = buyer_intent(session)
    print_buyer_intent(rows, out)
    return rows


def neo4j_settings() -> tuple[str, str, str]:
    auth_user, _, auth_password = os.environ.get("NEO4J_AUTH", "").partition("/")
    uri = os.environ.get("NEO4J_URI", f"bolt://localhost:{os.environ.get('FACTORY_NEO4J_BOLT_PORT', '7687')}")
    user = os.environ.get("NEO4J_USER") or auth_user or "neo4j"
    password = os.environ.get("NEO4J_PASSWORD") or auth_password
    if not password:
        raise SystemExit("set NEO4J_PASSWORD or NEO4J_AUTH=neo4j/<password> in .env (see .env.example)")
    return uri, user, password


def main() -> None:
    from dotenv import load_dotenv
    from neo4j import GraphDatabase

    load_dotenv(PACKAGE_DIR / ".env")
    uri, user, password = neo4j_settings()
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        run(driver)


if __name__ == "__main__":
    main()
