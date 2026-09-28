# Runtime Database Role Cutover

This is the blocking database procedure for staging and production. RegEngine
uses three independent PostgreSQL login roles against one database. A fourth,
provider-controlled credential is used only to provision roles and transfer
ownership; it is never an application or Alembic credential.

| Variable | Exact role | Where it is allowed |
|---|---|---|
| `DATABASE_URL` | `regengine` | Consolidated tenant-data runtime |
| `ADMIN_DATABASE_URL` | `regengine_sysadmin` | Control plane and classified maintenance |
| `MIGRATIONS_DATABASE_URL` | `regengine_migrator` | One-off migration/pre-deploy job only |
| Provider credential (do not store as a RegEngine variable) | Provider-defined | Role creation, `CONNECT`, and ownership transfer only |

All three RegEngine roles must be `NOSUPERUSER NOBYPASSRLS NOCREATEDB
NOCREATEROLE NOREPLICATION`. None may participate in an incoming or outgoing
role membership. The two runtime roles must own no database, schema, relation,
sequence, or function. The migration role must exclusively own the database
and protected application objects. Never put a URL, password, token, or key in
a command transcript or release-evidence record.

## 1. Provision roles with the provider credential

Create or pin the roles in a provider-admin session. Supply passwords through
the provider secret interface, not SQL history.

```sql
ALTER ROLE regengine
  LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE regengine_sysadmin
  LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE regengine_migrator
  LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;

GRANT CONNECT ON DATABASE <regengine_database>
  TO regengine, regengine_sysadmin, regengine_migrator;
```

Remove every incoming or outgoing membership involving any RegEngine database
role. Do not replace direct ACLs with `GRANT regengine TO
regengine_sysadmin`; v111 rejects that topology.

```sql
SELECT member_role.rolname AS member_role,
       granted_role.rolname AS inherited_role
FROM pg_auth_members AS membership
JOIN pg_roles AS member_role ON member_role.oid = membership.member
JOIN pg_roles AS granted_role ON granted_role.oid = membership.roleid
WHERE member_role.rolname IN (
          'regengine', 'regengine_sysadmin', 'regengine_migrator'
      )
   OR granted_role.rolname IN (
          'regengine', 'regengine_sysadmin', 'regengine_migrator'
      );
```

The result must be empty. Revoke each reported membership from the provider
session before continuing.

## 2. Make the migration role the dedicated owner

For a new database, create it with `regengine_migrator` as owner. For an
existing database, change the database owner and transfer every protected
schema object from the previous migration owner before running Alembic.

```sql
ALTER DATABASE <regengine_database> OWNER TO regengine_migrator;
```

Connect to that database as the provider administrator and inventory ownership
in `public`, `fsma`, `audit`, `dlq`, and `ingestion`. The database, those
schemas, and all relations, sequences, indexes, and application functions in
them must resolve to `regengine_migrator` before v111 can converge the ACLs.
On PostgreSQL 15+, `public` may resolve to the built-in
`pg_database_owner`; v111 accepts that alias only after independently proving
that `regengine_migrator` owns the current database. Trusted extension member
functions may retain their provider bootstrap owner, but the containing
extension must be owned by `regengine_migrator`.

```sql
SELECT 'schema' AS kind, n.nspname AS object_name,
       pg_get_userbyid(n.nspowner) AS owner
FROM pg_namespace AS n
WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
UNION ALL
SELECT CASE
           WHEN c.relkind = 'S' THEN 'sequence'
           WHEN c.relkind IN ('i', 'I') THEN 'index'
           ELSE 'relation'
       END,
       format('%I.%I', n.nspname, c.relname),
       pg_get_userbyid(c.relowner)
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
  AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f', 'i', 'I')
UNION ALL
SELECT 'extension', e.extname, pg_get_userbyid(e.extowner)
FROM pg_extension AS e
JOIN pg_namespace AS n ON n.oid = e.extnamespace
WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
UNION ALL
SELECT 'function',
       format('%I.%I(%s)', n.nspname, p.proname,
              pg_get_function_identity_arguments(p.oid)),
       pg_get_userbyid(p.proowner)
FROM pg_proc AS p
JOIN pg_namespace AS n ON n.oid = p.pronamespace
WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
  AND NOT EXISTS (
      SELECT 1
      FROM pg_depend AS dependency
      WHERE dependency.classid = 'pg_proc'::regclass
        AND dependency.objid = p.oid
        AND dependency.deptype = 'e'
  )
ORDER BY 1, 2;
```

