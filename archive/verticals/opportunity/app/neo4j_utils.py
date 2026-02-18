from __future__ import annotations

import threading
from typing import Optional

from neo4j import GraphDatabase

from .config import settings

_driver = None
_driver_lock = threading.Lock()


def get_driver():
    global _driver
    if _driver is None:
        with _driver_lock:
            if _driver is None:
                _driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                    max_connection_lifetime=3600,
                    max_connection_pool_size=50,
                    connection_acquisition_timeout=60,
                )
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


CYPHER_ARBITRAGE_BASE = """
MATCH (c:Concept)<-[:ABOUT]-(p1:Provision)-[:HAS_THRESHOLD]->(t1:Threshold),
      (p2:Provision)-[:ABOUT]->(c),
      (p2)-[:HAS_THRESHOLD]->(t2:Threshold),
      (p1)-[:PROVENANCE]->(prov1:Provenance),
      (p2)-[:PROVENANCE]->(prov2:Provenance),
      (p1)-[:IN_DOCUMENT]->(d1:Document),
      (p2)-[:IN_DOCUMENT]->(d2:Document)
WHERE t1.unit_normalized = t2.unit_normalized
  AND t1.unit_normalized IS NOT NULL
  AND abs(t1.value - t2.value) / CASE WHEN t1.value = 0 THEN 1 ELSE t1.value END >= $rel_delta
{jurisdiction_filter}
{concept_filter}
{since_filter}
RETURN c.name AS concept,
       p1.text AS text1, t1.value AS v1, t1.unit_normalized AS unit,
       p2.text AS text2, t2.value AS v2,
       prov1.doc_id AS doc_id_1,
       prov1.start AS start_1,
       prov1.end AS end_1,
       prov2.doc_id AS doc_id_2,
       prov2.start AS start_2,
       prov2.end AS end_2,
       d1.source_url AS source_url_1,
       d2.source_url AS source_url_2
ORDER BY abs(t1.value - t2.value) DESC
LIMIT $limit
"""

CYPHER_GAP = """
MATCH (j1:Jurisdiction {name: $j1})<-[:APPLIES_TO]-(p1:Provision)-[:ABOUT]->(c:Concept)
WHERE NOT EXISTS {
  MATCH (j2:Jurisdiction {name: $j2})<-[:APPLIES_TO]-(p2:Provision)-[:ABOUT]->(c)
}
MATCH (p1)-[:PROVENANCE]->(prov:Provenance)
MATCH (p1)-[:IN_DOCUMENT]->(d:Document)
RETURN c.name AS concept,
       p1.text AS example_text,
       prov.doc_id AS doc_id,
       prov.start AS start,
       prov.end AS end,
       d.source_url AS source_url
LIMIT $limit
"""


def build_arbitrage_query(
    jurisdiction_1: Optional[str],
    jurisdiction_2: Optional[str],
    concept: Optional[str],
    include_since: bool,
) -> str:
    jurisdiction_filter = ""
    if jurisdiction_1 and jurisdiction_2:
        jurisdiction_filter = (
            "  AND EXISTS { MATCH (p1)-[:APPLIES_TO]->(:Jurisdiction {name: $j1}) }\n"
            "  AND EXISTS { MATCH (p2)-[:APPLIES_TO]->(:Jurisdiction {name: $j2}) }\n"
        )
    concept_filter = ""
    if concept:
        concept_filter = "  AND toLower(c.name) = toLower($concept)\n"
    since_filter = ""
    if include_since:
        since_filter = "  AND d1.created_at >= $since\n  AND d2.created_at >= $since\n"
    return CYPHER_ARBITRAGE_BASE.format(
        jurisdiction_filter=jurisdiction_filter,
        concept_filter=concept_filter,
        since_filter=since_filter,
    )
