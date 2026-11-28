---
name: verify
description: >
  Build, run and drive the RegEngine monolith locally so a change can be
  observed at its HTTP surface (not via tests). Two recipes for PostgreSQL +
  Redis + uvicorn server.main:app: a cloud session with no Docker daemon, and
  a local macOS session with Docker Desktop and Homebrew Redis.
---

# Verify a change by running the app

In a cloud session follow "Services" and "Env and boot". On a Mac follow
"Local macOS session" instead of those two. The rest applies to both.

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

Roles must mirror `scripts/init-postgres.sh`: migrations run as the
NOSUPERUSER/NOBYPASSRLS database owner `regengine_migrator` (v111 rejects an
elevated migrator), the app as NOBYPASSRLS roles. `get_tenant_context()` must exist before
`alembic upgrade head`, or the V043 migration fails with
"app.tenant_id not set".

```bash
psql -h 127.0.0.1 -U postgres -v ON_ERROR_STOP=1 \
  -c "CREATE ROLE regengine_migrator LOGIN PASSWORD 'pw' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;" \
  -c "CREATE DATABASE regengine OWNER regengine_migrator;" \
  -c "CREATE ROLE regengine LOGIN PASSWORD 'pw' NOSUPERUSER NOBYPASSRLS;" \
  -c "CREATE ROLE regengine_sysadmin LOGIN PASSWORD 'pw' NOSUPERUSER NOBYPASSRLS;" \
  -c "GRANT CONNECT ON DATABASE regengine TO regengine, regengine_sysadmin;"
psql -h 127.0.0.1 -U regengine_migrator -d regengine -c "CREATE OR REPLACE FUNCTION get_tenant_context() RETURNS UUID AS \$f\$ DECLARE tid TEXT; BEGIN tid := NULLIF(current_setting('app.tenant_id', TRUE), ''); IF tid IS NULL THEN RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS'; END IF; RETURN tid::UUID; END; \$f\$ LANGUAGE plpgsql STABLE;"
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
  echo MIGRATIONS_DATABASE_URL=postgresql://regengine_migrator:pw@127.0.0.1:5432/regengine  # pragma: allowlist secret
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

## Local macOS session

A Mac has no `/usr/lib/postgresql`, no `fuser` and usually no `.env`, and
Homebrew `libpq` ships `psql` without a server. Postgres runs in a throwaway
Docker container and Redis is the Homebrew `redis-server`.

- Never use ports 5432, 6379 or 8000, and never stop a container you did not
  start. The developer's own containers (`docker-compose.dev.yml`,
  `restart: unless-stopped`) come back on those ports whenever Docker starts,
  and other sessions run this recipe at the same time. The first block picks
  three free ports.
- Each block is one Bash call. A new call is a new shell, so state lives in
  files under `$S` and every block starts by reading `$S/state`.
- A worktree has no `venv/`. `$VENV` is the main checkout's. Do not install
  into it; if an import fails there, say so.
- `"$S/run" CMD` runs CMD with only the verify env file, so nothing exported
  by the developer's shell profile (a real DSN or API key) reaches the app.

```bash
S=<scratchpad dir>/verify; mkdir -p "$S/home" "$S/tmp"
VENV="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/venv"
free_port() { "$VENV/bin/python" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])'; }
{ echo "VENV=$VENV"; echo "PGPORT=$(free_port)"; echo "RPORT=$(free_port)"; echo "APPPORT=$(free_port)"; echo "PGNAME=regengine-verify-pg-$(date +%s)"; } > "$S/state"
# Teardown may quit Docker Desktop only if this run started it.
docker info >/dev/null 2>&1 && echo already_running > "$S/docker_started_by" || echo this_run > "$S/docker_started_by"
docker desktop start    # waits for the engine; a no-op when it is already up
cat "$S/state" "$S/docker_started_by"
```

`scripts/init-postgres.sh` creates the three roles and
`get_tenant_context()`, so the role SQL from the cloud recipe is not needed.
`docker run` pulls `postgres:17` if the image is missing.

```bash
S=<scratchpad dir>/verify; . "$S/state"
# Fail closed: the port must be free before the run, and the container that
# publishes it afterwards must be the one this run started.
! lsof -nP -iTCP:$PGPORT -sTCP:LISTEN -t >/dev/null 2>&1 \
  && docker run -d --rm --name "$PGNAME" \
       -e POSTGRES_USER=regengine_owner -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=regengine \
       -e POSTGRES_INITDB_ARGS="--encoding=UTF8 --locale=en_US.UTF-8" \
       -p "127.0.0.1:$PGPORT:5432" \
       -v "$PWD/scripts/init-postgres.sh:/docker-entrypoint-initdb.d/init-postgres.sh:ro" \
       --tmpfs /var/lib/postgresql/data postgres:17 > "$S/pg.cid" \
  && docker exec "$(cat "$S/pg.cid")" sh -c 'for i in $(seq 1 60); do pg_isready -h 127.0.0.1 -q && exit 0; sleep 1; done; exit 1' \
  && [ "$(docker ps -q --no-trunc --filter "publish=$PGPORT")" = "$(cat "$S/pg.cid")" ] \
  || { echo "port $PGPORT busy, docker run failed, or the container on it is not ours; stop here"; false; }
