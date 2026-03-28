# Scaling Guide Runbook

## Service Information
- **Target metrics:** Latency p95 < 2000ms, Error rate < 1%, CPU < 70%, Memory < 80%
- **Scaling triggers:** Any metric exceeding thresholds for > 5 minutes
- **Cost impact:** Bootstrapped founder — every resource doubles monthly AWS bill

---

## Prerequisites

- kubectl access to production cluster
- Prometheus/Grafana monitoring access
- Resource quotas defined in K8s namespace
- Database connection pool settings documented

---

## When to Scale

### Red Flags (Scale Within 15 min)

```bash
# High CPU usage
kubectl top pods -n regengine | grep ingestion

# High memory usage
kubectl top pods -n regengine --containers

# Connection pool exhaustion
kubectl exec -it postgres-0 -- psql -c \
  "SELECT count(*) FROM pg_stat_activity WHERE state != 'idle';"
# If > 90 of 100: SCALE DB

# Ingestion queue backing up
curl http://admin-service:8400/health | jq .ingestion_queue_depth
# If > 50000: SCALE INGESTION

# Latency degradation
# If p95 > 2500ms for 5 min: SCALE BACKEND
```

---

## Layer 1: Railway Service Scaling

### Ingestion Service

**Current:** 2 replicas, 512Mi RAM, 250m CPU

```bash
# Check current usage
kubectl top pod -l app=ingestion

# Scale up (if CPU > 70% or queue > 50k)
kubectl scale deployment/ingestion --replicas=4

# Monitor recovery (5 min)
kubectl logs -l app=ingestion --tail=20 -f
curl http://admin-service:8400/health | jq .ingestion_queue_depth

# Verify throughput improved
# (Check Prometheus: rate(ingestion_events_total[5m]))
```

**Cost impact:** +$120/month per replica (2 replicas = $240 baseline)

### Admin Service

**Current:** 1 replica, 256Mi RAM, 100m CPU

```bash
# Scale up if FDA export slow or RLS queries heavy
kubectl scale deployment/admin --replicas=2
kubectl rollout status deployment/admin --timeout=5m

# Monitor latency
# (Check Prometheus: histogram_quantile(0.95, http_request_duration_seconds))
```

**Cost impact:** +$60/month per replica

### Compliance Service

**Current:** 1 replica, 256Mi RAM, 100m CPU

```bash
# Scale only if query workload increases
kubectl scale deployment/compliance --replicas=2
```

**Cost impact:** +$60/month per replica

---

## Layer 2: PostgreSQL Connection Pool Tuning

### Current Configuration

```bash
# Check current settings
kubectl exec -it postgres-0 -- psql -c "SHOW max_connections;"
kubectl exec -it postgres-0 -- psql -c "SHOW shared_buffers;"
```

### Increase Connection Pool (Non-Disruptive)

```bash
# Temp increase (survives until next restart)
kubectl exec -it postgres-0 -- psql -c \
  "ALTER SYSTEM SET max_connections = 150;"

# Reload config
kubectl exec -it postgres-0 -- psql -c "SELECT pg_reload_conf();"

# Verify change
kubectl exec -it postgres-0 -- psql -c "SHOW max_connections;"
```

**Cost impact:** None (same RDS instance)

### Monitor Connection Usage

```bash
# Active connections
kubectl exec -it postgres-0 -- psql -c \
  "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;"

# Long-running queries (> 1 min)
kubectl exec -it postgres-0 -- psql -c \
  "SELECT pid, query, query_start FROM pg_stat_activity WHERE query_start < now() - INTERVAL '1 minute';"
```

**Action:** If > 80% of max_connections in use, scale further or optimize queries.

---

## Layer 3: Redis Memory Limits

### Current Configuration

**Instance:** 256MB (ElastiCache)

```bash
# Check memory usage
redis-cli INFO memory
# Expected: used_memory < 200MB

# Check eviction policy
redis-cli CONFIG GET maxmemory-policy
# Should be: allkeys-lru (least recently used)
```

### Scale Redis (if memory > 90%)

