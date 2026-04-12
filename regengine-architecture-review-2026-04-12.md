# RegEngine Architecture Review

**Date:** April 12, 2026
**Scope:** Full system — backend, frontend, data layer, deployment, security, observability
**Audience:** Christopher (founder), future engineering hires

---

## 1. System Overview

RegEngine is a multi-tenant SaaS platform for FDA FSMA 204 food traceability compliance. It ingests supply chain data (documents, EDI, IoT sensors, federal sources), normalizes it into canonical traceability records, runs compliance rules, and provides a dashboard for food companies to prove regulatory readiness.

### Current Topology

```
                        ┌──────────────┐
                        │   Vercel CDN  │
                        │  (Next.js 14) │
                        └──────┬───────┘
                               │ rewrites /api/*
                               ▼
                    ┌──────────────────────┐
                    │   Railway (monolith)  │
                    │   FastAPI + Uvicorn   │
                    │   35+ routers         │
                    │   9 middleware layers  │
                    └──┬───┬───┬───┬───┬──┘
                       │   │   │   │   │
              ┌────────┘   │   │   │   └────────┐
              ▼            ▼   ▼   ▼            ▼
         PostgreSQL    Redis  Neo4j  Redpanda  Sentry/OTel
         (Supabase)                  (Kafka)
```

**Key architectural decision (March 2026):** Consolidated 6 microservices (ingestion, admin, graph, NLP, compliance, scheduler) into a single FastAPI monolith. Service boundaries preserved via router isolation and `DISABLED_ROUTERS` feature flags.

---

## 2. What's Working Well

**Multi-tenant isolation is layered correctly.** Tenant context flows through JWT claims → middleware → request.state → PostgreSQL RLS. Row-level security is enforced at the DB level with `FORCE ROW LEVEL SECURITY`, which means even a bug in application code can't leak cross-tenant data. This is the right design for a compliance product.

**The monolith consolidation was the right call.** For a solo founder, 6 Railway services meant 6 deployment pipelines, 6 sets of logs, and 6 health checks to babysit. The consolidated monolith with feature-flagged routers gives you the same logical separation with dramatically simpler operations. The `DISABLED_ROUTERS` env var is clever — it lets you turn features on/off per environment without code changes.

**Domain model is well-structured for FSMA 204.** The 7 CTE types (harvesting through transformation), KDE capture, lot-level traceability chains, and 24-hour FDA response workflow map cleanly to the regulatory requirements. The canonical persistence layer with amendment chains gives you audit-grade immutability.

**Middleware stack is production-grade.** Request size limits, per-tenant rate limiting, request timeouts, circuit breakers on external dependencies, structured logging, and request ID propagation — this is more mature than most seed-stage platforms.

**96 test files across services.** Not comprehensive coverage, but a solid foundation that covers the critical paths.

---

## 3. Architecture Gaps & Risks

### 3.1 CRITICAL: Single-Process Uvicorn

**The problem:** The monolith runs as a single Uvicorn process with no worker pool. This means one CPU core handles all request processing. Async I/O helps for database queries and HTTP calls, but any synchronous operation (PDF OCR via label vision, regex-heavy compliance rules, large CSV parsing) blocks the entire event loop.

**Impact:** Under moderate load (50+ concurrent requests), tail latency will spike. A single slow compliance evaluation blocks ingestion requests.

**Fix:** Add Gunicorn as the process manager with 2-4 Uvicorn workers:

```dockerfile
CMD ["gunicorn", "server.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "--bind", "0.0.0.0:8000"]
```

**Effort:** 1-2 hours. High impact.

### 3.2 CRITICAL: Migration Race Condition

**The problem:** The admin service runs `alembic upgrade head` at startup. If Railway scales to 2+ instances, both run migrations concurrently. PostgreSQL advisory locks help, but concurrent DDL can still deadlock or produce inconsistent state.

**Fix:** Decouple migrations from service startup. Options:
1. Railway deploy command (run migrations as a one-shot job before service starts)
2. Leader election via PostgreSQL advisory lock — first instance runs migrations, others wait
3. Separate migration step in CI/CD pipeline

**Effort:** 2-4 hours. Prevents a class of deployment failures.

### 3.3 HIGH: Scheduler Cannot Scale Horizontally