# Same rule for Redis: its process_id must match the pidfile this run wrote.
rm -f "$S/redis.pid"
! lsof -nP -iTCP:$RPORT -sTCP:LISTEN -t >/dev/null 2>&1 \
  && redis-server --port "$RPORT" --bind 127.0.0.1 --save "" --appendonly no --daemonize yes --pidfile "$S/redis.pid" --dir "$S" --logfile "$S/redis.log" \
  && for i in $(seq 1 50); do redis-cli -p "$RPORT" ping >/dev/null 2>&1 && break; done \
  && [ "$(redis-cli -p "$RPORT" info server | tr -d '\r' | awk -F: '/^process_id:/{print $2}')" = "$(cat "$S/redis.pid")" ] \
  || { echo "port $RPORT busy, or the Redis on it is not the one this run started; stop here"; false; }
```

```bash
S=<scratchpad dir>/verify; . "$S/state"
umask 077
{
  grep -E "^(ENABLED_ROUTERS|WEBAUTHN_EXPECTED_ORIGIN)=" .env.example
  echo "REGENGINE_INFLOW_WORKBENCH_PATH=$S/inflow_workbench.json"
  echo REGENGINE_ENV=development
  echo REGENGINE_AUTH_STRICT=
  echo "DATABASE_URL=postgresql://regengine:pw@127.0.0.1:$PGPORT/regengine"  # pragma: allowlist secret
  echo "ADMIN_DATABASE_URL=postgresql+psycopg://regengine_sysadmin:pw@127.0.0.1:$PGPORT/regengine"  # pragma: allowlist secret
  echo "MIGRATIONS_DATABASE_URL=postgresql://regengine_migrator:pw@127.0.0.1:$PGPORT/regengine"  # pragma: allowlist secret
  echo "REDIS_URL=redis://127.0.0.1:$RPORT/0"
  echo AUTH_TEST_BYPASS_TOKEN=verify-bypass-token-local
  echo AUTH_TEST_BYPASS_TENANT_ID=11111111-1111-1111-1111-111111111111
  for v in AUTH_SECRET_KEY JWT_SECRET AUDIT_INTEGRITY_KEY REGENGINE_INTERNAL_SECRET AUDIT_PII_HASH_SALT TOOL_ACCESS_SECRET WEBHOOK_HMAC_SECRET; do echo "$v=$(openssl rand -hex 32)"; done
  echo "MFA_ENCRYPTION_KEY=$("$VENV/bin/python" -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
} > "$S/verify.env"
cat > "$S/run" <<EOF
#!/bin/bash
exec env -i PATH="$VENV/bin:/usr/bin:/bin:/usr/sbin:/sbin" HOME="$S/home" TMPDIR="$S/tmp" \\
  LANG=en_US.UTF-8 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \\
  bash -c 'set -a; . "\$0"; set +a; exec "\$@"' "$S/verify.env" "\$@"
