"""
Regulation Loader
=================
Parse regulations and load them into Neo4j.

Hardening (#1351)
-----------------
* Env-var reads (``NEO4J_URI`` / ``NEO4J_USER`` / ``NEO4J_PASSWORD``) moved
  out of the ``__init__`` signature defaults — they used to be evaluated
  at *class definition* time, so env changes after module import never
  applied. They are now read inside ``__init__`` on each construction.
* Empty password is refused outright unless the caller passes
  ``allow_empty_password=True`` (useful only in local dev against an
  unauthenticated embedded Neo4j). In a prod-like environment this raises
  ``RuntimeError`` rather than silently building a driver that may
  connect without auth.
* The blocking Neo4j ``session.run`` body of the (async) ``load()`` method
  now runs via :func:`asyncio.to_thread`, so FastAPI workers no longer
  stall their event loop for the duration of an ingest.
* Optional ``tenant_id`` kwarg on ``load()``: when supplied, the loader
  also writes ``RegulatoryObligation {obligation_id, tenant_id}`` nodes
  keyed by a stable hash of the obligation text. This aligns the loader
  graph shape with what ``RegulatoryEngine._persist_evaluation`` expects
  (which MATCHes ``RegulatoryObligation {obligation_id, tenant_id}``) so
  coverage can actually be non-zero after a load.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase
import structlog

from kernel.parser import RegulationParser

logger = structlog.get_logger("regulation-loader")


def _obligation_id_from_text(text: str) -> str:
    """Derive a stable obligation_id from its text.

    SHA-256 truncated to 32 hex chars — collision-resistant enough for
    regulation obligations, short enough to be human-scannable in logs.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


class RegulationLoader:
    """Utility to parse regulations and load them into Neo4j graph (v2).

    See module docstring for hardening notes (#1351).
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        *,
        allow_empty_password: bool = False,
    ):
        # Read env vars at call time — not at class-definition time — so
        # tests and per-worker config changes apply.
        if uri is None:
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        if user is None:
            user = os.getenv("NEO4J_USER", "neo4j")
        if password is None:
            password = os.getenv("NEO4J_PASSWORD", "")

        if not password and not allow_empty_password:
            raise RuntimeError(
                "RegulationLoader refuses to build an unauthenticated Neo4j "
                "driver: NEO4J_PASSWORD is empty. Pass "
                "allow_empty_password=True explicitly for local dev against "
                "an embedded / auth-disabled Neo4j."
            )

        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            logger.info("neo4j_driver_initialized", uri=uri)
        except Exception as e:
            logger.error("neo4j_driver_init_failed", error=str(e))
            raise

    def close(self) -> None:
        """Close the Neo4j driver."""
        if hasattr(self, "driver"):
            self.driver.close()

    # -----------------------------------------------------------------
    # Blocking core — runs off the event loop via ``asyncio.to_thread``.
    # -----------------------------------------------------------------

    def _load_sync(
        self,
        sections: List[Dict[str, Any]],
        regulation_name: str,
        version: str,
        tenant_id: Optional[str],
    ) -> None:
        """Synchronous Neo4j write. Always invoked via ``to_thread``."""
        with self.driver.session() as session:
            # Existing graph shape (Regulation/Section/Citation/Obligation{text}/Penalty)
            # — unchanged to preserve the ingestion service contract.
            session.run(
                """
                MERGE (r:Regulation {name: $name})
                SET r.version = $version, r.updated_at = datetime()
                WITH r
                UNWIND $sections as sec
                MERGE (s:Section {id: sec.section_id, regulation: $name})
                MERGE (r)-[:HAS_SECTION]->(s)
                SET s.title = sec.title,
                    s.text = sec.text,
                    s.jurisdiction = sec.jurisdiction,
                    s.effective_date = sec.effective_date,
                    s.content_hash = sec.content_hash

                WITH s, sec
                UNWIND sec.citations as cit
                MERGE (c:Citation {text: cit})
                MERGE (s)-[:CITES]->(c)

                WITH s, sec
                UNWIND sec.obligations as ob
                MERGE (o:Obligation {text: ob})
                MERGE (s)-[:REQUIRES]->(o)

                WITH s, sec
                UNWIND sec.penalties as pen
                MERGE (p:Penalty {text: pen})
                MERGE (s)-[:HAS_PENALTY]->(p)
                """,
                name=regulation_name,
                version=version,
                sections=sections,
            )

            # New: when the caller supplies a tenant_id, also write
            # RegulatoryObligation {obligation_id, tenant_id} nodes so the
            # engine's coverage MATCH (o:RegulatoryObligation {obligation_id,
            # tenant_id}) actually finds something (#1351).
            if tenant_id:
                ob_rows = [
                    {
                        "obligation_id": _obligation_id_from_text(ob),
                        "text": ob,
                    }
                    for sec in sections
                    for ob in sec.get("obligations") or []
                ]
                if ob_rows:
                    session.run(
                        """
                        UNWIND $rows as row
                        MERGE (ro:RegulatoryObligation {
                            obligation_id: row.obligation_id,
                            tenant_id: $tenant_id
                        })
                        SET ro.text = row.text,
                            ro.regulation_name = $name,
                            ro.version = $version,
                            ro.updated_at = datetime()
                        """,
                        rows=ob_rows,
                        tenant_id=tenant_id,
                        name=regulation_name,
                        version=version,
                    )

    async def load(
        self,
        source: str,
        source_type: str,
        regulation_name: str,
        version: str = "1.0",
        *,
        tenant_id: Optional[str] = None,
    ) -> int:
        """Parse ``source`` and load sections / obligations / penalties into Neo4j.

        Args:
            source: Path or URL to the regulation document.
            source_type: ``pdf`` / ``docx`` / ``url`` / ``html``.
            regulation_name: Human-readable identifier of the regulation.
            version: Version tag for the loaded regulation.
            tenant_id: When provided, also write
                ``RegulatoryObligation {obligation_id, tenant_id}`` nodes
                aligned with the engine's coverage queries (#1351).

        Returns:
            Number of sections loaded.
        """
        logger.info(
            "ingesting_regulation_v2",
            name=regulation_name,
            source=source,
            version=version,
            tenant_scoped=bool(tenant_id),
        )

        parser = RegulationParser()
        sections = await parser.parse(source, source_type)

        # Run the blocking Neo4j writes off the event loop so a slow Neo4j
        # does not stall the request-handling worker (#1351).
        await asyncio.to_thread(
            self._load_sync,
            sections,
            regulation_name,
            version,
            tenant_id,
        )

        logger.info(
            "regulation_loaded_v2",
            name=regulation_name,
            sections_count=len(sections),
            tenant_scoped=bool(tenant_id),
        )
        return len(sections)

    def _query(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Helper for running read queries (used by internal/browsing components)."""
        with self.driver.session() as session:
            result = session.run(query, **kwargs)
            return [dict(record) for record in result]
