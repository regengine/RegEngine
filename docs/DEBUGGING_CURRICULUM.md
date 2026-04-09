# RegEngine Debugging Curriculum

**Version:** 1.0
**Created:** 2026-04-08
**Audience:** Engineering team (current + future hires)
**Format:** 10-week program, one module per week, real incident review as capstone

---

## How to Use This Document

Each module maps directly to RegEngine's stack, services, and known failure patterns. Examples reference real services, real configuration, and real incidents from the project's history. The curriculum progresses from individual contributor skills (Modules 1-4) through senior/staff-level practices (5-6), team-level practices (7-9), to organizational culture (10).

---

## Module 1: Foundations -- Know Your System Before It Breaks

### RegEngine Architecture Map

```
                        Vercel (frontend)
                              |
                     Next.js 15 App Router
                    TypeScript / React 18
                     Supabase Auth (JWT)
                              |
                    Railway (backend x3)
                   +---------+---------+
                   |         |         |
              admin-api  ingestion  compliance
              (8400)     (8000)     (8500)
                   |         |         |
                   +----+----+---------+
                        |
                  PostgreSQL 17 (Supabase)
                  - Row-Level Security
                  - Recursive CTEs (lot tracing)
                  - pg_notify (task queue)
                  - 53+ migrations (Alembic)
```

**Logical services** (all FastAPI, single monolith target):
| Service | Port | Owns |
|---------|------|------|
| Admin | 8400 | Tenants, auth, onboarding, users |
| Ingestion | 8000 | Webhooks, CSV/XLSX import, FDA export, scraping |
| Graph | 8200 | Supply chain traceability, recursive CTEs, lot tracing |
| NLP | 8100 | FSMA document extraction, regulatory text analysis |
| Compliance | 8500 | Obligation tracking, validation rules engine |
| Scheduler | -- | Background jobs, deadline monitoring, APScheduler |

**Shared libraries** (`services/shared/`):
- `auth.py` -- Authentication, constant-time comparison, fail-closed rate limiting
- `audit_logging.py` -- SHA-256 hash-chained audit trail
- `canonical_event.py` -- FSMA event definition (single source of truth)
- `cte_persistence.py` -- Critical Traceability Event storage
- `fsma_validation.py` -- Requirement validation
- `identity_resolution.py` -- Entity/facility reference resolution
- `exception_queue.py` -- Remediation queue for validation exceptions
- `api_key_store.py` -- API key validation with rate limiting
- `base_config.py` -- `BaseServiceSettings` + `ObjectStorageMixin`

### The Three Pillars of Observability in RegEngine

| Pillar | Tool | Where to Look |
|--------|------|---------------|
| **Logs** | structlog + python-json-logger | Railway logs, `docker-compose logs -f <service>` |
| **Metrics** | Prometheus + Grafana | `docker-compose --profile monitoring up`, exporters for postgres/redis/node |
| **Traces** | OpenTelemetry + Jaeger | `http://localhost:16686` (local), Sentry (prod) |

**Key:** All three are configured in `docker-compose.yml`. Production uses Sentry for errors and PostHog for product analytics.

### SLAs, SLOs, and SLIs -- What "Broken" Means

Defined in `docs/nfr/slos.yaml`:

| SLI | Target | What It Means for Customers |
|-----|--------|----------------------------|
| Trace latency (p95) | 2000ms | Lot tracing must return in <2s or recall drill is too slow |
| Availability | 99.9% (30d) | ~43 min/month downtime budget |
| Ingestion throughput | 10K events/min sustained | Bulk CSV imports must not queue-starve the system |
| Recall drill creation (p95) | 3000ms | FDA 24-hour clock is ticking -- drill setup can't be slow |
| Export generation (p95) | 5000ms | FDA records request response time |

**Business context:** FSMA 204 compliance deadline is July 20, 2028. A customer in an active FDA recall has a 24-hour response window. If RegEngine can't produce an FDA package in that window, the customer faces enforcement action.

### Environment Awareness

| Environment | Frontend | Backend | Database | Key Differences |
|-------------|----------|---------|----------|-----------------|
| **Local dev** | `localhost:3000` | Docker services (ports 8000-8500) | Local PostgreSQL + Neo4j + Redis | All 15+ containers, full stack |
| **Staging** | Vercel preview | Railway (dev) | Supabase (dev project) | Feature flags may differ |
| **Production** | Vercel Pro | Railway Pro (3 services) | Supabase Pro | RLS enforced, preshared key auth |

**Config drift risks:**
- `.env.example` has 60+ variables -- any mismatch between local and Railway can cause silent failures
- `REGENGINE_ENV` controls behavior: `development` / `test` / `production`
- `ENABLE_PCOS` feature flag changes compliance scoring behavior
- Auth: JWT 30-day expiry, cookies 30-day expiry, middleware graceful fallback
- Vercel env vars: `ADMIN_SERVICE_URL` must be set (C1 from API audit)

### Where the Bodies Are Buried

Known fragile areas (from audits and incident history):

