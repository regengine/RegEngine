# Admin Service

The Admin service exposes tenant and overlay management APIs. Database schema changes are managed by the repository-level Alembic chain under [`../../alembic/versions`](../../alembic/versions).

## Running migrations

Run Alembic from the repository root so admin tables and row-level security policies are present before the API begins handling traffic:

```bash
MIGRATIONS_DATABASE_URL="postgresql://schema-owner:password@postgres:5432/regengine" ./scripts/run-migrations.sh
```

Set `ADMIN_DATABASE_URL` to a Postgres connection string accessible from the container, for example:

```bash
export ADMIN_DATABASE_URL="postgresql://regengine_sysadmin:password@postgres:5432/regengine"
```

`ADMIN_DATABASE_URL` is required outside explicit local/test use. The service only permits SQLite fallback when `ADMIN_FALLBACK_SQLITE` is set and `REGENGINE_ENV` is `development`, `test`, or `local`; cloud deployment markers such as Railway or Vercel disable the fallback. In production it must connect as `regengine_sysadmin` with `NOSUPERUSER NOBYPASSRLS` to the same migrated database as `DATABASE_URL`; startup rejects any other posture.
