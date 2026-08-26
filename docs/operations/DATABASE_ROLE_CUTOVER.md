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
regengine_sysadmin`; v114 rejects that topology.

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
them must resolve to `regengine_migrator` before v114 can converge the ACLs.
On PostgreSQL 15+, `public` may resolve to the built-in
`pg_database_owner`; v114 accepts that alias only after independently proving
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
merely by re-running v114: ownership must be transferred first.

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
- application schema without trusted migration state: exit 78 and require an
  operator-reviewed recovery.

It never stamps an unknown schema to head. After Alembic, it re-applies the
same v114 cutover used by CI. The cutover uses closed table, column, sequence,
and function inventories; removes wildcard/default runtime grants; proves the
dedicated-owner role, database, schemas, relations, indexes, extensions, and
application functions; and leaves new objects inaccessible until a reviewed
migration classifies them.

Before choosing any of those states, the runner fails with exit 65 if the
shared database contains either unpublished draft revision
`6f4c2a9d8b17`/`b71d9e4c2a60`, a `trg_v111_*` trigger, or a
`seed_definer_*` policy. Those artifacts came from the pre-linearization
v110/v111 candidate and must not be layered under the reviewed chain:

```text
51701aedee57 (v109)
  -> 6f8c2d1a4b90 (v110)
  -> df664d92adba (v111)
  -> d8b2056471a7 (v112)
  -> 228275bfe7e1 (v113)
  -> 036afcef7299 (v114)
```

Restore a pre-draft backup or perform a provider-reviewed catalog repair,
verify the database is byte-for-byte at the reviewed v112 posture, and only
then stamp that verified revision. Do not delete draft stamps, triggers, or
policies merely to make the preflight green.

For an audited repair after ACL drift, use the same migration credential:

```bash
MIGRATIONS_DATABASE_URL='<injected regengine_migrator URL>' \
REGENGINE_MIGRATIONS_ROLE=regengine_migrator \
  .venv/bin/python scripts/apply_runtime_role_cutover.py
```

`REGENGINE_MIGRATIONS_ROLE` is a non-secret identity pin and must match the
username encoded in `MIGRATIONS_DATABASE_URL`; when omitted, v114 derives the
same exact identity from the URL. Do not use this repair command to conceal
ownership drift. It intentionally fails for a superuser/BYPASSRLS credential,
role membership, mismatched database/schema/object ownership, or an identity
pin mismatch until the provider administrator corrects the posture.

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
