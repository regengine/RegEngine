# Graph Service

Graph analytics service using Neo4j for relationship mapping, opportunity detection, and compliance arbitrage analysis.

## Overview

The Graph service provides graph-based analytics for the RegEngine platform, enabling:
- **Regulatory arbitrage detection** across compliance frameworks
- **Compliance gap analysis** using graph traversal
- **Framework relationship mapping** (SOC2, ISO27001, HIPAA, etc.)
- **Control overlap visualization** for certification efficiency

### Key Features

- Neo4j graph database integration
- Cypher query optimization
- Real-time opportunity scoring
- Multi-framework traversal
- Cached relationship graphs

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   FastAPI    │────▶│    Neo4j     │────▶│    Redis     │
│  Graph API   │     │  Graph DB    │     │    Cache     │
└──────────────┘     └──────────────┘     └──────────────┘
       │
       ▼
┌──────────────┐
│  PostgreSQL  │
│ Audit Trails │
└──────────────┘
```

## API Endpoints

### Find Arbitrage Opportunities

```http
GET /graph/arbitrage?framework_from=SOC2&framework_to=ISO27001
Authorization: Bearer <token>
```

**Response:**
```json
{
  "opportunities": [
    {
      "id": "arb-123",
      "from_framework": "SOC2",
      "to_framework": "ISO27001",
      "overlap_controls": 45,
      "total_controls": 114,
      "overlap_percentage": 39.5,
      "estimated_savings_hours": 180,
      "path": [
        {"control": "SOC2-CC6.1", "maps_to": "ISO-A.9.2.1"},
        {"control": "SOC2-CC6.2", "maps_to": "ISO-A.9.2.2"}
      ]
    }
  ]
}
```

### Compliance Gap Analysis

```http
GET /graph/gaps?current_framework=SOC2&target_framework=HIPAA
Authorization: Bearer <token>
```

**Response:**
```json
{
  "gaps": [
    {
      "control_id": "HIPAA-164.308",
      "control_name": "Administrative Safeguards",
      "missing_in": "SOC2",
      "remediation_effort": "medium",
      "priority": "high"
    }
  ],
  "coverage_percentage": 67.3,
  "total_gaps": 12
}
```

### Framework Relationships

```http
GET /graph/frameworks/<framework_id>/relationships
Authorization: Bearer <token>
```

**Response:**
```json
{
  "framework": "SOC2",
  "related_frameworks": [
    {
      "framework_id": "ISO27001",
      "relationship_type": "maps_to",
      "strength": 0.85,
      "control_overlap": 45
    },
    {
      "framework_id": "NIST_CSF",
      "relationship_type": "aligns_with",
      "strength": 0.72,
      "control_overlap": 38
    }
  ]
}
```

### FSMA Traceability Event Search

```http
GET /api/v1/fsma/traceability/search/events?start_date=2026-02-01&end_date=2026-03-01&product_contains=lettuce&facility_contains=Supplier%20X&cte_type=RECEIVING&limit=100
X-RegEngine-API-Key: <api-key>
```

**Response:**
```json
{
  "count": 2,
  "events": [
    {"event_id": "evt-1", "type": "RECEIVING"},
    {"event_id": "evt-2", "type": "RECEIVING"}
  ],
  "has_more": false,
  "next_cursor": null,
  "filters": {
    "start_date": "2026-02-01",
    "end_date": "2026-03-01",
    "product_contains": "lettuce",
    "facility_contains": "Supplier X",
    "cte_type": "RECEIVING"
  }
}
```

## Cypher Queries

### Find Shortest Path Between Frameworks

```cypher
MATCH path = shortestPath(
  (f1:Framework {name: 'SOC2'})-[*]-(f2:Framework {name: 'ISO27001'})
)
RETURN path, length(path) as distance
```

### Calculate Overlap Score

```cypher
MATCH (f1:Framework {name: $framework1})-[:HAS_CONTROL]->(c1:Control)
MATCH (f2:Framework {name: $framework2})-[:HAS_CONTROL]->(c2:Control)
WHERE c1.requirement = c2.requirement
RETURN count(c1) as overlap_count
```

### Find High-Value Arbitrage

```cypher
MATCH (f1:Framework)-[:MAPS_TO]->(f2:Framework)
WITH f1, f2, count(*) as overlap
WHERE overlap > 30
RETURN f1.name, f2.name, overlap,
       overlap * 4.0 as estimated_hours_saved
ORDER BY overlap DESC
LIMIT 10
```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `NEO4J_URI` | Neo4j connection URI | `bolt://localhost:7687` | ✅ |
| `NEO4J_USER` | Neo4j username | `neo4j` | ✅ |
| `NEO4J_PASSWORD` | Neo4j password | - | ✅ (prod) |
| `REDIS_URL` | Redis cache | `redis://localhost:6379/2` | ✅ |
| `CACHE_TTL` | Cache expiration (seconds) | `3600` | ❌ |
| `MAX_PATH_DEPTH` | Max graph traversal depth | `5` | ❌ |

