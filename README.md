# RegEngine

**System of record for FSMA 204 traceability and compliance decisions.**

RegEngine ingests food supply chain events (EPCIS XML, EDI, CSV, manual entry),
resolves entity identities, evaluates FSMA 204 compliance rules, and produces
audit-ready artifacts for FDA reporting.

## Production Spine

The production-critical path is:

```
ingestion → canonicalization → identity resolution → compliance evaluation → audit output → FDA export
```

Everything outside this path is secondary. Graph expansion, advanced NLP,
generalized regulation support, and speculative platform abstractions are NOT
on the production spine and must not shape core architecture decisions.

## Architecture

Today: 6 FastAPI microservices on Railway + Next.js frontend on Vercel.
Target: modular monolith on PostgreSQL, replacing Kafka/Neo4j/Redis. Consolidation
is planned but not yet started — see [ARCHITECTURE.md](ARCHITECTURE.md).

| Service | Port | Purpose |
|---------|------|---------|
| admin | 8001 | Tenant management, API keys, user auth, bulk upload |
| ingestion | 8002 | Webhook ingestion, CTE/KDE validation, EPCIS normalization |
| compliance | 8500 | Compliance scoring, rule evaluation, export generation |
| graph | 8003 | Knowledge graph, identity resolution, supply chain queries |
| nlp | 8004 | Document ingestion, regulatory text extraction |
| scheduler | 8005 | Cron jobs, recall drills, export scheduling |

Shared code lives in `services/shared/` (56 modules, 433 import references),
including the compliance rules engine and kernel/control plane.

**Infrastructure (current):** PostgreSQL (Supabase), Redis, Neo4j, Redpanda
(Kafka-compatible), Railway (backend), Vercel (frontend).

**Infrastructure (target):** PostgreSQL only — Redis replaced by Postgres-backed
queues/cache, Neo4j replaced by recursive CTEs, Kafka replaced by outbox pattern.

## Quickstart

Prerequisites: Python 3.13, Node 24, Docker, `uv`, `pnpm`.

```bash
# Install deps
uv sync
pnpm install

# Start local infra (Postgres, Redis, Neo4j, Redpanda)
docker compose up -d

# Run migrations
uv run python -m services.shared.db.migrate

# Start a service (e.g. ingestion)
uv run uvicorn services.ingestion.main:app --port 8002 --reload

# Start the frontend
cd apps/web && pnpm dev
```

Use the `regengine-service-runner` skill to start/stop services and tail logs.

## Development

- **Migrations:** `services/shared/db/migrations/` — see `regengine-migrations` skill.
- **Testing:** `uv run pytest services/<name>/tests/` per service. Full-suite
  runs currently cascade due to fixture bleed; per-file runs are reliable.
- **Refactor/debug workflows:** `regengine-refactor`, `regengine-troubleshoot` skills.
- **API quality checks:** `regengine-api-quality` skill.
- **Deploy:** `regengine-deploy` skill wraps Railway + Vercel flows.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — dependency management, tech debt tracking.
- [CURRENT_SYSTEM_MAP.md](CURRENT_SYSTEM_MAP.md) — internal survival map.

## Contributing

Solo-founder repo. PRs from the worktree workflow; security and compliance fixes
take precedence over cosmetic changes. Phone-test critical flows before merging
to `main`.
