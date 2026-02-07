"""
FSMA 204 Demo Data Loader.

Loads sample supply chain data into Neo4j for demonstration purposes.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

import structlog

logger = structlog.get_logger("fsma-demo-loader")


# =============================================================================
# DEMO DATA
# =============================================================================

DEMO_FACILITIES = [
    {
        "gln": "1234567890128",
        "name": "Sunny Valley Farms",
        "address": "123 Farm Road, Salinas, CA 93901",
        "facility_type": "GROWER",
    },
    {
        "gln": "2345678901234",
        "name": "Fresh Cut Co",
        "address": "456 Processing Lane, Fresno, CA 93721",
        "facility_type": "PROCESSOR",
    },
    {
        "gln": "3456789012340",
        "name": "Metro Foods Distribution",
        "address": "789 Distribution Dr, Oakland, CA 94612",
        "facility_type": "DISTRIBUTOR",
    },
    {
        "gln": "4567890123456",
        "name": "Valley Wholesale",
        "address": "321 Wholesale Ave, Stockton, CA 95202",
        "facility_type": "DISTRIBUTOR",
    },
    {
        "gln": "5678901234562",
        "name": "SuperMart Store #42",
        "address": "100 Retail St, San Jose, CA 95110",
        "facility_type": "RETAILER",
    },
]

DEMO_LOTS = [
    {
        "tlc": "SV-20240115-001",
        "product_description": "Romaine Lettuce, Whole Heads",
        "quantity": 500,
        "unit_of_measure": "cases",
        "gtin": "10012345678902",
        "tenant_id": "demo-tenant",
    },
    {
        "tlc": "FC-20240116-A",
        "product_description": "Chopped Romaine Salad Mix",
        "quantity": 250,
        "unit_of_measure": "cases",
        "gtin": "10023456789013",
        "tenant_id": "demo-tenant",
    },
    {
        "tlc": "FC-20240116-B",
        "product_description": "Romaine Hearts, 3-pack",
        "quantity": 250,
        "unit_of_measure": "cases",
        "gtin": "10023456789020",
        "tenant_id": "demo-tenant",
    },
]

DEMO_EVENTS = [
    # Grower ships to processor
    {
        "event_id": "evt-001",
        "type": "SHIPPING",
        "lot_tlc": "SV-20240115-001",
        "from_gln": "1234567890128",
        "to_gln": "2345678901234",
        "event_date": "2024-01-15",
        "event_time": "14:00:00",
        "quantity": 500,
        "reference_doc": "BOL-SV-20240115-001",
        "confidence": 0.98,
    },
    # Processor receives
    {
        "event_id": "evt-002",
        "type": "RECEIVING",
        "lot_tlc": "SV-20240115-001",
        "at_gln": "2345678901234",
        "event_date": "2024-01-16",
        "event_time": "08:00:00",
        "quantity": 500,
        "reference_doc": "RCV-FC-20240116-001",
        "confidence": 0.97,
    },
    # Processor transforms into two products
    {
        "event_id": "evt-003",
        "type": "TRANSFORMATION",
        "input_lots": ["SV-20240115-001"],
        "output_lot": "FC-20240116-A",
        "at_gln": "2345678901234",
        "event_date": "2024-01-16",
        "event_time": "10:00:00",
        "input_quantity": 250,
        "output_quantity": 250,
        "reference_doc": "PROD-FC-20240116-001",
        "confidence": 0.95,
    },
    {
        "event_id": "evt-004",
        "type": "TRANSFORMATION",
        "input_lots": ["SV-20240115-001"],
        "output_lot": "FC-20240116-B",
        "at_gln": "2345678901234",
        "event_date": "2024-01-16",
        "event_time": "11:00:00",
        "input_quantity": 250,
        "output_quantity": 250,
        "reference_doc": "PROD-FC-20240116-002",
        "confidence": 0.95,
    },
    # Processor ships to distributors
    {
        "event_id": "evt-005",
        "type": "SHIPPING",
        "lot_tlc": "FC-20240116-A",
        "from_gln": "2345678901234",
        "to_gln": "3456789012340",
        "event_date": "2024-01-17",
        "event_time": "06:00:00",
        "quantity": 100,
        "reference_doc": "BOL-FC-20240117-001",
        "confidence": 0.96,
    },
    {
        "event_id": "evt-006",
        "type": "SHIPPING",
        "lot_tlc": "FC-20240116-B",
        "from_gln": "2345678901234",
        "to_gln": "4567890123456",
        "event_date": "2024-01-17",
        "event_time": "07:00:00",
        "quantity": 150,
        "reference_doc": "BOL-FC-20240117-002",
        "confidence": 0.96,
    },
    # Distributors receive
    {
        "event_id": "evt-007",
        "type": "RECEIVING",
        "lot_tlc": "FC-20240116-A",
        "at_gln": "3456789012340",
        "event_date": "2024-01-17",
        "event_time": "10:00:00",
        "quantity": 100,
        "reference_doc": "RCV-MF-20240117-001",
        "confidence": 0.94,
    },
    {
        "event_id": "evt-008",
        "type": "RECEIVING",
        "lot_tlc": "FC-20240116-B",
        "at_gln": "4567890123456",
        "event_date": "2024-01-17",
        "event_time": "11:00:00",
        "quantity": 150,
        "reference_doc": "RCV-VW-20240117-001",
        "confidence": 0.93,
    },
    # Distributor ships to retailer
    {
        "event_id": "evt-009",
        "type": "SHIPPING",
        "lot_tlc": "FC-20240116-A",
        "from_gln": "3456789012340",
        "to_gln": "5678901234562",
        "event_date": "2024-01-18",
        "event_time": "05:00:00",
        "quantity": 50,
        "reference_doc": "BOL-MF-20240118-001",
        "confidence": 0.95,
    },
    # Retailer receives
    {
        "event_id": "evt-010",
        "type": "RECEIVING",
        "lot_tlc": "FC-20240116-A",
        "at_gln": "5678901234562",
        "event_date": "2024-01-18",
        "event_time": "08:00:00",
        "quantity": 50,
        "reference_doc": "RCV-SM-20240118-001",
        "confidence": 0.92,
    },
]


# =============================================================================
# CYPHER GENERATION
# =============================================================================

def generate_facility_cypher(facility: Dict[str, Any]) -> str:
    """Generate Cypher to create/merge a facility node."""
    return f"""