| Area | Risk | File(s) |
|------|------|---------|
| Auth fallthrough | Supabase down = silent JWT fallback, no logging | `services/shared/auth.py` |
| No token refresh | Long compliance workflows lose session | Frontend middleware |
| ~470 bare `except Exception` | Swallows real errors silently | Scattered across backend |
| Dual migration system | Alembic + raw SQL, overlapping version numbers | `migrations/` |
| Neo4j Cypher injection | Fixed in M8 but pattern could recur | `services/graph/` |
| Hardcoded test passwords | Default API key in source | Multiple test files |
| 130 mock/fallback files | Demo data can mask real API failures | Frontend `lib/` |

**Exercise:** Pick one service. Draw its dependency chain from HTTP request to database query to response. Identify every point where a failure would produce a user-visible error vs. a silent degradation.

---

## Module 2: Triage & Classification

### Severity Assessment for RegEngine

| Severity | Definition | RegEngine Examples |
|----------|------------|-------------------|
| **P0** | Data loss, compliance failure, active recall blocked | FDA export produces wrong data; audit trail chain broken; CTE events lost; recall drill can't complete |
| **P1** | Core workflow blocked, no workaround | Ingestion pipeline down; bulk CSV import fails; compliance scoring returns wrong results |
| **P2** | Feature degraded, workaround exists | Graph tracing slow but functional; NLP extraction partial; dashboard shows stale data |
| **P3** | Cosmetic, minor UX issue | UI alignment, non-critical page 404, demo data showing where real data expected |

**The compliance multiplier:** Any bug that affects data integrity in the canonical event store, the audit trail hash chain, or FDA export formats is automatically P0, regardless of how many users are affected. A single corrupted CTE record can invalidate an entire recall response.

### Blast Radius Estimation

```
Request arrives at Vercel
  -> Frontend renders (React Query cache)
    -> API call to Railway (admin/ingestion/compliance)
      -> PostgreSQL query (RLS scoped to tenant)
        -> Response with canonical data

Failure at each layer:
  Vercel down    = ALL customers, ALL features
  Railway down   = ALL customers, API features only (cached UI still loads)
  One service    = Specific workflows (e.g., ingestion down = no imports, but compliance scoring works)
  PostgreSQL     = ALL customers, ALL data (P0 by definition)
  RLS policy bug = Data leak between tenants (P0, security incident)
```

**Multi-tenancy amplifier:** Because RegEngine uses Row-Level Security, a bug in RLS policies doesn't just affect one customer -- it potentially exposes every tenant's data to every other tenant. Any RLS-related bug is an automatic P0 security incident.

### Signal vs. Noise in RegEngine

| Signal (investigate) | Noise (probably safe to ignore) |
|---------------------|---------------------------------|
| Hash chain verification failure in audit log | Flaky Neo4j connection during migration away from Neo4j |
| `check_blocking_defects()` returning unexpected blockers | Rate limiter triggering on internal health checks |
| Canonical event validation rejecting known-good data | PostHog analytics events failing to send |
| RLS policy returning rows from wrong tenant | Sentry capturing handled demo-data fallbacks |
| Migration version conflict between Alembic and raw SQL | Redis connection timeout when Redis is being phased out |

### Categorization Checklist

When a bug arrives, classify it:

- [ ] **Regression** -- did this work before? Check `git log` for recent changes to the affected service
- [ ] **Infrastructure** -- is Railway/Supabase/Vercel having an incident? Check status pages
- [ ] **Data corruption** -- is the canonical event store or audit trail affected? If yes, P0 immediately
- [ ] **Race condition** -- does it only happen under concurrent ingestion or bulk operations?
- [ ] **Config error** -- did an env var change? Check Railway dashboard vs. `.env.example`
- [ ] **Third-party** -- is Supabase Auth, PostHog, or Sentry the root cause?
- [ ] **Schema mismatch** -- was a migration applied to prod but not the code that uses it (or vice versa)?

### The First 5 Minutes

1. **Capture state before it changes:**
   - Railway logs for the affected service (last 30 min)
   - Sentry error details (stack trace, breadcrumbs, user context)
   - `SELECT count(*) FROM canonical_events WHERE created_at > now() - interval '1 hour'` (is ingestion still flowing?)
   - Current migration version: `SELECT version_num FROM alembic_version`

2. **Notify:**
   - If P0: document in incident channel immediately
   - If data integrity: check audit trail hash chain verification
   - If multi-tenant: verify RLS is not leaking (`SET app.current_tenant = '<other_tenant_id>'; SELECT ...`)

3. **Preserve evidence:**
   - Screenshot or copy the exact error before retrying
   - Note the tenant_id, user_id, and request_id if available
   - Check if the issue is tenant-specific or global

**Exercise:** You receive a Sentry alert: `IntegrityError: duplicate key value violates unique constraint "canonical_events_pkey"`. Walk through the triage checklist. What's the severity? What's the blast radius? What do you capture first?

---

## Module 3: Reproduction

### The Discipline of "Reproduce Before You Fix"

RegEngine's compliance domain makes this non-negotiable. A "fix" that doesn't address the actual root cause could:
- Silently corrupt the canonical event store
- Break the audit trail hash chain
- Cause FDA export to produce incorrect data
- Pass in dev but fail under production RLS policies

**Rule:** No PR gets merged for a bug fix without a reproduction case, either as a test or documented steps.

### Gathering Reproduction Steps

RegEngine-specific data to collect from vague reports:

