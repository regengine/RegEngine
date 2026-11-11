# RegEngine Deployment Guide

This guide describes the **checked-in deployment configuration**, reviewed
against the repository on 2026-11-04. It does not establish what version or
configuration is currently running. Confirm deployment identity and settings
with the hosting provider before acting.

## Deployment model

The root `Dockerfile` builds a consolidated FastAPI backend, `server.main:app`;
the Next.js frontend is built separately. `railway.toml` selects that
Dockerfile, probes `/readiness`, and configures restart on failure. These files
are configuration in source, not evidence of a successful live deployment.

The container installs `requirements.lock`, copies application and migration
files, runs `scripts/run-migrations.sh`, then starts Gunicorn/Uvicorn. The
migration runner takes a PostgreSQL advisory lock, refuses to stamp an existing
unversioned application schema, runs Alembic and the runtime-role cutover, and
fails startup if these steps fail. The command removes
`MIGRATIONS_DATABASE_URL` before starting Gunicorn.

## Configuration and release checks

- Follow [DATABASE_ROLE_CUTOVER.md](DATABASE_ROLE_CUTOVER.md) for the separate
  tenant runtime, privileged runtime, and schema-owner database credentials.
  Deployed migration runs require `MIGRATIONS_DATABASE_URL`; the local fallback
  to `DATABASE_URL` is for scratch environments, not deployed databases.
- Strict deployed authentication requires Redis and a valid
  `MFA_ENCRYPTION_KEY`; PostgreSQL and Redis are readiness dependencies in that
  mode. Do not regenerate an existing MFA key without a recovery plan for
  ciphertext encrypted with the old key. Neo4j is optional for readiness and
  depends on the enabled graph paths.
- Production router exposure requires the exact allowlist in
  `server/router_policy.py`. Consult `.env.example` and the target environment
  for other required settings; names and secrets must be managed per
  environment, never committed or pasted into release records.
- For privileged frontend proxy routes, configure the same dedicated
  `REGENGINE_PROXY_IP_HMAC_KEY` on the frontend and backend for each
  environment. Keep it server-side and distinct across environments. Before
  promotion, verify client attribution and rejection of spoofed, altered, or
  stale attestations with synthetic requests; see `frontend/src/lib/proxy-ip-attestation.ts`
  and `services/shared/proxy_ip_attestation.py`.
- For Stripe tenant creation and system metrics, use separately scoped
  credentials; see [SERVICE_ACCOUNTS.md](SERVICE_ACCOUNTS.md) and
  `services/admin/app/system_routes.py`. Keep database and generic backend
  credentials out of the frontend environment.
- Verify the selected commit, backend and frontend CI, migration compatibility,
  backup and rollback plan, and the intended environment before release. A
  successful build or merge does not establish that the new image is serving.
- Inspect `.github/workflows/deploy.yml` for the configured CI gate and deploy
  triggers. Workflow enablement, hosting settings, and actual release state are
  external to the checkout. [RELEASE_BRANCH_DEPLOYS.md](../runbooks/RELEASE_BRANCH_DEPLOYS.md)
  records a proposed release model and the manual script; verify current
  authorization and ownership before using either.

## Verification

- Check `/health` for liveness and reported build identity, then `/readiness`
  for dependency readiness. Compare `build.commit_sha` to the intended SHA;
  an absent SHA does not identify the running version.
- Review startup and migration logs without exposing secrets. Exercise the
  authenticated tenant flow and the relevant ingest, persistence and export
  path with authorized synthetic data. Record results and deployment IDs.
- The frontend build command is `npm --prefix frontend run build`. A local image
  can be built with `docker build -t regengine-backend .`; a successful build
  alone is not a deployment or production readiness check.

See [OPERATIONS.md](OPERATIONS.md) for local operations,
[DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) for recovery guidance, and
[FSMA_RAILWAY_DEPLOYMENT.md](FSMA_RAILWAY_DEPLOYMENT.md) for historical
multi-service context.