MERGE (f:Facility {{gln: '{facility["gln"]}'}})
SET f.name = '{facility["name"]}',
    f.address = '{facility["address"]}',
    f.facility_type = '{facility["facility_type"]}',
    f.updated_at = datetime()
"""


def generate_lot_cypher(lot: Dict[str, Any]) -> str:
    """Generate Cypher to create/merge a lot node."""
    return f"""
MERGE (l:Lot {{tlc: '{lot["tlc"]}'}})
SET l.product_description = '{lot["product_description"]}',
    l.quantity = {lot["quantity"]},
    l.unit_of_measure = '{lot["unit_of_measure"]}',
    l.gtin = '{lot.get("gtin", "")}',
    l.tenant_id = '{lot.get("tenant_id", "default")}',
    l.updated_at = datetime()
"""


def generate_event_cypher(event: Dict[str, Any]) -> str:
    """Generate Cypher to create a trace event with relationships."""
    cypher_parts = []
    
    # Create event node
    cypher_parts.append(f"""
MERGE (e:TraceEvent {{event_id: '{event["event_id"]}'}})
SET e.type = '{event["type"]}',
    e.event_date = '{event["event_date"]}',
    e.event_time = '{event.get("event_time", "")}',
    e.quantity = {event.get("quantity", 0)},
    e.reference_doc = '{event.get("reference_doc", "")}',
    e.confidence = {event.get("confidence", 0.0)},
    e.tenant_id = 'demo-tenant',
    e.updated_at = datetime()
""")
    
    # Create relationships based on event type
    if event["type"] == "SHIPPING":
        cypher_parts.append(f"""
WITH e
MATCH (l:Lot {{tlc: '{event["lot_tlc"]}'}})
MERGE (l)-[:UNDERWENT]->(e)
WITH e
MATCH (from:Facility {{gln: '{event["from_gln"]}'}})
MERGE (from)-[:SHIPPED]->(e)
WITH e
MATCH (to:Facility {{gln: '{event["to_gln"]}'}})
MERGE (e)-[:SHIPPED_TO]->(to)
""")
    
    elif event["type"] == "RECEIVING":
        cypher_parts.append(f"""