Use provider-reviewed `ALTER ... OWNER TO regengine_migrator` statements for
mismatched schemas, relations, and application functions. PostgreSQL has no
`ALTER EXTENSION ... OWNER` command; an extension-owner mismatch requires
provider-reviewed `REASSIGN OWNED` or a clean database provisioned under the
migration role. `REASSIGN OWNED` is acceptable only when the old owner is a
dedicated RegEngine migration role and the provider has confirmed that it owns
no unrelated objects in the database. A migration-owner change is not repaired
merely by re-running v111: ownership must be transferred first.

## 3. Run the full migration chain with only the migration credential

The migration/pre-deploy job receives `MIGRATIONS_DATABASE_URL`; it must not
receive either runtime URL. The web process receives `DATABASE_URL` and
`ADMIN_DATABASE_URL`; it must not receive the provider credential. The current
container runner also unsets `MIGRATIONS_DATABASE_URL` before `gunicorn` as a
defense in depth while deployments transition to a separate pre-deploy job.

```bash
MIGRATIONS_DATABASE_URL='<injected regengine_migrator URL>' \
REGENGINE_MIGRATIONS_ROLE=regengine_migrator \
  ./scripts/run-migrations.sh
```

The runner has only three accepted states:

- fresh database: run the complete Alembic chain;
- populated `alembic_version`: upgrade to head; or
- application schema without trusted migration state: exit 65 and require an
  operator-reviewed recovery.

It never stamps an unknown schema to head. After Alembic, it re-applies the
same v111 cutover used by CI. The cutover uses closed table, column, sequence,
and function inventories; removes wildcard/default runtime grants; proves the
dedicated-owner role, database, schemas, relations, indexes, extensions, and
application functions; and leaves new objects inaccessible until a reviewed
migration classifies them.

For an audited repair after ACL drift, use the same migration credential:

```bash
MIGRATIONS_DATABASE_URL='<injected regengine_migrator URL>' \
REGENGINE_MIGRATIONS_ROLE=regengine_migrator \
  .venv/bin/python scripts/apply_runtime_role_cutover.py
```

`REGENGINE_MIGRATIONS_ROLE` is a non-secret identity pin and must match the
username encoded in `MIGRATIONS_DATABASE_URL`; when omitted, v111 derives the
same exact identity from the URL. Do not use this repair command to conceal
ownership drift. It intentionally fails for a superuser/BYPASSRLS credential,
role membership, mismatched database/schema/object ownership, or an identity
pin mismatch until the provider administrator corrects the posture.

### v126 (`c51d4898e0a2`): CSV retention and agent-worker grants

v126 grants the runtime role what `POST /api/v1/ingest/csv` and the
agent-artifact worker write, and pins each `fsma.manifest_blobs` row to its own
tenant's run with an `(ingestion_run_id, tenant_id)` foreign key.

- Before the deploy, run `runbooks/predeploy-v126-misattached-blobs.sql` from a
  provider superuser or BYPASSRLS session. It must return no rows; otherwise
  v126 refuses with the row count and changes nothing. Do not review those rows
  from a plain schema-owner session: under FORCE RLS it errors without a
  tenant, and with one it sees no `fsma.ingestion_runs` rows and flags every
  blob of that tenant. The runbook header shows the schema-owner alternative
  (NO FORCE inside a transaction that is rolled back).
- After the deploy, and again after the next one, run
  `runbooks/verify-v126-runtime-grants.sql` as the migration owner. Every row,
  including `== READY`, must report `ok = t`. It pins its own search_path, so a
  session with `search_path=public,fsma,extensions` gives the same result.

## 4. Configure and verify runtime boot

The consolidated Railway service requires:

