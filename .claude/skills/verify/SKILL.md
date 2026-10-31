---
name: verify
description: >
  Build, run and drive the RegEngine monolith locally so a change can be
  observed at its HTTP surface (not via tests). Recipe for a cloud session
  with no Docker daemon: local PostgreSQL 16 + Redis + uvicorn server.main:app.
---

# Verify a change by running the app

## Services (no Docker daemon in cloud sessions)

PostgreSQL 16 binaries are at `/usr/lib/postgresql/16/bin`; `redis-server` is
on PATH. Postgres refuses to run as root, and the `postgres` user cannot
traverse the scratchpad, so put the data dir under `/var/lib/postgresql`.

```bash
PGBIN=/usr/lib/postgresql/16/bin; D=/var/lib/postgresql/verify-data
# Fail closed, as one chained command: ports 5432 and 6379 must be free before
# anything starts, a leftover data dir stops initdb, and the Redis holding
# port 6379 afterwards must be the one this recipe launched (its pidfile).
RPID=/var/lib/postgresql/verify-redis.pid; rm -f "$RPID"
! fuser 5432/tcp >/dev/null 2>&1 && ! fuser 6379/tcp >/dev/null 2>&1 \
  && su postgres -s /bin/bash -c "$PGBIN/initdb -D $D -U postgres --auth=trust -E UTF8 >/dev/null && $PGBIN/pg_ctl -D $D -l /var/lib/postgresql/pg.log -o '-p 5432 -k /var/lib/postgresql -c listen_addresses=127.0.0.1' start" \
  && pg_isready -h 127.0.0.1 -p 5432 \
  && redis-server --port 6379 --bind 127.0.0.1 --daemonize yes --pidfile "$RPID" \
  && redis-cli -p 6379 ping \
  && [ "$(fuser 6379/tcp 2>/dev/null | tr -d ' ')" = "$(cat "$RPID" 2>/dev/null)" ] \
  || { echo "local service setup failed, or port 5432/6379 is held by something else; stop here"; false; }
```

Roles must mirror `scripts/init-postgres.sh`: migrations run as a superuser
owner, the app as NOBYPASSRLS roles. `get_tenant_context()` must exist before
`alembic upgrade head`, or the V043 migration fails with
"app.tenant_id not set".

```bash
psql -h 127.0.0.1 -U postgres -v ON_ERROR_STOP=1 \
  -c "CREATE ROLE regengine_owner LOGIN PASSWORD 'pw' SUPERUSER;" \
  -c "CREATE DATABASE regengine OWNER regengine_owner;" \
  -c "CREATE ROLE regengine LOGIN PASSWORD 'pw' NOSUPERUSER NOBYPASSRLS;" \
  -c "CREATE ROLE regengine_sysadmin LOGIN PASSWORD 'pw' NOSUPERUSER NOBYPASSRLS;"
psql -h 127.0.0.1 -U regengine_owner -d regengine -c "CREATE OR REPLACE FUNCTION get_tenant_context() RETURNS UUID AS \$f\$ DECLARE tid TEXT; BEGIN tid := NULLIF(current_setting('app.tenant_id', TRUE), ''); IF tid IS NULL THEN RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS'; END IF; RETURN tid::UUID; END; \$f\$ LANGUAGE plpgsql STABLE;"
```

## Env and boot

Do not `source .env`: it holds `<placeholder>` values that break the shell.
Write a self-contained env file. Every secret below is required at startup
(missing `AUDIT_INTEGRITY_KEY` or `MFA_ENCRYPTION_KEY` aborts the lifespan).

