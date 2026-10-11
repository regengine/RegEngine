from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import structlog
from neo4j import AsyncGraphDatabase

logger = structlog.get_logger("traceability-linker")


def _require_tenant_id(tenant_id: str) -> str:
    """Fail closed when the tenant is missing.

    Running any Obligation MATCH without a tenant predicate would let one
    tenant link or read another tenant's private obligation, so reject
    empty values instead of degrading to an unscoped query.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required and must be non-empty to prevent cross-tenant access")
    return tenant_id


# Obligation rows are quarantined by Decision 3 (Oct 8, 2026): an
# Obligation is shared across tenants only when a catalog writer
# explicitly marks it (``catalog = true``; see
# services/ingestion/app/regulation_loader.py and the catalog note in
# services/admin/app/supplier_graph_sync.py). A null tenant_id alone
# shares nothing: unmarked null-tenant rows match no tenant, and
# tenant-stamped rows are confined to their tenant. A backfill script
# (scripts/backfill_obligation_catalog.py) must mark pre-existing catalog
# rows before this predicate deploys, or regulation lookups go empty.
_OBLIGATION_TENANT_PREDICATE = "(o.tenant_id = $tenant_id OR o.catalog = true)"


class TraceabilityLinker:
    """Engine for linking regulatory obligations to supply chain events and lots."""

    def __init__(
        self, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = os.getenv("NEO4J_PASSWORD", "")
    ):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self):
        """Close the Neo4j driver."""
        await self.driver.close()

    async def link_obligation_to_traceability(self, obligation_id: str, tenant_id: str) -> List[Dict[str, Any]]:
        """Identify which TraceEvents or Lots are governed by a specific obligation.

        Uses keyword matching and category overlapping to establish links.
        """
        _require_tenant_id(tenant_id)
        async with self.driver.session() as session:
            # 1. Fetch obligation text and metadata. Scoped so a tenant can
            # use marked catalog rows but not another tenant's private
            # obligation or an unmarked null-tenant row.
            obs_res = await session.run(
                f"""
                MATCH (o:Obligation {{id: $id}})
                WHERE {_OBLIGATION_TENANT_PREDICATE}
                RETURN o.text as text, o.category as category
            """,
                id=obligation_id,
                tenant_id=tenant_id,
            )
            obs = await obs_res.single()
            if not obs:
                return []

            text = obs["text"].lower()

            # 2. Heuristic mapping.
            # If obligation mentions 'temperature', 'cooling', 'receiving', etc.,
            # link to corresponding CTEs. The GOVERNS MERGE below re-checks
            # the quarantine predicate so the edge only lands on an
            # own-tenant or marked-catalog obligation.

            keywords = []
            if "shipping" in text:
                keywords.append("SHIPPING")
            if "receiving" in text:
                keywords.append("RECEIVING")
            if "transformation" in text or "processing" in text:
                keywords.append("TRANSFORMATION")
            if "cooling" in text:
                keywords.append("COOLING")
            if "creation" in text:
                keywords.append("CREATION")

            links = []
            if keywords:
                # Link to TraceEvents of specified type
                link_res = await session.run(
                    f"""
                    MATCH (e:TraceEvent)
                    WHERE e.tenant_id = $tenant_id AND e.type IN $keywords
                    MATCH (o:Obligation {{id: $obs_id}})
                    WHERE {_OBLIGATION_TENANT_PREDICATE}
                    MERGE (o)-[r:GOVERNS]->(e)
                    SET r.linked_at = datetime(), r.link_type = 'keyword_match'
                    RETURN e.event_id as event_id, e.type as type
                """,
                    tenant_id=tenant_id,
                    keywords=keywords,
                    obs_id=obligation_id,
                )
                links.extend([dict(record) async for record in link_res])

            return links

    async def get_governing_regulations(self, lot_tlc: str, tenant_id: str) -> List[Dict[str, Any]]:
        """Find all regulations (via obligations) governing a specific lot."""
        _require_tenant_id(tenant_id)
        async with self.driver.session() as session:
            query = f"""
                MATCH (l:Lot {{tlc: $tlc, tenant_id: $tenant_id}})-[:UNDERWENT]->(e:TraceEvent {{tenant_id: $tenant_id}})
                MATCH (o:Obligation)-[:GOVERNS]->(e)
                WHERE {_OBLIGATION_TENANT_PREDICATE}
                MATCH (o)<-[:REQUIRES]-(s:Section)
                RETURN DISTINCT s.regulation as regulation, o.text as requirement, o.id as requirement_id
            """
            result = await session.run(query, tlc=lot_tlc, tenant_id=tenant_id)
            return [dict(record) async for record in result]

    async def get_impacted_lots(self, obligation_id: str, tenant_id: str) -> List[Dict[str, Any]]:
        """Find all lots impacted by a specific regulatory obligation."""
        _require_tenant_id(tenant_id)
        async with self.driver.session() as session:
            query = f"""
                MATCH (o:Obligation {{id: $id}})-[:GOVERNS]->(e:TraceEvent {{tenant_id: $tenant_id}})
                WHERE {_OBLIGATION_TENANT_PREDICATE}
                MATCH (l:Lot)-[:UNDERWENT]->(e)
                WHERE l.tenant_id = $tenant_id
                AND e.tenant_id = $tenant_id
                RETURN DISTINCT l.tlc as tlc, l.product_description as description
            """
            result = await session.run(query, id=obligation_id, tenant_id=tenant_id)
            return [dict(record) async for record in result]
