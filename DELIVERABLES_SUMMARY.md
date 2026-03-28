# RegEngine Operations & Load Testing Deliverables

**Date:** 2026-03-27  
**Status:** Complete  

---

## Item 1: Operational Runbooks (5 files)

All runbooks follow the format: **Prerequisites → Steps → Rollback → Escalation**

### 1. Deploy Security Hardening Runbook
**File:** `/sessions/gracious-cool-bell/mnt/RegEngine/runbooks/deploy-security-hardening.md`  
**Lines:** 167 | **Use case:** Safe deployment of security audit fixes (11 PRs)

**Content:**
- 5-phase deployment (Infrastructure → DB → Backend → Frontend → Verification)
- Per-phase health checks and monitoring
- Immediate rollback triggers
- Verification checklist for all hardening changes

### 2. Incident Response Runbook
**File:** `/sessions/gracious-cool-bell/mnt/RegEngine/runbooks/incident-response.md`  
**Lines:** 283 | **Use case:** Production troubleshooting and triage

**Content:**
- Triage checklist (which service is failing?)
- Per-service health check commands (ingestion, admin, compliance, graph, DB, frontend)
- 5 common failure modes with fixes:
  - 503 Service Unavailable
  - 500 Database Errors
  - Ingestion Queue Backing Up
  - Neo4j Cluster Split-Brain
  - Frontend Deployment Failures
- Escalation path (single-person operation)
- Post-incident template

### 3. Rollback Procedure Runbook
**File:** `/sessions/gracious-cool-bell/mnt/RegEngine/runbooks/rollback-procedure.md`  
**Lines:** 243 | **Use case:** Rapid recovery from failed deployments

**Content:**
- Quick decision tree (which layer to rollback?)
- Layer-by-layer rollback:
  - Frontend (Vercel rollback: 1 min)
  - Backend Services (K8s rollout undo: 2-5 min)
  - Database Migrations (revert SQL + restart: 5-10 min)
  - Neo4j Graph (restart cluster + failover: 5-15 min)
- Full system rollback procedure
- Verification checklist
- Post-rollback actions

### 4. Scaling Guide Runbook
**File:** `/sessions/gracious-cool-bell/mnt/RegEngine/runbooks/scaling-guide.md`  
**Lines:** 317 | **Use case:** Resource scaling decisions with founder budget constraints

**Content:**
- Red flags (CPU > 70%, queue > 50k, p95 > 2500ms)
- Service-specific scaling:
  - Railway services (ingestion, admin, compliance)
  - PostgreSQL connection pool tuning
  - Redis memory limits
  - Kafka/Redpanda partitions
- Cost-conscious strategy (bootstrapped founder focus):
  - Phase 1: Optimize before scaling
  - Phase 2: Scale strategically
  - Phase 3: Monitor ROI
  - Emergency scaling procedures
- Monitoring targets and alert thresholds

### 5. Monitoring & Alerts Runbook
**File:** `/sessions/gracious-cool-bell/mnt/RegEngine/runbooks/monitoring-alerts.md`  
**Lines:** 373 | **Use case:** Health endpoint monitoring and alert response

**Content:**
- Per-service health endpoints (expected responses):
  - Ingestion (8100)
  - Admin (8400)
  - Compliance (8200)
  - Graph/Neo4j (7687)
  - PostgreSQL
  - Frontend
- Prometheus metrics with thresholds:
  - Request latency (p95 per service)
  - Error rates (5xx errors)
  - Throughput (req/s)
  - Resource usage (CPU, memory)
  - Database metrics (connections, query latency)
  - Message queue (lag, depth)
- Grafana dashboard overview
- Alert response procedures (5 critical alerts)
- Manual 5-minute health check script
- Escalation matrix

---

## Item 2: K6 Load Testing Scaffolding (2 files)

Both tests follow the same pattern: **3-stage ramp-up → sustain → ramp-down** with thresholds: p95 < 2000ms, error < 1%, throughput > 100 req/s

### 1. Ingestion Service Load Test
**File:** `/sessions/gracious-cool-bell/mnt/RegEngine/tests/load/k6-ingestion-test.js`  
**Lines:** 212 | **Run with:** `BASE_URL=... API_KEY=... k6 run tests/load/k6-ingestion-test.js`

**Content:**
- MVP flow simulation:
  - Phase 1: CSV file upload (multipart)
  - Phase 2: Status polling (check processing, max 10 attempts)
  - Phase 3: Data export (retrieve results)
- Custom metrics:
  - `ingestion_upload_duration` (Trend)
  - `ingestion_status_duration` (Trend)
  - `ingestion_export_duration` (Trend)
  - `ingestion_uploads_total` (Counter, > 100/min threshold)
- Test CSV generator for realistic payload
- Setup/teardown logging

### 2. Admin Service Load Test
**File:** `/sessions/gracious-cool-bell/mnt/RegEngine/tests/load/k6-admin-test.js`  
**Lines:** 230 | **Run with:** `BASE_URL=... API_KEY=... k6 run tests/load/k6-admin-test.js`

**Content:**
- Compliance-heavy workload:
  - Phase 1: FDA export endpoint (POST with format options)
  - Phase 2: Compliance status queries (GET with tenant isolation)
  - Phase 3: RLS Query Assessment (heavy DB filtering)
  - Phase 4: List exports (RLS-filtered pagination)
  - Phase 5: Audit log queries (read-only, high sensitivity)
- Custom metrics:
  - `admin_export_duration` (Trend)
  - `admin_status_duration` (Trend)
  - `admin_rqa_duration` (Trend)
  - `admin_exports_total` (Counter, > 100/min threshold)
- RLS isolation verification checks
- Cross-tenant data leakage detection

---

## Summary

### Runbooks (5 files, 1,383 lines)
- All under 400 lines (concise, executable)
- Follows existing neo4j-disaster-recovery.md format
- Ready for production use
- Single-person operation (Christopher)

### Load Tests (2 files, 442 lines)
- Both use k6 (same as existing user-journey.js)
- Environment variable support (BASE_URL, API_KEY)
- SLO thresholds: p95 < 2000ms, error < 1%, throughput > 100 req/s
- Ready to run immediately

### Files Created
1. `/sessions/gracious-cool-bell/mnt/RegEngine/runbooks/deploy-security-hardening.md` ✓
2. `/sessions/gracious-cool-bell/mnt/RegEngine/runbooks/incident-response.md` ✓
3. `/sessions/gracious-cool-bell/mnt/RegEngine/runbooks/rollback-procedure.md` ✓
4. `/sessions/gracious-cool-bell/mnt/RegEngine/runbooks/scaling-guide.md` ✓
5. `/sessions/gracious-cool-bell/mnt/RegEngine/runbooks/monitoring-alerts.md` ✓
6. `/sessions/gracious-cool-bell/mnt/RegEngine/tests/load/k6-ingestion-test.js` ✓
7. `/sessions/gracious-cool-bell/mnt/RegEngine/tests/load/k6-admin-test.js` ✓

### Next Steps
- Review runbooks for clarity and accuracy
- Run k6 tests against staging to verify endpoints
- Set up Prometheus scraping for k6 metrics
- Configure Alertmanager routing for incident runbook
