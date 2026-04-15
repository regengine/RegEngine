# Founder Knowledge

**Purpose:** The mental map that only the founder carries, made visible.
A new technical leader should read this before touching anything.

Last updated: 2026-04-14.

---

## Hidden Assumptions

### Auth and Environment Detection

- `REGENGINE_ENV` controls whether auth bypass tokens work. If unset in a cloud
  environment (Railway, Vercel), the code in `shared/env.py` **forces it to
  "production"** and logs a critical warning. This means auth bypass is impossible
  on Railway/Vercel even if you forget to set the variable. But in manual/local
  deploys outside of recognized cloud providers, the default is "development"
  which **enables auth bypass**.

- `AUTH_SECRET_KEY` (JWT signing) **must be identical** between the admin service
  (Railway) and the frontend (Vercel). If they differ, users authenticate
  successfully but every subsequent API call fails with 401. This is the #1
  cause of "login works but nothing loads" reports.

- The admin service uses `ADMIN_DATABASE_URL` (not `DATABASE_URL`). If you
  set up a new environment and only configure `DATABASE_URL`, the admin service
  will derive its connection string differently and may connect to the wrong
  database or fail silently.

### Supabase Is Optional (and Silently Absent)

- Supabase credential validation was **removed** after an H2 postmortem where
  validation failures caused production outages. `SupabaseManager.get_client()`
  now returns `None` if creds are missing.
- This means Supabase-dependent features (password reset, certain token flows)
  fail silently with only a warning log. If you expect Supabase to work, you
  must verify creds are set AND watch for warning-level logs.

### Tenant Context Resolution

- Tenant identity is resolved in this priority order (see `shared/middleware/tenant_context.py`):
  1. JWT token claims (user requests)
  2. `X-RegEngine-Tenant-ID` header — **only trusted** if `X-RegEngine-Internal-Secret`
     matches the `REGENGINE_INTERNAL_SECRET` env var. If the secret doesn't match,
     the header is silently ignored and tenant is derived from JWT/API key instead.
  3. API key lookup (maps key to tenant via api_key_store)
- If none of these resolve a tenant, the request proceeds **without tenant context**,
  which means RLS won't filter and the query may return cross-tenant data or fail.

### Scheduler Assumptions

- The scheduler service uses leader election — only one instance processes jobs.
  If you scale to multiple scheduler instances, only the elected leader runs
  APScheduler jobs. The others idle.
- The FSMA nightly sync job fires at 02:00 UTC daily and calls the ingestion
  service over HTTP. If the ingestion service is down at that time, the sync
  silently fails (logged, but no retry until the next 02:00 UTC run).
- The in-memory webhook DLQ in `scheduler/app/notifications.py` is **volatile** —
  lost on service restart. The persistent DLQ in `shared/webhook_dlq.py`
  (PostgreSQL-backed) survives restarts but is a separate system.

---

## Known Fragile Paths

### Dual-Write Migration (canonical_persistence.py)

- `canonical_persistence.py` writes to BOTH `fsma.traceability_events` (new canonical)
  AND `fsma.cte_events` (legacy). This dual-write is temporary but has been in
  place since the canonical model was introduced.
- Export and graph sync code still reads from `cte_events`. You cannot remove the
  dual-write until those consumers are migrated to read from `traceability_events`.
- The dual-write code is interleaved with the long-term persistence logic, not
  isolated behind a flag. Removing it requires careful surgery.

### EDI Segment Parsing (edi_ingestion.py)

- EDI X12 parsing is string-based with regex patterns matching segment positions.
  The mapping between EDI segment fields and CTE fields is implicit in the code,
  not in a configuration file. A single off-by-one in segment indexing silently
  produces wrong data.
- There are no snapshot tests for EDI → CTE transformation. Changes to the parser
  should be verified against known-good EDI input/output pairs.

### Hash Chain Integrity

- The hash chain in `fsma.hash_chain` is append-only and tamper-evident. Each
  entry's `chain_hash = SHA-256(previous_chain_hash | event_hash)`. The GENESIS
  block (first entry per tenant) has `previous_chain_hash = NULL`.
- If you manually insert or delete rows in `traceability_events` without going
  through `canonical_persistence.py`, the hash chain will be broken. There is
  no automatic repair mechanism — a broken chain requires manual investigation.
- The chain verification function is in `cte_persistence.py` (`verify_chain()`),
  but it verifies the legacy `cte_events` chain, not the canonical one. This
  is a gap.

### Frontend Service URL Resolution

- `frontend/src/lib/api-config.ts` resolves backend service URLs from env vars.
  On Vercel, if env vars are missing, it returns an empty string (not localhost).
  This causes 502 errors that look like backend failures but are actually
  missing frontend configuration.
- Locally, it falls back to `localhost:<port>` which works if services are running
  but gives confusing errors if only some services are up.

---

## Places I Avoid Touching and Why

