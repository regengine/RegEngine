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
    POSTGRES_URL       (default: postgresql://postgres:postgres@localhost:5433/regengine)
"""


import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone
from uuid import uuid4


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
