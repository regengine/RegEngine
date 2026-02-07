#!/usr/bin/env python3
"""
Apply Neo4j database constraints for RegEngine.

This script reads the Cypher constraint definitions from init_constraints.cypher
and applies them to the Neo4j database.

Usage:
    python apply_constraints.py

Environment variables:
    NEO4J_URI: Neo4j connection URI (default: bolt://localhost:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (required)
    NEO4J_CONSTRAINTS_FILE: Cypher file to apply (optional)
"""

import os
import sys
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    print("Error: neo4j package not found. Install with: pip install neo4j")
    sys.exit(1)


def apply_constraints():
    """Apply constraints from the Cypher file to Neo4j."""
    # Get Neo4j connection details
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    
    if not password:
        print("Error: NEO4J_PASSWORD environment variable is required")
        sys.exit(1)
    
    # Read constraints file
    script_dir = Path(__file__).parent
    constraints_file_name = os.getenv("NEO4J_CONSTRAINTS_FILE", "init_constraints.cypher")
    constraints_file = script_dir / constraints_file_name
    
    if not constraints_file.exists():
        print(f"Error: Constraints file not found: {constraints_file}")
        sys.exit(1)
    
    with open(constraints_file, 'r') as f:
        cypher_content = f.read()
    
    # Split into individual statements (by semicolon)
    statements = [s.strip() for s in cypher_content.split(';') if s.strip()]
    
    # Filter out comments and empty lines
    statements = [
        s for s in statements 
        if s and not s.startswith('//') and 'CREATE CONSTRAINT' in s
    ]
    
    print(f"Connecting to Neo4j at {uri}...")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            for i, statement in enumerate(statements, 1):
                print(f"\nApplying constraint {i}/{len(statements)}...")
                print(f"Statement: {statement[:80]}...")
                
                try:
                    result = session.run(statement + ";")
                    result.consume()
                    print("✓ Constraint applied successfully")
                except Exception as e:
                    # Check if it's just a "constraint already exists" error
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "equivalent constraint" in error_msg:
                        print("✓ Constraint already exists (skipped)")
                    else:
                        print(f"✗ Error applying constraint: {e}")
                        raise
        
        print("\n" + "="*60)
        print("All constraints applied successfully!")
        print("="*60)
        
    finally:
        driver.close()


if __name__ == "__main__":
    apply_constraints()
