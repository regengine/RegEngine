# Opportunity Service

Regulatory arbitrage detection and compliance cost savings discovery using Neo4j graph analytics.

## Overview

The Opportunity service analyzes regulatory requirements across frameworks to identify potential cost savings, redundant controls, and opportunities for compliance optimization. It uses Neo4j graph database to model complex relationships between regulations, controls, and organizational capabilities.

### Key Features

- **Graph-Based Analysis:** Neo4j for relationship mapping
- **Multi-Framework Support:** Cross-regulation opportunity detection
- **Cost Savings Calculator:** ROI estimation for compliance improvements
- **Redundancy Detection:** Identify overlapping controls
- **Gap Analysis:** Find missing controls across frameworks
- **Real-Time Queries:** Sub-second graph traversal

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   FastAPI    │────▶│    Neo4j     │────▶│   Cypher     │
│   Query API  │     │  Graph DB    │     │   Queries    │
└──────────────┘     └──────────────┘     └──────────────┘
       │
       ▼
┌──────────────┐
│  PostgreSQL  │
│  Audit Trail │
└──────────────┘
```

### Graph Schema

```
(Regulation)-[:REQUIRES]->(Control)
(Control)-[:MAPS_TO]->(Framework)
(Organization)-[:IMPLEMENTS]->(Control)
(Control)-[:OVERLAPS_WITH]->(Control)
(Opportunity)-[:SAVES]->(Cost)
```

## API Endpoints

### Find Savings Opportunities

```http
POST /opportunity/find
Content-Type: application/json
Authorization: Bearer <jwt_token>

{
  "tenant_id": "uuid",
  "frameworks": ["SOC2", "HIPAA", "GDPR"],
  "current_controls": ["MFA", "encryption_at_rest", "access_logs"],
  "target_frameworks": ["ISO27001"]
}
```

**Response:**
```json
{
  "opportunities": [
    {
      "id": "opp-001",
      "type": "control_reuse",
      "title": "Reuse MFA for ISO 27001 A.9.4.2",
      "description": "Your existing MFA implementation satisfies ISO 27001 access control requirements",
      "estimated_savings": {
        "amount": 15000,
        "currency": "USD",
        "period": "annual"
      },
      "effort": "low",
      "frameworks_affected": ["ISO27001"],
      "controls_reused": ["MFA"],
      "confidence": 0.92
    },
    {
      "id": "opp-002",
      "type": "redundancy_elimination",
      "title": "Consolidate Duplicate Encryption Audits",
      "description": "HIPAA and SOC2 require identical encryption audits - consolidate to single annual review",
      "estimated_savings": {
        "amount": 8000,
        "currency": "USD",
        "period": "annual"
      },
      "effort": "medium",
      "frameworks_affected": ["HIPAA", "SOC2"],
      "confidence": 0.85
    }
  ],
  "total_savings": {
    "amount": 23000,
    "currency": "USD",
    "period": "annual"
  },
  "summary": {
    "total_opportunities": 2,
    "high_confidence": 1,
    "medium_confidence": 1,
    "low_confidence": 0
  }
}
```

### Analyze Control Gaps

```http
POST /opportunity/gaps
Content-Type: application/json
Authorization: Bearer <jwt_token>

{
  "tenant_id": "uuid",
  "target_framework": "ISO27001",
  "current_controls": ["MFA", "encryption_at_rest"]
}
```

**Response:**
```json
{
  "gaps": [
    {
      "control_id": "A.12.6.1",
      "name": "Management of technical vulnerabilities",
      "description": "Establish vulnerability scanning and patch management",
      "priority": "high",
      "estimated_cost": {
        "implementation": 25000,
        "annual_maintenance": 12000
      },
      "recommended_solutions": [
        {
          "name": "Automated Vulnerability Scanning",
          "vendor": "Tenable",
          "cost": 15000
        }
      ]
    }
  ],
  "summary": {
    "total_gaps": 1,
    "high_priority": 1,
    "total_estimated_cost": 37000
  }
}
```

### Get Compliance Roadmap

```http
GET /opportunity/roadmap?tenant_id=<uuid>&target_framework=ISO27001
Authorization: Bearer <jwt_token>
```

**Response:**
```json
{
  "roadmap": [
    {
      "phase": 1,
      "duration_weeks": 4,
      "items": [
        {
          "control": "A.9.4.2",
          "action": "Document existing MFA implementation",
          "effort": "low",
          "cost": 2000
        }
      ]
    },
    {
      "phase": 2,
      "duration_weeks": 8,
      "items": [
        {
          "control": "A.12.6.1",
          "action": "Implement vulnerability scanning",
          "effort": "high",
          "cost": 25000
        }
      ]
    }
  ],
  "total_duration_weeks": 12,
  "total_cost": 27000
}
```

### Query Relationships

```http
POST /opportunity/query
Content-Type: application/json
Authorization: Bearer <jwt_token>

