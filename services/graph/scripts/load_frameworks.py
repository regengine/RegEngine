#!/usr/bin/env python3
"""
Load compliance frameworks and controls into Neo4j
Supports: SOC2, ISO27001, NIST CSF, PCI-DSS, and more
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.neo4j_utils import Neo4jClient
import structlog

logger = structlog.get_logger("graph-loader")

# Framework definitions with controls
FRAMEWORKS = {
    "SOC2": {
        "version": "2017",
        "category": "Security & Privacy",
        "description": "AICPA's SOC 2 framework for service organizations",
        "controls": [
            {
                "id": "CC6.1",
                "requirement": "Logical and physical access controls",
                "description": "The entity implements logical access security software, infrastructure, and architectures...",
                "effort_hours": 8.0,
            },
            {
                "id": "CC6.2",
                "requirement": "User identification and authentication",
                "description": "Prior to issuing system credentials and granting access...",
                "effort_hours": 4.0,
            },
            {
                "id": "CC6.3",
                "requirement": "Network and data transmission security",
                "description": "The entity authorizes, modifies, or removes access...",
                "effort_hours": 6.0,
            },
            {
                "id": "CC7.1",
                "requirement": "Detection of security events",
                "description": "To meet its objectives, the entity uses detection and monitoring...",
                "effort_hours": 12.0,
            },
            {
                "id": "CC7.2",
                "requirement": "Response to security incidents",
                "description": "The entity monitors system components and the operation...",
                "effort_hours": 8.0,
            },
        ],
    },
    "ISO27001": {
        "version": "2022",
        "category": "Information Security",
        "description": "International standard for information security management systems",
        "controls": [
            {
                "id": "A.9.2.1",
                "requirement": "User registration and de-registration",
                "description": "Formal user registration and de-registration process...",
                "effort_hours": 4.0,
            },
            {
                "id": "A.9.2.2",
                "requirement": "User access provisioning",
                "description": "Formal user access provisioning process to assign or revoke access...",
                "effort_hours": 4.0,
            },
            {
                "id": "A.9.4.1",
                "requirement": "Information access restriction",
                "description": "Access to information and application system functions...",
                "effort_hours": 6.0,
            },
            {
                "id": "A.12.4.1",
                "requirement": "Event logging",
                "description": "Event logs recording user activities, exceptions, faults...",
                "effort_hours": 8.0,
            },
            {
                "id": "A.16.1.1",
                "requirement": "Responsibilities and procedures",
                "description": "Management responsibilities and procedures for ensuring a quick...",
                "effort_hours": 12.0,
            },
        ],
    },
    "NIST_CSF": {
        "version": "1.1",
        "category": "Cybersecurity",
        "description": "NIST Cybersecurity Framework",
        "controls": [
            {
                "id": "ID.AM-1",
                "requirement": "Physical devices and systems inventory",
                "description": "Physical devices and systems within the organization are inventoried",
                "effort_hours": 4.0,
            },
            {
                "id": "PR.AC-1",
                "requirement": "Identity and credential management",
                "description": "Identities and credentials are issued, managed, verified...",
                "effort_hours": 6.0,
            },
            {
                "id": "PR.AC-4",
                "requirement": "Access permissions and authorizations",
                "description": "Access permissions and authorizations are managed...",
                "effort_hours": 6.0,
            },
            {
                "id": "DE.CM-1",
                "requirement": "Network monitoring",
                "description": "The network is monitored to detect potential cybersecurity events",
                "effort_hours": 8.0,
            },
            {
                "id": "RS.RP-1",
                "requirement": "Response plan execution",
                "description": "Response plan is executed during or after an incident",
                "effort_hours": 12.0,
            },
        ],
    },
    "PCI_DSS": {
        "version": "4.0",
        "category": "Payment Security",
        "description": "Payment Card Industry Data Security Standard",
        "controls": [
            {
                "id": "1.1.1",
                "requirement": "Firewall configuration standards",
                "description": "Processes and mechanisms for installing and maintaining network security controls",
                "effort_hours": 8.0,
            },
            {
                "id": "2.2.1",
                "requirement": "Configuration standards",
                "description": "Configuration standards are defined and implemented...",
                "effort_hours": 6.0,
            },
            {
                "id": "8.2.1",
                "requirement": "User identification",
                "description": "All users are assigned a unique ID before access is granted...",
                "effort_hours": 4.0,
            },
            {
                "id": "10.2.1",
                "requirement": "Audit logs",
                "description": "Audit logs are implemented to support detection...",
                "effort_hours": 8.0,
            },
            {
                "id": "12.10.1",
                "requirement": "Incident response plan",
                "description": "An incident response plan exists and is ready to be initiated...",
                "effort_hours": 16.0,
            },
        ],
    },
}


async def load_framework(session, name: str, data: dict):
    """Load a single framework and its controls"""
    logger.info("loading_framework", framework=name)
    
    try:
        # Create framework node
        await session.run(
            """
            MERGE (f:Framework {name: $name})
            SET f.version = $version,
                f.category = $category,
                f.description = $description,
                f.last_updated = datetime()
            """,
            name=name,
            version=data["version"],
            category=data["category"],
            description=data["description"],
        )
        
        # Create control nodes and relationships
        for control in data["controls"]:
            await session.run(
                """
                MATCH (f:Framework {name: $framework})
                MERGE (c:Control {control_id: $id})
                SET c.requirement = $requirement,
                    c.description = $description,
                    c.effort_hours = $effort_hours
                MERGE (f)-[:HAS_CONTROL]->(c)
                """,
                framework=name,
                id=control["id"],
                requirement=control["requirement"],
                description=control.get("description", ""),
                effort_hours=control.get("effort_hours", 4.0),
            )
        
        logger.info(
            "framework_loaded",
            framework=name,
            controls=len(data["controls"])
        )
        
    except Exception as exc:
        logger.exception("framework_load_failed", framework=name, error=str(exc))
        raise


async def create_relationships():
    """Create explicit relationships between frameworks based on control overlap"""
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        
        async with client.session() as session:
            logger.info("creating_relationships")
            
            # Create MAPS_TO relationships for frameworks with >20% overlap
            await session.run("""
                MATCH (f1:Framework)-[:HAS_CONTROL]->(c1:Control)
                MATCH (f2:Framework)-[:HAS_CONTROL]->(c2:Control)
                WHERE f1.name < f2.name AND c1.requirement = c2.requirement
                WITH f1, f2, count(c2) as overlap
                WHERE overlap > 2
                MATCH (f2)-[:HAS_CONTROL]->(total:Control)
                WITH f1, f2, overlap, count(total) as total_controls,
                     toFloat(overlap) / count(total) as strength
                WHERE strength > 0.2
                MERGE (f1)-[r:MAPS_TO]->(f2)
                SET r.control_overlap = overlap,
                    r.strength = strength,
                    r.last_updated = datetime()
                RETURN f1.name, f2.name, overlap, strength
            """)
            
            logger.info("relationships_created")
            
    except Exception as exc:
        logger.exception("relationship_creation_failed", error=str(exc))
        raise
    finally:
        if client:
            await client.close()


async def verify_load():
    """Verify frameworks were loaded correctly"""
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        
        async with client.session() as session:
            # Count frameworks
            result = await session.run("MATCH (f:Framework) RETURN count(f) as count")
            data = await result.single()
            framework_count = data["count"]
            
            # Count controls
            result = await session.run("MATCH (c:Control) RETURN count(c) as count")
            data = await result.single()
            control_count = data["count"]
            
            # Count relationships
            result = await session.run(
                "MATCH (:Framework)-[r:HAS_CONTROL]->(:Control) RETURN count(r) as count"
            )
            data = await result.single()
            has_control_count = data["count"]
            
            result = await session.run(
                "MATCH (:Framework)-[r:MAPS_TO]->(:Framework) RETURN count(r) as count"
            )
            data = await result.single()
            maps_to_count = data["count"]
            
            logger.info(
                "load_verified",
                frameworks=framework_count,
                controls=control_count,
                has_control=has_control_count,
                maps_to=maps_to_count
            )
            
            print(f"\n✅ Load verification:")
            print(f"   Frameworks: {framework_count}")
            print(f"   Controls: {control_count}")
            print(f"   HAS_CONTROL relationships: {has_control_count}")
            print(f"   MAPS_TO relationships: {maps_to_count}")
            
    except Exception as exc:
        logger.exception("verification_failed", error=str(exc))
        raise
    finally:
        if client:
            await client.close()


async def main():
    """Main loading function"""
    logger.info("framework_loading_starting", frameworks=len(FRAMEWORKS))
    print(f"\n📊 Loading {len(FRAMEWORKS)} compliance frameworks...")
    
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        
        async with client.session() as session:
            for name, data in FRAMEWORKS.items():
                await load_framework(session, name, data)
                print(f"   ✅ {name}")
        
        await client.close()
        
        # Create relationships
        print("\n🔗 Creating framework relationships...")
        await create_relationships()
        
        # Verify
        await verify_load()
        
        logger.info("framework_loading_complete")
        print("\n✅ All frameworks loaded successfully!")
        print("   Next step: Start the Graph service with 'uvicorn app.main:app --reload --port 8003'")
        
    except Exception as exc:
        logger.exception("loading_failed", error=str(exc))
        print(f"\n❌ Loading failed: {exc}")
        sys.exit(1)
    finally:
        if client:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
