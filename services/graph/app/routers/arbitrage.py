"""
Framework Arbitrage Detection Router
Endpoints for compliance framework overlap, gap analysis, and relationships
"""

from fastapi import APIRouter, HTTPException, Query
import structlog

from ..neo4j_utils import Neo4jClient
from ..models.framework import (
    ArbitrageResponse,
    ArbitrageOpportunity,
    ControlMapping,
    GapAnalysisResponse,
    ComplianceGap,
    FrameworkRelationshipsResponse,
    FrameworkRelationship,
    Effort,
    Priority,
)
from ..queries import arbitrage_queries

logger = structlog.get_logger("graph-api.arbitrage")

arbitrage_router = APIRouter(prefix="/graph", tags=["arbitrage"])


@arbitrage_router.get("/arbitrage", response_model=ArbitrageResponse)
async def find_arbitrage_opportunities(
    framework_from: str = Query(..., description="Source framework (e.g., SOC2)"),
    framework_to: str = Query(..., description="Target framework (e.g., ISO27001)"),
):
    """
    Find arbitrage opportunities between two compliance frameworks.
    
    Analyzes control overlap and calculates potential time savings when
    leveraging existing compliance work for certification in a new framework.
    
    **Example:**
    ```
    GET /graph/arbitrage?framework_from=SOC2&framework_to=ISO27001
    ```
    """
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        
        async with client.session() as session:
            # Get overlap between frameworks
            overlap_result = await session.run(
                arbitrage_queries.OVERLAP_QUERY,
                framework1=framework_from,
                framework2=framework_to
            )
            overlap_data = await overlap_result.single()
            
            if not overlap_data:
                logger.info(
                    "no_overlap_found",
                    framework_from=framework_from,
                    framework_to=framework_to
                )
                return ArbitrageResponse(opportunities=[])
            
            overlap_count = overlap_data["overlap_count"]
            mappings = overlap_data["mappings"]
            
            # Get total controls in target framework
            total_result = await session.run(
                arbitrage_queries.TOTAL_CONTROLS_QUERY,
                framework=framework_to
            )
            total_data = await total_result.single()
            total_controls = total_data["total_controls"] if total_data else 0
            
            if total_controls == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"Framework '{framework_to}' not found or has no controls"
                )
            
            # Calculate metrics
            overlap_percentage = (overlap_count / total_controls) * 100
            estimated_savings = overlap_count * 4.0  # 4 hours per control average
            
            # Create control mappings
            control_mappings = [
                ControlMapping(
                    control_from=m["from"],
                    control_to=m["to"],
                    confidence=m.get("confidence", 1.0),
                    requirement_from=m.get("requirement_from"),
                    requirement_to=m.get("requirement_to"),
                )
                for m in mappings
            ]
            
            # Create opportunity
            opportunity = ArbitrageOpportunity(
                id=f"arb-{framework_from.lower()}-{framework_to.lower()}",
                from_framework=framework_from,
                to_framework=framework_to,
                overlap_controls=overlap_count,
                total_controls=total_controls,
                overlap_percentage=round(overlap_percentage, 2),
                estimated_savings_hours=estimated_savings,
                path=control_mappings[:10],  # Limit to first 10 mappings
            )
            
            logger.info(
                "arbitrage_opportunity_found",
                framework_from=framework_from,
                framework_to=framework_to,
                overlap=overlap_count,
                savings=estimated_savings
            )
            
            return ArbitrageResponse(opportunities=[opportunity])
            
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "arbitrage_query_error",
            framework_from=framework_from,
            framework_to=framework_to,
            error=str(exc)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing arbitrage: {str(exc)}"
        ) from exc
    finally:
        if client:
            await client.close()