{
  "cypher": "MATCH (r:Regulation)-[:REQUIRES]->(c:Control) WHERE r.framework = $framework RETURN c",
  "parameters": {
    "framework": "SOC2"
  }
}
```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `NEO4J_URI` | Neo4j bolt connection | `bolt://localhost:7687` | ✅ |
| `NEO4J_USER` | Neo4j username | `neo4j` | ✅ |
| `NEO4J_PASSWORD` | Neo4j password | - | ✅ |
| `DATABASE_URL` | PostgreSQL for audit trail | - | ✅ |
| `JWT_SECRET` | JWT validation secret | `dev-secret` | ✅ (prod) |
| `ALLOWED_ORIGINS` | CORS origins | `*` | ⚠️ (prod) |
| `CACHE_TTL_SECONDS` | Query cache duration | `300` | ❌ |

## Local Development

### Prerequisites

- Python 3.9+
- Neo4j 5.0+
- PostgreSQL 14+
- Docker (recommended)

### Setup

```bash
cd services/opportunity

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt  # For testing

# Start Neo4j (Docker)
docker run \
    --name neo4j \
    -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH=neo4j/password \
    -e NEO4J_PLUGINS='["apoc"]' \
    neo4j:5.0

# Set environment variables
cp .env.example .env
# Edit .env with your configuration

# Seed graph database
python scripts/seed_graph.py

# Start development server
uvicorn app.main:app --reload --port 8008
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app tests/ --cov-report=html

# View coverage
open htmlcov/index.html  # macOS
```

### Access Neo4j Browser

Open http://localhost:7474 and connect with credentials from .env

## Docker Deployment

### docker-compose.yml

```yaml
opportunity-api:
  build: ./services/opportunity
  ports:
    - "8008:8000"
  environment:
    - NEO4J_URI=bolt://neo4j:7687
    - NEO4J_USER=neo4j
    - NEO4J_PASSWORD=${NEO4J_PASSWORD}
    - DATABASE_URL=postgresql://admin:${DB_PASSWORD}@postgres:5432/regengine_admin
    - JWT_SECRET=${JWT_SECRET}
  depends_on:
    - postgres
    - neo4j
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3

neo4j:
  image: neo4j:5.0
  ports:
    - "7474:7474"  # Browser
    - "7687:7687"  # Bolt
  environment:
    - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
    - NEO4J_PLUGINS=["apoc"]
    - NEO4J_dbms_security_procedures_unrestricted=apoc.*
  volumes:
    - neo4j_data:/data
```

### Start Services

```bash
# Development
docker-compose up opportunity-api

# Production
docker-compose -f docker-compose.prod.yml up -d opportunity-api
```

## Health Check

```bash
curl http://localhost:8008/health
```

**Healthy Response:**
```json
{
  "status": "healthy",
  "service": "opportunity-api",
  "version": "1.0.0",
  "timestamp": "2026-01-27T18:30:00Z",
  "dependencies": {
    "neo4j": "connected",
    "postgresql": "connected"
  },
  "graph_stats": {
    "total_nodes": 1543,
    "total_relationships": 4821,
    "frameworks": 8
  }
}
```

**Unhealthy Response (503):**
```json
{
  "status": "unhealthy",
  "service": "opportunity-api",
  "error": "Neo4j connection failed",
  "timestamp": "2026-01-27T18:30:00Z"
}
```

## Graph Data Model

### Node Types

| Label | Properties | Description |
|-------|------------|-------------|
| `Regulation` | `id`, `name`, `framework`, `version` | Regulatory requirement |
| `Control` | `id`, `name`, `description`, `category` | Security/compliance control |
| `Framework` | `id`, `name`, `standard_body` | Compliance framework (SOC2, ISO, etc.) |
| `Organization` | `id`, `name`, `tenant_id` | Customer organization |
| `Opportunity` | `id`, `type`, `savings`, `confidence` | Identified cost savings |

### Relationship Types

| Type | From | To | Properties |
|------|------|-----|-----------|
| `REQUIRES` | Regulation | Control | `mandatory`, `priority` |
| `IMPLEMENTS` | Organization | Control | `status`, `last_audit` |
| `MAPS_TO` | Control | Framework | `mapping_confidence` |
| `OVERLAPS_WITH` | Control | Control | `overlap_percentage` |
| `SAVES` | Opportunity | Organization | `amount`, `currency` |

## Example Cypher Queries

### Find Redundant Controls

```cypher
MATCH (c1:Control)<-[:REQUIRES]-(r1:Regulation),
      (c2:Control)<-[:REQUIRES]-(r2:Regulation)
WHERE id(c1) < id(c2)
  AND c1.description = c2.description
  AND r1.framework <> r2.framework
RETURN c1.name AS control,
       r1.framework AS framework1,
       r2.framework AS framework2,
       c1.estimated_annual_cost AS cost
ORDER BY c1.estimated_annual_cost DESC
```

