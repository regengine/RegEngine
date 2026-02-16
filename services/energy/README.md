# Energy Service

NERC CIP-013 Cybersecurity Compliance & Snapshot Management for Electrical Substations

## Overview

The Energy service provides cryptographic snapshot capabilities for tracking compliance state over time, supporting regulatory audits and forensic investigations in the energy sector.

### Key Features

- **Immutable Snapshots:** Cryptographically signed compliance states with SHA-256 hashing
- **Chain Integrity:** Sequential hash-chain verification prevents tampering
- **Streaming Exports:** CSV and JSON exports for large datasets (100k+ rows)
- **Structured Error Handling:** Comprehensive error responses with proper HTTP codes
- **Rate Limiting:** 10 snapshots/minute per IP address
- **Snapshot Verification:** Corruption detection and chain validation

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   FastAPI   │────▶│ SQLAlchemy   │────▶│ PostgreSQL   │
│   Endpoints │     │   Models     │     │   Database   │
└─────────────┘     └──────────────┘     └──────────────┘
       │
       ▼
┌──────────────────┐
│  Snapshot Engine │
│  - Hash Chain    │
│  - Signatures    │
│  - Validation    │
└──────────────────┘
```

## API Endpoints

### Create Snapshot
```http
POST /energy/snapshots
Content-Type: application/json

{
  "substation_id": "SUB-001",
  "facility_name": "Main Substation",
  "system_status": "NOMINAL",
  "assets": [
    {"asset_id": "XFMR-1", "status": "ONLINE"}
  ],
  "esp_config": {
    "firewall_enabled": true,
    "ids_active": true
  },
  "patch_metrics": {
    "last_patch": "2026-01-15",
    "pending_updates": 0
  },
  "trigger_reason": "Scheduled compliance audit"
}
```

**Response:**
```json
{
  "snapshot_id": "550e8400-e29b-41d4-a716-446655440000",
  "snapshot_time": "2026-01-27T10:30:00Z",
  "system_status": "NOMINAL",
  "asset_summary": {"total": 1, "online": 1},
  "content_hash": "a3f5...",
  "signature_hash": "b7c2..."
}
```

### List Snapshots
```http
GET /energy/snapshots?limit=50&offset=0&from_time=2026-01-01T00:00:00Z&to_time=2026-01-31T23:59:59Z
```

### Get Snapshot Details
```http
GET /energy/snapshots/{snapshot_id}
```

**Response includes:**
- Full snapshot payload
- Chain integrity status
- Verification results
- Related snapshots (previous/next in chain)

### Export Snapshots
```http
GET /energy/snapshots/export?format=csv&from_time=2026-01-01T00:00:00Z&to_time=2026-01-31T23:59:59Z
```

**Formats:** `csv` or `json`  
**Streaming:** Yes (handles large datasets efficiently)

### Verify Snapshot
```http
GET /energy/snapshots/{snapshot_id}/verify
```

Returns corruption status and chain validation results.

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | - | ✅ |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | `*` | ⚠️ Production |
| `LOG_LEVEL` | Logging verbosity | `info` | ❌ |
| `DEBUG` | Enable debug mode (pool logging) | `false` | ❌ |

### Example Configuration

```bash
export DATABASE_URL="postgresql://admin:password@postgres:5432/regengine_admin"
export ALLOWED_ORIGINS="https://app.regengine.co,https://admin.regengine.co"
export LOG_LEVEL="info"
```

## Local Development

### Prerequisites
- Python 3.9+
- PostgreSQL 14+
- Docker (optional, recommended)

### Setup

```bash
cd services/energy

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt  # For testing

# Set environment variables
cp .env.example .env
# Edit .env with your DATABASE_URL

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8700
```

### Testing

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=app tests/ --cov-report=html

# View coverage
open htmlcov/index.html  # macOS
# or xdg-open htmlcov/index.html  # Linux
```

**Current Test Coverage:** ~70%

## Docker Deployment

### docker-compose.yml

```yaml
energy-api:
  build: ./services/energy
  ports:
    - "8700:8000"
  environment:
    - DATABASE_URL=postgresql://admin:${DB_PASSWORD}@postgres:5432/regengine_admin
    - ALLOWED_ORIGINS=${ALLOWED_ORIGINS}
    - LOG_LEVEL=info
  depends_on:
    - postgres
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

### Start Service

```bash
# Development
docker-compose up energy-api