**The problem:** APScheduler's BlockingScheduler runs in a single thread. If you deploy two scheduler instances, every job runs twice (duplicate FDA scrapes, duplicate alerts, duplicate billing cycles).

**Fix options:**
1. **Short-term:** Add a PostgreSQL advisory lock at startup — only one scheduler instance acquires the lock. Others stay idle as hot standby.
2. **Medium-term:** Switch to APScheduler's distributed job store (PostgreSQL-backed) so jobs are claimed, not duplicated.
3. **Long-term:** Replace with Celery Beat + Redis broker for distributed task scheduling.

**Effort:** Option 1 is 2-3 hours. Option 2 is 1-2 days.

### 3.4 HIGH: Silent Degradation on Redis Failure

**The problem:** Rate limiting, circuit breakers, and JWT key registry all fall back to in-memory implementations when Redis is unavailable. This is logged but not alerted. In a multi-replica deployment, each instance tracks its own state — a tenant could get 4x their rate limit (one per replica), and circuit breakers won't coordinate.

**Fix:**
1. Add Sentry alerts on Redis fallback events (not just log lines)
2. Consider fail-closed for rate limiting — if Redis is down, reject requests above a conservative default rather than allowing unlimited throughput
3. Add a `/ready` endpoint that fails when Redis is unavailable (distinct from `/health`)

**Effort:** 3-4 hours.

### 3.5 MEDIUM: Tenant Header Spoofing — Mitigated but Verify

**The problem (was HIGH, now mitigated):** The `X-RegEngine-Tenant-ID` header was a spoofing vector. This has been addressed: the nginx gateway (`infra/gateway/nginx.conf`) strips the header on all external routes (`proxy_set_header X-RegEngine-Tenant-ID "";`), the middleware rejects unauthenticated header usage, and security tests (`tests/security/test_header_remediation.py`) verify the fix.

**Remaining action:** Verify the nginx gateway is deployed in production (not just in config). If Railway routes traffic directly to the monolith without nginx, the gateway stripping doesn't apply. Add the header-strip logic to the FastAPI middleware as defense-in-depth.

**Effort:** 1-2 hours to verify and add middleware-level stripping.

### 3.6 MEDIUM: No Database Failover

**The problem:** Single PostgreSQL instance on Supabase with no read replicas. If Supabase has an outage, RegEngine is fully down. No connection pooling (PgBouncer) configured — under load, connection exhaustion is likely.

**Fix:**
1. Enable Supabase connection pooling (they offer PgBouncer as a toggle)
2. Add a read replica for compliance report queries and audit log reads
3. Add DATABASE_URL health checks to the `/ready` endpoint

**Effort:** Pooling is a config change. Read replicas depend on Supabase plan.

### 3.7 MEDIUM: Neo4j Community Edition Limits

**The problem:** Neo4j Community Edition has no clustering, no online backup, and no role-based access. For a compliance product where graph relationships are core to traceability, this is a single point of failure with no HA story.

**Fix options:**
1. If graph queries are read-heavy and write-rare, consider migrating graph relationships to PostgreSQL with recursive CTEs (eliminates a dependency)
2. If graph is essential, budget for Neo4j Aura (managed HA) or Enterprise Edition
3. At minimum, add scheduled Neo4j backups

**Effort:** Migration is a multi-week project. Backups are a few hours.

### 3.8 MEDIUM: No API Versioning Strategy

**The problem:** 35+ routers are mounted directly. No `/v1/`, `/v2/` prefix strategy for breaking changes. The SDK publishes models that external clients depend on. A breaking change to `Record` or `TraceResult` will break integrations.

**Fix:** Establish API versioning now while the customer base is small. Router prefixes already use `/v1/` in some places — standardize it and document the deprecation policy.

**Effort:** 4-6 hours to audit and standardize.

### 3.9 LOW: Frontend Single-Region Deployment

**The problem:** Vercel functions are pinned to `sfo1`. For customers outside the US West Coast, API proxy latency adds 50-200ms per request.

**Fix:** Remove the region pin or set to `iad1` (US East, closer to most food company HQs). Vercel edge functions can also reduce cold starts.

**Effort:** Config change. Revisit when you have customers complaining about latency.

---

## 4. Data Architecture Assessment

