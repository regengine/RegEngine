# Disaster Recovery — Railway Production

| | |
|---|---|
| Scope | Railway project `RegEngine-Prod` (`4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51`), environments `production` (`37be1945-0c0c-4aa5-b151-fbb4b7548abd`) and `staging` (`42a820d5-755e-45a2-9cdd-dba1624d703b`) |
| Last verified against Railway | 2026-09-29 00:02 UTC: inventory, backup schedules and PITR enabled (section 3), and a backup-and-restore drill of the staging database (section 9) |
| Owner | Christopher Sellers |
| Replaces | The AWS plan previously in this file and `docs/runbooks/disaster-recovery.md`. Neither described production. See section 10. |

This is the single disaster-recovery document. The incident process, severity
tiers, communication templates and postmortem template are in
[INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).

## Read this first: backup state

As of 2026-09-29 00:02 UTC, in both `production` and `staging`:

| Service | Backup schedule | PITR | On-demand backup (production) |
|---|---|---|---|
| `Postgres` | daily, weekly, monthly | on, restorable from 2026-09-28 23:57 UTC | `pre-pitr-enable-20260928`, 2026-09-28 23:54 UTC, never expires |
| `Redis` | daily, weekly, monthly | n/a | `pre-pitr-enable-20260928`, 2026-09-28 23:54 UTC, never expires |
| `neo4j` | daily, weekly, monthly | n/a | `pre-pitr-enable-20260928`, 2026-09-28 23:54 UTC, never expires |

- **Postgres RPO is about one minute.** The restore window grows to about four
  weeks. The WAL archive is in a Railway bucket, `Postgres-PITR`, in region
  `sjc`; the database volume is in `us-west2`.
- **Redis and Neo4j RPO is 24 hours** (the daily backup). Redis holds the only
  copy of Stripe subscription state (section 6.5).
- **Not yet covered:** a copy outside Railway (section 3, step 5), and object
  storage (open question 3). RTO has never been measured.
- **Before these changes (until 2026-09-28 23:55 UTC):** there were no
  schedules and PITR was off. The only backups were Railway's own
  `Pre-Security-Patch Backup` snapshots, taken before image auto-updates and
  kept for 30 days. The production Postgres one, from 2026-08-22, was already
  past its expiry.
- No GitHub workflow, Railway cron service, or scheduler job runs
  `scripts/backup_postgres.sh` or `scripts/backup_neo4j.sh`.

Check the current state with these commands; the first two also answer for
`-s Redis` and `-s neo4j`:

```bash
railway postgres pitr schedule list -p 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51 -e production -s Postgres
railway postgres pitr backup list -p 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51 -e production -s Postgres
railway postgres pitr status -p 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51 -e production -s Postgres
```

`pitr status` should show `Archiver: enabled`, a recent `Last archived at`,
and a `Restorable up to` within the last few minutes.

## 1. Open questions (not verified)

1. Whether the expired manual Postgres backup (`191e5479-36a7-4f51-af5e-e92cff2be367`,
   2026-08-22) can still be restored. The CLI still lists it a week after its
   expiry. Nobody has tried to restore it. Since 2026-09-28 newer backups
   exist, so this matters only for data from before then.
2. The Railway plan tier, what backups and PITR cost on it, and how many days
   of deployment images it keeps. That retention sets how far back a rollback
   can go (section 7).
3. Whether production object storage (`OBJECT_STORAGE_ENDPOINT_URL`,
   `RAW_DATA_BUCKET`, `PROCESSED_DATA_BUCKET`) is Cloudflare R2, as decided in
   `docs/decisions/2026-05-12-object-storage.md`, and whether its buckets are
   versioned or backed up. They hold the only copy of ingested documents, and
   nothing in Railway covers them (section 4).
4. Whether a Railway volume backup of a running Postgres or Neo4j is
   crash-consistent. Railway's documentation does not say. Postgres replays its
   WAL on start, so a crash-consistent snapshot should recover; this has not
   been tested.
5. Restore time for production-sized data. The staging drill used a 17 MB
   database. The production Postgres backup was 322 MB on 2026-08-22.
6. Whether any copy of the production secrets exists outside Railway, for
   example in `cw-vault`. If the Railway project is deleted, the database role
   passwords and application keys may exist nowhere else.
7. The production database name. It is `railway` per the owner; staging
   confirms `railway` for its own Postgres service. The production name was not
   read directly, because reading it requires the variable values.
8. How the Postgres template's `POSTGRES_PASSWORD`, `PGPASSWORD`,
   `DATABASE_URL` and `DATABASE_PUBLIC_URL` variables reference each other, and
   therefore the exact steps to rotate the template superuser password
   (section 8.1).
9. Answered 2026-09-28: `railway postgres pitr schedule set`,
   `schedule list`, `backup create` and `backup list` all work for the `Redis`
   and `neo4j` services. `backup restore` has not been tried on them.
