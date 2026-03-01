#!/usr/bin/env python3
"""Redis-backed Postgres/ingestion to Neo4j sync worker.

Consumes queue events from `neo4j-sync` and upserts FSMA graph nodes for
products, locations, and CTE records.
"""

from __future__ import annotations

import json
import os
import signal
import sys
from typing import Any

from neo4j import GraphDatabase

try:
    import redis
except ImportError as exc:  # pragma: no cover - runtime dependency check
    raise RuntimeError("redis package is required for fsma_sync_worker") from exc


QUEUE_KEY = os.getenv("NEO4J_SYNC_QUEUE", "neo4j-sync")
BLOCK_TIMEOUT_SEC = int(os.getenv("NEO4J_SYNC_BLOCK_TIMEOUT_SEC", "5"))


class FSMASyncWorker:
    def __init__(self) -> None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "neo4j")

        self.redis = redis.from_url(redis_url)
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.running = True

    def stop(self, *_args: Any) -> None:
        self.running = False

    def run(self) -> None:
        print(f"FSMA sync worker started. Queue={QUEUE_KEY}")
        while self.running:
            message = self.redis.blpop(QUEUE_KEY, timeout=BLOCK_TIMEOUT_SEC)
            if message is None:
                continue

            _, payload = message
            try:
                decoded = json.loads(payload.decode("utf-8"))
                self._dispatch(decoded)
            except Exception as exc:
                print(f"sync_worker_error: {exc}")

        self.driver.close()
        print("FSMA sync worker stopped")

    def _dispatch(self, payload: dict[str, Any]) -> None:
        event = payload.get("event")
        data = payload.get("data", {})

        if event == "cte.created":
            self._sync_cte(data.get("cte", {}))
        elif event == "product.created":
            self._sync_product(data.get("product", {}))
        elif event == "location.created":
            self._sync_location(data.get("location", {}))
        else:
            print(f"sync_worker_skipped_unknown_event: {event}")

    def _sync_cte(self, cte: dict[str, Any]) -> None:
        cte_id = cte.get("id")
        if not cte_id:
            return

        properties = {
            "event_type": cte.get("event_type"),
            "event_time": cte.get("event_time"),
            "epcis_event_type": cte.get("epcis_event_type"),
            "epcis_action": cte.get("epcis_action"),
            "validation_status": cte.get("validation_status"),
            "tlc": cte.get("tlc"),
            "lot_code": cte.get("lot_code"),
            "data_source": cte.get("data_source"),
        }

        with self.driver.session() as session:
            session.run(
                """
                MERGE (cte:CTE {id: $id})
                SET cte += $properties
                """,
                id=cte_id,
                properties=properties,
            )

            tlc = cte.get("tlc")
            if tlc:
                session.run(
                    """
                    MERGE (lot:Lot {tlc: $tlc})
                    SET lot.lot_code = coalesce($lot_code, lot.lot_code)
                    WITH lot
                    MATCH (cte:CTE {id: $cte_id})
                    MERGE (cte)-[:INVOLVES_LOT]->(lot)
                    """,
                    tlc=tlc,
                    lot_code=cte.get("lot_code"),
                    cte_id=cte_id,
                )

            product_id = cte.get("product_id")
            if product_id:
                session.run(
                    """
                    MERGE (product:Product {id: $product_id})
                    WITH product
                    MATCH (cte:CTE {id: $cte_id})
                    MERGE (cte)-[:INVOLVES_PRODUCT]->(product)
                    """,
                    product_id=product_id,
                    cte_id=cte_id,
                )

                if tlc:
                    session.run(
                        """
                        MATCH (product:Product {id: $product_id})
                        MATCH (lot:Lot {tlc: $tlc})
                        MERGE (product)-[:HAS_LOT]->(lot)
                        """,
                        product_id=product_id,
                        tlc=tlc,
                    )

            location_id = cte.get("location_id")
            if location_id:
                session.run(
                    """
                    MERGE (loc:Location {id: $location_id})
                    WITH loc
                    MATCH (cte:CTE {id: $cte_id})
                    MERGE (cte)-[:OCCURRED_AT]->(loc)
                    """,
                    location_id=location_id,
                    cte_id=cte_id,
                )

            source_location_id = cte.get("source_location_id")
            if source_location_id:
                session.run(
                    """
                    MERGE (src:Location {id: $source_location_id})
                    WITH src
                    MATCH (cte:CTE {id: $cte_id})
                    MERGE (cte)-[:SHIPPED_FROM]->(src)
                    """,
                    source_location_id=source_location_id,
                    cte_id=cte_id,
                )

            dest_location_id = cte.get("dest_location_id")
            if dest_location_id:
                session.run(
                    """
                    MERGE (dst:Location {id: $dest_location_id})
                    WITH dst
                    MATCH (cte:CTE {id: $cte_id})
                    MERGE (cte)-[:SHIPPED_TO]->(dst)
                    """,
                    dest_location_id=dest_location_id,
                    cte_id=cte_id,
                )

    def _sync_product(self, product: dict[str, Any]) -> None:
        product_id = product.get("id")
        if not product_id:
            return

        with self.driver.session() as session:
            session.run(
                """
                MERGE (product:Product {id: $id})
                SET product += $properties
                """,
                id=product_id,
                properties={
                    "name": product.get("name"),
                    "gtin": product.get("gtin"),
                    "sku": product.get("sku"),
                    "ftl_category": product.get("ftl_category"),
                    "ftl_covered": product.get("ftl_covered"),
                },
            )

    def _sync_location(self, location: dict[str, Any]) -> None:
        location_id = location.get("id")
        if not location_id:
            return

        with self.driver.session() as session:
            session.run(
                """
                MERGE (loc:Location {id: $id})
                SET loc += $properties
                """,
                id=location_id,
                properties={
                    "name": location.get("name"),
                    "gln": location.get("gln"),
                    "location_type": location.get("location_type"),
                    "fda_fei": location.get("fda_fei"),
                },
            )


def main() -> int:
    worker = FSMASyncWorker()
    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)

    worker.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
