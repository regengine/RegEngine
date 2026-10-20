"""Seed Neo4j with the bill / section / version graph.

Only the statute structure and one explicitly fictional organisation are
written. No real company names or relationships go into this graph.
"""

from __future__ import annotations

from neo4j import Driver

BILL = {
    "bill_id": "CO_SB24_205",
    "title": "Consumer Protections for Artificial Intelligence (SB24-205)",
    "jurisdiction": "US-CO",
    "source_uri": "https://leg.colorado.gov/bills/sb24-205",
}
SECTIONS = [
    {"citation": "C.R.S. § 6-1-1702", "heading": "Developer duties"},
    {"citation": "C.R.S. § 6-1-1703", "heading": "Deployer duties"},
    {"citation": "C.R.S. § 6-1-1706", "heading": "Enforcement"},
]
VERSIONS = [
    {"version_uid": "CO_SB24_205@V2", "label": "V2 (demo fixture)"},
]
EXAMPLE_ORG = "Example Corp (fictional)"


def seed_graph(driver: Driver, rule_uid: str, version_uid: str) -> None:
    with driver.session() as s:
        s.run(
            "MERGE (b:Bill {bill_id: $bill_id}) SET b.title = $title, b.jurisdiction = $jurisdiction, "
            "b.source_uri = $source_uri",
            **BILL,
        )
        for sec in SECTIONS:
            s.run(
                "MATCH (b:Bill {bill_id: $bill_id}) "
                "MERGE (s:Section {citation: $citation}) SET s.heading = $heading "
                "MERGE (b)-[:HAS_SECTION]->(s)",
                bill_id=BILL["bill_id"], **sec,
            )
        for ver in VERSIONS:
            s.run(
                "MATCH (b:Bill {bill_id: $bill_id}) "
                "MERGE (v:BillVersion {version_uid: $version_uid}) SET v.label = $label "
                "MERGE (b)-[:HAS_VERSION]->(v)",
                bill_id=BILL["bill_id"], **ver,
            )
        s.run(
            "MATCH (v:BillVersion {version_uid: $version_uid}), (s:Section {citation: 'C.R.S. § 6-1-1703'}) "
            "MERGE (r:Rule {rule_uid: $rule_uid}) "
            "MERGE (v)-[:DEFINES]->(r) MERGE (r)-[:CITES]->(s)",
            version_uid=version_uid, rule_uid=rule_uid,
        )
        s.run(
            "MERGE (o:ExampleOrg {name: $name}) SET o.fictional = true "
            "WITH o MATCH (r:Rule {rule_uid: $rule_uid}) MERGE (o)-[:EVALUATED_AGAINST]->(r)",
            name=EXAMPLE_ORG, rule_uid=rule_uid,
        )
