# RegEngine

**System of record for FSMA 204 food-supply-chain traceability, compliance evaluation, and FDA reporting.**

RegEngine ingests food supply chain events (EPCIS XML, EDI, CSV, webhook feeds, manual entry), resolves entity identities, evaluates FSMA 204 compliance rules, and emits audit-ready artifacts for FDA 204 exports.

## Status

Pre-production, solo-maintained. Ingestion and compliance surfaces run on Railway + Vercel with closed-alpha tenants. See [CHANGELOG.md](CHANGELOG.md) for ship history and [DEPLOY_AUDIT_2026-04-20.md](DEPLOY_AUDIT_2026-04-20.md) for the most recent deploy-path review.

## Production spine

```text
ingestion → canonicalization → identity resolution → compliance evaluation → audit output → FDA export
```

Everything outside this path is secondary. Graph expansion, advanced NLP, generalized regulation support, and speculative platform abstractions are **not** on the production spine and must not shape core architecture decisions. See [ARCHITECTURE.md](ARCHITECTURE.md) for the rationale.

## Architecture

**Today:** 6 FastAPI microservices on Railway + Next.js (App Router) frontend on Vercel.

**Target:** modular monolith on PostgreSQL, replacing Kafka/Neo4j/Redis. Planned, not yet started — see [ARCHITECTURE.md](ARCHITECTURE.md).

### Services

| Service | Responsibility |
| --- | --- |
| `admin` | Tenant management, API keys, user auth, MFA, bulk upload, audit logging |
| `ingestion` | Webhook ingestion, CTE/KDE validation, EPCIS/EDI/CSV normalization |
| `compliance` | Compliance scoring, rule evaluation, export generation |
| `graph` | Knowledge graph, identity resolution, supply-chain queries |
| `nlp` | Document ingestion, regulatory text extraction, FSMA clause mapping |
| `scheduler` | Cron jobs (recall drills, export scheduling, FDA warning-letter scrapes) |

Shared code lives in [services/shared/](services/shared/) (56 top-level modules; 130 files including subpackages). The top-level [kernel/](kernel/) package hosts the control plane, obligation engine, and FSMA applicability engine — wired into `services/ingestion` and `services/graph` routers.

### Infrastructure

**Current:** PostgreSQL (Supabase), Redis, Neo4j, Redpanda (Kafka-compatible), Railway (backend), Vercel (frontend).

**Target:** PostgreSQL only — Redis replaced by Postgres-backed queues/cache, Neo4j replaced by recursive CTEs, Kafka replaced by outbox pattern.

## Quickstart

Prerequisites: Python **3.11 or 3.12** (3.13 not yet supported — see [pyproject.toml](pyproject.toml)), Node 24+, Docker, and `npm`.

```bash
# 1. Python deps
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.lock

# 2. Frontend deps
cd frontend && npm install && cd ..

# 3. Local infra (Postgres only)
#    requires POSTGRES_PASSWORD in the environment
docker compose -f docker-compose.dev.yml up -d

# 4. Apply migrations
source venv/bin/activate
alembic upgrade head

# 5. Start a backend service (example: ingestion)
uvicorn services.ingestion.main:app --reload --port 8002

# 6. Start the frontend
cd frontend && npm run dev
```

The `regengine-service-runner` skill wraps start/stop/tail workflows for all services.

## Migrations

Alembic is the source of truth for schema. Migrations live in [alembic/versions/](alembic/versions/) at the repo root (not per-service). Railway runs `alembic upgrade head` on backend deploy.

The Alembic baseline consolidates historical Flyway-style SQL under [alembic/sql/](alembic/sql/); the original Flyway files under `services/admin/migrations/` are kept for reference only. New schema changes go through Alembic. Use the `regengine-migrations` skill for the full workflow.

## Testing

```bash
source venv/bin/activate

# Per-file runs are reliable
pytest services/ingestion/tests/test_<name>.py

# Full-suite runs currently cascade due to fixture bleed in services/ingestion/tests.
# CI's ingestion gate is collect-only, which hides this from PRs — do not trust
# a full-suite green locally as proof. Per-file is the ground truth.
```

## Deployment

- **Backend:** services deployed to Railway under the `RegEngine-Prod` project. Live-ingest rollout is in flight — see recent commits.
- **Frontend:** Vercel (Next.js App Router). See [frontend/](frontend/).
- **CI/CD:** GitHub Actions workflows in [.github/workflows/](.github/workflows/) — `backend-ci.yml`, `deploy.yml`, `security.yml`. The deploy gate reads check status before promoting.
- Orchestration via the `regengine-deploy` skill.