### What's Stored Where

| Store | Purpose | Size Concern |
|-------|---------|-------------|
| PostgreSQL | Canonical records, CTE events, audit logs, users, tenants, billing, rules, exceptions | Audit logs and CTE events grow unbounded per tenant |
| Neo4j | Supply chain graph relationships, facility-to-lot tracing | Graph depth scales with supply chain complexity |
| Redis | JWT keys, rate limit buckets, circuit breaker state | Small footprint, ephemeral |
| Redpanda | Event streaming between ingestion → NLP → graph | Retention policy not visible in config |

### Data Retention

The `data_retention.py` module (24KB) exists with retention policies and archival scheduling. This is good — FSMA requires records be kept for 2 years, but you don't want audit logs growing forever. Verify that archival actually runs on a schedule and that archived data is queryable for regulatory audits.

### Migration Health

9 migrations from baseline consolidation (March 24) through today. The migration script handles fresh, existing, and managed databases correctly. The only concern is the race condition noted in 3.2.

---

## 5. Observability Assessment

| Layer | Tool | Status |
|-------|------|--------|
| Error tracking | Sentry | Configured with source maps |
| Distributed tracing | OpenTelemetry (1.30.0) | Pinned version, good |
| Structured logging | structlog (JSON) | Production-grade |
| Metrics | Prometheus export | Endpoints exist |
| Frontend analytics | PostHog | Product analytics |
| Uptime monitoring | Not visible | Gap |

**Gap:** No uptime monitoring (Pingdom, Better Uptime, etc.) or on-call rotation visible. For a compliance product, you need an SLA story. Even a free-tier UptimeRobot on `/health` would help.

**Gap:** Circuit breaker metrics are local counters only — not exported to Prometheus. You can't see "how often is Neo4j tripping the breaker?" in a dashboard.

---

## 6. Security Assessment

**Strengths:**
- RLS enforced at DB level with FORCE ROW LEVEL SECURITY
- HSTS with 2-year preload, X-Frame-Options DENY, strict CSP with nonces
- API key scoping with jurisdiction-based entitlements
- Request size limits (10MB) and timeouts (120s)
- Non-root Docker user (appuser, UID 1001)

**Concerns:**
- Master API key has no rotation mechanism
- JWT key revocation requires waiting for time-based rotation (no emergency revocation path)
- Test bypass token guarded by env check — verify this is never set in production
- CORS origins need auditing — verify only production domains are allowed

---

## 7. Recommended Priority Order

For a resource-constrained founder, here's the order I'd tackle these:

### This Week (2-4 hours total)
1. **Add Gunicorn workers** — biggest performance win for minimal effort
2. **Verify nginx gateway is active in production** (tenant header stripping) — security verification
3. **Enable Supabase connection pooling** — config change, prevents connection exhaustion

### Next 2 Weeks
4. **Decouple migrations from startup** — prevents deployment failures when scaling
5. **Add Redis failure alerting** — know when you're running degraded
6. **Add uptime monitoring** — free tier is fine, just need visibility

### Before First Enterprise Customer
7. **Scheduler leader election** — prevents duplicate job execution
8. **API versioning standardization** — breaking changes will lose customers
9. **Neo4j backup strategy** — compliance product needs graph data durability
10. **JWT emergency revocation path** — security requirement for enterprise deals

### When Revenue Justifies It
11. PostgreSQL read replicas
12. Neo4j migration or HA upgrade
13. Multi-region frontend deployment
14. Distributed rate limiting (fail-closed mode)

---

## 8. Architecture Decision Record: Monolith vs. Microservices

**Decision:** Consolidate 6 microservices into 1 monolith (March 2026)
**Status:** Correct for current stage

**When to revisit:** If any of these become true:
- A single router's resource usage (CPU/memory) is starving others
- You need to deploy one service 10x more frequently than others
- Team grows beyond 3-4 engineers and deployment coordination becomes a bottleneck
- A single service needs a different scaling profile (e.g., NLP needs GPU instances)

The monolith is the right architecture until you have the revenue and team size to justify the operational overhead of microservices. The preserved service boundaries (separate router files, shared library, feature flags) make a future split straightforward.

---

*Generated from codebase analysis on April 12, 2026. Recommendations assume solo founder constraints.*
