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
from pathlib import Path
from typing import Any

# --- Ensure shared module is importable ---
_SERVICES_DIR = Path(__file__).resolve().parents[2]
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.observability.context import get_logger

logger = get_logger("fsma-sync-worker")

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
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        if not neo4j_password:
            raise ValueError(
                "NEO4J_PASSWORD must be set. "
                "Refusing to start with missing credentials."
            )

        self.redis = redis.from_url(redis_url)
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.running = True

    def stop(self, *_args: Any) -> None:
        self.running = False

    def run(self) -> None:
        logger.info("sync_worker_started", queue=QUEUE_KEY, tenant_id="system", request_id="worker-init")
        while self.running:
            message = self.redis.blpop(QUEUE_KEY, timeout=BLOCK_TIMEOUT_SEC)
            if message is None:
                continue

            _, payload = message
            try:
                decoded = json.loads(payload.decode("utf-8"))
                self._dispatch(decoded)
            except Exception as exc:
                logger.error("sync_worker_error", error=str(exc), tenant_id="system", request_id="worker-loop")

        self.driver.close()
        logger.info("sync_worker_stopped", tenant_id="system", request_id="worker-shutdown")

    def _dispatch(self, payload: dict[str, Any]) -> None:
        event = payload.get("event")
        data = payload.get("data", {})

        if event == "cte.created":
            self._sync_cte(data.get("cte", {}))
        elif event == "canonical.created":
            # V2: Canonical traceability events (downstream from canonical store)
            self._sync_canonical_event(data.get("canonical_event", {}))
        elif event == "product.created":
            self._sync_product(data.get("product", {}))
        elif event == "location.created":
            self._sync_location(data.get("location", {}))
        else:
            logger.warning("sync_worker_skipped_unknown_event", event=event, tenant_id="system", request_id="worker-dispatch")

    def _sync_cte(self, cte: dict[str, Any]) -> None:
        cte_id = cte.get("id")
        if not cte_id:
            return

        tenant_id = cte.get("tenant_id", "")

        properties = {
            "event_type": cte.get("event_type"),
            "event_time": cte.get("event_time"),
            "epcis_event_type": cte.get("epcis_event_type"),
            "epcis_action": cte.get("epcis_action"),
            "validation_status": cte.get("validation_status"),
            "tlc": cte.get("tlc"),
            "lot_code": cte.get("lot_code"),
            "data_source": cte.get("data_source"),
            "tenant_id": tenant_id,
        }

        with self.driver.session() as session:
            session.run(
                """
                MERGE (cte:CTE {id: $id, tenant_id: $tenant_id})
                SET cte += $properties
                """,
                id=cte_id,
                tenant_id=tenant_id,
                properties=properties,
            )

            tlc = cte.get("tlc")
            if tlc:
                session.run(
                    """
                    MERGE (lot:Lot {tlc: $tlc, tenant_id: $tenant_id})
                    SET lot.lot_code = coalesce($lot_code, lot.lot_code)
                    WITH lot
                    MATCH (cte:CTE {id: $cte_id, tenant_id: $tenant_id})
                    MERGE (cte)-[:INVOLVES_LOT]->(lot)
                    """,
                    tlc=tlc,
                    tenant_id=tenant_id,
                    lot_code=cte.get("lot_code"),
                    cte_id=cte_id,
                )

            product_id = cte.get("product_id")
            if product_id:
                session.run(
                    """
                    MERGE (product:Product {id: $product_id, tenant_id: $tenant_id})
                    WITH product
                    MATCH (cte:CTE {id: $cte_id, tenant_id: $tenant_id})
                    MERGE (cte)-[:INVOLVES_PRODUCT]->(product)
                    """,
                    product_id=product_id,
                    tenant_id=tenant_id,
                    cte_id=cte_id,
                )

                if tlc:
                    session.run(
                        """
                        MATCH (product:Product {id: $product_id, tenant_id: $tenant_id})
                        MATCH (lot:Lot {tlc: $tlc, tenant_id: $tenant_id})
                        MERGE (product)-[:HAS_LOT]->(lot)
                        """,
                        product_id=product_id,
                        tenant_id=tenant_id,
                        tlc=tlc,
                    )

            location_id = cte.get("location_id")
            if location_id:
                session.run(
                    """
                    MERGE (loc:Location {id: $location_id, tenant_id: $tenant_id})
                    WITH loc
                    MATCH (cte:CTE {id: $cte_id, tenant_id: $tenant_id})
                    MERGE (cte)-[:OCCURRED_AT]->(loc)
                    """,
                    location_id=location_id,
                    tenant_id=tenant_id,
                    cte_id=cte_id,
                )

            source_location_id = cte.get("source_location_id")
            if source_location_id:
                session.run(
                    """
                    MERGE (src:Location {id: $source_location_id, tenant_id: $tenant_id})
                    WITH src
                    MATCH (cte:CTE {id: $cte_id, tenant_id: $tenant_id})
                    MERGE (cte)-[:SHIPPED_FROM]->(src)
                    """,
                    source_location_id=source_location_id,
                    tenant_id=tenant_id,
                    cte_id=cte_id,
                )

            dest_location_id = cte.get("dest_location_id")
            if dest_location_id:
                session.run(
                    """
                    MERGE (dst:Location {id: $dest_location_id, tenant_id: $tenant_id})
                    WITH dst
                    MATCH (cte:CTE {id: $cte_id, tenant_id: $tenant_id})
                    MERGE (cte)-[:SHIPPED_TO]->(dst)
                    """,
                    dest_location_id=dest_location_id,
                    tenant_id=tenant_id,
                    cte_id=cte_id,
                )

    def _sync_canonical_event(self, event: dict[str, Any]) -> None:
        """Sync a canonical TraceabilityEvent to Neo4j.

        Creates graph nodes for the event, lot, and facility references,
        reading from the canonical model's richer field set (from/to
        facility references, entity references, provenance metadata).
        """
        event_id = event.get("event_id")
        if not event_id:
            return

        tenant_id = event.get("tenant_id", "")
        db_name = f"reg_tenant_{tenant_id.replace('-', '')}" if tenant_id else None
        # Validate database name to prevent injection via crafted tenant_id
        if db_name:
            import re
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{0,62}$', db_name):
                logger.warning("fsma_sync_invalid_db_name", db_name=db_name, tenant_id=tenant_id)
                return

        properties = {
            "event_type": event.get("event_type"),
            "event_timestamp": event.get("event_timestamp"),
            "source_system": event.get("source_system"),
            "confidence_score": event.get("confidence_score"),
            "schema_version": event.get("schema_version"),
            "sha256_hash": event.get("sha256_hash"),
            "tenant_id": tenant_id,
        }

        with self.driver.session(database=db_name) if db_name else self.driver.session() as session:
            # Upsert the TraceEvent node
            session.run(
                """
                MERGE (e:TraceEvent {event_id: $event_id, tenant_id: $tenant_id})
                SET e += $properties
                SET e.synced_at = datetime()
                """,
                event_id=event_id,
                tenant_id=tenant_id,
                properties=properties,
            )

            # Link to Lot via TLC
            tlc = event.get("traceability_lot_code")
            if tlc:
                session.run(
                    """
                    MERGE (lot:Lot {tlc: $tlc, tenant_id: $tenant_id})
                    ON CREATE SET lot.product_description = $product_ref, lot.created_at = datetime()
                    WITH lot
                    MATCH (e:TraceEvent {event_id: $event_id, tenant_id: $tenant_id})
                    MERGE (lot)-[:UNDERWENT]->(e)
                    """,
                    tlc=tlc,
                    tenant_id=tenant_id,
                    product_ref=event.get("product_reference", ""),
                    event_id=event_id,
                )

            # Link from-facility
            from_ref = event.get("from_facility_reference")
            if from_ref:
                session.run(
                    """
                    MERGE (f:Facility {identifier: $ref, tenant_id: $tenant_id})
                    ON CREATE SET f.name = $ref, f.created_at = datetime()
                    WITH f
                    MATCH (e:TraceEvent {event_id: $event_id, tenant_id: $tenant_id})
                    MERGE (f)-[:SHIPPED]->(e)
                    """,
                    ref=from_ref,
                    tenant_id=tenant_id,
                    event_id=event_id,
                )

            # Link to-facility
            to_ref = event.get("to_facility_reference")
            if to_ref:
                session.run(
                    """
                    MERGE (f:Facility {identifier: $ref, tenant_id: $tenant_id})
                    ON CREATE SET f.name = $ref, f.created_at = datetime()
                    WITH f
                    MATCH (e:TraceEvent {event_id: $event_id, tenant_id: $tenant_id})
                    MERGE (e)-[:SHIPPED_TO]->(f)
                    """,
                    ref=to_ref,
                    tenant_id=tenant_id,
                    event_id=event_id,
                )

        logger.info(
            "canonical_event_synced",
            event_id=event_id,
            event_type=event.get("event_type"),
            tenant_id=tenant_id,
            request_id="sync-canonical",
        )

    def _sync_product(self, product: dict[str, Any]) -> None:
        product_id = product.get("id")
        if not product_id:
            return

        tenant_id = product.get("tenant_id", "")

        with self.driver.session() as session:
            session.run(
                """
                MERGE (product:Product {id: $id, tenant_id: $tenant_id})
                SET product += $properties
                """,
                id=product_id,
                tenant_id=tenant_id,
                properties={
                    "name": product.get("name"),
                    "gtin": product.get("gtin"),
                    "sku": product.get("sku"),
                    "ftl_category": product.get("ftl_category"),
                    "ftl_covered": product.get("ftl_covered"),
                    "tenant_id": tenant_id,
                },
            )

    def _sync_location(self, location: dict[str, Any]) -> None:
        location_id = location.get("id")
        if not location_id:
            return

        tenant_id = location.get("tenant_id", "")

        with self.driver.session() as session:
            session.run(
                """
                MERGE (loc:Location {id: $id, tenant_id: $tenant_id})
                SET loc += $properties
                """,
                id=location_id,
                tenant_id=tenant_id,
                properties={
                    "name": location.get("name"),
                    "gln": location.get("gln"),
                    "location_type": location.get("location_type"),
                    "fda_fei": location.get("fda_fei"),
                    "tenant_id": tenant_id,
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