EOF
chmod +x "$S/run"
"$S/run" alembic upgrade head
```

```bash
S=<scratchpad dir>/verify; . "$S/state"
# Port free before the start, and the listener afterwards is the PID we wrote.
! lsof -nP -iTCP:$APPPORT -sTCP:LISTEN -t >/dev/null 2>&1 \
  && { nohup "$S/run" uvicorn server.main:app --host 127.0.0.1 --port "$APPPORT" > "$S/uvicorn.log" 2>&1 & echo $! > "$S/uvicorn.pid"; } \
  && curl -sS --fail --connect-timeout 5 --max-time 20 --retry 45 --retry-delay 2 --retry-max-time 180 --retry-connrefused --retry-all-errors "http://127.0.0.1:$APPPORT/health" \
  && [ "$(lsof -nP -iTCP:$APPPORT -sTCP:LISTEN -t)" = "$(cat "$S/uvicorn.pid")" ] \
  || { echo "port $APPPORT was busy, or the server on it is not ours; see $S/uvicorn.log"; false; }
```

The app is at `http://127.0.0.1:$APPPORT`. Where the sections below say
`psql -h 127.0.0.1 -U postgres -d regengine`, use the container's bootstrap
superuser, for row counts and nothing else:

```bash
S=<scratchpad dir>/verify; . "$S/state"
psql "postgresql://regengine_owner:pw@127.0.0.1:$PGPORT/regengine" -c "select count(*) from tenants"  # pragma: allowlist secret
```

Stop only what this run started:

```bash
S=<scratchpad dir>/verify; . "$S/state"
P=$(cat "$S/uvicorn.pid" 2>/dev/null); case "$(ps -o command= -p "$P" 2>/dev/null)" in *server.main:app*) kill "$P";; esac
R=$(cat "$S/redis.pid" 2>/dev/null)
[ -n "$R" ] && [ "$(redis-cli -p "$RPORT" info server 2>/dev/null | tr -d '\r' | awk -F: '/^process_id:/{print $2}')" = "$R" ] && redis-cli -p "$RPORT" shutdown nosave
[ "$(docker inspect -f '{{.Name}}' "$(cat "$S/pg.cid")" 2>/dev/null)" = "/$PGNAME" ] && docker stop "$(cat "$S/pg.cid")"
rm -rf "$S/keys" "$S/verify.env"
docker ps --format '{{.Names}}\t{{.RunningFor}}'; lsof -nP -iTCP:5432 -iTCP:6379 -sTCP:ESTABLISHED; cat "$S/docker_started_by"
```

Quit Docker Desktop (`docker desktop stop`) only if that last line prints
`this_run`, every container still listed is older than this run, and `lsof`
lists no connection on 5432 or 6379. Otherwise another session or the
developer is using Docker: leave it running and say so.

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
  `psql -h 127.0.0.1 -U postgres -d regengine` (superuser, so RLS does not
  hide rows).

### EDI routes

`/api/v1/ingest/edi` and `/api/v1/ingest/edi/document` require `edi.ingest`.
The bypass key lacks that scope (403), and a request with no key passes the
route in development but gets 401 inside `ingest_events`. Mint a tenant key
instead. The bypass key keeps working beside it.

```bash
S=<scratchpad dir>/verify; . "$S/state"    # cloud: S=<scratchpad dir>
# The app checks database-backed keys in development only with this set. Add
# it before the boot block. If the server is already up, stop it (the `P=`
# line of the teardown) and run the boot block again.
echo ENABLE_DB_API_KEYS=true >> "$S/verify.env"
# After alembic. Writes the tenant and the key as regengine_sysadmin through
# ADMIN_DATABASE_URL and marks the tenant's billing status in Redis.
# Cloud: `set -a; source "$S/verify.env"; set +a` first, then venv/bin/python.
"$S/run" python scripts/create_test_api_key.py --scopes edi.ingest --expires-days 1 --key-file "$S/keys/edi-key"
```