10. The exact Neo4j version running in production. The service builds from the
    upstream template `sukrutnrvd/neo4j-template`, whose Dockerfile today uses
    `neo4j:2026.04-community`. Production's last build was 2026-05-26.
11. Whether the per-tenant audit-chain check `POST /api/v1/chain/verify-all`
    (`services/ingestion/app/chain_verification_job.py`) is in production's
    `ENABLED_ROUTERS` allowlist.
12. How to rebuild a tenant's Redis billing record from Stripe. No tool or
    procedure exists (section 6.5).
13. Whether any Stripe subscriptions are live today, and therefore how much
    billing state a 24-hour Redis RPO can lose.

## 2. Inventory

All services run one replica in `us-west2`. There are no Railway buckets and
Postgres HA is not enabled.

| Service | Source | Volume (production) | Public TCP proxy |
|---|---|---|---|
| `RegEngine` | GitHub `regengine/RegEngine`, branch `main`, root `Dockerfile` | none | none. HTTP domain `regengine-production.up.railway.app` |
| `Postgres` | `ghcr.io/railwayapp-templates/postgres-ssl:18` (staging reports 18.6) | `postgres-volume`, 50 GB, at `/var/lib/postgresql/data` | yes, port 5432 |
| `Redis` | `redis:8.2.9`, started with `--save 60 1` (RDB snapshot every 60 s if anything changed; no AOF; no `maxmemory`, so Redis's default `noeviction` applies) | `redis-volume`, 5 GB, at `/data` | yes, port 6379 |
| `neo4j` | GitHub template `sukrutnrvd/neo4j-template`, Neo4j Community | `neo4j-volume`, 5 GB, at `/data` | yes, port 7687 |

Staging has the same four services, with 50 GB volumes.

**Boot sequence.** The `RegEngine` container runs `scripts/run-migrations.sh`
and then gunicorn (`Dockerfile`, `CMD`). Every deploy therefore runs
`alembic upgrade head` followed by the v111 runtime-role cutover, as
`regengine_migrator`. `railway.toml` sets the healthcheck to `/readiness`
(timeout 300 s) and the restart policy to `ON_FAILURE`, 3 retries.

**Database roles** (see [DATABASE_ROLE_CUTOVER.md](DATABASE_ROLE_CUTOVER.md)):

| Variable on `RegEngine` | Role | Attributes |
|---|---|---|
| `DATABASE_URL` | `regengine` | NOSUPERUSER NOBYPASSRLS |
| `ADMIN_DATABASE_URL` | `regengine_sysadmin` | NOSUPERUSER NOBYPASSRLS |
| `MIGRATIONS_DATABASE_URL` | `regengine_migrator`, owner of the database and schema objects | NOSUPERUSER NOBYPASSRLS |

The `Postgres` service's own `PGUSER` is the template superuser (verified on
staging: `rolsuper = t`). Logical dumps (section 6.3) use that superuser.

Staging has not had the bootstrap in DATABASE_ROLE_CUTOVER.md section 6
applied. On 2026-09-28 its `railway` database was at alembic `267d8053ced5`
(v079), and the `regengine_migrator` role did not exist.

**What each datastore is required for:**

- Postgres: always. `/readiness` returns 503 without it.
- Redis: always in production. Startup aborts without it, `/readiness`
  returns 503 (`server/main.py`, `readiness`), so deploys cannot pass their
  healthcheck, and bearer authentication returns 503.
- Neo4j: not probed by `/readiness` in production. The graph routers are not
  mounted there.
- Kafka: not used. `EVENT_BACKBONE` is unset in production and defaults to
  `pg`; background work runs from the Postgres task queue.

**Dependencies outside Railway:** object storage (`OBJECT_STORAGE_*`; section
4), Stripe, Resend, and the Vercel frontend. Supabase: the backend does not
use it in production; the frontend uses it for the developer portal, lead
capture and legacy Supabase sessions. This document does not cover the
recovery of these services.

## 3. Backup configuration

Steps 1 to 4 were done on 2026-09-28, approved by the owner, staging first and
then production. Step 5 is still open. Re-run a command here only to rebuild
a lost service or environment.

1. **Scheduled volume backups on all three services (done).** Railway
   retention: daily backups kept 6 days, weekly 27 days, monthly 89 days. Cost
   is the incremental size at volume pricing.

   ```bash
   railway postgres pitr schedule set --daily --weekly --monthly -p 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51 -e production -s Postgres
   railway postgres pitr schedule set --daily --weekly --monthly -p 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51 -e production -s Redis
   railway postgres pitr schedule set --daily --weekly --monthly -p 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51 -e production -s neo4j
   ```