```
1. Which tenant? (tenant_id from JWT or URL)
2. Which CTE type? (Harvesting, Cooling, Initial Packing, FLBR, Shipping, Receiving, Transformation)
3. What was the input? (CSV upload, webhook payload, manual entry, API call)
4. What was expected vs. actual?
5. Which page/endpoint? (64+ frontend routes, check browser URL)
6. What does the compliance score show? (6 dimensions -- which one is wrong?)
7. Is this during a recall drill or normal operation?
```

### Environment-Specific Reproduction

| Production behavior | Local reproduction approach |
|---------------------|-----------------------------|
| RLS blocks the query | Set `app.current_tenant` in psql session before running query |
| Preshared key auth rejects | Check `REGENGINE_INTERNAL_SECRET` matches between services |
| Supabase Auth JWT differs | Use local JWT generation with matching secret |
| Railway memory limits | Run with `docker-compose` resource limits matching Railway plan |
| Migration state differs | Run `alembic upgrade head` and verify `alembic_version` table |

**Critical:** Production uses Supabase-managed PostgreSQL with RLS enforced. Local dev often runs with RLS disabled or with a superuser connection that bypasses policies. Always test RLS-dependent bugs with a non-superuser role.

### Non-Deterministic Bugs in RegEngine

| Pattern | Where It Happens | How to Reproduce |
|---------|-----------------|------------------|
| Race condition | Concurrent CSV imports writing to same lot code | `pytest tests/load/` with concurrent workers |
| Timing-dependent | pg_notify task processing order | Add artificial delays, test with `asyncio.sleep` |
| Load-dependent | Bulk ingestion > 10K events/min | `tests/load/` performance suite |
| Order-dependent | Migration application order (Alembic vs raw SQL) | Fresh database, apply migrations from scratch |
| Auth-dependent | Token expiry during long compliance workflow | Set JWT expiry to 60s, run full workflow |

### When You Can't Reproduce

```
1. Check Sentry breadcrumbs for the exact request path
2. Query the audit log: SELECT * FROM audit_log WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 50
3. Check if the canonical event has an amendment chain: SELECT * FROM canonical_events WHERE supersedes_event_id IS NOT NULL
4. Compare the raw vs. normalized payload in the canonical event
5. Check if the compliance score calculation inputs match expectations
6. Look for "demo data fallback" -- the frontend falls back to mock data when API calls fail (130 mock files)
```

**Exercise:** A customer reports "my compliance score dropped from 94% to 67% overnight but I didn't change anything." Build a reproduction plan. What data do you need? Where do you look first? (Hint: check if `ENABLE_PCOS` changed, if new obligations were added, or if the hardcoded 94% fallback was removed.)

---

## Module 4: Isolation & Root Cause Analysis

### Binary Search Debugging in RegEngine

The canonical ingestion pipeline has clear stages. Bisect at each boundary:

```
Raw Input (CSV/webhook/API)
  -> Parsing (format-specific)
    -> Validation (fsma_validation.py)
      -> Normalization (canonical_event.py)
        -> Persistence (cte_persistence.py)
          -> Identity Resolution (identity_resolution.py)
            -> Compliance Scoring (6 dimensions)
              -> FDA Export (CSV/PDF/ZIP)
```

**Isolation technique:** Insert a known-good canonical event directly into the database. Does the compliance score calculate correctly? If yes, the bug is upstream (parsing/validation/normalization). If no, the bug is downstream (scoring/export).

### Dependency Isolation

| Symptom | Is it your code? | Is it the library? | Is it the infra? | Is it the data? |
|---------|-----------------|-------------------|-------------------|-----------------|
| 500 from admin-api | Check FastAPI route handler | Check SQLAlchemy query | Check Railway health / PostgreSQL | Check tenant data integrity |
| Compliance score wrong | Check scoring algorithm | Check fsma_rules.json | Check if migration V044 applied | Check if CTE records are complete |
| Graph trace incomplete | Check recursive CTE query | Check pg_trgm extension | Check PostgreSQL query plan | Check if lot codes are linked |
| NLP extraction fails | Check spaCy pipeline | Check model version | Check memory limits | Check document format |
| Audit trail broken | Check hash chain logic | Check hashlib behavior | Check transaction isolation | Check for concurrent writes |

### Diff-Based Debugging: "What Changed?"

RegEngine has 11 CI workflows with 54 quality checks. When something breaks:

```bash
# What deployed recently?
git log --oneline -20

# What changed in the affected service?
git diff HEAD~5..HEAD -- services/<service_name>/

# What migrations ran?
SELECT version_num, applied_at FROM alembic_version ORDER BY applied_at DESC;

# What config changed? (Railway dashboard -- no CLI equivalent yet)
# Check .env.example for new variables that might not be set in prod

# What traffic pattern changed?
# Check PostHog for usage spikes
# Check Sentry for new error patterns
```

### The Five Whys -- RegEngine Edition

**Example: FDA export produces CSV with missing columns**

1. **Why are columns missing?** The export template doesn't include `event_entry_timestamp`.
2. **Why isn't it in the template?** The column was added in migration V043 but the export code wasn't updated.
3. **Why wasn't the export code updated?** The migration and the export are in different services with no integration test between them.
4. **Why is there no integration test?** The E2E test (`test_e2e_fda_request.py`) was written after the migration but before the export change.
5. **Why did CI pass?** The test uses mock data that includes the column, not real database data.

