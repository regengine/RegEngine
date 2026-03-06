from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase
import structlog

from kernel.parser import RegulationParser

logger = structlog.get_logger("regulation-loader")

class RegulationLoader:
    """Utility to parse regulations and load them into Neo4j graph with enhanced schema (v2)."""

    def __init__(
        self, 
        uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687"), 
        user: str = os.getenv("NEO4J_USER", "neo4j"), 
        password: str = os.getenv("NEO4J_PASSWORD", "")
    ):
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            logger.info("neo4j_driver_initialized", uri=uri)
        except Exception as e:
            logger.error("neo4j_driver_init_failed", error=str(e))
            raise

    def close(self):
        """Close the Neo4j driver."""
        if hasattr(self, "driver"):
            self.driver.close()

    async def load(self, source: str, source_type: str, regulation_name: str, version: str = "1.0") -> int:
        """Parse source and load sections, obligations, and penalties into Neo4j.
        
        Returns:
            Number of sections loaded.
        """
        logger.info("ingesting_regulation_v2", name=regulation_name, source=source, version=version)
        parser = RegulationParser()
        sections = await parser.parse(source, source_type)
        
        with self.driver.session() as session:
            # Atomic regulation node creation and section linking
            # Includes Obligation and Penalty nodes, and cross-ref relationships
            session.run("""
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
            """, name=regulation_name, version=version, sections=sections)
            
        logger.info("regulation_loaded_v2", name=regulation_name, sections_count=len(sections))
        return len(sections)

    def _query(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Helper for running read queries (used by internal/browsing components)."""
        with self.driver.session() as session:
            result = session.run(query, **kwargs)
            return [dict(record) for record in result]
