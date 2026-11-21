# Local setup guide

This guide starts the consolidated backend, PostgreSQL and Redis, and the
frontend for development. It does not establish deployment readiness or prove
that a live environment has the same configuration. See the [root README](../../README.md)
for the capability inventory and [frontend README](../../frontend/README.md) for
frontend details.

## Prerequisites

- Python 3.11 or 3.12, as specified in [pyproject.toml](../../pyproject.toml).
- Node 22 from the repository's [.nvmrc](../../.nvmrc), and npm.
- Docker Engine or Desktop with Docker Compose.
- Access to the repository and package registries.

Run these commands from the repository root unless stated otherwise. The
example password below is for an isolated local database only. Keep real
credentials out of tracked files and do not print them in logs.

## Start infrastructure and migrate

```bash
python3 -m venv venv
source venv/bin/activate
pip install --require-hashes -r requirements.lock

export POSTGRES_PASSWORD=regengine
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml ps

export DATABASE_URL="postgresql://regengine:${POSTGRES_PASSWORD}@localhost:5432/regengine"
export ADMIN_DATABASE_URL="postgresql://regengine_sysadmin:${POSTGRES_PASSWORD}@localhost:5432/regengine"
export MIGRATIONS_DATABASE_URL="postgresql://regengine_owner:${POSTGRES_PASSWORD}@localhost:5432/regengine"
export REDIS_URL="redis://localhost:6379/0"
./scripts/run-migrations.sh
```

Wait until PostgreSQL is healthy before running migrations. Compose starts
PostgreSQL 17 and Redis 7; it does not start the backend, Neo4j, or a message
broker. The initialization script creates separate local runtime and schema
owner roles on a new database volume. Existing volumes retain their existing
credentials and data; changing `POSTGRES_PASSWORD` does not reinitialize them.
The migration runner refuses to stamp an existing unversioned application
schema. Investigate its reported state before proceeding.

## Start the backend

In a shell with the virtual environment and the variables above loaded:

```bash
export ENABLE_DB_API_KEYS=true
uvicorn server.main:app --reload --port 8000
```

The consolidated app listens at `http://localhost:8000`; in development its
OpenAPI interface is at `http://localhost:8000/docs`. Check liveness and
readiness separately:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/readiness
```

A successful health or readiness response does not validate a complete ingest
or export journey. Inspect readiness details and backend logs when it fails.
Legacy individual service entrypoints exist, but they are not the default
consolidated setup.

## Create a local API key

With the migrated local database and Redis running, and the same environment
variables set, run:

```bash
./venv/bin/python scripts/create_test_api_key.py
```

The script seeds a local test tenant and attempts to set its Redis subscription
to `trialing`; check its output for a skipped billing seed. The key is written
once to `~/.regengine/test-api-key` with restricted permissions, not printed in
full. The script refuses to overwrite the file by default; use a separate
`--key-file` for another key. Supply the key through `X-RegEngine-API-Key` to
protected API endpoints, and keep `ENABLE_DB_API_KEYS=true` in the backend
process. A local API key is not a browser login: protected UI workflows also
require the relevant user and tenant provisioning and authentication setup.
See the [authentication guide](../engineering/Authentication.md) and
[frontend README](../../frontend/README.md) for the identity and UI setup context.

## Start the frontend

In a separate shell:

```bash
cd frontend
npm ci
INGESTION_SERVICE_URL=http://localhost:8000 \
ADMIN_SERVICE_URL=http://localhost:8000 \
COMPLIANCE_SERVICE_URL=http://localhost:8000 \
GRAPH_SERVICE_URL=http://localhost:8000 \
NLP_SERVICE_URL=http://localhost:8000 \
npm run dev
```

Open `http://localhost:3000`. All five upstream names point to the same
backend process. They override the frontend's legacy per-service localhost
fallbacks; setting them does not enable an experimental router. Do not put
secrets in `NEXT_PUBLIC_*` variables, which are exposed to browsers.

## Validation and troubleshooting

```bash
# From the repository root, with the venv active
python3 -m pytest services/ingestion/tests -q --no-cov

# From frontend/
npm run lint
npm run test:run
```

Some integration tests require additional services or database configuration;
consult their skip or failure output. For a persisted local integration proof,
see the Inflow-to-RegEngine command in the [root README](../../README.md#local-development).

- If Compose is unhealthy, check `docker compose -f docker-compose.dev.yml ps`
  and the relevant service logs. PostgreSQL must be ready before migration.
- If authenticated ingest returns `401`, verify the key, header, and backend
  `ENABLE_DB_API_KEYS` setting. A missing or inactive subscription can return
  `402`; Redis uncertainty can return `503`.
- If the frontend cannot reach the backend, confirm the backend is listening on
  port 8000 and the upstream variables were set in the shell running Next.js.
- Stop the local services with `docker compose -f docker-compose.dev.yml down`.
  This preserves the database volume. Removing volumes destroys local data and
  should only be done intentionally after any needed backup.

See the [documentation index](../README.md) for architecture, runbooks, and
other guides.
