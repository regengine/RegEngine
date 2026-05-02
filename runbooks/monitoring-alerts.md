# Monitoring & Alerts Runbook

## Service Information
- **Monitoring system:** Prometheus + Grafana
- **Dashboard URL:** https://monitoring.regengine.internal/d/main
- **Alert routing:** Slack #incidents
- **Check frequency:** Every 5 minutes

---

## Prerequisites

- Prometheus scraping all services
- Prometheus 2.55+ or 3.x so scrape `http_headers` can pass `X-Metrics-Key`
- `METRICS_API_KEY` mounted into Prometheus at `/etc/prometheus/secrets/metrics-api-key`
- Grafana dashboards configured
- Alertmanager routing to Slack
- Health endpoints responding

---

## Per-Service Health Endpoints

### Ingestion Service (8100)

**Endpoint:** `http://ingestion-service:8100/health`

**Expected response (200 OK):**
```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "processed_events": 1000000,
  "queue_depth": 500,
  "last_event_timestamp": "2026-03-27T15:30:00Z",
  "postgres_connected": true,
  "redpanda_connected": true
}
```

**What to check:**
- `queue_depth < 10000` — Otherwise scaling needed
- `postgres_connected: true` — DB connectivity
- `redpanda_connected: true` — Message broker
- Response time < 500ms

---

### Admin Service (8400)

**Endpoint:** `http://admin-service:8400/health`

**Expected response (200 OK):**
```json
{
  "status": "healthy",
  "database_latency_ms": 25,
  "rls_policies_count": 8,
  "users_count": 42,
  "memory_usage_mb": 180
}
```

**What to check:**
- `database_latency_ms < 100` — RLS queries performing
- `rls_policies_count > 0` — Security policies active
- Response time < 500ms

---

### Compliance Service (8200)

**Endpoint:** `http://compliance-service:8200/health`

**Expected response (200 OK):**
```json
{
  "status": "healthy",
  "fda_export_available": true,
  "last_export_timestamp": "2026-03-27T12:00:00Z",
  "pending_exports": 3,
  "graph_connected": true
}
```

**What to check:**
- `fda_export_available: true` — Export feature working
- `graph_connected: true` — Neo4j connectivity
- Response time < 500ms

---

### Graph Service (Neo4j, 7687)

**Endpoint:** `http://neo4j-core-0:7687`

**Check cluster:**
```bash
kubectl exec neo4j-core-0 -- bin/cypher-shell \
  "CALL dbms.clustering.overview() YIELD role, database, groups"
```

**Expected output:**
```
role              | database | groups
---
LEADER            | neo4j    | []
FOLLOWER          | neo4j    | []
FOLLOWER          | neo4j    | []
```

**What to check:**
- All 3 nodes present
- At least 1 LEADER
- No UNKNOWN roles
- Cluster responds to queries in < 2 seconds

---

### PostgreSQL Database

**Endpoint:** Direct psql connection

```bash
# Connection health
kubectl exec -it postgres-0 -- psql -c "SELECT version();"

# Query performance (slow queries)
kubectl exec -it postgres-0 -- psql -c \
  "SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 5;"

# Connection pool
kubectl exec -it postgres-0 -- psql -c "SELECT count(*) FROM pg_stat_activity;"
```

**Expected:**
- PostgreSQL version 13+
- Slow queries < 100ms average
- Active connections < 95 (out of 100)
- Idle connections can be killed

---

## Key Prometheus Metrics & Thresholds

### Request Latency

```promql
# 95th percentile latency (all services)
histogram_quantile(
  0.95,
  sum by (service, le) (
    rate(http_request_duration_seconds_bucket{job="regengine-services"}[5m])
  )
)
```

| Service | Target | Alert Threshold |
|---------|--------|-----------------|
| Ingestion | < 500ms | > 1000ms |
| Admin | < 1000ms | > 2000ms |
| Compliance | < 800ms | > 1500ms |
| Graph | < 2000ms | > 3000ms |

### Error Rate

```promql
# Error ratio (5xx responses / all responses)
sum by (service) (
  rate(http_requests_total{job="regengine-services", status=~"5.."}[5m])
)
/
sum by (service) (
  rate(http_requests_total{job="regengine-services"}[5m])
)
```

**Target:** < 0.5% (0.005)
**Alert threshold:** > 1% (0.01)

### Throughput

```promql
# Requests per second
sum by (service) (rate(http_requests_total{job="regengine-services"}[1m]))
```

| Service | Target | Minimum |
|---------|--------|---------|
| Ingestion | 100-500 req/s | > 50 req/s |
| Admin | 50-100 req/s | > 20 req/s |
| Compliance | 10-30 req/s | > 5 req/s |

### Resource Usage

```promql
# CPU usage (per pod)
rate(container_cpu_usage_seconds_total[5m])

# Memory usage (per pod)
container_memory_usage_bytes
```