```bash
S=<scratchpad dir>/verify; . "$S/state"    # cloud: S=<scratchpad dir>; APPPORT=8000
# One 944 receipt. Each send needs its own ISA13, the 000000001 in the ISA and
# IEA segments: a repeat gets 409.
printf '%s~' \
  'ISA*00*          *00*          *ZZ*WHSENDER       *ZZ*RECEIVERID     *260105*1200*U*00401*000000001*0*P*>' \
  'GS*RE*WHSENDER*RECEIVERID*20260105*1200*1*X*004010' 'ST*944*0001' \
  'W17*F*20260105*RCPT-1*DEP-1*SHIP-1' \
  'N1*SF*Valley Fresh Farms*UL*0614141000012' 'N1*WH*Metro Cold Storage*UL*0614141000029' \
  'W07*120*CA**UK*00012345678905***00012345678905-LOT1' 'G69*Romaine Hearts 12ct' \
  'SE*7*0001' 'GE*1*1' 'IEA*1*000000001' > "$S/receipt_944.edi"
curl -sS -X POST "http://127.0.0.1:$APPPORT/api/v1/ingest/edi/document" \
  -H "X-RegEngine-API-Key: $(cat "$S/keys/edi-key")" \
  -H "X-Tenant-ID: 11111111-1111-1111-1111-111111111111" \
  -F "file=@$S/receipt_944.edi;type=application/edi-x12" \
  -F traceability_lot_code=UNUSED-FOR-944 -F tlc_source_reference=wh-receipt-source
```

- 944 and 945 need the `tlc_source_reference` form field. Without it the
  response is 201 with `accepted: 0` and a missing-KDE error on every line.
- A rejection record is kept in the worker's memory only. Read it from the
  `edi_fsma_rejection_recorded` line in the server log.
- `docs/engineering/TRACEABILITY_FILE_INTAKE.md` has the segment rules.
- Delete `$S/keys` when done.

## Gotchas

- Jev is live when `TYPESAFE_API_KEY` is in the session env; options like
  `semantic_review=true` then make real provider calls. The `jev_configured`
  boot log line says `key_present=`.
- The strict Jev review validator rejects some provider answers
  non-deterministically; re-run a semantic-review probe before calling it a
  regression.
- A database at alembic head has one rule definition, so an ingest writes no
  `fsma.rule_evaluations` rows. Seed the built-in rules first (next section)
  when a check depends on rule results.
- Stop only what this recipe started: `kill "$UVICORN_PID"`, then Redis only
  if the recorded PID is still a redis-server (a stale pidfile must never
  signal a reused PID):
  `R=$(cat "$RPID" 2>/dev/null); [ "$(ps -o comm= -p "$R" 2>/dev/null)" = redis-server ] && kill "$R"`,
  then `su postgres -s /bin/bash -c "$PGBIN/pg_ctl -D $D stop"`.

### Seeding rules

No least-privilege role can insert rule definitions: RLS blocks the migrator
and the runtime roles have no grant. This one step therefore uses the
bootstrap superuser, `regengine_owner` on macOS as below. In a cloud session
it is `postgres`: set `BOOTSTRAP_URL=postgresql://postgres@127.0.0.1:5432/regengine`
and call `venv/bin/python`. The running server picks the rules up without a
restart.

```bash
S=<scratchpad dir>/verify; . "$S/state"
"$S/run" env "BOOTSTRAP_URL=postgresql://regengine_owner:pw@127.0.0.1:$PGPORT/regengine" python - <<'PY'  # pragma: allowlist secret
import os, sys
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "services")]
from shared.db_url import sync_postgres_url
from shared.rules import seed_rule_definitions
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

with Session(create_engine(sync_postgres_url(os.environ["BOOTSTRAP_URL"]))) as session:
    print("rules inserted:", seed_rule_definitions(session))
    session.commit()
PY
```
