from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
import structlog

from ..neo4j_utils import Neo4jClient

logger = structlog.get_logger("graph-regulations")
router = APIRouter()

@router.get("/list", response_model=List[Dict[str, Any]])
async def list_regulations(
    jurisdiction: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """List all ingested regulations in the graph with optional filter."""
    async with Neo4jClient() as client:
        async with client.session() as session:
            where_clause = ""
            params = {"skip": skip, "limit": limit}
            if jurisdiction:
                where_clause = "WHERE r.jurisdiction = $jurisdiction "
                params["jurisdiction"] = jurisdiction

            query = f"""
                MATCH (r:Regulation)
                {where_clause}
                OPTIONAL MATCH (r)-[:HAS_SECTION]->(s)
                RETURN r.name as name, count(s) as section_count, r.version as version
                ORDER BY r.name
                SKIP $skip LIMIT $limit
            """
            result = await session.run(query, **params)
            return [dict(record) async for record in result]

@router.get("/{name}/sections")
async def get_regulation_sections(
    name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
):
    """Retrieve all sections for a specific regulation."""
    async with Neo4jClient() as client:
        async with client.session() as session:
            result = await session.run("""
                MATCH (r:Regulation {name: $name})-[:HAS_SECTION]->(s:Section)
                RETURN s.id as id, s.title as title, s.text as text, s.jurisdiction as jurisdiction, s.effective_date as effective_date
                ORDER BY s.id
                SKIP $skip LIMIT $limit
            """, name=name, skip=skip, limit=limit)
            sections = [dict(record) async for record in result]
            if not sections and skip == 0:
                raise HTTPException(status_code=404, detail="Regulation not found or has no sections")
            return sections

@router.get("/{name}/citations")
async def get_regulation_citations(
    name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
):
    """Retrieve all citations mentioned in a regulation."""
    async with Neo4jClient() as client:
        async with client.session() as session:
            result = await session.run("""
                MATCH (r:Regulation {name: $name})-[:HAS_SECTION]->(s)-[:CITES]->(c:Citation)
                RETURN DISTINCT c.text as citation, count(s) as mention_count
                ORDER BY mention_count DESC
                SKIP $skip LIMIT $limit
            """, name=name, skip=skip, limit=limit)
            return [dict(record) async for record in result]


@router.get("/search")
async def search_regulations(
    q: str = Query(..., min_length=2),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Full-text search across all codified regulation sections."""
    async with Neo4jClient() as client:
        async with client.session() as session:
            # Note: Requires a full-text index named 'sectionText' on (:Section {text})
            try:
                result = await session.run("""
                    CALL db.index.fulltext.queryNodes("sectionText", $q) YIELD node, score
                    RETURN node.id as section_id, node.title as title, node.text as text, 
                           node.regulation as regulation, score
                    ORDER BY score DESC
                    SKIP $skip LIMIT $limit
                """, q=q, skip=skip, limit=limit)
                return [dict(record) async for record in result]
            except Exception as e:
                logger.error("fulltext_search_failed", error=str(e), query=q)
                # Fallback to CONTAINS if index is missing (slower but functional for dev)
                result = await session.run("""
                    MATCH (s:Section)
                    WHERE s.text CONTAINS $q OR s.title CONTAINS $q
                    RETURN s.id as section_id, s.title as title, s.text as text, 
                           s.regulation as regulation, 1.0 as score
                    SKIP $skip LIMIT $limit
                """, q=q, skip=skip, limit=limit)
                return [dict(record) async for record in result]


@router.get("/mappings", response_model=List[Dict[str, Any]])
async def get_requirement_mappings(
    obligation_id: Optional[str] = Query(None),
    regulation: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Retrieve semantic mappings between requirements (cross-jurisdiction)."""
    async with Neo4jClient() as client:
        async with client.session() as session:
            where_clauses = []
            params = {"skip": skip, "limit": limit}
            
            if obligation_id:
                where_clauses.append("o1.text = $obligation_id")
                params["obligation_id"] = obligation_id
            if regulation:
                where_clauses.append("s1.regulation = $regulation")
                params["regulation"] = regulation
                
            where_stmt = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            
            query = f"""
                MATCH (o1:Obligation)-[r:MAPPED_TO]-(o2:Obligation)
                MATCH (o1)<-[:REQUIRES]-(s1:Section)
                MATCH (o2)<-[:REQUIRES]-(s2:Section)
                {where_stmt}
                RETURN o1.text as source_text, s1.regulation as source_reg,
                       o2.text as target_text, s2.regulation as target_reg,
                       r.confidence as confidence, r.justification as justification
                SKIP $skip LIMIT $limit
            """
            result = await session.run(query, **params)
            return [dict(record) async for record in result]


@router.post("/harmonize/{obligation_id}")
async def harmonize_requirement(obligation_id: str):
    """Trigger LLM-based semantic mapping for a specific requirement."""
    from shared.graph.mapping_engine import MappingEngine
    from ..config import settings
    
    engine = MappingEngine(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password
    )
    try:
        mappings = await engine.map_requirement(obligation_id)
        await engine.close()
        return {
            "status": "completed",
            "obligation_id": obligation_id,
            "mappings_found": len(mappings),
            "mappings": mappings
        }
    except Exception as e:
        await engine.close()
        logger.error("harmonization_api_failed", obligation_id=obligation_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Harmonization failed: {str(e)}")
