from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict, List, Optional
from uuid import UUID

from neo4j import AsyncGraphDatabase, AsyncSession, GraphDatabase

from .config import settings

_driver = None
_driver_lock = threading.Lock()


def driver():
    """Legacy driver function for backward compatibility."""
    global _driver
    if _driver is None:
        with _driver_lock:
            if _driver is None:
                _driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                    max_connection_lifetime=settings.neo4j_max_lifetime,
                    max_connection_pool_size=settings.neo4j_pool_size,
                    connection_acquisition_timeout=settings.neo4j_pool_timeout,
                )
    return _driver


def close_driver() -> None:
    """Close the legacy global driver."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


class Neo4jClient:
    """Neo4j client with multi-database support for tenant isolation."""

    # Database naming convention
    DB_GLOBAL = "neo4j"  # Default global database for regulatory data
    DB_TENANT_PREFIX = "reg_tenant_"

    def __init__(self, database: Optional[str] = None):
        """Initialize Neo4j client.

        Args:
            database: Database name. If None, uses default 'neo4j' database.
        """
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_lifetime=settings.neo4j_max_lifetime,
            max_connection_pool_size=settings.neo4j_pool_size,
            connection_acquisition_timeout=settings.neo4j_pool_timeout,
        )
        # Force usage of default database for Community Edition support
        # In Enterprise, we would use 'database' argument
        self.database = self.DB_GLOBAL

    @staticmethod
    def get_tenant_database_name(tenant_id: UUID) -> str:
        """Generate tenant-specific database name.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Database name in format: reg_tenant_<uuid>
        """
        return f"{Neo4jClient.DB_TENANT_PREFIX}{tenant_id}"

    @staticmethod
    def get_global_database_name() -> str:
        """Get global regulatory database name."""
        return Neo4jClient.DB_GLOBAL

    def session(self, **kwargs) -> Any:
        """Create a new async session for this database.

        Returns:
            Neo4j async session configured for this client's database
        """
        return self._driver.session(database=self.database, **kwargs)

    async def close(self) -> None:
        """Close the driver connection."""
        if self._driver:
            await self._driver.close()

    async def upsert_provision(
        self,
        *,
        document_id: str,
        doc_hash: str,
        provision: Dict[str, Any],
        embedding: Optional[List[float]] = None,
    ) -> None:
        """Upsert a provision node and link it to its document."""

        def _encode(value: Any) -> Any:
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return value

        extraction_payload = _encode(provision.get("extraction"))
        provenance_payload = _encode(provision.get("provenance"))

        async with self.session() as session:
            await session.run(
                CYPHER_UPSERT_PROVISION,
                document_id=document_id,
                doc_hash=doc_hash,
                provision_hash=provision.get("content_hash"),
                text_clean=provision.get("text_clean"),
                extraction=extraction_payload,
                provenance=provenance_payload,
                status=provision.get("status"),
                reviewer_id=provision.get("reviewer_id"),
                tenant_id=provision.get("tenant_id"),
                embedding=embedding,
                jurisdiction_codes=(provision.get("extraction", {}) or {}).get(
                    "jurisdiction_codes", []
                ),
            )

    async def create_tenant_database(self, tenant_id: UUID) -> None:
        """Create a new tenant database (requires admin privileges).

        Args:
            tenant_id: Tenant UUID

        Note:
            This requires the user to have CREATE DATABASE privileges in Neo4j.
            In Neo4j Community Edition, this may not be supported.
        """
        db_name = self.get_tenant_database_name(tenant_id)
        # Sanitize database name to prevent Cypher injection
        import re
        if not re.match(r'^[a-zA-Z0-9_\-]+$', db_name):
            raise ValueError(f"Invalid database name: {db_name}")
        # Connect to system database to create new database
        async with self._driver.session(database="system") as session:
            # Check if database already exists
            result = await session.run("SHOW DATABASES WHERE name = $name", name=db_name)
            if not await result.single():
                await session.run(f"CREATE DATABASE `{db_name}` IF NOT EXISTS")

    async def __aenter__(self):
        """Async context manager support."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager cleanup."""
        await self.close()


