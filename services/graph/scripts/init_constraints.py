#!/usr/bin/env python3
"""
Initialize Neo4j constraints and indexes for Graph service
Run this script once before loading framework data
"""

import asyncio
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j.exceptions import ClientError, ServiceUnavailable, SessionExpired
from app.neo4j_utils import Neo4jClient
import structlog

logger = structlog.get_logger("graph-init")


async def create_constraints():
    """Create Neo4j constraints for data integrity"""
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        
        async with client.session() as session:
            logger.info("creating_constraints")
            
            # Unique constraint(f:Framework) name
            try:
                await session.run("""
                    CREATE CONSTRAINT framework_name_unique IF NOT EXISTS
                    FOR (f:Framework) REQUIRE f.name IS UNIQUE
                """)
                logger.info("constraint_created", name="framework_name_unique")
            except ClientError as e:
                logger.warning("constraint_exists", name="framework_name_unique", error=str(e))
            
            # Unique constraint on control_id
            try:
                await session.run("""
                    CREATE CONSTRAINT control_id_unique IF NOT EXISTS
                    FOR (c:Control) REQUIRE c.control_id IS UNIQUE
                """)
                logger.info("constraint_created", name="control_id_unique")
            except ClientError as e:
                logger.warning("constraint_exists", name="control_id_unique", error=str(e))
            
            logger.info("constraints_completed")
    
    except (ClientError, ServiceUnavailable, SessionExpired, OSError) as exc:
        logger.exception("constraint_creation_failed", error=str(exc))
        raise
    finally:
        if client:
            await client.close()


async def create_indexes():
    """Create Neo4j indexes for query performance"""
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        
        async with client.session() as session:
            logger.info("creating_indexes")
            
            # Index on framework category
            try:
                await session.run("""
                    CREATE INDEX framework_category_idx IF NOT EXISTS
                    FOR (f:Framework) ON (f.category)
                """)
                logger.info("index_created", name="framework_category_idx")
            except ClientError as e:
                logger.warning("index_exists", name="framework_category_idx", error=str(e))
            
            # Index on control requirement (for overlap detection)
            try:
                await session.run("""
                    CREATE INDEX control_requirement_idx IF NOT EXISTS
                    FOR (c:Control) ON (c.requirement)
                """)
                logger.info("index_created", name="control_requirement_idx")
            except ClientError as e:
                logger.warning("index_exists", name="control_requirement_idx", error=str(e))
            
            # Index on control effort_hours (for gap prioritization)
            try:
                await session.run("""
                    CREATE INDEX control_effort_idx IF NOT EXISTS
                    FOR (c:Control) ON (c.effort_hours)
                """)
                logger.info("index_created", name="control_effort_idx")
            except ClientError as e:
                logger.warning("index_exists", name="control_effort_idx", error=str(e))
            
            logger.info("indexes_completed")
    
    except (ClientError, ServiceUnavailable, SessionExpired, OSError) as exc:
        logger.exception("index_creation_failed", error=str(exc))
        raise
    finally:
        if client:
            await client.close()


async def verify_setup():
    """Verify constraints and indexes were created"""
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        
        async with client.session() as session:
            # List constraints
            result = await session.run("SHOW CONSTRAINTS")
            constraints = []
            async for record in result:
                constraints.append(record.values()[0])
            
            logger.info("constraints_verified", count=len(constraints))
            
            # List indexes
            result = await session.run("SHOW INDEXES")
            indexes = []
            async for record in result:
                indexes.append(record.values()[0])
            
            logger.info("indexes_verified", count=len(indexes))
            
    except (ClientError, ServiceUnavailable, SessionExpired, OSError) as exc:
        logger.exception("verification_failed", error=str(exc))
        raise
    finally:
        if client:
            await client.close()


async def main():
    """Main initialization function"""
    logger.info("neo4j_initialization_starting")
    
    try:
        await create_constraints()
        await create_indexes()
        await verify_setup()
        
        logger.info("neo4j_initialization_complete")
        print("\n✅ Neo4j constraints and indexes created successfully!")
        print("   Next step: Run 'python scripts/load_frameworks.py' to load framework data")
        
    except (ClientError, ServiceUnavailable, SessionExpired, OSError) as exc:
        logger.exception("initialization_failed", error=str(exc))
        print(f"\n❌ Initialization failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
