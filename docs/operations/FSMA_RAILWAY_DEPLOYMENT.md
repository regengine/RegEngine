# FSMA Backend Deployment Runbook (Railway)

This is the P0 Phase 1A deployment path for the FSMA-first backend.

## 1. Target Services

Deploy these as separate Railway services:

| Service | Railway Root Directory | Default Local Port | Health Path |
|---|---|---:|---|
| `admin-service` | `services/admin` | `8400` | `/health` |
| `ingestion-service` | `services/ingestion` | `8000` | `/health` |
| `compliance-service` | `services/compliance` | `8500` | `/health` |
| `graph-service` | `services/graph` | `8200` | `/health` |

Notes:
- All service Dockerfiles now run with `PORT` from Railway at runtime.
- Keep PostgreSQL and Redis as Railway managed services.
- Use Neo4j Aura (or another managed Neo4j) for graph persistence.

## 2. Railway Project Setup

1. Create a Railway project and connect this GitHub repository.
2. Add managed PostgreSQL and Redis plugins.
3. Create four app services, each with the root directory shown above.
4. Confirm each service builds from its Dockerfile and gets a public Railway URL.

## 3. Required Environment Variables

Use [`docs/ENV_SETUP_CHECKLIST.md`] for full inventory. This section is only the P0 minimum.

### 3.1 admin-service

- `ADMIN_DATABASE_URL` (or `DATABASE_URL`)
- `REDIS_URL`
- `AUTH_SECRET_KEY`
- `ADMIN_MASTER_KEY`
- `SERVICE_AUTH_SECRET`
- `CORS_ORIGINS` (include `https://regengine.co`)
- `CORS_ALLOW_CREDENTIALS=true`
- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL` (for example `onboarding@regengine.co`)
- `INVITE_BASE_URL` (for example `https://regengine.co`)

### 3.2 ingestion-service

- `DATABASE_URL`
- `REDIS_URL`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_GROWTH_MONTHLY`
- `STRIPE_PRICE_SCALE_MONTHLY`
- `ADMIN_SERVICE_URL` (public URL of `admin-service`)
- `CORS_ORIGINS` (include `https://regengine.co`)
- `REGENGINE_INFLOW_WORKBENCH_PATH` (optional fallback only; Alembic v073 stores production workbench data in Postgres)

### 3.3 compliance-service

- `COMPLIANCE_DATABASE_URL` (or `DATABASE_URL`)

### 3.4 graph-service

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `REDIS_URL`

## 4. Apply SQL Migrations

Run from repo root after Railway Postgres is provisioned.

```bash
# Example: if one Postgres URL is shared by all services
export DATABASE_URL='postgresql://...'

# Optional explicit overrides (if each service uses different DB/database)
export ADMIN_DATABASE_URL="$DATABASE_URL"
export INGESTION_DATABASE_URL="$DATABASE_URL"
export COMPLIANCE_DATABASE_URL="$DATABASE_URL"

bash scripts/railway/run_phase1a_migrations.sh
```

What this executes:
- `services/admin/migrations/V*.sql`
- `services/ingestion/migrations/V*.sql`
- `migrations/V*.sql` (FSMA persistence migration lives here)
- `services/compliance/migrations/V*.sql`

Confirm Alembic v073 is applied before allowing design-partner data through
Inflow Workbench production evidence mode:

```bash
psql "$DATABASE_URL" -c "SELECT to_regclass('fsma.inflow_workbench_runs');"
```

For the full Inflow Workbench staging check, run:

```bash
export DATABASE_URL='postgresql://...'
export INGESTION_URL='https://<ingestion-service>.up.railway.app'
export REGENGINE_API_KEY='...' # optional if the deployed route requires it

bash scripts/railway/verify_inflow_workbench_staging.sh
```

This verifies the v073/V067 tables, append-only and no-truncate triggers, a
real Workbench run save through `ingestion-service`, the commit-decision audit
row, and the tenant readiness summary endpoint.

## 5. Apply Neo4j Constraints

After `graph-service` environment variables are set:

```bash
python services/graph/scripts/init_db_constraints.py
```

## 6. DNS Cutover

1. Choose the public API hostname strategy:
   - Single host: `api.regengine.co` points to one edge/gateway service.
   - Service hosts: `admin.api.regengine.co`, `ingestion.api.regengine.co`, etc.
2. If using the single-host P0 approach, point `api.regengine.co` to the Railway-provided domain for the API surface you expose.
3. Update frontend vars (`NEXT_PUBLIC_ADMIN_URL` and related) to the final production API host(s).

## 7. Health Verification

Set Railway service URLs and run:

```bash
export ADMIN_URL='https://<admin-service>.up.railway.app'
export INGESTION_URL='https://<ingestion-service>.up.railway.app'
export COMPLIANCE_URL='https://<compliance-service>.up.railway.app'
export GRAPH_URL='https://<graph-service>.up.railway.app'

bash scripts/railway/verify_phase1a_health.sh
```

Manual checks (optional):

```bash
curl -fsS "$ADMIN_URL/health"
curl -fsS "$INGESTION_URL/health"
curl -fsS "$COMPLIANCE_URL/health"
curl -fsS "$GRAPH_URL/health"
```

## 8. Phase 1A Exit Criteria

- PostgreSQL and Redis are running on Railway.
- Four backend services are deployed and healthy.
- SQL migrations are fully applied without errors.
- Neo4j constraints are applied.
- Production DNS/API URLs resolve and are reachable from frontend.