```text
REGENGINE_ENV=production
REGENGINE_REQUIRE_RLS_ENFORCEMENT=1
DATABASE_URL=<regengine credential>
ADMIN_DATABASE_URL=<regengine_sysadmin credential to the same database>
ENABLED_ROUTERS=<the release-approved exact allowlist>
```

Production hard-requires RLS regardless of configuration drift; keeping
`REGENGINE_REQUIRE_RLS_ENFORCEMENT=1` is explicit deployment evidence. Both
engines must abort on an unknown role, an inert role, a database mismatch,
missing `FORCE RLS`, policy-manifest drift, unexpected ownership/membership,
or ACL drift.

Run the following from a shell where the URLs are already injected. These
commands output posture and non-secret database identity only.

```bash
psql "$DATABASE_URL" -XAt -v ON_ERROR_STOP=1 -c \
  "SELECT session_user, current_user, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication, current_database(), inet_server_addr(), inet_server_port() FROM pg_roles WHERE rolname = current_user;"

psql "$ADMIN_DATABASE_URL" -XAt -v ON_ERROR_STOP=1 -c \
  "SELECT session_user, current_user, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication, current_database(), inet_server_addr(), inet_server_port() FROM pg_roles WHERE rolname = current_user;"
```

The first seven fields must be `regengine|regengine|f|f|f|f|f` and
`regengine_sysadmin|regengine_sysadmin|f|f|f|f|f`. Database, server address,
and port must match. A provider login with `SET ROLE` is rejected even when
its effective role name looks correct.
From the protected metrics endpoint, require both series to be zero:

```text
regengine_rls_enforcement_inert{engine="shared"} 0
regengine_rls_enforcement_inert{engine="admin"} 0
```

Every PostgreSQL transaction begins by setting all security GUCs to an empty
or false transaction-local baseline on the same backend that runs the query.
Tenant transactions then set only `app.tenant_id`. Global control-plane work
must use `ADMIN_DATABASE_URL` and an approved call site that explicitly sets
`regengine.is_sysadmin=true` for that transaction. The retired
`regengine.system_context` GUC is always reset false and no current RLS policy
may reference it.

## 5. Acceptance evidence and residual risk

Run the direct-role suite with four independently authenticated URLs: the
migration owner, runtime role, admin role, and a provider-only fixture role for
hostile topology tests. Any skip fails CI. Also run the fresh-chain, seeded
mid-chain, Alembic drift, migrated RLS, and two-tenant route matrix gates.

Database triggers add an immutable database-role trail for privileged DML.
PostgreSQL DML triggers cannot audit `SELECT`, and a database role is not a
human identity, so endpoint audit remains authoritative for user ID, session
ID, action, target, request ID, source IP, and selected tenant.

RLS protects application and connection-pool mistakes. It does not make a
stolen raw runtime credential safe: a holder of `regengine` can set the
tenant GUC before issuing SQL, and a holder of `regengine_sysadmin` can arm its
exact-role global policies. Keep credentials in the platform secret store,
rotate on suspected disclosure, and do not expose database connectivity to
customers.

Promotion is blocked unless both runtime canaries report enforced, the
two-tenant matrix shows no cross-tenant read/write/artifact change, and the
sanitized release record identifies the frontend SHA, backend SHA/deployment
ID, Alembic head, enabled-router set, commands, results, and verification date.
Never include secret values or connection URLs. A bypass-RLS credential,
schema-owner runtime, shared admin key, disabled posture gate, or wider router
set is not an acceptable rollback.

## 6. Staging: one-command fresh-database bootstrap

Staging never had the dedicated-owner topology, so every staging deploy since
`scripts/run-migrations.sh` began requiring `MIGRATIONS_DATABASE_URL` exits
before gunicorn starts. Staging uses the FRESH path. The script creates a new
database, `regengine_staging`, owned by `regengine_migrator`. The existing
staging database (the one `DATABASE_PUBLIC_URL` names, normally `railway`) is
left untouched as an archive, and the script refuses to target it. This avoids
transferring ownership, recreating extensions, and running the irreversible
old-revision data migrations (v088, v090, v091, v094).