**Root cause:** Test/production data divergence. **Fix:** Integration test that runs against a real database with migration-created schema.

### Common Root Cause Patterns in RegEngine

| Pattern | RegEngine Manifestation |
|---------|------------------------|
| **Resource exhaustion** | Railway container OOM during bulk NLP processing (spaCy model loading) |
| **Cascading failure** | Supabase Auth down -> silent JWT fallback -> stale sessions -> wrong tenant data |
| **Schema mismatch** | Alembic migration applied but raw SQL migration in `migrations/` not run (dual system) |
| **Retry storm** | `apiFetch` exponential backoff + React Query retry = 3 x 3 = 9 retries per failed request |
| **Data corruption** | Bare `except Exception` swallowing a validation error, allowing bad data into canonical store |
| **Tenant isolation break** | Missing `tenant_id` in a WHERE clause or Neo4j MERGE key (M8 from audit) |
| **Clock skew** | `event_entry_timestamp` vs `created_at` vs `event_date` confusion in compliance calculations |

### Reading Stack Traces in RegEngine

FastAPI + SQLAlchemy + Pydantic stack traces have a specific shape:

```
# Layer 1: FastAPI route handler
File "services/admin/routes.py", line 142, in create_tenant
# Layer 2: Service logic
File "services/shared/auth.py", line 89, in verify_token
# Layer 3: Database
File "sqlalchemy/engine/base.py", line 1900, in execute
# Layer 4: PostgreSQL driver
psycopg.errors.UniqueViolation: duplicate key value violates unique constraint

KEY INSIGHT: The real bug is usually at Layer 1 or 2. Layers 3-4 are just
the messenger. Look at what YOUR code passed to the database, not at what
the database complained about.
```

**Exercise:** You see this in Sentry: `sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection to server at "db.supabase.co" refused`. Walk through dependency isolation. Is it your code, the library, the infra, or the data? What's your first diagnostic step?

---

## Module 5: Instrumentation & Tooling

### Structured Logging in RegEngine

RegEngine uses `structlog` + `python-json-logger`. Every log entry should include:

```python
# Required context in every log line:
{
    "tenant_id": "uuid",          # WHO is affected
    "request_id": "uuid",         # Correlation ID for tracing
    "service": "admin|ingestion|compliance|graph|nlp|scheduler",
    "event": "human_readable",    # WHAT happened
    "level": "info|warning|error",
    "timestamp": "iso8601"        # WHEN
}

# For compliance-critical operations, also include:
{
    "cte_type": "Shipping|Receiving|...",
    "event_id": "uuid",           # Canonical event reference
    "audit_hash": "sha256"        # Hash chain reference
}
```

**Log levels in RegEngine context:**
- `ERROR`: Something that affects data integrity, compliance scoring, or user workflows
- `WARNING`: Degraded operation (demo fallback activated, retry triggered, rate limit approaching)
- `INFO`: Normal operations (event ingested, export generated, compliance score calculated)
- `DEBUG`: Diagnostic detail (SQL queries, payload contents, auth token claims)

### Distributed Tracing

RegEngine uses OpenTelemetry 1.30.0 (all 4 packages must version-match):

```
Frontend (Next.js instrumentation.ts)
  -> Vercel proxy route (/api/proxy/*)
    -> Railway service (FastAPI instrumentation)
      -> PostgreSQL (auto-instrumented)
      -> Neo4j (if still connected)
      -> Redis (if still connected)
```

**Local tracing:** Jaeger UI at `http://localhost:16686` (started via `docker-compose`).
**Production tracing:** Sentry Performance tab (traces are sent via OpenTelemetry -> Sentry).

**Key traces to watch:**
- `POST /api/v1/ingestion/webhook` -- full ingestion pipeline
- `GET /api/v1/compliance/score/{tenant_id}` -- compliance scoring
- `GET /api/v1/graph/trace/{lot_code}` -- supply chain traversal
- `POST /api/v1/requests/{id}/submit` -- FDA package submission (most complex)

### Profiling RegEngine

| What to Profile | Tool | When |
|----------------|------|------|
| Slow API endpoints | Sentry Performance | p95 > SLO threshold |
| Database queries | `EXPLAIN ANALYZE` in psql | Any query > 100ms |
| Recursive CTE depth | `EXPLAIN (ANALYZE, BUFFERS)` | Lot tracing > 3 hops |
| Memory usage | Railway metrics dashboard | NLP service (spaCy model = ~500MB) |
| Frontend bundle | `npx next build --analyze` | Bundle > 500KB per route |
| React renders | React DevTools Profiler | Dashboard feels sluggish |

### Database Debugging

```sql
-- Active queries (find long-running operations)
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC;

-- Lock contention (bulk imports can cause this)
SELECT blocked_locks.pid AS blocked_pid,
       blocking_locks.pid AS blocking_pid,
       blocked_activity.query AS blocked_query
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
WHERE NOT blocked_locks.granted;

-- RLS policy verification (CRITICAL for tenant isolation)
SET app.current_tenant = '<tenant_id>';
EXPLAIN ANALYZE SELECT * FROM canonical_events WHERE tenant_id = '<other_tenant_id>';
-- Should return 0 rows even though rows exist

-- Migration state
SELECT * FROM alembic_version;

-- Audit trail integrity check
SELECT e1.id, e1.chain_hash, e2.chain_hash as expected
FROM audit_log e1
JOIN audit_log e2 ON e2.id = e1.id - 1
WHERE e1.chain_hash != sha256(e2.chain_hash || e1.content_hash);
```

