# Migration Recovery Runbook

**Severity:** Assess impact and escalate through the incident process.
**Owner:** On-call engineer, with database and security owners as appropriate.

This runbook describes how to assess a migration failure in the checked-in
application. It is not evidence of the version, database, backup availability,
or configuration of a deployed environment. Confirm those facts before acting.
The application uses Alembic revisions; the deploy runner uses a PostgreSQL
advisory lock and refuses to stamp an existing unversioned application schema.
See [deployment guidance](../operations/PRODUCTION_DEPLOYMENT.md),
[database role cutover](../operations/DATABASE_ROLE_CUTOVER.md), and
[scripts/run-migrations.sh](../../scripts/run-migrations.sh).

## 1. Contain and collect evidence

1. Involve the incident and database owners. Identify the affected environment,
   deployed image and intended commit, database, failed revision, error, and
   affected tenant or customer flows. Preserve sanitized logs and timestamps.
2. Stop further rollout or write activity when appropriate under the incident
   plan. Do not assume the failed operation was atomic: inspect the actual
   revision for transaction boundaries, external effects, and data changes.
3. Establish a recoverable backup or restore point and verify its suitability
   before changing state. Check the current platform and backup inventory; the
   dated observations in [disaster recovery](../operations/DISASTER_RECOVERY.md)
   do not themselves prove a backup exists or is restorable.

## 2. Inspect migration state

With authorized access to the intended database, and the appropriate
schema-owner migration credential configured **without printing its value**,
inspect the database revision and the checked-out migration graph:

```bash
alembic current
alembic heads
alembic history --verbose
```

In deployed environments Alembic reads `MIGRATIONS_DATABASE_URL`; local or CI
scratch databases may fall back to `DATABASE_URL`. See
[alembic/env.py](../../alembic/env.py). Compare the database revision with the
head of the **intended release** and the failed revision, not just the latest
checkout. A missing or untrusted `alembic_version` requires investigation;
the migration runner refuses to stamp an unknown schema. Do not stamp it to
make deployment succeed. `alembic check` checks ORM autogenerate drift and is
not a substitute for inspecting migration state or raw-SQL-managed tables.

Assess actual schema and data against the relevant revision and sanitized
incident evidence. Verify any transaction or partial-state assumptions against
the specific migration and database. Do not infer that a successful liveness
probe proves tenant isolation, data integrity, or export functionality.

## 3. Choose and rehearse recovery

Prepare a recovery plan reviewed by the responsible database and security
owners. Select between a corrective forward migration and restoring a verified
backup based on the actual state, data-loss tolerance, and revision behavior.
Rehearse it against an isolated copy when feasible. Review data, RLS policies,
privileges, audit evidence, and application compatibility; record the chosen
recovery point and any expected loss or interruption. Follow the applicable
[disaster recovery procedure](../operations/DISASTER_RECOVERY.md) after verifying
its environment-specific steps. A restored older database may be migrated again
by the application on startup; review the intended image and migration behavior
before reconnecting it.

Do not run a downgrade, manual DDL, direct SQL migration, or `alembic stamp`
without a revision-specific, reviewed plan and a verified recovery path. Some
Alembic downgrades discard data or security controls. The v085 and v108
revisions explicitly guard destructive downgrades in deployed environments;
that is not a guarantee that every other downgrade is guarded. Inspect the
actual `downgrade()` implementations and tests for the revision range.

## 4. Verify and resume

After the reviewed recovery, compare the actual revision with the intended
release and verify the affected schema, data, tenant isolation, audit and hash
chain integrity, and relevant ingest and export workflows with authorized
synthetic data. Check `/health` and `/readiness` separately, then confirm the
results with incident owners before resuming traffic. A passing health check is
not a substitute for these checks. Record the outcome and any unresolved data
or customer impact in the incident record.

## Historical appendix: retired standalone SQL

An older version of this runbook described a dual-migration setup, direct
execution of standalone `V052`/`V053` files, manual SQL rollback and stamping.
Those are historical procedures, **not current instructions**. The old text is
available in [Git history at revision e438a0d2](https://github.com/regengine/RegEngine/blob/e438a0d21d03da0a95a995cce560087ce057233e/docs/runbooks/MIGRATION_ROLLBACK.md).
Do not execute it without a separately reviewed recovery plan.

The historic names are easily confused with different Alembic revision labels:

- The checked-in Alembic [v057 revision](../../alembic/versions/20260415_v057_schema_additions.py)
  includes the historical growing-event change for `fsma.traceability_events`.
- The checked-in Alembic [v072 revision](../../alembic/versions/20260428_71e79e111c5d_v072_cte_events_tenant_idempotency.py)
  adds the tenant-scoped idempotency index when `fsma.cte_events` exists;
  the revision skips that operation when the table is absent.
- The Alembic [v052](../../alembic/versions/20260411_ensure_tenant_tables_v052.py)
  and [v053](../../alembic/versions/20260412_add_last_login_at_v053.py) revisions
  instead concern tenant tables and the user last-login column respectively.

These source files establish what the revisions implement, not that a particular
database has applied them. Determine the actual revision and schema before
planning recovery.
