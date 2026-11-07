# Codebase Map

The project-level orientation document. Five runbooks, `FOUNDER_KNOWLEDGE.md`,
`CANONICAL_OWNERSHIP.md` and `docs/CLAUDE_MD_SUGGESTED.md` all point here for
"the verified map"; this file is that destination (#2926, #2874).

This is an orientation map, not a live deployment attestation. Important
claims should be checked against the current source and target environment.
`scripts/check_docs_links.py` runs in CI and fails when a doc in
the live set references a repo path that does not exist, which is the specific
rot that made this file necessary.

---

## 1. Configured topology

The checked-in configuration describes a consolidated backend and a separate
frontend. It does not verify the current live deployment.

| Artifact | What | Where |
|---|---|---|
| Backend | A **single consolidated FastAPI monolith**, `server/main.py`, one Docker image | Railway (`railway.toml`, `Dockerfile`) |
| Frontend | Next.js App Router app in `frontend/` | Vercel |

Supporting infrastructure: PostgreSQL (Supabase, RLS-enforced), Redis, and
Neo4j (optional graph mirror — see §6).

The `services/*` directories organize router domains and code paths used by the
consolidated app; their presence does not establish separate deployments. Any
document, manifest or runbook that
describes a six-service topology is describing the retired architecture; all
five files in `runbooks/` carry an explicit `LEGACY:` banner saying so, and
`infra/k8s/` describes that same retired topology.

Railway's healthcheck path is `/readiness` (`railway.toml`). Its container
filesystem is ephemeral and `railway.toml` declares **no volume** — anything
written to local disk is lost on every deploy.

## 2. Repository layout

| Path | Role |
|---|---|
| `server/` | The monolith entrypoint. `main.py` composes routers according to runtime policy; `workers/` holds the in-process background runners. |
| `services/` | Domain code mounted by the monolith (see §3). |
| `alembic/versions/` | **Sole owner of the database schema.** The app performs no runtime DDL. |
| `frontend/` | Next.js app with its own CI workflow and deployment configuration. |
| `regengine/` | The source-installable Python SDK/CLI (`regengine-verify` etc.), packaged separately from the platform. |
| `tests/` | Cross-cutting suites: data integrity, SDK, scripts, shared. |
| `scripts/` | Operational and CI helper scripts. |
| `.github/workflows/` | CI and deployment workflow definitions (see §7). |
| `docs/` | Reference documentation. **`docs/archive/` is historical** — those files describe the tree as it was on their date and are deliberately not kept current. |
| `runbooks/` | Operational runbooks; all five currently carry a `LEGACY:` banner. |
| `infra/k8s/` | Manifests for the retired k8s topology. |

## 3. `services/` — domain code inside the monolith

Counts are `.py` files, excluding tests, at the time of writing — they indicate
relative weight, not a contract.

| Directory | Role | src / tests |
|---|---|---|
| `services/ingestion/` | The largest domain: event ingest, EDI/EPCIS parsing, billing, compliance scoring, recall reporting. | 198 / 197 |
| `services/shared/` | Cross-domain libraries: auth, RLS/tenant context, canonical event model, CTE persistence, circuit breakers, Kafka compat. | 149 / 54 |
| `services/admin/` | Tenant/team administration, erasure, supplier graph sync, webhook outbox. | 75 / 96 |
| `services/graph/` | Neo4j-backed lineage, trace and FSMA query surface. | 51 / 30 |
| `services/nlp/` | Regulation extraction, obligation conversion, entity resolution. | 34 / 29 |
| `services/scheduler/` | Runs **in-process** in the monolith via `server/workers/embedded_scheduler.py`, with Postgres advisory-lock leader election. | 22 / 27 |
| `services/compliance/` | Compliance evidence surface. | 9 / 13 |

## 4. Router gating

[`server/router_policy.py`](../server/router_policy.py) requires an exact
`ENABLED_ROUTERS` allowlist in production. Missing or extra names abort startup;
`DISABLED_ROUTERS` and the experimental bypass are rejected in production.
Development and test have separate controls. A route in source is not proof it
is available in a target environment; graph and NLP are excluded from the
checked-in production set. See the [router surface audit](engineering/ROUTER_SURFACE.md).

## 5. Database

Schema is owned entirely by Alembic (`alembic/versions/`). The app performs no
runtime DDL as of v098/v099. Inspect the revision graph and migration status
for the target database; repository files alone do not establish that migrations
have been applied.

Tenant isolation depends on both authenticated application tenant context and
PostgreSQL RLS policies. The tenant GUC is caller-settable by a holder of runtime
credentials, so RLS is not a defense against arbitrary SQL with those credentials.
See [ADR-004](architecture/decisions/ADR-004-security-release-boundary.md).

## 6. Background work and health

[`ASYNC_PROCESSES.md`](../ASYNC_PROCESSES.md) describes background work.
[`server/main.py`](../server/main.py) defines `/health` as liveness and
`/readiness` as a bounded dependency check. Readiness returns 503 for a failed
PostgreSQL check, unavailable Redis in strict runtimes, a failed essential
ingestion worker or enabled embedded scheduler, and probe timeout or capacity
exhaustion. Neo4j and rate-limiter checks do not independently fail readiness.
With graph disabled, Neo4j can be reported as not probed; that does not prove
its availability. Consult the component details in the response and the target
system's own monitoring.

## 7. Tests and CI

Backend tests run under pytest from the repo root. `pyproject.toml` sets
`--import-mode=importlib` and `asyncio_mode = "auto"`.

`pyproject.toml` includes `services/shared/tests` and `infra/gateway/tests`
in the default `testpaths`; collection alone does not establish that tests pass.
Some suites require live infrastructure or credentials. Workflow definitions
in `.github/workflows/` describe configured checks, not their current results.

## 8. Keeping this file honest

`scripts/check_docs_links.py` fails CI when a document in the live set — root
`*.md`, `runbooks/`, and this file — references a repo path that does not
exist. It runs as the `docs-link-check` hard gate in `backend-ci.yml`. Paths
named deliberately *because* they were removed are declared in
`.docs-link-allowlist` with a reason, so the exemption is auditable.

The check does not currently cover `docs/**`; that tree carries a substantial
backlog of stale references, concentrated in `docs/archive/` where staleness is
correct by design. Widening the scope means triaging that backlog first.