### Network-Level Debugging

```bash
# Verify Railway service is reachable from Vercel proxy
curl -H "X-Internal-Secret: $REGENGINE_INTERNAL_SECRET" \
     https://<railway-url>/health

# Check if preshared key auth is the problem
# (Vercel proxy adds X-Internal-Secret header; Railway validates it)
# Missing or mismatched = 401/403

# DNS resolution for Supabase
dig db.<project-ref>.supabase.co

# TLS certificate check (Railway auto-manages, but Supabase custom domains may not)
openssl s_client -connect <host>:443 -servername <host> </dev/null 2>/dev/null | openssl x509 -dates
```

**Exercise:** A customer reports that lot tracing is taking 15 seconds (SLO is 2s at p95). Walk through the profiling steps. What's your first query? Where do you look in Jaeger? What would you `EXPLAIN ANALYZE`?

---

## Module 6: Debugging Under Pressure (Incident Response)

### RegEngine Incident Roles

For a solo founder (current state), all roles collapse to one person. As the team grows:

| Role | Responsibility | RegEngine Context |
|------|---------------|-------------------|
| **Incident Commander** | Drives investigation, makes decisions | Decides: rollback vs. hotfix vs. feature-flag |
| **Investigator** | Digs into logs, traces, queries | Railway logs, Sentry, psql |
| **Communicator** | Updates stakeholders | Customer Slack, status page, investor updates |

### Communication Cadence

```
T+0:   "We're aware of [symptom]. Investigating."
T+15m: "Root cause identified as [X]. Working on [mitigation]."
T+30m: "Mitigation applied: [what you did]. Monitoring for [metric]."
T+1h:  "Incident resolved. [Brief summary]. Postmortem to follow."
```

**For RegEngine specifically:** If the incident affects FDA export or recall drill capability, explicitly note: "Recall drill capability is [affected/not affected]. FDA export is [affected/not affected]."

### Mitigation Playbook