# Production
docker-compose -f docker-compose.prod.yml up -d energy-api
```

## Health Check

```bash
curl http://localhost:8700/health
```

**Healthy Response:**
```json
{
  "status": "healthy",
  "service": "energy-api",
  "version": "1.0.0",
  "timestamp": "2026-01-27T18:30:00Z",
  "dependencies": [
    {"name": "postgresql", "status": "healthy"}
  ],
  "snapshot_count": 12450,
  "chain_integrity": "verified"
}
```

**Unhealthy Response (503):**
```json
{
  "status": "unhealthy",
  "error": "Database connection failed",
  "timestamp": "2026-01-27T18:30:00Z"
}
```

## Recent Enhancements

### Phase 3 (January 2026) ✅

1. **JSON Streaming Export**
   - Implemented `generate_json_stream()` for efficient large exports
   - Supports same filters as CSV export

2. **Structured Error Handling**
   - `ErrorResponse` Pydantic model for consistent error responses
   - Proper HTTP status codes (400, 404, 500)
   - Database rollback on errors

3. **Database Configuration** (Platform Audit Remediation)
   - Connection pool sizing (10 base, 20 overflow)
   - Connection validation with `pool_pre_ping`
   - Query timeout enforcement (30s)
   - Connection recycling (1 hour)

4. **Date Range Validation**
   - Export endpoints validate `from_time < to_time`
   - Prevents invalid date range queries

**Full Details:** See [Phase 3 Walkthrough](../../../.gemini/antigravity/brain/7d7505a4-d970-423a-a7c4-2696610c7c9e/walkthrough.md)

## Database Schema

```sql
CREATE TABLE compliance_snapshots (
    snapshot_id UUID PRIMARY KEY,
    snapshot_time TIMESTAMPTZ NOT NULL,
    substation_id VARCHAR(100) NOT NULL,
    facility_name VARCHAR(255) NOT NULL,
    system_status VARCHAR(50) NOT NULL,
    snapshot_payload JSONB NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    signature_hash VARCHAR(64),
    previous_hash VARCHAR(64),
    generated_by VARCHAR(50) NOT NULL,
    generator_user_id VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_snapshots_time ON compliance_snapshots(snapshot_time DESC);
CREATE INDEX idx_snapshots_substation ON compliance_snapshots(substation_id);
CREATE INDEX idx_snapshots_hash ON compliance_snapshots(content_hash);
```

### Migrations

```bash
# Create new migration
alembic revision -m "description"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1

# Check current version
alembic current

# View migration history
alembic history
```

## Security Considerations

### Rate Limiting

Enforced via `slowapi`:
- 10 snapshots/minute per IP address
- Exceeding limit returns HTTP 429
- Reset window: 60 seconds

### Authentication

**Status:** ✅ CERTIFIED (Admin service JWT integration complete)  
Access is enforced via the `get_current_user` dependency in `app/main.py`.

### Data Integrity

- SHA-256 hashing for content verification
- Sequential hash-chain prevents insertion attacks
- Immutable records (no UPDATE/DELETE operations)
- Cryptographic signatures for non-repudiation

## Production Checklist

### Before Deployment

- [ ] Configure `DATABASE_URL` with production credentials
- [ ] Set `ALLOWED_ORIGINS` to specific domains (remove `*`)
- [ ] Enable SSL/TLS for database connections
- [ ] Integrate user authentication (JWT)
- [ ] Migrate to Redis for horizontal scaling
- [ ] Set up monitoring and alerting
- [ ] Run load tests (target: 100 req/s)
- [ ] Review and update rate limits

### Monitoring

**Prometheus Metrics:**
- `/metrics` endpoint available
- Request counts, latencies, error rates
- Connection pool stats (after update)

**Recommended Alerts:**
- Health check failures
- Database connection errors
- High error rates (>5%)
- Slow queries (>5s)

## Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL status
docker-compose ps postgres

# Test connection manually
psql "postgresql://admin:password@localhost:5432/regengine_admin"

# View service logs
docker-compose logs -f energy-api

# Check connection pool stats (if DEBUG=true)
grep "pool" logs/energy-api.log
```

### Migration Errors

```bash
# View current schema version
alembic current

# Force to specific version (⚠️ dangerous)
alembic stamp head

# Reset and reapply (⚠️ destroys data)
alembic downgrade base
alembic upgrade head
```

### Performance Issues

```bash
# Enable query logging
export DATABASE_URL="${DATABASE_URL}?echo=true"

# Run performance tests
pytest tests/test_performance.py -v

# Check for slow queries
docker exec -it postgres psql -U admin -d regengine_admin \
  -c "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

## Related Documentation

- [Platform Audit Report](../../../.gemini/antigravity/brain/7d7505a4-d970-423a-a7c4-2696610c7c9e/MASTER_AUDIT_REPORT.md)
- [Phase 3 Implementation](../../../.gemini/antigravity/brain/7d7505a4-d970-423a-a7c4-2696610c7c9e/walkthrough.md)
- [Energy Vertical Overview](../../../.gemini/antigravity/knowledge/reg_engine_energy_vertical/artifacts/overview.md)
- [NERC CIP-013 Compliance Guide](../../docs/compliance/NERC_CIP_013.md)

## Contributing

See: [CONTRIBUTING.md](../../CONTRIBUTING.md)

## License

Proprietary - RegEngine Platform  
Copyright © 2026 RegEngine Inc.
