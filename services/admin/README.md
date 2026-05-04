# Admin Service

The Admin service exposes tenant and overlay management APIs. The container now runs SQL migrations automatically at startup so that required tables and row-level security policies are present before the API begins handling traffic.

## Running migrations

Migrations are plain SQL files stored in [`services/admin/migrations`](./migrations). When the container starts, the entrypoint script executes each `*.sql` file against the database pointed to by `ADMIN_DATABASE_URL`. The process is idempotent: migrations rely on `IF NOT EXISTS` guards and can be re-run safely during restarts.

Set `ADMIN_DATABASE_URL` to a Postgres connection string accessible from the container, for example:

```bash
export ADMIN_DATABASE_URL="postgresql://admin:password@postgres:5432/regengine"
```

`ADMIN_DATABASE_URL` is required outside explicit local/test use. The service only permits SQLite fallback when `ADMIN_FALLBACK_SQLITE` is set and `REGENGINE_ENV` is `development`, `test`, or `local`; cloud deployment markers such as Railway or Vercel disable the fallback. In production, configure `ADMIN_DATABASE_URL` so tenant isolation policies are applied before serving requests.
