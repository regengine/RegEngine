# Rollback Procedure Runbook

## Service Information
- **Applies to:** Ingestion, Admin, Compliance, Graph, Frontend
- **Criticality:** Tier 1
- **Recovery Time:** 2-10 minutes depending on layer

---

## Prerequisites

- kubectl access to production cluster
- Vercel CLI authenticated
- PostgreSQL psql access
- Previous image versions tagged in GHCR
- Database backup available

---

## Quick Decision Tree

| Symptom | Fix | Time |
|---------|-----|------|
| Frontend broken (login/UI) | Vercel rollback | 1 min |
| Backend 5xx errors | K8s rollout undo | 2 min |
| Database queries fail | Migrate rollback + restart | 5 min |
| Neo4j cluster down | K8s restart + failover | 5 min |

---

## Layer 1: Frontend Rollback (Vercel)

### Complete Rollback

```bash
# Show recent deployments
vercel list deployments --limit 10

# Rollback to previous stable
vercel rollback
```

**Expected output:** "Rollback successful. Previous build restored."

### Verify

```bash
curl -I https://regengine.co
# Expected: 200 OK

# Check DevTools that login flow works
```

**Time:** 1 minute

---

## Layer 2: Backend Service Rollback (K8s)

### Single Service Rollback

```bash
# For ingestion, admin, compliance, or graph
kubectl rollout undo deployment/{SERVICE_NAME} -n regengine

# Example:
kubectl rollout undo deployment/ingestion -n regengine

# Watch rollout progress
kubectl rollout status deployment/ingestion -n regengine --timeout=5m
```

### Rollback All Services

```bash
for svc in ingestion admin compliance graph; do
  kubectl rollout undo deployment/$svc -n regengine
  kubectl rollout status deployment/$svc --timeout=5m
done
```

### Verify Health

```bash
# Check all pods running
kubectl get pods -n regengine

# Test health endpoint
curl -s http://ingestion-service:8100/health | jq .status
```

**Time:** 2-5 minutes

---

## Layer 3: Database Migration Rollback

### Identify Current State

```bash
# List applied migrations
kubectl exec -it postgres-0 -- psql -c \
  "SELECT version, description, installed_on FROM schema_migrations ORDER BY version DESC LIMIT 5;"
```

### Rollback Last Migration

```bash
# Find the revert script (usually numbered migrations/revert_*.sql)
ls -la migrations/ | grep revert

# Apply rollback
kubectl exec -it postgres-0 -- psql -f migrations/revert_latest.sql

# Verify rollback
kubectl exec -it postgres-0 -- psql -c \
  "SELECT version, description, installed_on FROM schema_migrations ORDER BY version DESC LIMIT 5;"
```

### Restart Backend Services (to reconnect)

```bash
kubectl rollout restart deployment/ingestion -n regengine
kubectl rollout status deployment/ingestion --timeout=5m
```

**Example Revert Scripts:**
- `migrations/revert_rls_sysadmin_audit.sql` — Roll back RLS policies
- `migrations/revert_audit_log_schema.sql` — Roll back audit table

**Time:** 5-10 minutes

---

## Layer 4: Graph (Neo4j) Rollback

### Check Current State

```bash
# Cluster status
kubectl exec neo4j-core-0 -- bin/cypher-shell \
  "CALL dbms.cluster.coremembers() YIELD memberId, role, addresses"

# Data integrity check
kubectl exec neo4j-core-0 -- bin/cypher-shell \
  "MATCH (n) RETURN count(n) as total_nodes"
```

### Restart Neo4j Cluster

```bash
# Delete StatefulSet (preserves PVCs)
kubectl delete statefulset neo4j-core -n regengine --cascade=orphan

# Recreate StatefulSet (data persists)
kubectl apply -f infra/k8s/base/neo4j-statefulset.yaml

# Wait for cluster to rejoin
kubectl rollout status statefulset/neo4j-core --timeout=10m

# Verify cluster health
kubectl exec neo4j-core-0 -- bin/cypher-shell \
  "CALL dbms.cluster.overview() YIELD role, database"
```

### Restore from Backup (if data corruption)

```bash
# Stop neo4j
kubectl scale statefulset neo4j-core --replicas=0

# Restore backup from S3
kubectl create job neo4j-restore-$(date +%s) \
  --from=cronjob/neo4j-restore-backup \
  --env="BACKUP_SOURCE=s3://regengine-backups/neo4j/latest-full.tar.gz"

# Monitor restore job
kubectl logs job/neo4j-restore-* -f

# Once complete, restart cluster
kubectl scale statefulset neo4j-core --replicas=3
```

**Time:** 5-15 minutes (10+ min with full restore)

---

## Layer 5: Full System Rollback

**Use only if multiple layers are broken:**

```bash
# 1. Stop ingestion to prevent data inconsistency
kubectl scale deployment/ingestion --replicas=0

# 2. Rollback database
kubectl exec -it postgres-0 -- psql -f migrations/revert_latest.sql

# 3. Rollback Neo4j (if needed)
kubectl delete statefulset neo4j-core -n regengine --cascade=orphan
kubectl apply -f infra/k8s/base/neo4j-statefulset.yaml

# 4. Rollback all backend services
for svc in admin compliance graph; do
  kubectl rollout undo deployment/$svc -n regengine
done

# 5. Restart ingestion
kubectl scale deployment/ingestion --replicas=2
kubectl rollout status deployment/ingestion --timeout=5m

# 6. Rollback frontend
vercel rollback

# 7. Verify system health
curl -s https://api.regengine.co/health | jq .
```

**Time:** 15-20 minutes

---

## Verification Checklist

- [ ] `kubectl get pods -n regengine` — all pods Running
- [ ] `curl https://api.regengine.co/health` — 200 OK
- [ ] `curl https://regengine.co` — 200 OK, login works
- [ ] Ingestion queue size < 1000
- [ ] Database connection count < 95
- [ ] Neo4j cluster all nodes LEADER/FOLLOWER
- [ ] p95 latency < 2500ms (monitoring)
- [ ] Error rate < 0.5% (monitoring)

---

## Post-Rollback

1. Document what triggered rollback
2. Review logs to identify root cause
3. Fix underlying issue before re-deploying
4. Test fix in staging environment
5. Schedule post-mortem if critical