```bash
# Upgrade to 512MB
# Option 1: CLI (preferred for bootstrapped founder — zero downtime)
aws elasticache modify-cache-cluster \
  --cache-cluster-id regengine-redis \
  --cache-node-type cache.t3.medium \
  --apply-immediately

# Option 2: K8s (if running in-cluster)
kubectl set resources deployment/redis \
  --limits=memory=512Mi \
  --requests=memory=256Mi

# Monitor during upgrade (auto-failover ~ 2-3 min)
redis-cli INFO replication
```

**Cost impact:** +$30/month for 512MB → 1GB

### Monitor Key Size

```bash
# Top 10 largest keys
redis-cli --scan --pattern '*' | while read key; do
  redis-cli --memkeys | head -10
done

# If any key > 100MB: Consider archiving or sharding
```

---

## Layer 4: Kafka/Redpanda Partition Scaling

### Current Configuration

**Topic:** `fsma_documents` — 6 partitions, 1 replica

```bash
# Check broker health
kubectl exec -it redpanda-0 -- rpk cluster info

# Check partition distribution
kubectl exec -it redpanda-0 -- rpk topic list -d
```

### Add Partitions (if lag > 100k messages)

```bash
# Check consumer lag
kubectl exec -it redpanda-0 -- rpk group describe regengine-consumer

# Scale partitions (non-disruptive)
kubectl exec -it redpanda-0 -- rpk topic alter-config fsma_documents \
  --set num_partitions=12

# Rebalance consumers
kubectl rollout restart deployment/ingestion
```

**Cost impact:** None (same Redpanda cluster)

### Monitor Throughput

```bash
# Messages produced per second
kubectl exec -it redpanda-0 -- rpk topic stats fsma_documents

# Expected: 100-500 msg/sec at normal load
# If > 1000: Add partitions
```

---

## Cost-Conscious Scaling Strategy (Bootstrapped Founder)

**Rule of thumb:** Every scale-up adds ~$200-300/month. Only scale when necessary.

### Phase 1: Optimize Before Scaling

1. **Profile slow queries** — Often 1-2 queries cause 80% of latency
   ```bash
   # Top slow queries
   kubectl exec -it postgres-0 -- psql -c \
     "SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 5;"
   ```

2. **Add indexes** — Cheap and immediate
   ```bash
   kubectl exec -it postgres-0 -- psql -c \
     "CREATE INDEX CONCURRENTLY idx_documents_tenant_id ON documents(tenant_id);"
   ```

3. **Cache hot data** — Redis before scaling backend
   ```bash
   # If dashboard queries slow, cache results
   # Cost: $0 (use existing Redis)
   ```

### Phase 2: Scale Strategically

1. **Scale stateless services first** (ingestion, admin)
2. **Tune database connection pool** (free)
3. **Add caching layer** (cheap)
4. **Only then scale database** (expensive)

### Phase 3: Monitor ROI

```bash
# After each scale-up, measure impact
# - Did latency improve? (goal: p95 < 2000ms)
# - Did throughput improve? (goal: > 10k events/min)
# - Cost vs benefit worthwhile?

# If no improvement, rollback and investigate root cause
```

---

## Emergency Scaling

**If production is degraded and customers complaining:**

```bash
# Max scaling (temporary)
kubectl scale deployment/ingestion --replicas=8
kubectl scale deployment/admin --replicas=4

# Upgrade Redis and DB (one-time cost hit)
aws elasticache modify-cache-cluster --cache-node-type cache.t3.xlarge

# Once stable, optimize and scale back down
```

---

## Rollback Scaling

```bash
# If scaling didn't help or bill increased unexpectedly
kubectl scale deployment/ingestion --replicas=2
kubectl scale deployment/admin --replicas=1

# Downgrade expensive resources
aws elasticache modify-cache-cluster --cache-node-type cache.t3.micro
```

---

## Monitoring Targets

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| CPU usage | < 60% | > 75% for 5 min |
| Memory usage | < 60% | > 80% for 5 min |
| p95 latency | < 2000ms | > 2500ms for 5 min |
| Error rate | < 1% | > 2% for 5 min |
| Queue depth | < 10k | > 50k for 3 min |
| DB connections | < 80% | > 90% for 5 min |

Check Grafana dashboard: `https://monitoring.regengine.internal/d/main`