| Symptom | Immediate Mitigation | How |
|---------|---------------------|-----|
| API returning 500s | Rollback Railway deployment | Railway dashboard -> Deployments -> Rollback |
| Frontend broken | Rollback Vercel deployment | `vercel rollback` or Vercel dashboard |
| Database schema broken | Point-in-time recovery | Supabase dashboard -> Database -> Backups |
| Auth completely down | Enable local JWT fallback (it's already there -- this is the auth fallthrough "bug") | This is the one case where the silent fallback is actually useful |
| Compliance scoring wrong | Disable blocking enforcement temporarily | Feature flag or config change |
| Data corrupted | Stop ingestion, assess blast radius, plan data repair | Kill ingestion service on Railway, query extent of damage |
| Recall drill blocked | Manual FDA package assembly from database exports | Direct SQL export of canonical events for the affected lots |

### War Room Discipline

**One theory at a time.** When debugging under pressure, resist the urge to chase multiple hypotheses simultaneously. Instead:

1. State the hypothesis: "I think the bulk CSV import is causing lock contention on canonical_events"
2. Define the test: "Run `SELECT * FROM pg_locks WHERE NOT granted` during a bulk import"
3. Time-box: 10 minutes per hypothesis
4. If disproven, move to next hypothesis. Document what you ruled out.

### When to Escalate

| Situation | Escalate To |
|-----------|-------------|
| Supabase Auth service degradation | Supabase support (status.supabase.com) |
| Railway container won't start | Railway support (Discord or dashboard) |
| Vercel build failures not caused by code | Vercel support |
| PostgreSQL corruption (not a migration bug) | Supabase support -- do NOT attempt manual repair |
| OpenTelemetry data loss | Check OTEL collector config, not the application |

**Exercise:** It's 2am. Sentry fires: `CRITICAL: audit_log chain_hash mismatch detected`. What do you do? Walk through the first 15 minutes. Who do you notify? What do you mitigate? What do you NOT touch?

---

## Module 7: Fix Development & Verification

### The Smallest Possible Fix

**Incident fix checklist:**
- [ ] Does this fix ONLY the bug, with no refactoring?
- [ ] Is the fix smaller than 50 lines of code?
- [ ] Does it have a test that fails before and passes after?
- [ ] Does it pass all 54 CI quality checks?
- [ ] If it touches `services/shared/`, have you verified it doesn't break other services?

**RegEngine-specific constraint:** If the fix touches anything in the canonical pipeline (canonical_event.py, cte_persistence.py, fsma_validation.py), it needs the 12-step E2E integration test to pass: `pytest tests/test_e2e_fda_request.py -v`.

### Regression Testing

```bash
# Minimum test coverage for any fix:
pytest tests/ -k "test_relevant_module" -v

# If the fix touches shared libraries:
pytest tests/shared/ -v
pytest tests/security/ -v  # Especially tenant isolation

# If the fix touches compliance:
pytest tests/compliance/ -v
pytest tests/data_integrity/ -v

# If the fix touches auth:
pytest tests/security/test_tenant_isolation.py -v
pytest tests/security/test_session_security.py -v

# Full E2E (if canonical pipeline is affected):
pytest tests/test_e2e_fda_request.py -v

# Frontend (if UI is affected):
cd frontend && npx vitest run
cd frontend && npx playwright test
```

### Canary Deployments

RegEngine's deployment topology supports staged rollout:

1. **Vercel preview deployment** -- every PR gets a preview URL automatically
2. **Railway staging** -- deploy to staging environment first
3. **Production** -- only after staging verification

For risky fixes:
- Deploy backend change to Railway staging
- Point Vercel preview at Railway staging
- Run the affected workflow end-to-end in preview
- Then promote to production

### Data Repair

When a bug corrupts state in RegEngine, fixing the code isn't enough. The canonical event store and audit trail have integrity guarantees:

```sql
-- 1. Identify affected records
SELECT id, tenant_id, cte_type, created_at
FROM canonical_events
WHERE [condition matching the bug]
ORDER BY created_at;

-- 2. Check if audit trail is affected
SELECT id, content_hash, chain_hash
FROM audit_log
WHERE event_id IN (SELECT id FROM canonical_events WHERE [condition]);

-- 3. If records need correction, use the amendment chain (NOT direct UPDATE)
-- The canonical model supports corrections via supersedes_event_id:
INSERT INTO canonical_events (
    tenant_id, cte_type, supersedes_event_id, ...
) VALUES (
    ..., '<original_event_id>', ...
);

-- 4. NEVER delete canonical events or audit log entries
-- The hash chain would break. Use amendment/supersede pattern instead.
```

### Rollback Planning

Before deploying any fix, document:

| Question | Answer |
|----------|--------|
| Can this be rolled back? | Railway: yes (instant). Vercel: yes (instant). Database migration: maybe (down migration written?) |
| What happens if the fix makes things worse? | [Specific worst case for this fix] |
| Is there a feature flag that can disable this code path? | Check `ENABLE_PCOS` and `/api/v1/features` |
| How long until we know if the fix worked? | [Metric to watch, expected recovery time] |

**Exercise:** You've identified that a bulk import bug is writing duplicate canonical events. Write the smallest fix, the regression test, and the data repair plan. Remember: you can't delete canonical events (hash chain), so how do you handle the duplicates?

---

## Module 8: Post-Incident Review

### Blameless Postmortem Template for RegEngine

```markdown
## Incident: [Title]
**Date:** [Date]
**Duration:** [Start to resolution]
**Severity:** P0/P1/P2/P3
**Impact:** [Users affected, data affected, compliance impact]

## Timeline
| Time | Event |
|------|-------|
| T+0  | [Trigger / first alert] |
| T+Xm | [Key investigation steps] |
| T+Xm | [Mitigation applied] |
| T+Xm | [Resolution confirmed] |

## Root Cause
[What actually caused the incident. Be specific. Name the file, the line, the query, the config.]

## Contributing Factors
1. [Factor 1 -- e.g., "bare except Exception swallowed the validation error"]
2. [Factor 2 -- e.g., "no integration test for this code path"]
3. [Factor 3 -- e.g., "staging doesn't have RLS enabled, so bug wasn't caught"]

## What Went Well
- [Things that helped detection, mitigation, or resolution]

## What Went Wrong
- [Things that delayed detection, mitigation, or resolution]

## Action Items
| Item | Owner | Due | Type |
|------|-------|-----|------|
| [Specific action] | [Name] | [Date] | Prevent / Detect / Mitigate |

## Compliance Impact
- [ ] Was the canonical event store affected?
- [ ] Was the audit trail hash chain affected?
- [ ] Would this have impacted an active FDA recall response?
- [ ] Do we need to notify affected tenants?
```

### Action Items That Actually Prevent Recurrence

**Bad action items** (don't do these):
- "Be more careful when writing migrations"
- "Review code more thoroughly"
- "Add more tests"

**Good action items** (do these):
- "Add CI check that verifies every canonical_events column is included in FDA export template" -- prevents the specific class of bug
- "Replace 10 bare `except Exception` in ingestion service with specific exception types" -- prevents error swallowing
- "Add RLS-enabled test user to integration test suite" -- catches tenant isolation bugs before prod
- "Add `event_entry_timestamp IS NOT NULL` constraint to canonical_events" -- database enforces the invariant

### Measuring MTTR

Track for each incident:
- **Time to detect:** Alert fired -> human acknowledged
- **Time to triage:** Acknowledged -> severity assigned, correct person investigating
- **Time to mitigate:** Investigating -> customer impact reduced/eliminated
- **Time to resolve:** Mitigated -> root cause fixed and deployed

**RegEngine target MTTRs:**
| Severity | Detect | Mitigate | Resolve |
|----------|--------|----------|---------|
| P0 | < 5 min (Sentry alert) | < 30 min | < 4 hours |
| P1 | < 15 min | < 1 hour | < 24 hours |
| P2 | < 1 hour | < 4 hours | Next sprint |

**Exercise:** Write a postmortem for this scenario: A migration added a NOT NULL column to canonical_events without a default value. The migration succeeded (table was empty in staging) but failed in production (table had data). Ingestion was down for 45 minutes.

---

## Module 9: Systemic Prevention

### Chaos Engineering for RegEngine

Start small. RegEngine's pre-revenue status means chaos experiments should be local/staging only:

| Experiment | What to Break | What to Watch |
|------------|--------------|---------------|
| Kill Supabase Auth | Block auth endpoint in `/etc/hosts` | Does the silent JWT fallback work? Does it log? |
| Slow database | `SET statement_timeout = '100ms'` in test | Do API endpoints return useful errors or 500? |
| Corrupt a canonical event | INSERT with wrong hash | Does compliance scoring catch it? Does audit verification fail? |
| Exceed rate limit | Flood an endpoint | Does rate limiting work? Does it fail closed? |
| Revoke RLS policy | Drop a policy in staging | Do queries return cross-tenant data? |

### Error Budgets

Based on `docs/nfr/slos.yaml`:

```
Availability SLO: 99.9% (30-day rolling)
Error budget: 0.1% = 43.2 minutes/month

If you've burned 30 minutes this month on incidents:
  -> 13 minutes remaining
  -> Freeze risky deployments
  -> Focus on reliability work

If you have full budget:
  -> Safe to ship new features
  -> Safe to run chaos experiments
```

### Code Review Through a Debuggability Lens

When reviewing PRs, ask:

- [ ] If this fails at 2am, will the logs tell me what happened?
- [ ] Is there a bare `except Exception` that would swallow the real error?
- [ ] If the database query is slow, will I be able to find it in traces?
- [ ] If this produces wrong data, will the compliance scoring catch it?
- [ ] Is the tenant_id in every WHERE clause and every Neo4j MERGE key?
- [ ] If I need to rollback this change, is there a down migration?
- [ ] Does this maintain the audit trail hash chain?

### Designing for Observability

**RegEngine's observability stack:**

```
Application Code
  |-- structlog (structured JSON logs)
  |-- OpenTelemetry SDK (traces + metrics)
  |-- Sentry SDK (errors + performance)
  |-- PostHog SDK (product analytics)
  |
  v
OpenTelemetry Collector (otel-collector in docker-compose)
  |-- Jaeger (local trace visualization)
  |-- Prometheus (metrics scraping)
  |-- Grafana (dashboards)
  |     |-- postgres-exporter
  |     |-- redis-exporter
  |     |-- node-exporter
  v
Production: Sentry (errors + traces) + PostHog (analytics)
```

**Health checks** -- every service exposes `/health`:
```python
@app.get("/health")
async def health():
    # Check database connectivity
    # Check migration version matches expected
    # Return service version, uptime, dependency status
```

### Runbooks

RegEngine already has operational runbooks. Key ones:

| Runbook | Location | Covers |
|---------|----------|--------|
| Operations | `docs/OPERATIONS.md` | Starting stack, health checks, common issues |
| Credential Rotation | `docs/CREDENTIAL_ROTATION_RUNBOOK.md` | Rotating secrets, API keys |
| Disaster Recovery | `docs/DISASTER_RECOVERY.md` | Backup procedures, RTO/RPO targets |
| RLS Deployment | `docs/rls_deployment_runbook.md` | Row-Level Security changes |
| Production Checklist | `docs/PRODUCTION_READINESS_CHECKLIST.md` | Pre-deploy verification |
| Security Hardening | `docs/DEPLOY_CHECKLIST_SECURITY_HARDENING.md` | Security deployment steps |

**Missing runbooks to create:**
- Bulk data repair (canonical events)
- FDA recall response (24-hour clock)
- Tenant data migration
- Migration rollback (Alembic down)

### Dependency Management

| Dependency | Risk Level | Mitigation |
|------------|-----------|------------|
| Supabase (Auth + DB) | High -- single point of failure | Silent JWT fallback (auth), daily backups (DB) |
| Railway (compute) | Medium -- instant rollback available | Preview deployments, health checks |
| Vercel (frontend) | Low -- static assets cached at edge | Instant rollback, preview URLs |
| OpenTelemetry 1.30.0 | Medium -- all 4 packages MUST version-match | Pinned in pyproject.toml |
| Sentry 1.40.0+ | Low -- degraded observability only | Pinned, not on critical path |
| spaCy | Medium -- large model, memory-heavy | Pin model version, monitor memory |

**Exercise:** Design a runbook for "Canonical event store audit trail hash chain is broken." Include: detection, blast radius assessment, mitigation, repair steps, and verification.

---

## Module 10: Team & Culture

### Knowledge Transfer

**Current state:** Solo founder with deep context. Every piece of debugging knowledge is in one person's head (plus these docs and audit trails).

**Transfer mechanisms:**
1. This curriculum document
2. Existing runbooks in `docs/`
3. Git commit history with detailed messages
4. Audit trail in `docs/audits/`
5. Architecture Decision Records in `docs/architecture/decisions/`
6. 11 CI workflows that encode quality standards

**For new hires:**
- Week 1: Run the full stack locally (`docker-compose up`), read this curriculum Modules 1-2
- Week 2: Fix a P3 bug with pair debugging. Read Modules 3-4
- Week 3: Add a feature with observability (logs, traces). Read Modules 5-6
- Week 4: Run incident simulation (controlled chaos experiment in staging). Read Modules 7-8
- Month 2: On-call rotation begins (with senior backup)

### Pair Debugging Protocol

```
1. Driver: The person who reported or discovered the bug
   Navigator: A more experienced team member (or vice versa for training)

2. Driver shares their screen and walks through:
   - What they observed
   - What they've already tried
   - Their current hypothesis

3. Navigator asks:
   - "What does the log say?" (not "did you check the logs?")
   - "Can you show me the Sentry trace?"
   - "What changed since this last worked?"

4. Time-box: 30 minutes. If not solved, escalate or schedule a mob session.
```

### Bug Bashes

Monthly, 2-hour sessions focused on one area:

| Month | Focus Area | What to Look For |
|-------|-----------|-----------------|
| 1 | Canonical pipeline integrity | Malformed events, missing KDEs, broken hash chains |
| 2 | Tenant isolation | RLS bypass attempts, cross-tenant data leaks |
| 3 | Error handling | Bare `except Exception` audit, swallowed errors |
| 4 | Demo data cleanup | Mock fallbacks masking real API failures |
| 5 | Migration health | Dual system conflicts, missing down migrations |
| 6 | FDA export accuracy | Compare exports against FSMA 204 requirements |

### On-Call Rotation

**Prerequisites before going on-call:**
- [ ] Can start the full stack locally
- [ ] Has access to Railway, Vercel, Supabase dashboards
- [ ] Has Sentry alerts configured
- [ ] Has read all runbooks in `docs/`
- [ ] Has completed incident simulation (Module 6 exercise)
- [ ] Knows how to rollback each deployment target

**On-call expectations:**
- Acknowledge P0/P1 alerts within 15 minutes
- Mitigate within 30 minutes (rollback is always an option)
- Don't try to root-cause at 2am -- mitigate, go back to sleep, investigate in the morning
- Document everything in the incident channel

### Debugging Journal

Maintain a shared knowledge base of past incidents and patterns. Suggested structure:

```markdown
## [Date] - [Brief Title]
**Severity:** P0/P1/P2/P3
**Service:** admin / ingestion / compliance / graph / nlp / scheduler / frontend
**Pattern:** regression / infra / data corruption / race condition / config / third-party
**Root cause:** [One sentence]
**Key insight:** [What would have caught this faster]
**Related:** [Links to postmortem, PR, runbook]
```

Store in `docs/incidents/` with one file per incident.

---

## Capstone: Real Incident Simulation

### Scenario

You are on-call. It's 10pm on a Wednesday. A design partner is running their first real recall drill using RegEngine. They've loaded 5,000 CTE events over the past week. They click "Generate FDA Package" and get a spinner that never resolves.

**Your investigation will touch every module in this curriculum:**

1. **Module 1:** What services are involved in FDA package generation?
2. **Module 2:** What's the severity? (Hint: active recall drill, 24-hour FDA clock)
3. **Module 3:** Can you reproduce in staging with 5,000 events?
4. **Module 4:** Is it the query, the export, the network, or the frontend?
5. **Module 5:** What do the traces show? Where does the request spend its time?
6. **Module 6:** What do you tell the customer? What's the mitigation?
7. **Module 7:** What's the smallest fix? How do you verify it?
8. **Module 8:** What's the postmortem? What are the action items?
9. **Module 9:** What systemic change prevents this class of bug?
10. **Module 10:** How do you document this so the next engineer doesn't hit it?

**Grading criteria:**
- Did you mitigate before root-causing?
- Did you communicate to the customer?
- Did the fix include a regression test?
- Did the postmortem produce actionable items (not "be more careful")?
- Did you update or create a runbook?

---

## Appendix: Quick Reference

### Diagnostic Commands

```bash
# Service health
curl http://localhost:8400/health  # Admin
curl http://localhost:8000/health  # Ingestion
curl http://localhost:8500/health  # Compliance
curl http://localhost:8200/health  # Graph
curl http://localhost:8100/health  # NLP

# Logs (local)
docker-compose logs -f admin-api
docker-compose logs -f ingestion-service
docker-compose logs -f compliance-api

# Database
psql $DATABASE_URL -c "SELECT version_num FROM alembic_version;"
psql $DATABASE_URL -c "SELECT count(*) FROM canonical_events;"
psql $DATABASE_URL -c "SELECT * FROM pg_stat_activity WHERE state != 'idle';"

# Test suites
pytest tests/ -v                              # All tests
pytest tests/test_e2e_fda_request.py -v       # E2E pipeline
pytest tests/security/test_tenant_isolation.py # RLS verification
pytest tests/data_integrity/ -v               # Data invariants

# Frontend
cd frontend && npx vitest run                 # Unit tests
cd frontend && npx playwright test            # E2E tests
cd frontend && npx next build                 # Build verification
```

### Key Files for Debugging

| What You're Debugging | Start Here |
|-----------------------|------------|
| Auth failures | `services/shared/auth.py`, `frontend/src/middleware.ts` |
| Ingestion pipeline | `services/ingestion/routes.py`, `services/shared/canonical_event.py` |
| Compliance scoring | `services/compliance/`, `services/shared/fsma_validation.py` |
| Lot tracing | `services/graph/`, `services/shared/cte_persistence.py` |
| Tenant isolation | `migrations/` (RLS policies), `services/shared/auth.py` |
| Audit trail | `services/shared/audit_logging.py` |
| FDA export | `services/ingestion/` (export routes) |
| Frontend API calls | `frontend/src/hooks/use-api-query.ts`, `frontend/src/lib/api/` |
| Config / env vars | `.env.example`, `services/shared/base_config.py` |
