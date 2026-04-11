# Database Optimization Guide

**Date:** January 27, 2026  
**Services:** All backend services using PostgreSQL

---

## Overview

This guide documents database optimization strategies for the RegEngine platform, including query logging, index optimization, and connection pool monitoring.

---

## 1. Slow Query Logging

### PostgreSQL Configuration

Add to `postgresql.conf` or Docker environment:

```conf
# Log slow queries (> 200ms)
log_min_duration_statement = 200

# Log query plans for slow queries
auto_explain.log_min_duration = 500
auto_explain.log_analyze = on
auto_explain.log_verbose = on

# Log connections and disconnections
log_connections = on
log_disconnections = on

# Log checkpoint activity
log_checkpoints = on
```

###Docker Compose Configuration

```yaml
postgres:
  image: postgres:14
  environment:
    - POSTGRES_LOG_MIN_DURATION_STATEMENT=200
  command: >
    postgres
    -c log_min_duration_statement=200
    -c log_connections=on
    -c log_disconnections=on
```

### Python Query Logging

**File:** `shared/database.py`

```python
import logging
import time
from contextlib import contextmanager
from sqlalchemy import event
from sqlalchemy.engine import Engine

# Configure logging
logger = logging.getLogger('database.queries')

@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(time.time())
    logger.debug(f"Query: {statement}")

@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total_time = time.time() - conn.info['query_start_time'].pop()
    
    if total_time > 0.2:  # Log queries > 200ms
        logger.warning(
            f"Slow query ({total_time:.2f}s): {statement[:200]}",
            extra={
                'duration': total_time,
                'query': statement,
                'parameters': parameters
            }
        )
```

---

## 2. Index Optimization

### Admin Service Indexes

**File:** `services/admin/migrations/V023__performance_indexes.sql`

```sql
-- User lookups by email
CREATE INDEX IF NOT EXISTS idx_users_email
ON users(email) WHERE NOT deleted;

-- Tenant lookups
CREATE INDEX IF NOT EXISTS idx_users_tenant
ON users(tenant_id, is_active);

-- API key lookups
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash
ON api_keys(key_hash) WHERE NOT revoked;

-- Audit log queries
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp
ON audit_logs(timestamp DESC, service, action);

-- Analyze tables
ANALYZE users;
ANALYZE tenants;
ANALYZE api_keys;
ANALYZE audit_logs;
```

---

## 3. Connection Pool Monitoring

### SQLAlchemy Pool Configuration

**File:** `shared/database.py`

```python
from sqlalchemy import create_engine, event
from sqlalchemy.pool import QueuePool
import prometheus_client as prom

# Prometheus metrics
db_pool_size = prom.Gauge(
    'db_pool_size',
    'Current database connection pool size',
    ['service', 'state']
)

db_pool_overflow = prom.Gauge(
    'db_pool_overflow',
    'Current overflow connections',
    ['service']
)

db_pool_checkedout = prom.Gauge(
    'db_pool_checkedout',
    'Connections currently checked out',
    ['service']
)

def create_monitored_engine(database_url, service_name):
    engine = create_engine(
        database_url,
        poolclass=QueuePool,
        pool_size=20,              # Connections to keep open
        max_overflow=10,           # Additional connections allowed
        pool_timeout=30,           # Seconds to wait for connection
        pool_recycle=3600,         # Recycle connections after 1 hour
        pool_pre_ping=True,        # Verify connections before use
        echo_pool='debug'          # Log pool activity
    )
    
    # Monitor pool metrics
    @event.listens_for(engine, "connect")
    def receive_connect(dbapi_conn, connection_record):
        pool = engine.pool
        db_pool_size.labels(service=service_name, state='open').set(pool.size())
        db_pool_overflow.labels(service=service_name).set(pool.overflow())
        db_pool_checkedout.labels(service=service_name).set(pool.checkedout())
    
    return engine
```

### Pool Status Endpoint

**File:** `services/*/app/main.py`

```python
@app.get("/metrics/database")
async def database_metrics():
    pool = engine.pool
    
    return {
        "pool_size": pool.size(),
        "overflow": pool.overflow(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "total_connections": pool.size() + pool.overflow(),
        "utilization_percent": (pool.checkedout() / pool.size()) * 100
    }
```

---

## 4. Query Performance Analysis

### Find Missing Indexes

```sql
-- Tables with sequential scans
SELECT schemaname, tablename, seq_scan, seq_tup_read,
       idx_scan, idx_tup_fetch,
       seq_tup_read / seq_scan as avg_seq_read
FROM pg_stat_user_tables
WHERE seq_scan > 0
ORDER BY seq_tup_read DESC
LIMIT 20;
```

### Index Usage Statistics

```sql
-- Unused indexes
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
AND indexname NOT LIKE '%_pkey'
ORDER BY schemaname, tablename;
```

### Table Bloat Analysis

```sql
-- Check table bloat
SELECT
  schemaname, tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) -
                 pg_relation_size(schemaname||'.'||tablename)) AS external_size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 20;
```

---

## 5. Monitoring Dashboard

### Prometheus Queries

```promql
# Average query duration
rate(db_query_duration_seconds_sum[5m]) / rate(db_query_duration_seconds_count[5m])

# 95th percentile query time
histogram_quantile(0.95, rate(db_query_duration_seconds_bucket[5m]))

# Connection pool utilization
db_pool_checkedout / db_pool_size

# Slow query rate
rate(db_slow_queries_total[5m])
```

### Grafana Dashboard

Import template: `infra/grafana/dashboards/database-performance.json`

**Panels:**
- Query duration (p50, p95, p99)
- Connection pool utilization
- Slow query rate
- Table sizes
- Index hit ratio

---

## 6. Optimization Checklist

### Before Deployment

- [ ] Run `EXPLAIN ANALYZE` on frequent queries
- [ ] Check index usage with `pg_stat_user_indexes`
- [ ] Verify connection pool settings
- [ ] Enable slow query logging
- [ ] Set up monitoring alerts

### Regular Maintenance

- [ ] Weekly: Review slow query logs
- [ ] Monthly: Analyze table bloat
- [ ] Monthly: Check for unused indexes
- [ ] Quarterly: Review and update statistics

---

## 7. Quick Reference

### Enable Logging

```bash
# Edit postgresql.conf
docker exec -it postgres vim /var/lib/postgresql/data/postgresql.conf

# Reload config
docker exec -it postgres psql -U postgres -c "SELECT pg_reload_conf();"
```

### View Slow Queries

```bash
# Tail PostgreSQL logs
docker logs -f postgres 2>&1 | grep "duration:"
```

### Check Pool Status

```bash
curl http://localhost:8000/metrics/database
```

### Run Migrations

```bash
cd services/admin
python -m alembic upgrade head
```

---

**Status:** Optimization framework ready  
**Next:** Apply migrations and monitor metrics
