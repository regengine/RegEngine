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

6 FastAPI microservices on Railway + Next.js frontend on Vercel.
Target architecture is a modular monolith (consolidation not yet started).

| Service | Port | Purpose |
|---------|------|---------|
| admin | 8001 | Tenant management, API keys, user auth, bulk upload |
| ingestion | 8002 | Webhook ingestion, CTE/KDE validation, EPCIS normalization |
| compliance | 8500 | Compliance scoring, rule evaluation, export generation |
| graph | 8003 | Knowledge graph, identity resolution, supply chain queries |
| nlp | 8004 | Document ingestion, regulatory text extraction |
| scheduler | 8005 | Cron jobs, recall drills, export scheduling |

Shared code lives in `services/shared/` (56 modules, 433 import references).

**Infrastructure:** PostgreSQL (Supabase), Redis, Neo4j, Redpanda (Kafka-compatible), Railway (backend), Vercel (frontend).

See [ARCHITECTURE.md](ARCHITECTURE.md) for dependency management and technical debt tracking.
See [CURRENT_SYSTEM_MAP.md](CURRENT_SYSTEM_MAP.md) for the internal survival map.