@arbitrage_router.get("/gaps", response_model=GapAnalysisResponse)
async def analyze_compliance_gaps(
    current_framework: str = Query(..., description="Current framework (e.g., SOC2)"),
    target_framework: str = Query(..., description="Target framework (e.g., HIPAA)"),
):
    """
    Identify compliance gaps between current and target frameworks.
    
    Finds controls present in the target framework but missing in the current
    framework, along with estimated remediation effort and priorities.
    
    **Example:**
    ```
    GET /graph/gaps?current_framework=SOC2&target_framework=HIPAA
    ```
    """
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        
        async with client.session() as session:
            # Get gaps
            gap_result = await session.run(
                arbitrage_queries.GAP_QUERY,
                current=current_framework,
                target=target_framework
            )
            
            gaps_list = []
            total_hours = 0.0
            
            async for record in gap_result:
                estimated_hours = record.get("estimated_hours", 4.0)
                total_hours += estimated_hours
                
                # Determine effort and priority based on hours
                if estimated_hours <= 4:
                    effort = Effort.LOW
                elif estimated_hours <= 12:
                    effort = Effort.MEDIUM
                else:
                    effort = Effort.HIGH
                
                # Priority inversely related to effort for quick wins
                if estimated_hours <= 4:
                    priority = Priority.HIGH
                elif estimated_hours <= 12:
                    priority = Priority.MEDIUM
                else:
                    priority = Priority.LOW
                
                gap = ComplianceGap(
                    control_id=record["control_id"],
                    control_name=record["control_name"],
                    missing_in=current_framework,
                    description=record.get("description"),
                    remediation_effort=effort,
                    priority=priority,
                    estimated_hours=estimated_hours
                )
                gaps_list.append(gap)
            
            # Get coverage percentage
            coverage_result = await session.run(
                arbitrage_queries.COVERAGE_QUERY,
                current=current_framework,
                target=target_framework
            )
            coverage_data = await coverage_result.single()
            
            coverage_percentage = coverage_data["coverage_percentage"] if coverage_data else 0.0
            
            logger.info(
                "gaps_analyzed",
                current=current_framework,
                target=target_framework,
                gaps_found=len(gaps_list),
                coverage=coverage_percentage
            )
            
            return GapAnalysisResponse(
                gaps=gaps_list,
                coverage_percentage=round(coverage_percentage, 2),
                total_gaps=len(gaps_list),
                estimated_total_hours=round(total_hours, 2)
            )
            
    except Exception as exc:
        logger.exception(
            "gap_analysis_error",
            current=current_framework,
            target=target_framework,
            error=str(exc)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing gaps: {str(exc)}"
        ) from exc
    finally:
        if client:
            await client.close()


@arbitrage_router.get(
    "/frameworks/{framework_id}/relationships",
    response_model=FrameworkRelationshipsResponse
)
async def get_framework_relationships(framework_id: str):
    """
    Get all frameworks related to the specified framework.
    
    Returns frameworks with significant control overlap, showing relationship
    strength and the number of overlapping controls.
    
    **Example:**
    ```
    GET /graph/frameworks/SOC2/relationships
    ```
    """
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        
        async with client.session() as session:
            # Try explicit relationships first
            rel_result = await session.run(
                arbitrage_queries.RELATIONSHIPS_QUERY,
                framework=framework_id
            )
            
            relationships = []
            async for record in rel_result:
                rel = FrameworkRelationship(
                    framework_id=record["framework_id"],
                    framework_name=record["framework_name"],
                    relationship_type=record.get("relationship_type", "maps_to"),
                    strength=record.get("strength", 0.5),
                    control_overlap=record.get("control_overlap", 0)
                )
                relationships.append(rel)
            
            # If no explicit relationships, discover them dynamically
            if not relationships:
                discover_result = await session.run(
                    arbitrage_queries.DISCOVER_RELATIONSHIPS_QUERY,
                    framework=framework_id
                )
                
                async for record in discover_result:
                    rel = FrameworkRelationship(
                        framework_id=record["framework_id"],
                        framework_name=record["framework_name"],
                        relationship_type=record["relationship_type"],
                        strength=round(record["strength"], 3),
                        control_overlap=record["control_overlap"]
                    )
                    relationships.append(rel)
            
            logger.info(
                "relationships_found",
                framework=framework_id,
                related_count=len(relationships)
            )
            
            return FrameworkRelationshipsResponse(
                framework=framework_id,
                related_frameworks=relationships
            )
            
    except Exception as exc:
        logger.exception(
            "relationships_query_error",
            framework=framework_id,
            error=str(exc)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error querying relationships: {str(exc)}"
        ) from exc
    finally:
        if client:
            await client.close()


@arbitrage_router.get("/frameworks")
async def list_frameworks():
    """
    List all available compliance frameworks in the graph.
    
    **Example:**
    ```
    GET /graph/frameworks
    ```
    """
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        
        async with client.session() as session:
            result = await session.run(arbitrage_queries.ALL_FRAMEWORKS_QUERY)
            
            frameworks = []
            async for record in result:
                frameworks.append({
                    "name": record["name"],
                    "version": record.get("version", "unknown"),
                    "category": record.get("category", "unknown"),
                    "description": record.get("description")
                })
            
            return {"count": len(frameworks), "frameworks": frameworks}
            
    except Exception as exc:
        logger.exception("list_frameworks_error", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Error listing frameworks: {str(exc)}"
        ) from exc
    finally:
        if client:
            await client.close()