Run it from the repository root. It needs the Railway CLI 5.47.2 or newer
(logged in), `psql` and `python3`:

```bash
bash scripts/railway/bootstrap_staging_database.sh            # dry run: read-only checks + full plan
bash scripts/railway/bootstrap_staging_database.sh --apply    # execute
bash scripts/railway/bootstrap_staging_database.sh --apply --redeploy   # execute, then redeploy RegEngine
```

The script refuses a run, before writing anything, in each of these cases:

- The environment is not exactly `staging`. Production is always refused.
- `--database` does not fully match `^regengine_[a-z0-9_]{1,53}$`.
- The Railway CLI is older than 5.47.2. Older CLIs hide sealed variables, so
  existing secrets would be regenerated.
- `railway run` does not report exactly this project
  (`4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51` unless `--project` says otherwise)
  and environment.
- The Postgres service's `DATABASE_PUBLIC_URL` is not that service's own
  `RAILWAY_TCP_PROXY_DOMAIN:RAILWAY_TCP_PROXY_PORT`.
- The server is older than PostgreSQL 15.
- `psql --version` reports a major version older than 13. libpq before 13
  silently ignores `PGCHANNELBINDING`, and that setting is what protects the
  passwords (see step 1). The check relies on psql being linked against the
  libpq of its own major version, as the PGDG, Homebrew and Debian/Ubuntu
  packages are.
- A RegEngine role is a member of a foreign role and used that membership's
  ADMIN OPTION to grant the foreign role to another role outside RegEngine.
  Revoking that membership would cascade outside RegEngine, and
  `--adopt-existing-roles` never does that. Revoke those grants by hand after
  review, then re-run. The dry run lists them as `BLOCKING GRANT`.
- A pre-existing `regengine*` role is used outside the target database. That
  covers objects, privileges or settings in other databases, open sessions
  there, role memberships, and any elevated attribute (SUPERUSER, BYPASSRLS,
  CREATEROLE, CREATEDB or REPLICATION). The same check also runs on the server
  inside the provisioning transaction. Roles are cluster-wide, so changing
  such a role needs `--adopt-existing-roles` after review. The dry run lists
  what it found.
- A pre-existing role that this bootstrap did not create has a URL variable
  that is missing, sealed, or not pointing at that role on
  `regengine_staging`. The URL must use the staging private endpoint:
  `${{Postgres.PGHOST}}:${{Postgres.PGPORT}}` or its rendered value. This
  case also needs `--adopt-existing-roles`. The bootstrap marks every role
  it creates or adopts with a `COMMENT ON ROLE`. That marker lets its own
  re-runs tell its roles from foreign ones.
- A role whose password would be kept cannot log in with its stored URL.
  This is tested before anything is written. The refusal says
  `stored URL password for <role> does not log in; re-run with --apply --rotate-passwords`.

`--apply` then does the following:

