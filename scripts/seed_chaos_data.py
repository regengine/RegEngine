"""
RegEngine Chaos Test Data Seeder
================================
Seeds known quantities of test data into Neo4j and PostgreSQL
before chaos engineering tests run. This ensures data integrity
checks are meaningful (not just 0 -> 0).


Usage:
    python seed_chaos_data.py                  # Seed all stores
    python seed_chaos_data.py --neo4j-only     # Seed Neo4j only
    python seed_chaos_data.py --postgres-only  # Seed Postgres only
    python seed_chaos_data.py --cleanup        # Remove seeded data


Environment variables:
    NEO4J_URI          (default: bolt://localhost:7687)
    NEO4J_USER         (default: neo4j)
    NEO4J_PASSWORD     (default: neo4j)
    POSTGRES_URL       (default: postgresql://regengine:regengine@localhost:5433/regengine_admin)
"""


import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text
from neo4j import GraphDatabase

# APScheduler imports for persistent job seeding
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("chaos-seeder")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://regengine:regengine@localhost:5433/regengine_admin")


# Seed tag so we can identify and clean up test data
CHAOS_SEED_TAG = "chaos_test_seed"


# How much data to seed
NEO4J_REGULATION_COUNT = 25
NEO4J_SECTION_COUNT = 50      # 2 sections per regulation
NEO4J_REQUIREMENT_COUNT = 100  # 2 requirements per section
POSTGRES_API_KEY_COUNT = 10
POSTGRES_SCHEDULER_JOB_COUNT = 15