## Local Development

### Prerequisites

- Python 3.9+
- Neo4j 4.4+ (or 5.x)
- Redis 6+

### Setup

```bash
cd services/graph

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your Neo4j credentials

# Start Neo4j (Docker)
docker run -d \
  --name neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5.0

# Load framework data
python scripts/load_frameworks.py

# Start development server
uvicorn app.main:app --reload --port 8003
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app tests/ --cov-report=html

# Integration tests only
pytest tests/integration/ -v
```

## Docker Deployment

```yaml
graph-api:
  build: ./services/graph
  ports:
    - "8003:8000"
  environment:
    - NEO4J_URI=bolt://neo4j:7687
    - NEO4J_USER=neo4j
    - NEO4J_PASSWORD=${NEO4J_PASSWORD}
    - REDIS_URL=redis://redis:6379/2
  depends_on:
    - neo4j
    - redis
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3

neo4j:
  image: neo4j:5.0
  ports:
    - "7474:7474"  # HTTP
    - "7687:7687"  # Bolt
  environment:
    - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
  volumes:
    - neo4j_data:/data
```

## Health Check

```bash
curl http://localhost:8200/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "graph-api",
  "version": "1.0.0",
  "neo4j_connected": true,
  "redis_connected": true
}
```

## Performance Optimization

### Query Optimization

**Index Creation:**
```cypher
CREATE INDEX framework_name IF NOT EXISTS
FOR (f:Framework) ON (f.name);

CREATE INDEX control_id IF NOT EXISTS  
FOR (c:Control) ON (c.control_id);

CREATE CONSTRAINT framework_id IF NOT EXISTS
FOR (f:Framework) REQUIRE f.id IS UNIQUE;
```

**Query Caching:**
- Redis caching for frequently accessed patterns
- TTL: 1 hour for framework relationships
- Cache invalidation on data updates

### Connection Pooling

```python
# app/neo4j_client.py
driver = GraphDatabase.driver(
    neo4j_uri,
    auth=(neo4j_user, neo4j_password),
    max_connection_lifetime=3600,
    max_connection_pool_size=50,
    connection_acquisition_timeout=60
)
```

## Data Model

### Node Types

**Framework:**
```cypher
(:Framework {
  id: string,
  name: string,
  version: string,
  category: string,
  last_updated: datetime
})
```

**Control:**
```cypher
(:Control {
  control_id: string,
  requirement: string,
  description: text,
  effort_hours: float
})
```

### Relationship Types

- `HAS_CONTROL` - Framework to Control
- `MAPS_TO` - Framework to Framework
- `DEPENDS_ON` - Control to Control
- `SATISFIES` - Control to Requirement

## Common Operations

### Add New Framework

```python
# scripts/add_framework.py
from app.graph_client import create_framework

create_framework(
    name="CMMC 2.0",
    version="2.0",
    controls=[
        {"id": "AC.1.001", "requirement": "Access Control"},
        # ...
    ]
)
```

### Update Mappings

```cypher
MATCH (c1:Control {control_id: 'SOC2-CC6.1'})
MATCH (c2:Control {control_id: 'ISO-A.9.2.1'})
MERGE (c1)-[r:MAPS_TO]->(c2)
SET r.confidence = 0.95
```

### Calculate Savings

```python
# app/analytics.py
def calculate_arbitrage_value(from_framework, to_framework):
    overlap = get_control_overlap(from_framework, to_framework)
    avg_hours_per_control = 4.0
    return overlap * avg_hours_per_control
```

## Troubleshooting

### Neo4j Connection Issues

```bash
# Check Neo4j status
docker logs neo4j

# Test connection
cypher-shell -u neo4j -p password
```

### Slow Queries

```cypher
# View query execution plan
EXPLAIN MATCH (f:Framework)-[:HAS_CONTROL]->(c:Control)
WHERE f.name = 'SOC2'
RETURN c

# Profile actual execution
PROFILE MATCH (f:Framework)-[:HAS_CONTROL]->(c:Control)
WHERE f.name = 'SOC2'
RETURN c
```

### Cache Invalidation

```bash
# Clear Redis cache for graph service
redis-cli -n 2 FLUSHDB
```

## Related Documentation

- [Compliance Service](../compliance/README.md) - Framework definitions
- [Neo4j Best Practices](../../docs/neo4j-best-practices.md)

## License

Proprietary - RegEngine Platform  
Copyright © 2026 RegEngine Inc.