WITH e
MATCH (l:Lot {{tlc: '{event["lot_tlc"]}'}})
MERGE (l)-[:UNDERWENT]->(e)
WITH e
MATCH (f:Facility {{gln: '{event["at_gln"]}'}})
MERGE (e)-[:OCCURRED_AT]->(f)
""")
    
    elif event["type"] == "TRANSFORMATION":
        # Link input lots
        for input_tlc in event.get("input_lots", []):
            cypher_parts.append(f"""
WITH e
MATCH (input:Lot {{tlc: '{input_tlc}'}})
MERGE (input)-[:CONSUMED]->(e)
""")
        
        # Link output lot
        cypher_parts.append(f"""
WITH e
MATCH (output:Lot {{tlc: '{event["output_lot"]}'}})
MERGE (e)-[:PRODUCED]->(output)
WITH e
MATCH (f:Facility {{gln: '{event["at_gln"]}'}})
MERGE (e)-[:OCCURRED_AT]->(f)
""")
    
    return "\n".join(cypher_parts)


def generate_full_demo_cypher() -> str:
    """Generate complete Cypher script for demo data."""
    lines = ["// FSMA 204 Demo Data", "// Generated by RegEngine", ""]
    
    lines.append("// Create Facilities")
    for facility in DEMO_FACILITIES:
        lines.append(generate_facility_cypher(facility))
    
    lines.append("\n// Create Lots")
    for lot in DEMO_LOTS:
        lines.append(generate_lot_cypher(lot))
    
    lines.append("\n// Create Events and Relationships")
    for event in DEMO_EVENTS:
        lines.append(generate_event_cypher(event))
    
    return "\n".join(lines)


# =============================================================================
# MAIN LOADER
# =============================================================================

def load_demo_data(neo4j_uri: str = None, username: str = "neo4j", password: str = None):
    """
    Load demo data into Neo4j.
    
    Args:
        neo4j_uri: Neo4j connection URI (default: from NEO4J_URI env)
        username: Neo4j username
        password: Neo4j password (default: from NEO4J_PASSWORD env)
    """
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("neo4j package not installed. Install with: pip install neo4j")
        print("\nAlternatively, copy the Cypher below into Neo4j Browser:\n")
        print(generate_full_demo_cypher())
        return
    
    uri = neo4j_uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    pwd = password or os.getenv("NEO4J_PASSWORD", "password")
    
    print(f"Connecting to Neo4j at {uri}...")
    
    driver = GraphDatabase.driver(uri, auth=(username, pwd))
    
    try:
        with driver.session() as session:
            # Create facilities
            print("Creating facilities...")
            for facility in DEMO_FACILITIES:
                session.run(generate_facility_cypher(facility))
            
            # Create lots
            print("Creating lots...")
            for lot in DEMO_LOTS:
                session.run(generate_lot_cypher(lot))
            
            # Create events
            print("Creating events and relationships...")
            for event in DEMO_EVENTS:
                session.run(generate_event_cypher(event))
            
            print("Demo data loaded successfully!")
            
            # Verify
            result = session.run("MATCH (n) RETURN labels(n) as type, count(*) as count")
            print("\nNode counts:")
            for record in result:
                print(f"  {record['type']}: {record['count']}")
                
    finally:
        driver.close()


def export_demo_json(output_path: str = None):
    """Export demo data as JSON for reference."""
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "facilities": DEMO_FACILITIES,
        "lots": DEMO_LOTS,
        "events": DEMO_EVENTS,
    }
    
    if output_path:
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Demo data exported to {output_path}")
    else:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Load FSMA 204 demo data")
    parser.add_argument("--uri", help="Neo4j URI (default: bolt://localhost:7687)")
    parser.add_argument("--password", help="Neo4j password")
    parser.add_argument("--export-json", help="Export demo data as JSON to this path")
    parser.add_argument("--export-cypher", action="store_true", help="Print Cypher statements")
    
    args = parser.parse_args()
    
    if args.export_cypher:
        print(generate_full_demo_cypher())
    elif args.export_json:
        export_demo_json(args.export_json)
    else:
        load_demo_data(neo4j_uri=args.uri, password=args.password)
