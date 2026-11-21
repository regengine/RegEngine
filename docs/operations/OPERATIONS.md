# RegEngine Operations Runbook

This runbook describes the checked-in local dependency stack and operational
entry points. It does not establish the status of staging or production.

## Local dependencies

`docker-compose.dev.yml` defines PostgreSQL 17 and Redis 7 only. It requires
`POSTGRES_PASSWORD` and initializes separate database logins through
`scripts/init-postgres.sh`. Start and inspect the dependencies from the
repository root:

```bash
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml logs --tail 100 postgres redis
```

Use the setup instructions in [README.md](../../README.md) and `.env.example`
for application configuration and run the consolidated backend separately.
Stopping the stack with `docker compose -f docker-compose.dev.yml down` keeps
its named data volume. Do not remove volumes while troubleshooting unless the
owner has approved data loss and the recovery plan is understood.

The older `scripts/start-stack.sh`, `scripts/stop-stack.sh`, and
`scripts/verify-health.sh` target a multi-service setup and are not health or
startup checks for this minimal stack.

## Deployed backend

The root Dockerfile starts `server.main:app` after the migration runner. Check
`/health` for liveness and reported build SHA and `/readiness` for dependency
readiness; compare the SHA with the intended release. Strict deployed readiness
requires PostgreSQL and Redis. A successful probe alone does not prove that
individual tenant workflows, exports, or backups work. See
[PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) for release checks.

If startup or readiness fails, inspect sanitized deployment logs and the
reported dependency status. Confirm database role configuration and migration
state before taking corrective action; use
[DATABASE_ROLE_CUTOVER.md](DATABASE_ROLE_CUTOVER.md) and
[MIGRATION_ROLLBACK.md](../runbooks/MIGRATION_ROLLBACK.md). Do not stamp an
unknown database schema or delete data to make a deploy pass.

## Other procedures

- [Incident response](INCIDENT_RESPONSE.md) and [disaster recovery](DISASTER_RECOVERY.md).
- [Credential rotation](CREDENTIAL_ROTATION_RUNBOOK.md) and
  [launch trust provisioning](LAUNCH_TRUST_PROVISIONING.md).
- Inbound email is not included in the production router allowlist; see
  [EMAIL_INGESTION.md](../engineering/EMAIL_INGESTION.md) before planning its use.