2. **Point-in-time recovery for Postgres (done).** RPO is about one minute
   (`archive_timeout=60`). pgBackRest takes a weekly full and a daily
   differential backup, and keeps 4 fulls, which gives about four weeks of
   window. Storage and egress are billed at bucket rates.

   ```bash
   railway postgres pitr enable -p 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51 -e production -s Postgres
   ```

   Enabling redeploys Postgres. In production, `/readiness` returned 503 for
   about 15 to 20 seconds (23:56:32–23:56:46 UTC). The first base backup
   completed at 23:56:58. Coverage is not retroactive.

   **After any Postgres restart, check the scheduler.** Enabling PITR, a
   restore, and Railway's security auto-updates all restart Postgres. This
   restart left the `Remediation Notification Outbox Drain` job hung on a dead
   connection: every later run logged `skipped: maximum number of running
   instances reached (1)` until `RegEngine` was redeployed. The shared engine
   sets no connect timeout or TCP keepalives. After any Postgres restart,
   search the `RegEngine` logs for that message; if it appears, run
   `railway redeploy -p 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51 -e production -s RegEngine --yes`.

3. **`Redis` and `neo4j` schedules (done, in step 1).** A Redis restore has
   security side-effects; read section 6.5 first.

4. **Before any risky migration or data repair,** take an on-demand backup and
   keep it:

   ```bash
   railway postgres pitr backup create --name pre-<change> -p 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51 -e production -s Postgres
   railway postgres pitr backup lock <BACKUP_ID> -p 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51 -e production -s Postgres
   ```

   A manual backup can be at most 50% of the volume size (25 GB for
   `postgres-volume`).

5. **A copy outside Railway (open; owner decision).** Volume backups live with
   the volume: wiping a volume deletes all of its backups, and they restore
   only into the same project and environment. The PITR archive is in a
   Railway bucket in the same project. For a copy that survives losing the
   project, run the logical dump in section 6.3 on a schedule to storage you
   control. Nothing does this today. Decide where the copies go (`S3_BUCKET`
   for `backup_postgres.sh`) and what runs the job.

## 4. What is and is not backed up

"Volume backup" means the schedules in section 3, step 1. Nothing outside
Railway is covered yet (section 3, step 5).

| Data | Lives in | Covered by | Not covered, or notes |
|---|---|---|---|
| Tenant data, FSMA records, audit trail, users, API key records | `Postgres`, database `railway` | Volume backup (whole cluster). PITR. Logical dump (section 6.3) | The logical dump holds one database with no roles, owners or GRANTs; section 6.3 rebuilds them |
| Database roles and their passwords | `Postgres` cluster (`pg_authid`) and the `RegEngine` URL variables | Volume backup and PITR | Not in the logical dump. Passwords rotated after a backup no longer match it (section 6.1, step 5) |
| Railway variables (every secret) | Railway | Nothing | A deployment rollback restores the variables that deployment had (section 7). No other copy is verified (open question 6) |
| Regulation graph (from `POST /v1/ingest/regulation`) | `neo4j` volume, the only copy | Volume backup | Otherwise only recoverable by re-uploading the source files (section 6.4) |
| Supplier onboarding graph mirror | `neo4j` volume, mirrored from Postgres | Volume backup | Postgres is the source, but no rebuild tool exists (section 6.4) |
| Stripe subscription and customer state (`billing:*`) | `Redis`, the only copy | Volume backup | No rebuild from Stripe exists (section 6.5) |
| JWT signing-key registry, token revocations, MFA lockouts, idempotency cache, rate limits | `Redis` | Volume backup | Restoring an old snapshot re-enables keys revoked since then (section 6.5) |
| Browser sessions, task queue, webhook outbox | Postgres | As Postgres | — |
| Raw uploaded documents (`RAW_DATA_BUCKET`) and normalized documents (`PROCESSED_DATA_BUCKET`) | External object storage, the only copy (Postgres keeps metadata, hashes and the storage key) | Nothing in Railway | Open question 3. The hashes in Postgres can verify a re-supplied original |
| Code | GitHub | GitHub | — |
| Deployed images | Railway | Railway image retention (plan-dependent) | Open question 2 |
| Railway service settings (images, start commands, volumes, TCP proxies) | Railway | Nothing | Only `railway.toml` is in the repo. Recreate a lost service from the table in section 2 |

## 5. Recovery objectives

Stated only as far as the backups support them:

| Datastore | RPO | Mechanism | RTO |
|---|---|---|---|
| Postgres | About 1 min, back to 2026-09-28 23:57 UTC (window grows to ~4 weeks) | PITR (section 6.2) | Not measured |
| Postgres, older than the PITR window | 24 h, back 89 days | Volume backups (section 6.1) | Not measured |
| Redis | 24 h | Volume backups (section 6.5) | Not measured |
| Neo4j | 24 h | Volume backups (section 6.4) | Not measured |

Until 2026-09-28 23:55 UTC there were no schedules and no PITR, so RPO was
unbounded.

The previous targets in this file (RTO 4 h, RPO 15 min) were never backed by
any backup mechanism, and have been removed. Set an RTO only after a timed
production-size restore (section 9).

