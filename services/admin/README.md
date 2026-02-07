# Admin Service

The Admin service exposes tenant and overlay management APIs. The container now runs SQL migrations automatically at startup so that required tables and row-level security policies are present before the API begins handling traffic.

## Running migrations

Migrations are plain SQL files stored in [`services/admin/migrations`](./migrations). When the container starts, the entrypoint script executes each `*.sql` file against the database pointed to by `ADMIN_DATABASE_URL`. The process is idempotent: migrations rely on `IF NOT EXISTS` guards and can be re-run safely during restarts.

Set `ADMIN_DATABASE_URL` to a Postgres connection string accessible from the container, for example:

```bash
export ADMIN_DATABASE_URL="postgresql://admin:password@postgres:5432/regengine"
```

If `ADMIN_DATABASE_URL` is not provided, migrations are skipped and a warning is logged. In production, ensure the variable is configured so tenant isolation policies are applied before serving requests.