| Area | Why |
|------|-----|
| `cte_persistence.py` hash chain logic | Tamper-evident integrity. Any bug here is a compliance breach. |
| `stripe_billing.py` webhook handling | Stripe webhook signature verification is fiddly. Breaking it silently drops payment events. Also: this file lives in the ingestion service but is functionally admin/billing — confusing. |
| EDI segment mapping in `edi_ingestion.py` | Fragile string parsing with no snapshot tests. |
| `shared/auth.py` JWT validation | Multiple auth strategies (JWT, API key, bypass token) with subtle priority ordering. |
| `graph/app/routers/fsma/compliance.py` | Heavy Neo4j dependency. Will be rewritten entirely during Neo4j→PostgreSQL consolidation. Not worth incremental fixes. |
| Alembic migration v051 (RLS tenant tables) | Largest migration (20.8KB). Adds RLS infrastructure. Do not modify — add new migrations instead. |

---

## Environment Variable Gotchas

There are 144+ env vars in `.env.example`. Here is what actually matters:

### Must Be Set (no safe default, will break if missing)

| Variable | Why |
|----------|-----|
| `AUTH_SECRET_KEY` | JWT signing. Must match between admin (Railway) and frontend (Vercel). |
| `DATABASE_URL` | Primary PostgreSQL connection. |
| `ADMIN_DATABASE_URL` | Admin service PostgreSQL. Different from DATABASE_URL in production. |
| `REGENGINE_INTERNAL_SECRET` | Service-to-service tenant header trust. |
| `ADMIN_MASTER_KEY` | Admin API master key for bootstrapping. |

### Should Be Set (has defaults but defaults are wrong for production)

| Variable | Default | Why It Matters |
|----------|---------|---------------|
| `REGENGINE_ENV` | "development" | Controls auth bypass. Cloud auto-forces "production" but manual deploys don't. |
| `CORS_ALLOWED_ORIGINS` | regengine.co domains | Must include your actual domain. |
| `MINIO_ROOT_USER/PASSWORD` | "minioadmin" | Default creds are publicly known. |

### Can Be Ignored (optional features, safe to leave unset)

| Variable | What Happens If Unset |
|----------|-----------------------|
| `GROQ_API_KEY` / `OPENAI_API_KEY` | LLM mapping engine disabled. CSV/manual mapping still works. |
| `NEO4J_*` | Graph service won't connect. Production spine works without it. |
| `KAFKA_*` / `REDPANDA_*` | Kafka consumers won't start. PostgreSQL task queue handles NLP/graph work. |
| Supabase vars | Supabase features silently disabled. Core auth works via JWT. |
| `SENTRY_DSN` | Error tracking disabled. |
| `ENABLE_OTEL` | Defaults to true. Set false to disable OpenTelemetry. |

### Railway Shared Variables

Railway requires you to click the SHARE button per service for shared variables.
Setting a variable on one service does NOT propagate to others. Each of the 6
services needs its own copy of `DATABASE_URL`, `REGENGINE_INTERNAL_SECRET`, etc.

---

## Migration Caveats

- Alembic migrations run against the `fsma` schema. The migration connection
  string defaults to `postgresql://regengine:regengine@postgres:5432/regengine`
  in local dev.
- Migration v051 (RLS tenant feature tables) is the largest at 20.8KB and adds
  Row-Level Security infrastructure. It must run successfully before any RLS-dependent
  code works.
- Migrations v048-v055 are sequential and must run in order. Skipping one will
  break the Alembic version chain.
- There is no rollback automation. Each migration would need a manual `downgrade`
  script (most don't have one written).

---

## What Is NOT What It Seems

| Thing | What You'd Expect | What It Actually Is |
|-------|-------------------|---------------------|
| `services/ingestion/app/stripe_billing.py` | Billing code in the billing service | Billing code in the **ingestion** service (historical accident) |
| `services/shared/` (56 modules) | Lightweight shared utilities | A hidden monolith — contains core domain logic, persistence, identity resolution, rules engine, and audit |
| `fsma.cte_events` table | The canonical event store | Legacy table being replaced by `fsma.traceability_events`. Still written to (dual-write) and read from (exports, graph sync). |
| Graph service compliance router | Compliance evaluation | Neo4j-based graph queries + CSV export. Separate from the actual rules engine in `shared/rules/`. |
| `services/scheduler` | Simple cron runner | Leader-elected orchestrator with 7 APScheduler jobs, Kafka producer, webhook delivery, and FDA scraping |

---

## FSMA 204 Is the Only Vertical

- The frontend middleware (`frontend/src/middleware.ts`) blocks non-FSMA verticals.
  `ALLOWED_VERTICALS = ['food-safety', 'fsma', 'fsma-204']`.
- `DEFAULT_VERTICAL = "food-safety"` is hardcoded in `frontend/src/lib/api-config.ts`.
- The backend has no vertical isolation — all tables, rules, and logic are FSMA-specific.
- Do not attempt to generalize for other regulations without a deliberate architecture
  decision. The current system is NOT a platform — it is a single-regulation product.
