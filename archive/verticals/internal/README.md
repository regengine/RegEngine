# Internal Service

Internal systems service for RegEngine administrative and diagnostic functionality.

## Overview

The Internal service provides system administration, monitoring, debugging, and diagnostic capabilities for the RegEngine platform. It serves as the operational backbone for DevOps, SRE, and platform administrators.

### Key Features

- **System Diagnostics:** Health checks, service status, dependency monitoring
- **Administrative Tools:** Platform configuration, feature flags, maintenance mode
- **Audit Logging:** Centralized audit trail for all platform operations
- **Performance Metrics:** Real-time performance monitoring and analytics
- **Debugging Tools:** Request tracing, log aggregation, error tracking

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   FastAPI    │────▶│  PostgreSQL  │────▶│  Prometheus  │
│   Admin API  │     │  Audit Logs  │     │   Metrics    │
└──────────────┘     └──────────────┘     └──────────────┘
       │
       ▼
┌──────────────┐
│    Redis     │
│ Feature Flags│
└──────────────┘
```

## API Endpoints

### System Status

```http
GET /internal/status
Authorization: X-Admin-Key: <admin_key>
```

**Response:**
```json
{
  "overall_status": "healthy",
  "services": [
    {
      "name": "admin",
      "status": "healthy",
      "uptime_seconds": 345600,
      "version": "1.2.0"
    },
    {
      "name": "ingestion",
      "status": "degraded",
      "details": {
        "queue_size": 150,
        "threshold": 100
      }
    }
  ],
  "timestamp": "2026-01-27T18:00:00Z"
}
```

### Diagnostics

```http
GET /internal/diagnostics
Authorization: X-Admin-Key: <admin_key>
```

**Response:**
```json
{
  "database": {
    "postgresql": {
      "status": "healthy",
      "connection_pool": {
        "active": 5,
        "idle": 15,
        "max": 20
      },
      "latency_ms": 12
    }
  },
  "cache": {
    "redis": {
      "status": "healthy",
      "memory_used_mb": 245,
      "hit_rate": 0.87
    }
  },
  "external_services": {
    "neo4j": {
      "status": "healthy",
      "version": "5.0.0"
    }
  }
}
```

### Audit Logs

```http
GET /internal/audit-logs?service=energy&action=snapshot_create&limit=100
Authorization: X-Admin-Key: <admin_key>
```

**Response:**
```json
{
  "logs": [
    {
      "id": "audit-12345",
      "timestamp": "2026-01-27T18:00:00Z",
      "service": "energy",
      "action": "snapshot_create",
      "user_id": "user-123",
      "tenant_id": "tenant-456",
      "details": {
        "snapshot_id": "snap-789",
        "substation_id": "sub-001"
      },
      "ip_address": "192.168.1.100"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

### Feature Flags

```http
GET /internal/feature-flags
Authorization: X-Admin-Key: <admin_key>
```

**Response:**
```json
{
  "flags": {
    "ocr_enabled": true,
    "beta_energy_export": false,
    "maintenance_mode": false
  }
}
```

```http
PUT /internal/feature-flags/beta_energy_export
Authorization: X-Admin-Key: <admin_key>

{
  "enabled": true
}
```

### Metrics

```http
GET /internal/metrics
Authorization: X-Admin-Key: <admin_key>
```

**Response (Prometheus format):**
```
# HELP regengine_requests_total Total HTTP requests
# TYPE regengine_requests_total counter
regengine_requests_total{service="energy",method="POST",status="200"} 1234

# HELP regengine_request_duration_seconds HTTP request duration
# TYPE regengine_request_duration_seconds histogram
regengine_request_duration_seconds_bucket{le="0.1"} 800
regengine_request_duration_seconds_bucket{le="0.5"} 950
regengine_request_duration_seconds_bucket{le="1.0"} 990
regengine_request_duration_seconds_sum 450.2
regengine_request_duration_seconds_count 1000
```

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection | - | ✅ |
| `REDIS_URL` | Redis cache connection | `redis://localhost:6379/1` | ✅ |
| `ADMIN_KEY` | Master admin key | - | ✅ (prod) |
| `PROMETHEUS_PORT` | Metrics export port | `9090` | ❌ |
| `LOG_LEVEL` | Logging verbosity | `INFO` | ❌ |
| `AUDIT_RETENTION_DAYS` | Audit log retention | `90` | ❌ |

## Local Development

### Prerequisites

- Python 3.9+
- PostgreSQL 14+
- Redis 6+

### Setup

```bash
cd services/internal

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your configuration

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8003
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app tests/ --cov-report=html
```

## Docker Deployment

```yaml
internal-api:
  build: ./services/internal
  ports:
    - "8003:8000"
    - "9090:9090"  # Prometheus metrics
  environment:
    - DATABASE_URL=postgresql://admin:${DB_PASSWORD}@postgres:5432/regengine_admin
    - REDIS_URL=redis://redis:6379/1
    - ADMIN_KEY=${ADMIN_KEY}
  depends_on:
    - postgres
    - redis
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

## Health Check

```bash
curl http://localhost:8003/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "internal-api",
  "version": "1.0.0"
}
```

## Security

### Admin Key Authentication

All endpoints require the `X-Admin-Key` header:

```http
X-Admin-Key: <admin_key>
```

**Generate a new admin key:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### IP Whitelisting

Configure allowed IP ranges in `.env`:

```env
ALLOWED_IPS=192.168.1.0/24,10.0.0.0/8
```

## Audit Trail

All administrative actions are logged to the audit table:

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    service VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    user_id UUID,
    tenant_id UUID,
    details JSONB,
    ip_address INET,
    user_agent TEXT
);

CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX idx_audit_service ON audit_logs(service);
CREATE INDEX idx_audit_action ON audit_logs(action);
```

## Monitoring

### Prometheus Integration

Metrics exported at `/internal/metrics`:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'regengine-internal'
    static_configs:
      - targets: ['internal-api:9090']
```

### Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `regengine_requests_total` | Counter | Total HTTP requests |
| `regengine_request_duration_seconds` | Histogram | Request latency |
| `regengine_errors_total` | Counter | Total errors by service |
| `regengine_db_connections` | Gauge | Active DB connections |
| `regengine_cache_hit_rate` | Gauge | Redis cache efficiency |

## Common Operations

### Enable Maintenance Mode

```bash
curl -X PUT http://localhost:8003/internal/feature-flags/maintenance_mode \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### Query Recent Errors

```bash
curl "http://localhost:8003/internal/audit-logs?action=error&limit=50" \
  -H "X-Admin-Key: $ADMIN_KEY"
```

### Check Service Dependencies

```bash
curl http://localhost:8003/internal/diagnostics \
  -H "X-Admin-Key: $ADMIN_KEY"
```

## Troubleshooting

### High Memory Usage

```bash
# Check Redis memory
redis-cli INFO memory

# Clear cache if needed
redis-cli FLUSHDB
```

### Slow Queries

```sql
-- Find slow queries in PostgreSQL
SELECT query, mean_exec_time 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;
```

### Service Dependency Issues

```bash
# Test all service connections
curl http://localhost:8003/internal/diagnostics
```

## Related Documentation

- [Platform Architecture](../../docs/architecture/overview.md)
- [Monitoring Guide](../../docs/ops/monitoring.md)
- [Security Best Practices](../../docs/security/admin_keys.md)

## License

Proprietary - RegEngine Platform  
Copyright © 2026 RegEngine Inc.
