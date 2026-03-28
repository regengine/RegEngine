# Production Incident Response Runbook

## Service Information
- **On-call:** Christopher (primary, all services)
- **Escalation:** None (single-person team)
- **Severity Levels:** P1 (complete outage), P2 (service degradation), P3 (non-critical)

---

## Prerequisites

- Slack notifications enabled for production alerts
- Prometheus/Grafana access: https://monitoring.regengine.internal
- kubectl configured for production cluster
- Database access credentials stored securely

---

## Triage: Which Service is Failing?

### Step 1: Check Health Dashboard (5 seconds)

```bash
curl -s https://api.regengine.co/health | jq .
```

**Expected response:**
```json
{
  "status": "healthy",
  "services": {
    "ingestion": "healthy",
    "admin": "healthy",
    "compliance": "healthy",
    "graph": "healthy",
    "database": "healthy"
  }
}
```

### Step 2: Identify Failing Service (2 minutes)

Run per-service health checks (see below). Focus on any returning non-200 status or timeout.

---

## Per-Service Health Checks

### Ingestion Service (Port 8100)

```bash
curl -I http://ingestion-service:8100/health
# Expected: 200 OK

# Check ingestion queue depth
curl http://admin-service:8400/health | jq .ingestion_queue_depth
# Expected: < 10000

# Check memory usage
kubectl top pod -l app=ingestion
# Expected: < 500Mi
```

### Admin Service (Port 8400)

```bash
curl -I http://admin-service:8400/health
# Expected: 200 OK

# Check database connection
curl http://admin-service:8400/diagnostics/db
# Expected: {"status": "connected"}

# Check RLS policies
kubectl exec -it postgres-0 -- psql -c "SELECT COUNT(*) FROM pg_policies"
# Expected: > 5
```

### Compliance Service (Port 8200)

```bash
curl -I http://compliance-service:8200/health
# Expected: 200 OK

# Check FDA export availability
curl http://compliance-service:8200/exports/status
# Expected: 200 OK
```

### Graph Service (Neo4j) (Port 7687)

```bash
# Check cluster health
kubectl exec neo4j-core-0 -- bin/cypher-shell "CALL dbms.clustering.overview() YIELD role, database"
# Expected: All nodes show "LEADER" or "FOLLOWER"

# Check query performance
kubectl exec neo4j-core-0 -- bin/cypher-shell "MATCH (n) RETURN count(n)" --timeout=10s
# Expected: Completes in < 5 seconds
```

### Frontend (Vercel)

```bash
curl -I https://regengine.co
# Expected: 200 OK

# Check if static assets load
curl -I https://regengine.co/_next/static/chunks/main.js
# Expected: 200 OK
```

### PostgreSQL Database

```bash
# Connection check
kubectl exec -it postgres-0 -- psql -c "SELECT version();"

# Check connection pool
kubectl exec -it postgres-0 -- psql -c "SELECT count(*) FROM pg_stat_activity;"
# Expected: < 95 (max_connections is 100)

# Check slow queries
kubectl exec -it postgres-0 -- psql -c \
  "SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 5;"
```

---

## Common Failure Modes & Fixes

### Symptom: 503 Service Unavailable (All Endpoints)

**Likely cause:** API gateway or load balancer down

1. Check K8s cluster health:
   ```bash
   kubectl get nodes
   kubectl get pods -n regengine
   ```

2. Restart gateway:
   ```bash
   kubectl rollout restart deployment/gateway -n regengine
   kubectl rollout status deployment/gateway --timeout=2m
   ```

3. Monitor:
   ```bash
   kubectl logs -l app=gateway --tail=50 -f
   ```

---

### Symptom: 500 Database Errors (Ingestion/Admin)

**Likely cause:** PostgreSQL connection pool exhausted or slow queries

1. Check connection count:
   ```bash
   kubectl exec -it postgres-0 -- psql -c "SELECT count(*) FROM pg_stat_activity WHERE state != 'idle';"
   ```

2. Kill idle connections:
   ```bash
   kubectl exec -it postgres-0 -- psql -c \
     "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - INTERVAL '10 minutes';"
   ```

3. Increase connection pool (temporary):
   ```bash
   kubectl set env deployment/ingestion \
     DB_POOL_MAX=50 \
     DB_POOL_MIN=10
   ```

4. Monitor recovery:
   ```bash
   kubectl logs -l app=ingestion --tail=30 -f
   ```

---

### Symptom: Ingestion Queue Backing Up (> 20k messages)

**Likely cause:** Slow downstream processing or consumer lag

1. Check Kafka/Redpanda broker:
   ```bash
   kubectl exec -it redpanda-0 -- rpk cluster info
   ```

2. Monitor consumer lag:
   ```bash
   kubectl exec -it redpanda-0 -- rpk group list
   kubectl exec -it redpanda-0 -- rpk group describe regengine-consumer
   ```

3. Restart consumer:
   ```bash
   kubectl rollout restart deployment/ingestion
   kubectl rollout status deployment/ingestion --timeout=5m
   ```

---

### Symptom: Graph (Neo4j) Cluster Split-Brain

**Likely cause:** Network partition or node failure

1. Check cluster topology:
   ```bash
   kubectl exec neo4j-core-0 -- bin/cypher-shell \
     "CALL dbms.cluster.coremembers() YIELD memberId, addresses, role"
   ```

2. If 1+ nodes down: Kubernetes will auto-restart via StatefulSet

3. Verify re-join:
   ```bash
   kubectl logs statefulset/neo4j-core | grep -i "joined cluster"
   ```

4. If still broken: Trigger DR recovery (see rollback)

---

### Symptom: Frontend 404s or Broken Deploys

**Likely cause:** Vercel deployment failed or cache issue

1. Check Vercel deployment status:
   ```bash
   vercel list deployments
   ```

2. Rollback to last stable:
   ```bash
   vercel rollback
   ```

3. Clear CDN cache:
   ```bash
   vercel cache purge
   ```

---

## Escalation Path

Since this is a single-person operation:

- **P1 (Outage > 1 min):** Immediate diagnosis and fix attempt
- **P2 (Degradation):** Fix within 15 min or escalate to maintenance window
- **P3 (Non-critical):** Schedule for next planned maintenance

**No external escalation available.** If unfixable in 30 minutes, consider:
- Rollback to last known-good state
- Switch to read-only mode
- Post incident summary for later analysis

---

## Post-Incident Template

1. **What was the impact?** (start time, end time, affected users)
2. **Root cause:** (database, code, infra, external)
3. **Fix applied:** (steps taken to resolve)
4. **Prevention:** (what changes to prevent recurrence)
5. **Follow-up actions:** (code review, monitoring, testing)

**File at:** `/sessions/gracious-cool-bell/mnt/RegEngine/incidents/YYYYMMDD-incident-title.md`

Example:
```markdown
# 2026-03-27 Database Connection Pool Exhaustion

- **Duration:** 14:32 - 14:47 UTC (15 min)
- **Impact:** All ingestion endpoints returned 500
- **Root cause:** Long-running query holding connections + default pool size too small
- **Fix:** Killed idle connections, restarted ingestion service
- **Prevention:** Increase connection pool monitoring, add query timeout
```