## 6. Restore procedures

Set the project ID once per shell. It is an identifier, not a secret:

```bash
P=4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51
```

The logical-dump commands use Homebrew's PostgreSQL 18 client
(`/opt/homebrew/opt/postgresql@18/bin`), because pg_dump cannot dump a
server newer than itself, and the server is 18.

Never run `railway variables`, `railway run ... env` or `printenv` during
recovery; they print secrets. Every command below injects values into a child
process without printing them.

### 6.1 Postgres from a Railway volume backup (primary path)

Use this for data loss or corruption, when a backup exists from before the
damage. The restore replaces the volume that is mounted to the `Postgres`
service.

1. Record the current state so the restore can be undone. Railway also keeps
   the old volume, unmounted.

   ```bash
   railway postgres pitr backup create --name pre-restore-$(date -u +%Y%m%dT%H%M) -p $P -e production -s Postgres
   ```

2. Choose a backup:

   ```bash
   railway postgres pitr backup list -p $P -e production -s Postgres
   ```

3. Restore it. In the dashboard: `Postgres` → Backups → the backup → Restore,
   then review the staged change (Details) and click Deploy. From the CLI,
   which overwrites the data in place:

   ```bash
   railway postgres pitr backup restore <BACKUP_ID> -p $P -e production -s Postgres
   ```

   Railway mounts a new volume named after the backup's date. The previous
   volume keeps its name and stays in the project, unmounted.

4. Redeploy `RegEngine`. This resets its connection pools and runs
   `run-migrations.sh`, which upgrades an older schema to head and re-applies
   the runtime grants.

   ```bash
   railway redeploy -p $P -e production -s RegEngine --yes
   ```

5. If a role password was rotated after the backup was taken, the restored
   cluster holds the old one. The new deployment then fails to authenticate
   and never passes its healthcheck, and the running deployment cannot reach
   the database either. Give each affected role a new password and update its
   URL variable (section 8.1, steps 2 to 5).

6. Verify (section 6.6).

Writes made after the backup are lost. The unmounted previous volume still
holds them; recovering rows from it means mounting it on a temporary service,
which has not been tested.

### 6.2 Postgres point-in-time restore

```bash
railway postgres pitr restore --at 2026-10-01T12:00:00Z -p $P -e production -s Postgres
```

Railway creates a new service, `Postgres-restored-YYYYMMDD-HHMM`, and leaves
the source untouched. Roles and passwords come with it, because this is a
physical restore. To cut over, change the host in `DATABASE_URL`,
`ADMIN_DATABASE_URL` and `MIGRATIONS_DATABASE_URL` on `RegEngine` to the new
service's private host, in the order given in section 6.3, step 4 (dashboard
Variables tab; keep the variables sealed). Then redeploy `RegEngine` and
verify (section 6.6). This is also the only way
to rehearse a production restore without touching production data.

### 6.3 Postgres from a logical dump (copy outside Railway)

`scripts/backup_postgres.sh` writes plain SQL piped through gzip, from
`pg_dump --no-owner --no-privileges`, for one database. RLS settings and
policies are included. Roles, object owners and GRANTs are not, so the restore
recreates them. The test `tests/scripts/test_backup_postgres_format.py` pins
this format to the restore command below.

**Take a dump:**

```bash
railway run --no-local -p $P -e production -s Postgres -- \
  sh -c 'PATH=/opt/homebrew/opt/postgresql@18/bin:$PATH PGHOST="$RAILWAY_TCP_PROXY_DOMAIN" PGPORT="$RAILWAY_TCP_PROXY_PORT" PGSSLMODE=require exec ./scripts/backup_postgres.sh'
```

- `-s Postgres` injects that service's own `PG*` variables, which log in as the
  template superuser. Only a superuser or BYPASSRLS login dumps every row of
  the FORCE RLS tables. Never dump with `RegEngine`'s `DATABASE_URL`: pg_dump
  as the NOBYPASSRLS role `regengine` fails on RLS tables.
- The service's `PGHOST` is its private domain, which a laptop cannot reach.
  The override points libpq at the public TCP proxy. The single quotes make
  the variables expand in the shell that `railway run` starts, not in yours;
  nothing is printed.
- Output: `backups/postgres/railway_YYYYMMDD_HHMMSS.sql.gz` (`backups/` is
  gitignored). The script checks that the file is valid gzip containing a
  pg_dump stream, and deletes it if the dump failed. It uploads to S3 only if
  `S3_BUCKET` is set.

**Restore into a new Railway Postgres service:**

1. Add a Postgres service to the `production` environment and name it
   `Postgres-restore`: dashboard → New → Database → PostgreSQL, or
   `railway add --database postgres -p $P -e production` and then rename it.
   Set its image to
   `ghcr.io/railwayapp-templates/postgres-ssl:18`. The template's default tag
   and TCP proxy are not verified.