CYPHER_UPSERT = """
MERGE (d:Document {id: $doc_id})
  ON CREATE SET d.source_url = $source_url, d.created_at = timestamp()
  ON MATCH SET  d.source_url = coalesce($source_url, d.source_url)
WITH d
UNWIND $jurisdictions AS jname
  MERGE (j:Jurisdiction {name: jname})
  MERGE (d)-[:MENTIONS]->(j)
WITH d, collect(j) AS jurisdiction_nodes
UNWIND $obligations AS ob
  MERGE (c:Concept {name: coalesce(ob.concept, 'unspecified')})
    MERGE (p:Provision {pid: ob.pid})
    ON CREATE SET p.text = ob.text, p.tx_from = timestamp(), p.valid_from = timestamp(), p.hash = ob.hash, p.tenant_id = $tenant_id
    ON MATCH  SET p.text = ob.text, p.hash = ob.hash, p.tenant_id = $tenant_id
  MERGE (p)-[:IN_DOCUMENT]->(d)
  MERGE (p)-[:ABOUT]->(c)
  FOREACH (jn IN jurisdiction_nodes |
    MERGE (p)-[:APPLIES_TO]->(jn)
  )
  FOREACH (_ IN CASE WHEN ob.threshold_is_set THEN [1] ELSE [] END |
    MERGE (t:Threshold {pid: ob.pid})
      ON CREATE SET t.value = ob.threshold_value, t.unit = ob.threshold_unit, t.unit_normalized = ob.threshold_unit_normalized
      ON MATCH  SET t.value = ob.threshold_value, t.unit = ob.threshold_unit, t.unit_normalized = ob.threshold_unit_normalized
    MERGE (p)-[:HAS_THRESHOLD]->(t)
  )
  WITH p, ob
  MERGE (prov:Provenance {doc_id: $doc_id, start: ob.start, end: ob.end})
    ON CREATE SET prov.page = ob.page
    ON MATCH SET prov.page = coalesce(ob.page, prov.page)
  MERGE (p)-[:PROVENANCE]->(prov)
"""


CYPHER_UPSERT_PROVISION = """
MERGE (d:Document {hash: $doc_hash})
  ON CREATE SET d.id = $document_id, d.created_at = timestamp()
  ON MATCH SET d.id = coalesce(d.id, $document_id)
MERGE (p:Provision {hash: $provision_hash})
  ON CREATE SET
    p.text_clean = $text_clean,
    p.status = $status,
    p.reviewer_id = $reviewer_id,
        p.provenance = $provenance,
    p.extraction = $extraction,
    p.embedding = $embedding,
    p.doc_hash = $doc_hash,
    p.tenant_id = $tenant_id,
    p.created_at = timestamp()
  ON MATCH SET
    p.text_clean = $text_clean,
    p.status = $status,
    p.reviewer_id = $reviewer_id,
        p.provenance = $provenance,
    p.extraction = $extraction,
    p.embedding = $embedding,
    p.doc_hash = $doc_hash,
    p.tenant_id = $tenant_id
MERGE (p)-[:IN_DOCUMENT]->(d)
WITH p
UNWIND coalesce($jurisdiction_codes, []) AS jcode
    MERGE (j:Jurisdiction {code: jcode})
    MERGE (p)-[:APPLIES_TO]->(j)
"""


def upsert_from_entities(
    session, doc_id: str, source_url: str | None, entities: List[dict], tenant_id: str | None = None
):
    jurisdictions = sorted(
        {
            e.get("attrs", {}).get("name")
            for e in entities
            if e.get("type") == "JURISDICTION"
            and e.get("attrs")
            and e["attrs"].get("name")
        }
    ) or ["Unknown"]

    obligations = []
    obligation_entities = [e for e in entities if e.get("type") == "OBLIGATION"]
    thresholds = [e for e in entities if e.get("type") == "THRESHOLD"]

    for entity in obligation_entities:
        pid = f"{doc_id}:{entity['start']}:{entity['end']}"
        contained_thresholds = [
            t
            for t in thresholds
            if entity["start"] <= t.get("start", 0) <= entity["end"]
            and t.get("end", 0) <= entity["end"]
        ]
        threshold = contained_thresholds[0] if contained_thresholds else None
        threshold_attrs = threshold.get("attrs", {}) if threshold else {}
        obligations.append(
            {
                "pid": pid,
                "text": entity.get("text", ""),
                "hash": hashlib.sha256(entity.get("text", "").encode()).hexdigest()[
                    :16
                ],
                "start": entity.get("start"),
                "end": entity.get("end"),
                "concept": entity.get("attrs", {}).get("concept"),
                "page": entity.get("attrs", {}).get("page"),
                "threshold_is_set": bool(threshold),
                "threshold_value": threshold_attrs.get("value"),
                "threshold_unit": threshold_attrs.get("unit"),
                "threshold_unit_normalized": threshold_attrs.get("unit_normalized"),
            }
        )

    session.run(
        CYPHER_UPSERT,
        doc_id=doc_id,
        source_url=source_url,
        jurisdictions=jurisdictions,
        obligations=obligations,
        tenant_id=tenant_id
    )