1. As the Postgres template superuser, it pins the three roles with the
   attributes in section 1 and revokes their memberships. The pinned
   attributes add VALID UNTIL `infinity`, no connection limit, and no
   role-level settings. A grant of a RegEngine role is revoked with
   `CASCADE`; every grant that depends on it is itself a grant of that
   RegEngine role, so the cascade stays within what the dry run listed. This
   covers a membership re-granted by another member through its ADMIN OPTION.
   A RegEngine role's own membership of a foreign role is never cascaded.
   Each grant is re-checked just before it is revoked, so one an earlier
   cascade already removed is skipped silently.
   It then creates the database from `template0` if it
   is absent, runs `REVOKE ALL ... FROM PUBLIC`, and grants `CONNECT` to the
   three roles. It pins `search_path = public, fsma, extensions` and
   `timezone = UTC` for the migrator in that database only; these are the
   session defaults CI passes through `PGOPTIONS`.
   The superuser URL is used only inside the process that
   `railway run -s Postgres` starts. A launcher there turns the URL into libpq
   environment variables with `PGSSLMODE=require` and
   `PGCHANNELBINDING=require`. The URL and password never appear in a command
   line, in the output, or in a file.
   Every connection through the public proxy, superuser and role logins
   alike, requires TLS and SCRAM-SHA-256 with channel binding
   (SCRAM-SHA-256-PLUS over `tls-server-end-point`). Channel binding, not the
   certificate, is what protects the passwords. psql refuses to send a
   cleartext or MD5 password, or to finish SCRAM without binding it to the
   TLS channel it actually sees. An interceptor presenting its own
   certificate therefore gets no password and cannot relay the login. Railway's
   proxy certificate is self-signed, so the certificate itself is not
   CA-verified. The Railway server must allow SCRAM for these logins; if it
   does not, psql refuses to connect and the run stops.
   A timeout or Ctrl-C kills the whole
   child process group, including psql. Every session sets
   `client_connection_check_interval`, so the server also drops the session
   and rolls back its open transaction.
   Every psql the script starts gets a private, empty `HOME` and no inherited
   `PG*` settings. A personal `~/.postgresql/root.crt`, `PGSSLROOTCERT` or
   `PGSSLMODE` would otherwise turn `sslmode=require` into CA verification,
   and that fails against Railway's self-signed proxy certificate. The dry run
   notes when such a file or variable exists.
   `REVOKE ALL ... FROM PUBLIC` also removes the default `TEMP` privilege, so
   the runtime roles cannot create temporary tables. That makes staging
   stricter than CI, whose scratch databases keep PUBLIC's defaults. No
   runtime code path creates temporary objects: v119's temporary tables live
   inside a `SECURITY DEFINER` function owned by the migrator.
2. It logs in as `regengine_migrator` and creates `get_tenant_context()` with
   the same body the backend-ci live-db-suite seeds for a fresh chain.
3. It logs in as `regengine` and `regengine_sysadmin` to prove their passwords.
4. It writes the RegEngine variables in this order: `DATABASE_URL`,
   `ADMIN_DATABASE_URL` (both through `${{Postgres.PGHOST}}` and
   `${{Postgres.PGPORT}}`), then `AUTH_OTP_HMAC_SECRET`, `AUDIT_INTEGRITY_KEY`
   and `TOOL_ACCESS_SECRET` (only when missing), then `REGENGINE_ENV=staging`,
   `REGENGINE_REQUIRE_RLS_ENFORCEMENT=1` and
   `REGENGINE_MIGRATIONS_ROLE=regengine_migrator`, then
   `REDIS_URL=${{Redis.REDIS_URL}}` (only when missing). `MIGRATIONS_DATABASE_URL`
   goes last.

Railway CLI writes are not staged. They are live at once, and the next deploy,
including one triggered by a push, uses them. `--skip-deploys` only stops the
CLI itself from starting one. Because `MIGRATIONS_DATABASE_URL` is written
last, a deploy that starts mid-run stops at `run-migrations.sh` and gunicorn
never starts. On a first run it exits 64 because `MIGRATIONS_DATABASE_URL` is
still unset. On a `--rotate-passwords` re-run the variable still holds the
old password, so the migration login fails password authentication.
Every value goes to `railway variable set NAME --stdin`. To check what exists,
the script reads the raw variable values into memory. It prints names only,
never values.

Passwords change only for roles the run creates, or for all three roles with
`--rotate-passwords`. An existing role keeps its password only when its URL
variable is readable, names that role and `regengine_staging` on the staging
private endpoint, and logs in. That login is tested before anything is
written. If the variable is missing, sealed, points elsewhere, or its password
no longer logs in, the run refuses (exit 2) until `--rotate-passwords` is
given. After any rotation, redeploy. Once you seal the URLs, a re-run
therefore needs `--rotate-passwords`. If a run fails after changing
passwords, it says so; re-run with `--apply --rotate-passwords`.

Afterwards, seal the six secret variables in the dashboard and deploy once.
The first deploy logs `DB state: FRESH`, migrates to head, then logs
`runtime role cutover applied as role=regengine_migrator database=regengine_staging`
before gunicorn starts. `/readiness` should then return 200.
`tests/scripts/test_bootstrap_staging_database.py` covers the guards, the
write order, stdin-only values, password handling and process cleanup, all
without Docker.