2. Open psql on it as its superuser (`railway connect Postgres-restore -p $P -e production`)
   and create the roles and an empty database owned by the migrator.
   Generate a random password for each role, and do not paste it into chat or
   tickets. `\password` prompts for it and keeps it out of shell history.

   ```sql
   CREATE ROLE regengine LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
   CREATE ROLE regengine_sysadmin LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
   CREATE ROLE regengine_migrator LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
   \password regengine
   \password regengine_sysadmin
   \password regengine_migrator
   CREATE DATABASE regengine OWNER regengine_migrator TEMPLATE template0;
   REVOKE ALL ON DATABASE regengine FROM PUBLIC;
   GRANT CONNECT ON DATABASE regengine TO regengine, regengine_sysadmin, regengine_migrator;
   ALTER ROLE regengine_migrator IN DATABASE regengine SET search_path = public, fsma, extensions;
   ALTER ROLE regengine_migrator IN DATABASE regengine SET timezone = 'UTC';
   ```

3. Load the dump **as `regengine_migrator`**, so that it owns every restored
   object. psql prompts for the migrator password (`-W`):

   ```bash
   railway run --no-local -p $P -e production -s Postgres-restore -- \
     sh -c 'unset PGPASSWORD; export PATH=/opt/homebrew/opt/postgresql@18/bin:$PATH PGHOST="$RAILWAY_TCP_PROXY_DOMAIN" PGPORT="$RAILWAY_TCP_PROXY_PORT" PGSSLMODE=require PGUSER=regengine_migrator PGDATABASE=regengine; gunzip -c backups/postgres/railway_YYYYMMDD_HHMMSS.sql.gz | psql -X -W -q -v ON_ERROR_STOP=1'
   ```

4. Point `RegEngine` at the new database. Write each URL from stdin so that it
   never appears in a command line, and write `MIGRATIONS_DATABASE_URL` last.
   If a deploy starts partway through, it then stops at `run-migrations.sh`
   instead of booting against a mix of old and new databases. The host is the
   new service's private host, `${{Postgres-restore.PGHOST}}:${{Postgres-restore.PGPORT}}`,
   or its rendered value.

   ```bash
   railway variable set DATABASE_URL --stdin --skip-deploys -p $P -e production -s RegEngine
   railway variable set ADMIN_DATABASE_URL --stdin --skip-deploys -p $P -e production -s RegEngine
   railway variable set MIGRATIONS_DATABASE_URL --stdin --skip-deploys -p $P -e production -s RegEngine
   ```

   Seal all three in the dashboard afterwards.

5. Redeploy `RegEngine` (`railway redeploy -p $P -e production -s RegEngine --yes`).
   On boot, `run-migrations.sh` reports `DB state: ALREADY_MANAGED`, upgrades
   to head, and re-applies the v111 runtime-role cutover. That cutover rebuilds
   every runtime GRANT the dump left out, and logs
   `runtime role cutover applied as role=regengine_migrator database=regengine`.

6. Verify (section 6.6). Keep the old `Postgres` service until verification
   passes.

The dump command, the restore as migrator, the row-count check and the
migrate-and-cutover step were drilled on staging data on 2026-09-28 (section
9); the restore target was a local PostgreSQL 18. Steps 1, 2, 4 and 5, and the
`railway run` wrapper in step 3, have not been run.

### 6.4 Neo4j

**What it holds:**

- The regulation graph (Regulation, Section, Citation, Obligation, Penalty
  nodes) loaded by `POST /v1/ingest/regulation`. The staged upload file is
  deleted after loading, so this is the only copy
  (`services/ingestion/app/regulation_loader.py`).
- A mirror of supplier onboarding data (invites, facilities, FTL categories,
  lots, CTE events). Postgres is the source of truth, but no rebuild or
  backfill tool exists. `graph_outbox` is never populated, because no caller
  passes `db=` (`services/admin/app/supplier_graph_sync.py`,
  `services/admin/app/graph_outbox.py`).

**Impact.** `/readiness` does not probe Neo4j in production. If Neo4j is
down, `GET /v1/supplier/facilities/{id}/required-ctes` falls back to Postgres.
If Neo4j is up but **empty**, that route returns empty categories and CTEs
and does not fall back. FDA export and CTE ingestion read Postgres and are
unaffected.

**Restore from a Railway volume backup:**
`neo4j` → Backups → the backup → Restore → Deploy. The CLI form,
`railway postgres pitr backup restore <BACKUP_ID> -p $P -e production -s neo4j`,
has not been tried on a non-Postgres service (open question 9). Afterwards:

- The restored store keeps the password it had when backed up, because Neo4j
  sets its initial password only on an empty store. If `NEO4J_PASSWORD` was
  rotated since, set it back to match, or change the password with
  `cypher-shell` (section 8.3).