| Metric | Target | Alert |
|--------|--------|-------|
| Ingestion CPU | < 300m | > 400m |
| Ingestion Memory | < 400Mi | > 500Mi |
| Admin CPU | < 150m | > 250m |
| Admin Memory | < 256Mi | > 350Mi |

### Database Metrics

```promql
# Active connections
pg_stat_activity_count{state="active"}

# Max connections available
pg_settings_max_connections - pg_stat_activity_count{state="active"}

# Query latency
histogram_quantile(0.95, pg_stat_statements_mean_exec_time_seconds)
```

| Metric | Target | Alert |
|--------|--------|-------|
| Active connections | < 50 | > 80 |
| Query latency | < 100ms | > 200ms |

### Message Queue

```promql
# Kafka/Redpanda lag per consumer
kafka_consumer_group_lag

# Queue depth (depth of pending messages)
redpanda_kafka_request_latency
```

| Metric | Target | Alert |
|--------|--------|-------|
| Consumer lag | < 5000 msgs | > 20000 msgs |
| Queue processing rate | > 100 msg/s | < 50 msg/s |

---

## Grafana Dashboard Overview

**Main dashboard:** `https://monitoring.regengine.internal/d/main`

**Panels:**
1. **Service Health** — Green/red status for each service
2. **Latency Trends** — p95 latency over 1h/24h
3. **Error Rate** — 5xx errors, displayed as percentage
4. **Throughput** — Requests/sec per service
5. **Resource Usage** — CPU and memory per pod
6. **Database** — Connection count, slow queries, RLS policy execution
7. **Neo4j Cluster** — Cluster health, query performance
8. **Message Queue** — Kafka lag, throughput

**How to read:**
- **Green:** All metrics in healthy range
- **Yellow:** Warning threshold crossed (usually means scale-up coming)
- **Red:** Critical threshold crossed — investigate immediately

---

## Alert Response Procedures

### Alert: "Ingestion Latency p95 > 1000ms"

1. Check current queue depth:
   ```bash
   curl http://admin-service:8400/health | jq .ingestion_queue_depth
   ```

2. If queue > 30k, scale ingestion:
   ```bash
   kubectl scale deployment/ingestion --replicas=4
   ```

3. Check for slow downstream queries:
   ```bash
   kubectl logs -l app=ingestion --tail=50 | grep "duration"
   ```

4. Resolve in 5 min or escalate

---

### Alert: "Database Connection Pool Exhaustion"

1. Check active connections:
   ```bash
   kubectl exec -it postgres-0 -- psql -c \
     "SELECT count(*) FROM pg_stat_activity WHERE state != 'idle';"
   ```

2. Kill idle connections older than 5 min:
   ```bash
   kubectl exec -it postgres-0 -- psql -c \
     "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - INTERVAL '5 minutes';"
   ```

3. Increase pool size (if persistent):
   ```bash
   kubectl exec -it postgres-0 -- psql -c "ALTER SYSTEM SET max_connections = 150;"
   kubectl exec -it postgres-0 -- psql -c "SELECT pg_reload_conf();"
   ```

---

### Alert: "Neo4j Cluster Unhealthy"

1. Check cluster topology:
   ```bash
   kubectl exec neo4j-core-0 -- bin/cypher-shell \
     "CALL dbms.cluster.overview() YIELD role"
   ```

2. If node down, K8s will auto-restart

3. If cluster split, verify network connectivity:
   ```bash
   kubectl exec -it neo4j-core-0 -- ping neo4j-core-1
   ```

4. If network OK, restart cluster:
   ```bash
   kubectl delete statefulset neo4j-core --cascade=orphan
   kubectl apply -f infra/k8s/base/neo4j-statefulset.yaml
   ```

---

### Alert: "Error Rate > 1%"

1. Check error logs:
   ```bash
   kubectl logs -l app=ingestion --tail=100 | grep ERROR
   kubectl logs -l app=admin --tail=100 | grep ERROR
   ```

2. Identify service with highest errors

3. Check if recent deployment caused it:
   ```bash
   kubectl rollout history deployment/ingestion
   ```

4. If so, rollback immediately:
   ```bash
   kubectl rollout undo deployment/ingestion
   ```

---

## Manual Health Check (5-minute routine)

Run this check every 5 minutes during production support:

```bash
#!/bin/bash
echo "=== Service Health Check ==="
curl -s http://ingestion-service:8100/health | jq '.status'
curl -s http://admin-service:8400/health | jq '.status'
curl -s http://compliance-service:8200/health | jq '.status'
echo ""
echo "=== Latency (check Grafana) ==="
echo "p95 latency: https://monitoring.regengine.internal/d/main"
echo ""
echo "=== Resources ==="
kubectl top pods -n regengine | head -10
```

---

## Escalation

| Issue | Severity | Action |
|-------|----------|--------|
| 1 service down, others OK | P2 | Check logs, restart pod |
| 2+ services down | P1 | Run incident response |
| Database unavailable | P1 | Activate disaster recovery |
| Latency > 3s, errors < 1% | P3 | Scale and monitor |
| Latency > 3s, errors > 5% | P1 | Rollback immediately |