## Documentation

Root-level docs (consolidating is on the to-do; some overlap):

- [ARCHITECTURE.md](ARCHITECTURE.md) — dependency topology, tech-debt register, monolith target
- [CURRENT_SYSTEM_MAP.md](CURRENT_SYSTEM_MAP.md) — internal survival map of what talks to what
- [ASYNC_PROCESSES.md](ASYNC_PROCESSES.md) — queue, scheduler, and background-worker layout
- [CANONICAL_OWNERSHIP.md](CANONICAL_OWNERSHIP.md) — module ownership during consolidation
- [SECURITY.md](SECURITY.md) — security posture + vulnerability reporting
- [CHANGELOG.md](CHANGELOG.md) — release history
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution guide
- [DEPLOY_AUDIT_2026-04-20.md](DEPLOY_AUDIT_2026-04-20.md) — most recent deploy-path review
- [PRODUCT_FEATURE_LIST.md](PRODUCT_FEATURE_LIST.md) — feature inventory
- [FOUNDER_KNOWLEDGE.md](FOUNDER_KNOWLEDGE.md) — founder-context notes for AI collaborators
- [regengine-architecture-review-2026-04-12.md](regengine-architecture-review-2026-04-12.md) — architecture review snapshot
- [regengine-site-audit-2026-04-12.md](regengine-site-audit-2026-04-12.md) — site audit snapshot

## Known risks & tech debt

Honest summary of known, verified debt. Pointer to audits, not the audits themselves.

### Structural

- **6-service → monolith consolidation** is planned but not started. Cross-service calls happen via HTTP; there is no inter-service transactionality. Breaking changes in `services/shared/` cascade.
- **Dual migration systems** — Alembic at the repo root plus legacy Flyway SQL under `services/admin/migrations/` and `alembic/sql/`. Schema drift between the ORM (`sqlalchemy_models.py`) and the live database has bitten production; see PR #1892 (`audit_logs` uuid column drift → `operator does not exist: text = uuid`).
- **Fixture bleed in the ingestion test suite** — per-file tests pass, full-suite runs cascade. CI's ingestion gate is collect-only so this is invisible at PR time.

### Regulatory correctness

- **FSMA 204 CTE enforcement** — the rules engine runs ingestion non-blocking; rule failures surface in audit logs and dashboards rather than rejecting the event. Acceptable for closed-alpha, will need reconsideration before broader rollout.
- **Audit-chain integrity** — SHA-256 hash chain via `AuditLogger` in [services/admin/app/audit.py](services/admin/app/audit.py). v2 hash folds actor/severity/endpoint fields so SQL-rewrite of those fields breaks the chain (see #1415). Schema type-mismatch in `audit_logs` columns was fixed in alembic v065 (PR #1892).

### Security posture

- Tenant isolation is enforced by a mix of application-layer checks plus Postgres RLS. Policies live in Alembic v051/v056; `get_tenant_context()` returns `uuid` so columns holding `tenant_id` must be typed consistently — see [SECURITY.md](SECURITY.md) for the current posture.
- Frontend enforces **Supabase + custom JWT cross-auth**. A valid RegEngine JWT without a Supabase cookie bounces to `/login?error=session_expired` (see [frontend/src/app/login/LoginClient.tsx](frontend/src/app/login/LoginClient.tsx) and the #538/#1072 references there). Diagnostic workflow lives in the `regengine-troubleshoot` skill.
- Rate limiting (per-IP, per-email, per-tenant-scope), account lockout, and API-key scopes are in place across [services/admin/app/auth_routes.py](services/admin/app/auth_routes.py) and [services/ingestion/app/authz.py](services/ingestion/app/authz.py).

### Operational

- **Worktrees in active use** under [.claude/worktrees/](.claude/worktrees/) for parallel agent work. Run `git worktree list` before `git checkout <branch>` or scripts will fail silently on collision.
- **Issue-tracker drift** — auto-close can miss when PRs merge from non-default branches. Verify fix-target state against current `main` before acting on an issue number from an audit report.

## Contributing

Solo-maintained. PRs from the worktree workflow; security and compliance fixes take precedence over cosmetic changes. Phone-test critical flows before merging to `main`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for branching, commit style, and review norms.