- GDPR erasure deletes a user's identity graph nodes (`User`, `Account`,
  `TeamMember`, `SupplierContact`) and rewrites `actor_id` / `user_id` on
  their other graph nodes to a pseudonymous token
  (`services/admin/app/erasure_routes.py`). A backup from before an erasure
  brings the original nodes back, so repeat any erasure completed after the
  backup was taken.

**With no backup:** re-upload the regulation source files through
`POST /v1/ingest/regulation`. The supplier mirror stays empty until a rebuild
tool exists.

**`scripts/backup_neo4j.sh` does not apply to Railway.** It stops a
docker-compose service (or uses a local `neo4j-admin`), because Community
Edition can only be dumped offline, and Railway has neither. Its output is
restored on a local or docker-compose host, with Neo4j stopped:

```bash
neo4j-admin database load neo4j --from-path=backups/neo4j/<YYYYMMDD_HHMMSS> --overwrite-destination=true
```

### 6.5 Redis

Redis is not a cache here. Production refuses to start without it, and it
holds state that exists nowhere else.

| Keys | Only copy? | Lost if Redis is emptied | Effect of restoring an old snapshot |
|---|---|---|---|
| `billing:tenant:{id}`, `billing:subscription:*`, `billing:customer:*`, `billing:session:*` (no expiry) | **Yes** (`DESIGN_metering-billing.md`, `services/ingestion/app/stripe_billing/state.py`) | Every tenant gets 402 on paid routes (`POST /api/v1/webhooks/ingest`, FDA export, supplier-portal submit). Subscription webhooks cannot find their tenant and are dropped after 72 h. A new checkout creates a new tenant and a duplicate Stripe customer | Billing status reverts to the snapshot's; reconcile against Stripe for changes since then |
| `regengine:jwt:keys` (signing-key registry: rotated keys, revocation flags) | Yes, except the base key, which comes from `AUTH_SECRET_KEY` | The registry restarts from `AUTH_SECRET_KEY`. Tokens signed with rotated keys fail, so users log in again. If `AUTH_SECRET_KEY` had been revoked, it becomes valid again | **Keys revoked after the snapshot become valid again** |
| `regengine:jwt:revoked:*` | Yes | Revoked access tokens work again for their remaining lifetime (up to 15 min in production; 1 h if unknown) | Same |
| Old-style bearer and refresh sessions, MFA lockout and TOTP-replay keys, OTP counters | Yes | Those sessions end; lockouts and counters reset. Browser cookie sessions are in Postgres and survive | Sessions revoked since the snapshot come back |
| `idempotency:*` (24 h), `bulk_upload:*` (1 h), `edi:interchange:*` (7 d) | Yes, but short-lived | Retried POSTs, in-flight bulk uploads and EDI retransmissions can run again or must be redone | Stale idempotency reservations can return 409 until they expire |
| Rate-limit and throttle counters | No | Counters reset | — |

**Restore from a Railway volume backup:**

1. `Redis` → Backups → the backup → Restore → Deploy. The CLI form,
   `railway postgres pitr backup restore <BACKUP_ID> -p $P -e production -s Redis`,
   has not been tried on a non-Postgres service.
2. Redeploy `RegEngine` so that its workers reload the signing-key registry
   (each worker caches it until restart):
   `railway redeploy -p $P -e production -s RegEngine --yes`.
3. Rotate the JWT signing key immediately (CREDENTIAL_ROTATION_RUNBOOK.md,
   "JWT and session-key rotation"). This closes the re-enabled-key window and
   forces every bearer token to be re-issued.
4. Reconcile billing. In Stripe, list subscription events since the backup's
   timestamp and correct each affected tenant. No tool does this (open
   question 12).

**With no backup:** start Redis empty and redeploy `RegEngine`. Rotate
`AUTH_SECRET_KEY` if it had ever been revoked through the registry. Billing
must then be rebuilt tenant by tenant from Stripe (open question 12).
`SUBSCRIPTION_GATE_FAIL_OPEN=true` on `RegEngine` lifts the 402s in the
meantime; it also disables billing enforcement, so it is an owner decision.

### 6.6 Verify after any database restore

1. The new deployment reaches `SUCCESS`, which means `/readiness` returned 200
   within 300 s:
   `railway deployment list -p $P -e production -s RegEngine`.
   With `REGENGINE_REQUIRE_RLS_ENFORCEMENT=1`, both database engines abort
   boot on a superuser or BYPASSRLS login, missing FORCE RLS, or ACL drift
   (DATABASE_ROLE_CUTOVER.md section 4), so a `SUCCESS` deployment is itself
   evidence of the runtime-role posture.
2. The deploy log contains `runtime role cutover applied as role=regengine_migrator`.
3. `runbooks/verify-v126-runtime-grants.sql`, run as the migration owner,
   ends with `== READY: every check ok (failing: 0)`.
