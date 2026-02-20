from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import structlog
try:
    from langchain_core.prompts import PromptTemplate
except ImportError:
    from langchain.prompts import PromptTemplate
try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None
from neo4j import AsyncGraphDatabase

logger = structlog.get_logger("mapping-engine")

class MappingEngine:
    """Engine for semantic mapping and harmonization of global regulations."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password"
    ):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        self.llm = None
        if ChatGroq and os.getenv("GROQ_API_KEY"):
            try:
                self.llm = ChatGroq(model="grok-beta", temperature=0)
            except Exception:
                self.llm = None

    async def close(self):
        """Close the Neo4j driver."""
        await self.driver.close()

    async def map_requirement(self, obligation_id: str) -> List[Dict[str, Any]]:
        """Find and link similar obligations across different regulations.
        
        Returns:
            List of detected mappings.
        """
        if not self.llm:
            logger.warning("mapping_engine_disabled_no_llm")
            return []

        # 1. Fetch the source obligation and its context
        async with self.driver.session() as session:
            source_res = await session.run("""
                MATCH (o:Obligation {text: $id})<-[:REQUIRES]-(s:Section)
                RETURN o.text as text, s.regulation as regulation, s.id as section_id
                LIMIT 1
            """, id=obligation_id)
            source = await source_res.single()
            if not source:
                return []

            # 2. Find candidate obligations from OTHER regulations
            candidates_res = await session.run("""
                MATCH (o:Obligation)<-[:REQUIRES]-(s:Section)
                WHERE s.regulation <> $reg
                RETURN o.text as text, s.regulation as regulation, s.id as section_id
                LIMIT 20
            """, reg=source["regulation"])
            candidates = [dict(c) async for c in candidates_res]

        if not candidates:
            return []

        # 3. Use LLM to identify semantic matches
        mappings = []
        try:
            prompt = PromptTemplate.from_template(
                "Compare these regulatory obligations and identify if they represent the same requirement:\n"
                "Source: {source_text} (from {source_reg})\n\n"
                "Candidates:\n{candidates_text}\n\n"
                "Return only the indexes of candidates that match (comma-separated), or 'NONE'."
            )
            
            cand_text = "\n".join([f"{i}. {c['text']} (from {c['regulation']})" for i, c in enumerate(candidates)])
            # LLM invoke is usually synchronous in LangChain unless using ainvoke
            response = await self.llm.ainvoke(prompt.format(
                source_text=source["text"],
                source_reg=source["regulation"],
                candidates_text=cand_text
            ))
            result = response.content.strip().upper()
            
            if result != "NONE":
                matches = [int(idx.strip()) for idx in result.split(",") if idx.strip().isdigit()]
                for idx in matches:
                    if 0 <= idx < len(candidates):
                        match = candidates[idx]
                        mappings.append({
                            "source_id": obligation_id,
                            "target_id": match["text"],
                            "confidence": 0.9,
                            "justification": "Semantic harmonization via Grok-beta"
                        })

        except Exception as e:
            logger.error("llm_mapping_failed", error=str(e))
            return []

        # 4. Persistence: Create MAPPED_TO relationships in the graph
        if mappings:
            async with self.driver.session() as session:
                await session.run("""
                    UNWIND $mappings as map
                    MATCH (o1:Obligation {text: map.source_id})
                    MATCH (o2:Obligation {text: map.target_id})
                    MERGE (o1)-[r:MAPPED_TO]->(o2)
                    SET r.confidence = map.confidence,
                        r.justification = map.justification,
                        r.mapped_at = datetime()
                """, mappings=mappings)
                
        return mappings