# ---------------------------------------------------------------------------
# Neo4j Seeder
# ---------------------------------------------------------------------------
def seed_neo4j():
    """Seed Neo4j with a realistic regulatory graph structure."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        logger.error("❌ neo4j package not installed. Run: pip install neo4j")
        return False


    logger.info(f"🔌 Connecting to Neo4j at {NEO4J_URI}")
    
    # Retry logic for Neo4j connection
    import time
    max_retries = 30
    for attempt in range(max_retries):
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            driver.verify_connectivity()
            logger.info("✅ Neo4j connection verified")
            break
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"⚠️ Neo4j connection failed (attempt {attempt+1}/{max_retries}): {e}. Retrying in 2s...")
                time.sleep(2)
            else:
                logger.error(f"❌ Neo4j connection failed after {max_retries} attempts: {e}")
                return False

    with driver.session() as session:
        # Clean up any previous seed data first
        session.run(
            "MATCH (n {_chaos_seed: $tag}) DETACH DELETE n",
            tag=CHAOS_SEED_TAG
        )
        logger.info("🧹 Cleaned up previous seed data")

        # Create Regulation nodes
        regulations = []
        for i in range(NEO4J_REGULATION_COUNT):
            reg_id = f"REG-CHAOS-{i:04d}"
            regulations.append(reg_id)
            session.run(
                """
                CREATE (r:Regulation {
                    id: $id,
                    title: $title,
                    agency: $agency,
                    effective_date: $effective_date,
                    status: 'active',
                    _chaos_seed: $tag
                })
                """,
                id=reg_id,
                title=f"Test Regulation {i} - FSMA 204 Subsection",
                agency="FDA",
                effective_date="2026-01-01",
                tag=CHAOS_SEED_TAG,
            )

        logger.info(f"  📄 Created {NEO4J_REGULATION_COUNT} Regulation nodes")

        # Create Section nodes linked to Regulations
        sections = []
        for i in range(NEO4J_SECTION_COUNT):
            sec_id = f"SEC-CHAOS-{i:04d}"
            reg_id = regulations[i % NEO4J_REGULATION_COUNT]
            sections.append(sec_id)
            session.run(
                """
                MATCH (r:Regulation {id: $reg_id})
                CREATE (s:Section {
                    id: $sec_id,
                    title: $title,
                    section_number: $section_number,
                    _chaos_seed: $tag
                })
                CREATE (r)-[:HAS_SECTION]->(s)
                """,
                reg_id=reg_id,
                sec_id=sec_id,
                title=f"Section {i} - Traceability Requirements",
                section_number=f"{(i % 10) + 1}.{i}",
                tag=CHAOS_SEED_TAG,
            )

        logger.info(f"  📑 Created {NEO4J_SECTION_COUNT} Section nodes with HAS_SECTION relationships")

        # Create Requirement nodes linked to Sections
        for i in range(NEO4J_REQUIREMENT_COUNT):
            req_id = f"REQ-CHAOS-{i:04d}"
            sec_id = sections[i % NEO4J_SECTION_COUNT]
            session.run(
                """
                MATCH (s:Section {id: $sec_id})
                CREATE (req:Requirement {
                    id: $req_id,
                    text: $text,
                    severity: $severity,
                    _chaos_seed: $tag
                })
                CREATE (s)-[:HAS_REQUIREMENT]->(req)
                """,
                sec_id=sec_id,
                req_id=req_id,
                text=f"Requirement {i}: Maintain records of KDEs for CTEs in the food supply chain",
                severity=["critical", "major", "minor"][i % 3],
                tag=CHAOS_SEED_TAG,
            )

        logger.info(f"  ✅ Created {NEO4J_REQUIREMENT_COUNT} Requirement nodes with HAS_REQUIREMENT relationships")

        # Verify counts
        result = session.run(
            "MATCH (n {_chaos_seed: $tag}) RETURN count(n) AS node_count",
            tag=CHAOS_SEED_TAG
        ).single()
        total_nodes = result["node_count"]

        result = session.run(
            """
            MATCH (a {_chaos_seed: $tag})-[r]->(b {_chaos_seed: $tag})
            RETURN count(r) AS rel_count
            """,
            tag=CHAOS_SEED_TAG
        ).single()
        total_rels = result["rel_count"]

        logger.info(f"  📊 Neo4j totals: {total_nodes} nodes, {total_rels} relationships")

    driver.close()

    # Write manifest for the chaos test to reference
    manifest = {
        "neo4j_nodes": total_nodes,
        "neo4j_relationships": total_rels,
        "neo4j_regulations": NEO4J_REGULATION_COUNT,
        "neo4j_sections": NEO4J_SECTION_COUNT,
        "neo4j_requirements": NEO4J_REQUIREMENT_COUNT,
    }
    return manifest


# ---------------------------------------------------------------------------
# PostgreSQL Seeder
# ---------------------------------------------------------------------------
def seed_scheduler_jobs():
    """Seed persistent scheduler jobs using APScheduler."""
    logger.info("  📅 Seeding persistent scheduler jobs...")
    
    try:
        # Create a temporary scheduler to insert jobs into the DB
        jobstores = {
            'default': SQLAlchemyJobStore(url=POSTGRES_URL)
        }
        scheduler = BackgroundScheduler(jobstores=jobstores)
        # We don't need to start it to add jobs, but adding a jobstore requires it?
        # Actually add_jobstore works on running or stopped scheduler.
        # But allow tables to be created if not exist.
        
        # We start it in paused mode to avoid running jobs here
        scheduler.start(paused=True)

        for i in range(POSTGRES_SCHEDULER_JOB_COUNT):
            job_id = f"chaos-job-{i:04d}"
            # Use 'print' as it is safe and available everywhere
            scheduler.add_job(
                print,
                args=[f"Chaos Job {i} execution"],
                trigger=IntervalTrigger(minutes=60),
                id=job_id,
                name=f"Chaos Job {i}",
                replace_existing=True,
                coalesce=True
            )
            
        scheduler.shutdown()
        logger.info(f"  📅 Created {POSTGRES_SCHEDULER_JOB_COUNT} persistent scheduler jobs")
        
        return {"postgres_scheduler_jobs": POSTGRES_SCHEDULER_JOB_COUNT}
        
    except Exception as e:
        logger.error(f"  ❌ Failed to seed scheduler jobs: {e}")
        return None

def seed_postgres():
    """Seed PostgreSQL with API keys and Scheduler Jobs."""
    logger.info("🔌 Connecting to PostgreSQL")
    
    # Retry logic for PostgreSQL connection
    import time
    max_retries = 30
    engine = None
    
    for attempt in range(max_retries):
        try:
            engine = create_engine(POSTGRES_URL)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ PostgreSQL connection verified")
            break
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"⚠️ PostgreSQL connection failed (attempt {attempt+1}/{max_retries}): {e}. Retrying in 2s...")
                time.sleep(2)
            else:
                logger.error(f"❌ PostgreSQL connection failed after {max_retries} attempts: {e}")
                return False

    # 1. Seed API Keys (Raw SQL)
    api_manifest = {}
    try:
        with engine.connect() as conn:
            # Clean up API keys
            conn.execute(text(
                "DELETE FROM api_keys WHERE name LIKE 'Chaos Test Key %'"
            ))
            conn.commit()
            logger.info("🧹 Cleaned up previous API key seed data")
            
            # Seed API keys
            for i in range(POSTGRES_API_KEY_COUNT):
                 conn.execute(
                    text("""
                        INSERT INTO api_keys (id, tenant_id, key_hash, name, enabled, created_at)
                        VALUES (:id, :tenant_id, :key_hash, :name, true, :created_at)
                        ON CONFLICT (id) DO NOTHING
                    """),
                    {
                        "id": str(uuid4()),
                        "tenant_id": str(uuid4()),
                        "key_hash": f"hash_{i}",  # In real app this would be hashed
                        "name": f"Chaos Test Key {i:04d}",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            conn.commit()
            
            # Count API keys
            api_count = conn.execute(
                text("SELECT count(*) FROM api_keys WHERE name LIKE 'Chaos Test Key %'")
            ).scalar()
            api_manifest["postgres_api_keys"] = api_count
            logger.info(f"  🔑 Created {api_count} API keys")
            
        
    except Exception as e:
        logger.error(f"  ❌ Failed to seed API keys: {e}")
        return None

    # 2. Seed Scheduler Jobs (APScheduler)
    job_manifest = seed_scheduler_jobs()
    
    if job_manifest:
        api_manifest.update(job_manifest)

    engine.dispose()
    
    # Verify Total State
    # (Optional: check DB for jobs table)
    
    return api_manifest


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def cleanup_all():
    """Remove all chaos seed data from both stores."""
    logger.info("🧹 Cleaning up all chaos seed data...")

    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            result = session.run(
                "MATCH (n {_chaos_seed: $tag}) DETACH DELETE n RETURN count(n) AS deleted",
                tag=CHAOS_SEED_TAG
            ).single()
            logger.info(f"  Neo4j: deleted {result['deleted']} nodes")
        driver.close()
    except Exception as e:
        logger.warning(f"  Neo4j cleanup skipped: {e}")

    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(POSTGRES_URL)
        with engine.connect() as conn:
            r1 = conn.execute(text(
                "DELETE FROM api_keys WHERE name LIKE 'Chaos Test Key %'"
            ))
            # Cleanup persistent jobs
            # Table name is 'apscheduler_jobs' by default for SQLAlchemyJobStore
            try:
                r2 = conn.execute(text(
                    "DELETE FROM apscheduler_jobs WHERE id LIKE 'chaos-job-%'"
                ))
                jobs_deleted = r2.rowcount
            except Exception:
                jobs_deleted = 0 # Table might not exist if seeding failed
                
            conn.commit()
            logger.info(f"  PostgreSQL: deleted {r1.rowcount} API keys, {jobs_deleted} scheduler jobs")
        engine.dispose()
    except Exception as e:
        logger.warning(f"  PostgreSQL cleanup skipped: {e}")

    logger.info("✅ Cleanup complete")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Seed test data for chaos engineering tests")
    parser.add_argument("--neo4j-only", action="store_true", help="Seed Neo4j only")
    parser.add_argument("--postgres-only", action="store_true", help="Seed PostgreSQL only")
    parser.add_argument("--cleanup", action="store_true", help="Remove all seed data")
    parser.add_argument("--manifest", type=str, default="chaos_seed_manifest.json",
                        help="Path to write seed manifest (default: chaos_seed_manifest.json)")
    args = parser.parse_args()

    if args.cleanup:
        cleanup_all()
        return

    logger.info("🌱 Starting chaos test data seeding...")
    manifest = {"seeded_at": datetime.now(timezone.utc).isoformat(), "tag": CHAOS_SEED_TAG}

    seed_neo = not args.postgres_only
    seed_pg = not args.neo4j_only

    if seed_neo:
        neo4j_manifest = seed_neo4j()
        if neo4j_manifest:
            manifest.update(neo4j_manifest)
        else:
            logger.error("❌ Neo4j seeding failed")
            sys.exit(1)

    if seed_pg:
        pg_manifest = seed_postgres()
        if pg_manifest:
            manifest.update(pg_manifest)
        else:
            logger.error("❌ PostgreSQL seeding failed")
            sys.exit(1)

    # Write manifest file for the chaos test runner to consume
    with open(args.manifest, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"📋 Seed manifest written to {args.manifest}")
    logger.info(f"📊 Manifest: {json.dumps(manifest, indent=2)}")
    logger.info("✅ Seeding complete — ready for chaos!")


if __name__ == "__main__":
    main()