```bash
S=<scratchpad dir>
{
  grep -E "^(ENABLED_ROUTERS|REGENGINE_INFLOW_WORKBENCH_PATH|WEBAUTHN_EXPECTED_ORIGIN)=" .env
  echo REGENGINE_ENV=development
  echo REGENGINE_AUTH_STRICT=
  echo DATABASE_URL=postgresql://regengine:pw@127.0.0.1:5432/regengine  # pragma: allowlist secret
  echo ADMIN_DATABASE_URL=postgresql+psycopg://regengine_sysadmin:pw@127.0.0.1:5432/regengine  # pragma: allowlist secret
  echo MIGRATIONS_DATABASE_URL=postgresql://regengine_owner:pw@127.0.0.1:5432/regengine  # pragma: allowlist secret
  echo REDIS_URL=redis://127.0.0.1:6379/0
  echo AUTH_TEST_BYPASS_TOKEN=verify-bypass-token-local
  echo AUTH_TEST_BYPASS_TENANT_ID=11111111-1111-1111-1111-111111111111
  for v in AUTH_SECRET_KEY JWT_SECRET AUDIT_INTEGRITY_KEY REGENGINE_INTERNAL_SECRET AUDIT_PII_HASH_SALT TOOL_ACCESS_SECRET WEBHOOK_HMAC_SECRET; do echo "$v=$(openssl rand -hex 32)"; done
  echo "MFA_ENCRYPTION_KEY=$(venv/bin/python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
} > "$S/verify.env"
set -a; source "$S/verify.env"; set +a
venv/bin/alembic upgrade head          # ~107 revisions, under a minute
# One chained command: port 8000 must be free before uvicorn starts (or curl
# would probe someone else's server while ours is still importing), and the
# process holding the port after the probe must be the one we launched.
! fuser 8000/tcp >/dev/null 2>&1 \
  && { nohup venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000 > "$S/uvicorn.log" 2>&1 & UVICORN_PID=$!; } \
  && curl -sS --fail --connect-timeout 5 --max-time 20 --retry 45 --retry-delay 2 --retry-max-time 180 --retry-connrefused --retry-all-errors http://127.0.0.1:8000/health \
  && [ "$(fuser 8000/tcp 2>/dev/null | tr -d ' ')" = "$UVICORN_PID" ] \
  || { echo "port 8000 was busy, or PID ${UVICORN_PID:-none} is not the server on it; see $S/uvicorn.log"; false; }
```

Startup takes about 15 s. `/openapi.json` lists mounted routes; confirm the
route under test is there (`ENABLED_ROUTERS` gates routers).

## Driving tenant routes

- Header `X-RegEngine-API-Key: verify-bypass-token-local` gives a key bound to
  tenant `11111111-1111-1111-1111-111111111111` with `webhooks.ingest`, read,
  write and admin scopes. This works only because `REGENGINE_ENV=development`.
- Pass the tenant as `X-Tenant-ID` or form/query `tenant_id`. A different
  tenant returns 403; a conflicting header/form pair returns 400.
- With no key at all, dev mode falls back to an open principal (200, with a
  `dev_open_auth_activated` warning in the log). That path does not exist in
  production, so a "no auth" probe must send an invalid key to see the 401.
- Fixtures: `services/ingestion/tests/fixtures/*.csv`. Build XLSX from a CSV
  with `openpyxl`; to test understated-dimension handling, rewrite the
  `<dimension ref="...">` tag in `xl/worksheets/sheet1.xml` and re-zip.
- No-persistence check: count rows in `supplier_cte_events`, `audit_logs` and
  `funnel_events` before and after via
  `psql -h 127.0.0.1 -U regengine_owner -d regengine`.

## Gotchas

- Jev is live when `TYPESAFE_API_KEY` is in the session env; options like
  `semantic_review=true` then make real provider calls. The `jev_configured`
  boot log line says `key_present=`.
- The strict Jev review validator rejects some provider answers
  non-deterministically; re-run a semantic-review probe before calling it a
  regression.
- Stop only what this recipe started: `kill "$UVICORN_PID"`, then Redis only
  if the recorded PID is still a redis-server (a stale pidfile must never
  signal a reused PID):
  `R=$(cat "$RPID" 2>/dev/null); [ "$(ps -o comm= -p "$R" 2>/dev/null)" = redis-server ] && kill "$R"`,
  then `su postgres -s /bin/bash -c "$PGBIN/pg_ctl -D $D stop"`.
