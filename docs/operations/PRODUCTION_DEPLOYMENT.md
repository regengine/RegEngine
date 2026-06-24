# RegEngine Deployment Guide

> Status: verified 2026-05-06. This guide reflects the checked-in consolidated deploy path. RegEngine is still in a pre-production hardening phase.

## Deployment Model

RegEngine deploys as one consolidated FastAPI app behind a Next.js frontend.

Source-of-truth files:

- `railway.toml`
- `Dockerfile`
- `server/main.py`
- `scripts/run-migrations.sh`

The repository still contains service-shaped directories such as `services/ingestion` and `services/admin`, but the checked-in production target is the consolidated backend process started from `server.main:app`.

## What The Deploy Actually Does

The backend container:

1. installs dependencies from the root `requirements.lock`
2. copies the service directories, `kernel`, `plugins`, and `server`
3. runs Alembic migrations through `scripts/run-migrations.sh`
4. starts Gunicorn with Uvicorn workers for `server.main:app`

Railway currently:

- builds the repo-root `Dockerfile`
- probes `/readiness`
- restarts on failure

## Required Runtime Dependencies

- PostgreSQL via `DATABASE_URL`
- Python settings and secrets needed by the mounted routers

Optional but supported in code:

- Redis for rate limiting, queue/session helpers, and related runtime paths
- Neo4j integrations for graph-oriented modules

Do not assume legacy event-broker, Terraform, or multi-service AWS infrastructure are part of the active checked-in deploy contract unless a separate environment explicitly adds them.

## Pre-Deployment Checklist

- Root migrations are current: `alembic upgrade head`
- `requirements.lock` matches the intended Python dependency set
- frontend and backend CI are green
- environment variables match the routes you intend to expose
- any experimental router exposure is deliberate
- tenant/auth/rules settings are verified for the target environment

## Build And Run

### Build the backend image

```bash
docker build -t regengine-backend .
```

### Run the backend container

```bash
docker run --rm \
  -e DATABASE_URL="$DATABASE_URL" \
  -e PORT=8000 \
  -p 8000:8000 \
  regengine-backend
```

### Run the frontend separately

```bash
cd frontend
npm install
npm run build
npm run start
```

## Health Checks

- Backend readiness: `/readiness`
- Backend app wiring: `server/main.py`
- Frontend production build: `npm --prefix frontend run build`

Validate at minimum:

- backend starts cleanly after migrations
- readiness responds successfully
- auth/session flow works in the frontend
- primary FSMA workflows reach the consolidated backend as expected

## Operational Notes

- `server/main.py` runs startup validation, including ORM/database type alignment for the admin ORM path.
- Experimental routers can be auto-disabled in production unless explicitly enabled.
- Legacy service entrypoints still exist for local debugging, but they are not the checked-in production deploy target.
- The strongest production spine remains:

```text
ingest -> preflight -> persist evidence -> evaluate rules -> export
```

## What Not To Claim

This deployment guide should not be used to claim:

- six independent production backend services
- launch maturity beyond the verified deployment posture
- universal non-FSMA regulatory intelligence
- infrastructure commitments that are not backed by the current CI, config, and hosting setup

## Related Docs

- `README.md`
- `ARCHITECTURE.md`
- `docs/engineering/ROUTER_SURFACE.md`
- `docs/runbooks/RULES_ENGINE_ENFORCE_ROLLOUT.md`