4. Row counts are plausible for the recovery point. As the template superuser
   (`railway connect Postgres`), this lists every table's exact count:

   ```sql
   SELECT format('%I.%I', n.nspname, c.relname) AS tbl,
          (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname), false, true, '')))[1]::text::bigint AS row_count
   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname IN ('public','fsma','audit','dlq','ingestion') AND c.relkind IN ('r','p')
   ORDER BY 1;
   ```

5. The audit hash chain verifies for each tenant (`POST /api/v1/chain/verify-all`,
   if that router is enabled; open question 11).
6. No scheduler job is stuck: the `RegEngine` logs show
   `Remediation Notification Outbox Drain ... executed successfully` every 30
   seconds, and no `maximum number of running instances reached` (section 3,
   step 2).

## 7. Service recovery (the `RegEngine` app)

- **Crashed.** Railway restarts the container up to 3 times (`railway.toml`).
  After that, use the deployment's Restart button, or redeploy the same
  build:

  ```bash
  railway redeploy -p $P -e production -s RegEngine --yes
  ```

  `--from-source` deploys the latest commit on `main` instead.

- **Bad deploy.** Dashboard → `RegEngine` → Deployments → ⋯ on the last good
  deployment → Rollback. A rollback restores that deployment's image **and its
  variables**. On 2026-09-28 the five most recent production deployments
  reported `canRollback: true`. Do not use `railway down`; it removes the
  latest deployment and is not a rollback.

  Two limits:

  1. **Schema does not roll back.** On boot, the older image runs
     `alembic upgrade head`. If the database is at a revision that image does
     not know, Alembic fails, the deployment never passes `/readiness`, and
     Railway keeps the current deployment serving. To go back past a
     migration, restore the database (section 6) or ship a forward fix.
     Rolling back to an image older than v098 first requires the ROLLBACK
     section of `runbooks/prod-revoke-create-after-v098.sql`.
  2. **Variables roll back too.** After a credential rotation, rolling back to
     an earlier deployment restores the old credentials. The database login
     then fails, or a compromised secret returns. After rotating, only deploy
     forward.

- **Frontend.** Vercel instant rollback. This document does not cover it.

## 8. Credential rotation after a compromise

Order of work: contain, rotate, redeploy, verify, then record deployment IDs
and times without values (CREDENTIAL_ROTATION_RUNBOOK.md, step 6).

**Contain.** If a database, Redis or Neo4j credential may have leaked, remove
that service's public TCP proxy. Deleting it cuts internet access to that
service. The app is unaffected only if it connects over the private network.
For Postgres it does: the three URLs pointed at `postgres.railway.internal`
when last checked, on 2026-07-29. Whether `REDIS_URL` and `NEO4J_URI` use
private hosts is not verified. Check each in the dashboard's Variables tab
before deleting that service's proxy.

```bash
railway tcp-proxy list -p $P -e production -s Postgres
railway tcp-proxy delete <PROXY_ID> -p $P -e production -s Postgres
```

Without the proxy, laptop access goes over SSH (`railway connect Postgres --ssh`),
and the `$RAILWAY_TCP_PROXY_*` variables in section 6.3 no longer exist.

### 8.1 Production database roles

The staging bootstrap script refuses production, so production rotation is
manual. It has not been drilled.

1. Open psql as the template superuser: `railway connect Postgres -p $P -e production`.
2. Set new passwords (random, not pasted anywhere):
   `\password regengine`, `\password regengine_sysadmin`, `\password regengine_migrator`.
