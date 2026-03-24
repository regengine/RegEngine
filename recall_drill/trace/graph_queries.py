"""Neo4j graph traversal for FSMA 204 traceability recall drills."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from neo4j import AsyncGraphDatabase


@dataclass
class TraceResult:
    target_tlc: str
    lots_found: list[str]
    facilities: list[dict]
    upstream_depth: int
    downstream_depth: int
    gaps: list[str]
    orphans: list[str]
    edges: list[dict]

    @property
    def complete(self) -> bool:
        return len(self.gaps) == 0 and len(self.orphans) == 0

    def to_dict(self) -> dict:
        return {
            "target_tlc": self.target_tlc,
            "lots_found": len(self.lots_found),
            "facilities_identified": len(self.facilities),
            "upstream_depth": self.upstream_depth,
            "downstream_depth": self.downstream_depth,
            "gaps": self.gaps,
            "orphans": self.orphans,
            "trace_complete": self.complete,
        }


class TraceEngine:
    """Execute recall trace queries against Neo4j."""

    FIND_RELATED_LOTS = """
    MATCH (lot:Lot {tlc: $tlc})-[:SHIPPED_TO|RECEIVED_FROM|TRANSFORMED_INTO*1..10]-(related:Lot)
    RETURN DISTINCT related.tlc AS tlc, related.product AS product,
           related.event_date AS event_date
    ORDER BY related.event_date
    """

    TRAVERSE_UPSTREAM = """
    MATCH path = (target:Lot {tlc: $tlc})<-[:SHIPPED_TO|TRANSFORMED_INTO*1..20]-(upstream:Lot)
    RETURN upstream.tlc AS tlc, upstream.origin_gln AS facility_gln,
           upstream.origin_name AS facility_name, length(path) AS depth
    ORDER BY depth
    """

    TRAVERSE_DOWNSTREAM = """
    MATCH path = (target:Lot {tlc: $tlc})-[:SHIPPED_TO|TRANSFORMED_INTO*1..20]->(downstream:Lot)
    RETURN downstream.tlc AS tlc, downstream.destination_gln AS facility_gln,
           downstream.destination_name AS facility_name, length(path) AS depth
    ORDER BY depth
    """

    FIND_ORPHANS = """
    MATCH (lot:Lot)
    WHERE lot.tenant_id = $tenant_id
      AND NOT (lot)<-[:SHIPPED_TO|TRANSFORMED_INTO]-()
      AND lot.event_type <> 'harvesting'
    RETURN lot.tlc AS tlc, lot.product AS product
    """

    FIND_GAPS = """
    MATCH (a:Lot)-[:SHIPPED_TO]->(b:Lot)
    WHERE a.tenant_id = $tenant_id
      AND (b.immediate_previous_source IS NULL OR b.immediate_previous_source = '')
    RETURN a.tlc AS from_tlc, b.tlc AS to_tlc
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str = "neo4j",
    ):
        self._uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.getenv("NEO4J_USER", "neo4j")
        self._password = password or os.getenv("NEO4J_PASSWORD", "")
        self._database = database
        self._driver = AsyncGraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )

    async def close(self) -> None:
        await self._driver.close()

    async def _run(self, query: str, **params: Any) -> list[dict]:
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, **params)
            return [dict(record) async for record in result]

    async def find_all_related_lots(
        self, tlc: str, tenant_id: str | None = None
    ) -> list[dict]:
        return await self._run(self.FIND_RELATED_LOTS, tlc=tlc)

    async def traverse_upstream(self, tlc: str) -> list[dict]:
        return await self._run(self.TRAVERSE_UPSTREAM, tlc=tlc)

    async def traverse_downstream(self, tlc: str) -> list[dict]:
        return await self._run(self.TRAVERSE_DOWNSTREAM, tlc=tlc)

    async def full_trace(self, tlc: str, tenant_id: str) -> TraceResult:
        """Execute a complete forward + backward trace for a TLC."""
        upstream = await self.traverse_upstream(tlc)
        downstream = await self.traverse_downstream(tlc)
        orphans_raw = await self._run(self.FIND_ORPHANS, tenant_id=tenant_id)
        gaps_raw = await self._run(self.FIND_GAPS, tenant_id=tenant_id)

        all_lots = {tlc}
        facilities: dict[str, dict] = {}

        for rec in upstream:
            all_lots.add(rec["tlc"])
            if rec.get("facility_gln"):
                facilities[rec["facility_gln"]] = {
                    "gln": rec["facility_gln"],
                    "name": rec.get("facility_name", ""),
                    "direction": "upstream",
                }

        for rec in downstream:
            all_lots.add(rec["tlc"])
            if rec.get("facility_gln"):
                facilities[rec["facility_gln"]] = {
                    "gln": rec["facility_gln"],
                    "name": rec.get("facility_name", ""),
                    "direction": "downstream",
                }

        max_up = max((r["depth"] for r in upstream), default=0)
        max_down = max((r["depth"] for r in downstream), default=0)

        return TraceResult(
            target_tlc=tlc,
            lots_found=sorted(all_lots),
            facilities=list(facilities.values()),
            upstream_depth=max_up,
            downstream_depth=max_down,
            gaps=[f"{g['from_tlc']} -> {g['to_tlc']}" for g in gaps_raw],
            orphans=[o["tlc"] for o in orphans_raw],
            edges=[
                *[{"from": tlc, "to": r["tlc"], "dir": "upstream"} for r in upstream],
                *[{"from": tlc, "to": r["tlc"], "dir": "downstream"} for r in downstream],
            ],
        )
