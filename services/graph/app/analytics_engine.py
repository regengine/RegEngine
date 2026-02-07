"""Gap Analysis Mapping Engine for Graph Service."""

from typing import List, Dict, Any, Optional
import structlog
from .neo4j_utils import Neo4jClient
from .queries import arbitrage_queries

logger = structlog.get_logger("graph-api.analytics")


class GapAnalysisEngine:
    """
    Advanced engine for mapping regulatory gaps and overlaps.
    
    Supports semantic-aware mapping logic (to be enhanced with embeddings)
    and detailed remediation effort estimation.
    """
    
    def __init__(self, database: Optional[str] = None):
        self.database = database or Neo4jClient.get_global_database_name()
        self.client = Neo4jClient(database=self.database)

    async def analyze_framework_gap(
        self, 
        current_framework: str, 
        target_framework: str
    ) -> Dict[str, Any]:
        """
        Perform deep gap analysis between two frameworks.
        """
        async with self.client.session() as session:
            # 1. Fetch exact matches
            overlap_result = await session.run(
                arbitrage_queries.OVERLAP_QUERY,
                framework1=current_framework,
                framework2=target_framework
            )
            overlap_data = await overlap_result.single()
            
            # 2. Fetch missing controls (Gaps)
            gap_result = await session.run(
                arbitrage_queries.GAP_QUERY,
                current=current_framework,
                target=target_framework
            )
            
            gaps = []
            total_hours = 0.0
            async for record in gap_result:
                hours = record.get("estimated_hours", 4.0)
                gaps.append({
                    "control_id": record["control_id"],
                    "requirement": record["control_name"],
                    "description": record["description"],
                    "estimated_hours": hours,
                    "priority": "HIGH" if hours <= 4 else "MEDIUM"
                })
                total_hours += hours
                
            # 3. Calculate coverage
            coverage_result = await session.run(
                arbitrage_queries.COVERAGE_QUERY,
                current=current_framework,
                target=target_framework
            )
            coverage_data = await coverage_result.single()
            
            coverage_pct = coverage_data["coverage_percentage"] if coverage_data else 0.0
            
            return {
                "summary": {
                    "source": current_framework,
                    "target": target_framework,
                    "coverage_percentage": round(coverage_pct, 2),
                    "gap_count": len(gaps),
                    "estimated_remediation_hours": round(total_hours, 2)
                },
                "gaps": gaps,
                "overlap_count": overlap_data["overlap_count"] if overlap_data else 0
            }

    async def close(self):
        await self.client.close()