### Calculate Coverage

```cypher
MATCH (org:Organization {tenant_id: $tenantId})
MATCH (ctrl:Control)<-[:REQUIRES]-(reg:Regulation {framework: $framework})
OPTIONAL MATCH (org)-[impl:IMPLEMENTS]->(ctrl)
WITH org, COUNT(ctrl) AS total, COUNT(impl) AS implemented
RETURN org.name AS organization,
       total AS required_controls,
       implemented AS implemented_controls,
       toFloat(implemented) / total AS coverage_percentage
```

### Find Cheapest Path to Compliance

```cypher
MATCH path = shortestPath(
  (org:Organization {tenant_id: $tenantId})-[:IMPLEMENTS*]->(target:Framework {name: $targetFramework})
)
WITH path, reduce(cost = 0, rel IN relationships(path) | cost + coalesce(rel.implementation_cost, 5000)) AS total_cost
RETURN path, total_cost
ORDER BY total_cost ASC
LIMIT 1
```

## Opportunity Types

| Type | Description | Typical Savings |
|------|-------------|-----------------|
| `control_reuse` | Existing control satisfies new requirement | 50-100% of implementation |
| `redundancy_elimination` | Remove duplicate controls | 30-70% of annual cost |
| `framework_consolidation` | Merge similar frameworks | 20-40% of total cost |
| `automation` | Replace manual processes | 60-80% of labor cost |
| `policy_alignment` | Standardize documentation | 10-30% of audit cost |

## Performance Optimization

### Query Optimization

```python
# ✅ Use indexes
CREATE INDEX control_name FOR (c:Control) ON (c.name)
CREATE INDEX framework_id FOR (f:Framework) ON (f.id)

# ✅ Limit result sets
MATCH (c:Control) RETURN c LIMIT 100

# ❌ Avoid unbounded traversals
MATCH (n)-[*]->(m) RETURN n, m  # Bad!
```

### Caching Strategy

- Query results cached for 5 minutes (configurable)
- Invalidate on graph updates
- Use Redis for distributed caching

### Connection Pooling

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD),
    max_connection_lifetime=3600,
    max_connection_pool_size=50,
    connection_acquisition_timeout=60
)
```

## Monitoring

### Prometheus Metrics

Available at `/metrics`:

- `regengine_opportunity_queries_total` - Total queries executed
- `regengine_opportunity_query_duration_seconds` - Query time histogram
- `regengine_opportunity_graph_size_nodes` - Total nodes in graph
- `regengine_opportunity_savings_identified_total` - Total savings found

### Recommended Alerts

- Query time > 5 seconds (p95)
- Neo4j connection failure
- Graph size > 100K nodes (capacity planning)
- Error rate > 5%

## Troubleshooting

### Neo4j Connection Issues

```bash
# Check Neo4j status
docker ps | grep neo4j

# View Neo4j logs
docker logs neo4j

# Test connection
cypher-shell -a bolt://localhost:7687 -u neo4j -p password
```

### Slow Queries

```cypher
# Analyze query plan
EXPLAIN MATCH (n)-[:REQUIRES]->(m) RETURN n, m

# Profile query
PROFILE MATCH (n)-[:REQUIRES]->(m) RETURN n, m
```

```bash
# Enable query logging
# Add to neo4j.conf:
dbms.logs.query.enabled=true
dbms.logs.query.threshold=1s
```

### Graph Data Issues

```cypher
# Check for orphaned nodes
MATCH (n) WHERE NOT (n)--() RETURN count(n)

# Verify relationship integrity
MATCH (c:Control)<-[r:REQUIRES]-(reg:Regulation)
WHERE NOT exists(c.id) OR NOT exists(reg.id)
RETURN count(r)
```

## Data Seeding

### Initial Setup

```bash
# Seed common frameworks
python scripts/seed_frameworks.py

# Import controls from CSV
python scripts/import_controls.py --file data/soc2_controls.csv

# Generate opportunity graph
python scripts/generate_opportunities.py
```

### Sample Data

```cypher
// Create sample nodes
CREATE (soc2:Framework {id: 'SOC2', name: 'SOC 2 Type II'})
CREATE (mfa:Control {id: 'CC6.1', name: 'Multi-Factor Authentication'})
CREATE (org:Organization {id: '123', tenant_id: 'test-tenant', name: 'Acme Corp'})

// Create relationships
CREATE (soc2)-[:REQUIRES {mandatory: true}]->(mfa)
CREATE (org)-[:IMPLEMENTS {status: 'deployed', last_audit: date()}]->(mfa)
```

## Related Documentation

- [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/)
- [Graph Data Science](https://neo4j.com/docs/graph-data-science/current/)
- [Platform Architecture](../../docs/architecture/overview.md)

## Contributing

See: [CONTRIBUTING.md](../../CONTRIBUTING.md)

## License

Proprietary - RegEngine Platform  
Copyright © 2026 RegEngine Inc.
