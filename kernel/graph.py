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
        password: str = os.getenv("NEO4J_PASSWORD", "")
    ):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        self._groq_model = os.getenv("GROQ_MODEL", "llama3-70b-8192")
        self.llm = None
        if ChatGroq and os.getenv("GROQ_API_KEY"):
            try:
                self.llm = ChatGroq(model=self._groq_model, temperature=0)
            except Exception as e:
                logger.warning("groq_init_failed", model=self._groq_model, error=str(e))
                self.llm = None

    async def close(self):
        """Close the Neo4j driver."""
        await self.driver.close()

    async def map_requirement(self, obligation_id: str, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Find and link similar obligations across different regulations.

        Args:
            obligation_id: The obligation text to find mappings for.
            tenant_id: Optional tenant UUID string for multi-tenant isolation.

        Returns:
            List of detected mappings.
        """
        if not self.llm:
            logger.warning("mapping_engine_disabled_no_llm")
            return []

        # 1. Fetch the source obligation and its context
        async with self.driver.session() as session:
            tenant_filter = "AND o.tenant_id = $tenant_id" if tenant_id else ""
            source_res = await session.run(f"""
                MATCH (o:Obligation {{text: $id}})<-[:REQUIRES]-(s:Section)
                WHERE true {tenant_filter}
                RETURN o.text as text, s.regulation as regulation, s.id as section_id
                LIMIT 1
            """, id=obligation_id, tenant_id=tenant_id)
            source = await source_res.single()
            if not source:
                return []

            # 2. Find candidate obligations from OTHER regulations
            candidates_res = await session.run(f"""
                MATCH (o:Obligation)<-[:REQUIRES]-(s:Section)
                WHERE s.regulation <> $reg {tenant_filter}
                RETURN o.text as text, s.regulation as regulation, s.id as section_id
                LIMIT 20
            """, reg=source["regulation"], tenant_id=tenant_id)
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
                "Return each matching candidate as 'index:confidence' (e.g., '0:0.85,2:0.60'), "
                "or 'NONE' if no matches. Confidence is 0.0-1.0 where 1.0 is exact match."
            )
            
            cand_text = "\n".join([f"{i}. {c['text']} (from {c['regulation']})" for i, c in enumerate(candidates)])
            response = await self.llm.ainvoke(prompt.format(
                source_text=source["text"],
                source_reg=source["regulation"],
                candidates_text=cand_text
            ))
            result = response.content.strip().upper()
            
            if result != "NONE":
                min_confidence = 0.7
                for pair in result.split(","):
                    if ":" not in pair:
                        continue
                    idx_str, conf_str = pair.strip().split(":", 1)
                    if idx_str.isdigit():
                        idx = int(idx_str)
                        try:
                            confidence = float(conf_str.strip())
                        except ValueError:
                            confidence = 0.9
                        if 0 <= idx < len(candidates) and confidence >= min_confidence:
                            match = candidates[idx]
                            mappings.append({
                                "source_id": obligation_id,
                                "target_id": match["text"],
                                "confidence": confidence,
                                "justification": f"Semantic harmonization via {self._groq_model}"
                            })

        except Exception as e:
            logger.error("llm_mapping_failed", error=str(e))
            return []

        # 4. Persistence: Create MAPPED_TO relationships in the graph
        if mappings:
            tenant_match = ", tenant_id: $tenant_id" if tenant_id else ""
            async with self.driver.session() as session:
                await session.run(f"""
                    UNWIND $mappings as map
                    MATCH (o1:Obligation {{text: map.source_id{tenant_match}}})
                    MATCH (o2:Obligation {{text: map.target_id{tenant_match}}})
                    MERGE (o1)-[r:MAPPED_TO]->(o2)
                    SET r.confidence = map.confidence,
                        r.justification = map.justification,
                        r.mapped_at = datetime()
                """, mappings=mappings, tenant_id=tenant_id)
                
        return mappings