3. End sessions that authenticated with the old passwords:

   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity
   WHERE usename IN ('regengine', 'regengine_sysadmin', 'regengine_migrator');
   ```

4. Write the new URLs from stdin, in this order: `DATABASE_URL`, then
   `ADMIN_DATABASE_URL`, then `MIGRATIONS_DATABASE_URL`. Use the
   `railway variable set ... --stdin --skip-deploys` commands in section 6.3,
   step 4. The app is unavailable from step 2 until the redeploy finishes.
5. `railway redeploy -p $P -e production -s RegEngine --yes`, then run the
   checks in DATABASE_ROLE_CUTOVER.md section 4.

Rotating the template superuser is open question 8.

### 8.2 Staging database roles

```bash
bash scripts/railway/bootstrap_staging_database.sh                                    # dry run
bash scripts/railway/bootstrap_staging_database.sh --apply --rotate-passwords --redeploy
```

`--rotate-passwords` applies only after staging has been bootstrapped. On
2026-09-28 it had not been (section 2). The first `--apply` creates the roles
with new passwords, which is itself the rotation. Because `regengine` and
`regengine_sysadmin` already exist, the dry run may require
`--adopt-existing-roles`; it says so if it does. See DATABASE_ROLE_CUTOVER.md
section 6.

### 8.3 Other secrets

| Secret (variable) | Where | Rotation |
|---|---|---|
| JWT signing keys | Redis key registry (`regengine:jwt:keys`) | CREDENTIAL_ROTATION_RUNBOOK.md, "JWT and session-key rotation" |
| Tenant and workload API keys | Postgres | CREDENTIAL_ROTATION_RUNBOOK.md, "Rotation order" |
| `REDIS_PASSWORD` | `Redis` service; its start command runs `--requirepass $REDIS_PASSWORD` | Set a new value on `Redis` (it redeploys), confirm `REDIS_URL` on `RegEngine` resolves to it, then redeploy `RegEngine`. Not drilled; whether `REDIS_URL` is a reference variable in production is not verified |
| Neo4j password (`DB_PASSWORD` on `neo4j`, `NEO4J_PASSWORD` on `RegEngine`) | `neo4j` volume | Neo4j applies its initial password only to an empty store, so changing `DB_PASSWORD` alone does nothing. Change it with `cypher-shell` over the TCP proxy (`ALTER CURRENT USER SET PASSWORD FROM '<old>' TO '<new>'`), then update both variables and redeploy `RegEngine`. Not drilled |
| `STRIPE_SECRET_KEY`, `RESEND_API_KEY` (shared variable), `OBJECT_STORAGE_ACCESS_KEY_ID` / `OBJECT_STORAGE_SECRET_ACCESS_KEY` | Provider consoles | Roll at the provider, set the new value from stdin, redeploy `RegEngine` |
| `AUTH_SECRET_KEY`, `AUDIT_INTEGRITY_KEY`, `AUTH_OTP_HMAC_SECRET`, `TOOL_ACCESS_SECRET`, `WEBHOOK_HMAC_SECRET`, `KAFKA_EVENT_SIGNING_KEY`, `REGENGINE_PROXY_IP_HMAC_KEY`, `SCHEDULER_API_KEY`, `API_KEY`, `REGENGINE_API_KEY` | `RegEngine` variables | Not documented. Some of these sign or fingerprint stored data (for example, `AUTH_OTP_HMAC_SECRET` feeds `user_emails.email_fingerprint`), so rotating them can invalidate existing records. Review each one's readers before rotating |

## 9. Drills and backup changes

| Date | What | Result |
|---|---|---|
| 2026-09-28 | Staging `railway` database (alembic v079, 94 tables, 236 rows). Dumped with the section 6.3 command (`-e staging`). Restored as `regengine_migrator` into a local PostgreSQL 18.6 with the three roles created per section 6.3, step 2. Then ran `scripts/run-migrations.sh` as the migrator. | Dump 52 KB in about 10 s. Restore exited 0 with `ON_ERROR_STOP`. Per-table row counts identical to the source, 94 of 94 tables. Every restored object owned by `regengine_migrator`. RLS flags and all 102 policies present. `run-migrations.sh` ran 62 revisions (v079 to head) and logged `runtime role cutover applied`. Posture: `regengine\|regengine\|f\|f\|f\|f\|f` and `regengine_sysadmin\|regengine_sysadmin\|f\|f\|f\|f\|f`. `verify-v126-runtime-grants.sql`: `READY: every check ok (failing: 0)` |
| 2026-09-28 | Staging: enabled backup schedules on all three volumes, then PITR on `Postgres`. | Postgres redeployed and was ready about 1 minute after the deploy started (Railway stops the old container without a clean shutdown; crash recovery was immediate). Stanza created, first WAL pushed, first full backup at 23:54:22, restorable to 23:54:23 |
| 2026-09-28 | Production: on-demand backups `pre-pitr-enable-20260928` of all three volumes, schedules on all three, then PITR on `Postgres`. | `/readiness` 503 for about 15–20 s (23:56:32–23:56:46). First full backup at 23:56:58, restorable to 23:57:00. The scheduler's outbox-drain job hung on a dead connection until `RegEngine` was redeployed at 23:59:51 (no downtime, `/readiness` 200 throughout); the job then ran every 30 s |

Not yet drilled: any restore of a production backup, any Railway-side restore
step, and timing at production size. Rehearse a production restore with
section 6.2 (it creates a sibling service and leaves production untouched),
then delete the sibling. A volume-backup restore (section 6.1) replaces the
live volume, so it cannot be rehearsed in production. Record each drill here:
date, backup ID, duration, counts, and verification output. Never record
secrets.

## 10. History

Before 2026-09-28 this file described an AWS deployment: `aws s3 cp` backups
to `s3://regengine-backups`, ECS health checks and `aws logs tail /ecs/...`,
`aws rds restore-db-instance-to-point-in-time`, Route 53 failover, EC2
security-group isolation, and Kafka topic mirroring. `docs/runbooks/disaster-recovery.md`
described docker-compose services with S3 uploads. Production never ran on
either. Both texts remain in git history:

```bash
git log --follow -p -- docs/operations/DISASTER_RECOVERY.md
git log -p -- docs/runbooks/disaster-recovery.md
```

`scripts/backup_neo4j.sh` still targets a docker-compose or local Neo4j; see
section 6.4.
