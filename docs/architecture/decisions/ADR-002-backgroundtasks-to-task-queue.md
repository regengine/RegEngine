# ADR-002: Migrate FastAPI BackgroundTasks to durable fsma.task_queue

**Status:** Proposed
**Date:** 2026-04-18
**Decision Makers:** Christopher Sellers (solo technical founder)
**Supersedes:** (none)
**Related:** [#1267](https://github.com/PetrefiedThunder/RegEngine/issues/1267), migration V050 (`fsma.task_queue`)

---

## Context

RegEngine's ingestion service uses `fastapi.BackgroundTasks.add_task()` at 8 call sites across 4 route modules for work that **looks durable to the client** but is actually fire-and-forget within the request's event loop.

### Current BackgroundTasks call sites

| Route | File:line | Task |
|---|---|---|
| `POST /v1/ingest/{name}` | [`services/ingestion/app/routes.py:320`](services/ingestion/app/routes.py:320) | `process_regulation_ingestion` — full document parse + NLP |
| `POST /v1/ingest/federal-register` | [`routes_sources.py:36`](services/ingestion/app/routes_sources.py:36) | `_run_adapter_ingest` |
| `POST /v1/ingest/ecfr` | [`routes_sources.py:63`](services/ingestion/app/routes_sources.py:63) | `_run_adapter_ingest` |
| `POST /v1/ingest/fda` | [`routes_sources.py:89`](services/ingestion/app/routes_sources.py:89) | `_run_adapter_ingest` |
| `POST /v1/ingest/cppa` | [`routes_scraping.py:51, 56`](services/ingestion/app/routes_scraping.py:51) | `run_state_scrape_job` / `run_generic_scrape_job` |
| `POST /v1/ingest/all-regulations` | [`routes_scraping.py:99+`](services/ingestion/app/routes_scraping.py:99) | bulk sync (called nightly by scheduler) |
| `POST /v1/discovery/approve` | [`routes_discovery.py:106, 151`](services/ingestion/app/routes_discovery.py:106) | `discovery.scrape` |

### Why this is a correctness problem, not just a performance one

`fastapi.BackgroundTasks` runs tasks in the same event loop as the HTTP response. When Railway sends `SIGTERM` to a replica during a deploy:

1. Gunicorn forwards `SIGTERM` to each Uvicorn worker.
2. Uvicorn stops accepting new requests but **waits for in-flight work** — the graceful-timeout is 30s (`Dockerfile:53`).
3. Background tasks count as in-flight. **Any task that exceeds the 30s grace window is killed.**
4. On kill, the work is **lost**: no retry, no DLQ, no audit trail, no metric.

The scheduler calls `/v1/ingest/all-regulations` nightly ([`ASYNC_PROCESSES.md:15`](ASYNC_PROCESSES.md:15)). That endpoint returns `202 Accepted` as soon as the task is scheduled — so the scheduler records "nightly sync succeeded" even if the monolith was restarting mid-sync. **Silent data gaps.**

Worse: [`routes.py:318`](services/ingestion/app/routes.py:318) writes `status='queued'` to Redis *before* firing the background task. Callers polling that status get `queued` forever when the task dies before executing. No automation will ever transition the row to `failed`.

### Why this hasn't exploded yet

Three compensating factors have kept the blast radius small:

1. **Most tasks are idempotent.** The scheduler's nightly sync would re-run the next night, pulling the missed data. For stateless scrapes (Federal Register, eCFR), the tasks happen to complete inside the 30s window most of the time.
2. **Deploys are rare.** Railway deploys typically happen during business hours with operator attention. A SIGTERM in the middle of a cppa scrape is noticeable and manually re-runnable.
3. **The `fsma.task_queue` table already exists.** V050 (`alembic/versions/20260329_task_queue_v050.py`) created the table + `pg_notify` trigger in March 2026. The scheduler even has a janitor job that purges dead rows (`services/scheduler/main.py:571-631`). The infrastructure is warm; we're just not using it from the ingestion hot path.

### The strategic context

RegEngine is targeting an investor milestone where we claim "durable, auditable FSMA 204 ingestion." BackgroundTasks puts an asterisk on that claim every deploy. Closing the gap also unblocks:

- Retry policies for transient FDA/eCFR scraper failures (currently silent)
- Visibility metrics for queue depth, task age, and dead-task rate
- Idempotency enforcement at the task boundary (#1232 lives at the ingest boundary but there's no corresponding guard on the task side)
- Pulling the Redis `status='queued'` hack out of the hot path

---

## Decision

**Replace all 8 `BackgroundTasks.add_task(...)` sites with `enqueue_task(...)` against the existing `fsma.task_queue` table**, and run a dedicated worker process per service to drain the queue. The worker is built on Postgres `pg_notify` + polling fallback (no Redis, no Kafka, no Celery).

### Scope of what's included

1. New module `services/shared/task_queue.py` providing:
   - `enqueue_task(task_type: str, payload: dict, *, tenant_id: str | None, idempotency_key: str | None = None, priority: int = 0) -> int` — writes to `fsma.task_queue` and returns the task id
   - `TASK_HANDLERS: dict[str, Callable]` — registry mapping `task_type` string to handler function
   - `TaskWorker` class — runs the polling + pg_notify loop, claims pending rows via `SELECT ... FOR UPDATE SKIP LOCKED`, dispatches to the registered handler, transitions status to `completed` / `failed` / `dead`
   - Retry handling — exponential backoff based on `attempts < max_attempts`
   - Stale-lock recovery — rows locked for > 5 minutes are released back to `pending`
2. Per-service worker entrypoint (e.g., `services/ingestion/worker.py`) that imports its service's handler registry and calls `TaskWorker.run()`.
3. Migration of the 8 call sites, one PR per file, each with:
   - Handler function registered in `TASK_HANDLERS`
   - Route rewritten to call `enqueue_task(...)` and return the task id
   - Integration test verifying the task row is created with the right payload
   - Backward-compatible response shape (callers keep getting `{"task_id": ..., "status": "queued"}` — the `status` field now reflects actual DB state, not a Redis-cached lie)
4. Deprecation of the `background_tasks: BackgroundTasks` parameter from each route handler once the migration for that route lands.

### What's explicitly NOT in scope

- **Not replacing Kafka topics** — `fsma.task_queue` handles request-driven async work. Kafka (`nlp.needs_review`, `graph.update`, etc.) stays as the event-stream layer between services. (The V050 docstring claims the table "replaces Kafka" but that's aspirational — the actual Kafka consumers are separate and out of scope.)
- **Not changing Redis for user-facing status polling** — the Redis `ingest:status:{job_id}` row stays, but its lifecycle now mirrors `fsma.task_queue.status` via a handler callback. Clients' poll URL doesn't change.
- **Not adding a worker orchestrator** — one worker process per service replica, co-located with the API replica via a separate process in the same container. A full Kubernetes `Deployment` per service-worker pair is deferred until we have > 3 replicas (currently 1).
- **Not migrating scheduler BackgroundTasks** — the scheduler is already APScheduler-based and doesn't use FastAPI BackgroundTasks.

---

## Rationale

### Why pg_notify + fsma.task_queue over alternatives

#### Alternative A: Status quo (do nothing)

- **Pros:** zero work.
- **Cons:** every deploy leaks work; nightly sync silently skips; "durable ingestion" claim is a lie. This is the vulnerability #1267 documents. **Rejected.**

#### Alternative B: Celery + Redis

- **Pros:** mature ecosystem, good retry/backoff defaults, Flower for visibility.
- **Cons:** adds Redis as a hard dependency for durability (already in use for rate-limit + idempotency cache, but failures there degrade, not corrupt). Introduces pickle-based task serialization — a CVE surface every few years. Celery worker ergonomics on Railway require a separate dyno per queue, doubling deploy complexity. Solo founder ops cost is high. **Rejected.**

#### Alternative C: Vercel Queues

- **Pros:** durable, at-least-once delivery, built on Fluid Compute, public-beta GA path clear.
- **Cons:** We don't deploy on Vercel (we're on Railway). Adopting Vercel Queues = adopting Vercel Functions = a multi-month replatform. Not the right time. **Rejected.**

#### Alternative D: Raw Kafka topic

- **Pros:** Kafka is already deployed, we already consume it. Could add a new `ingestion.jobs` topic.
- **Cons:** Kafka's no-ack + at-least-once semantics are wrong for request-driven work where the caller needs a task id back. Kafka lacks row-level status tracking — the `queued → processing → completed` lifecycle would need an external store. **We'd end up reinventing `fsma.task_queue` on top of Kafka. Rejected.**

#### Alternative E: pg_notify + `fsma.task_queue` (this decision)

- **Pros:**
  - Table already exists (V050, March 2026). Janitor already purges it.
  - Postgres is the durability boundary we already operate — one fewer system to monitor, back up, or fail over.
  - `SELECT ... FOR UPDATE SKIP LOCKED` on the pending index gives us lock-free concurrency across worker replicas without Redis-based leader election.
  - RLS policy on `fsma.task_queue.tenant_id` gives us cross-tenant isolation for free — same pattern we use for every other tenant-scoped table.
  - `pg_notify` from the insert trigger wakes workers within ~ms; polling fallback keeps things moving if NOTIFY is missed under load.
  - Solo-founder ops cost is near-zero: no new infra, no new runbook, no new backup target.
- **Cons:**
  - Postgres is not a queue. At > 1000 tasks/sec we'd feel the pressure on `idx_task_queue_pending`. Current peak is ~10/sec, so we have 2 orders of magnitude of headroom. When we hit it, we migrate to a proper queue (and this ADR gets superseded).
  - Long-polling workers hold connections open — must size the pool accordingly.
  - Handlers that currently use `async def` need a sync/async adapter in the worker loop. Solvable; see the handler-runtime section below.

#### Handler runtime: sync worker with async adapter

Existing handlers (`_run_adapter_ingest`, `discovery.scrape`, `run_state_scrape_job`) are `async def` because they call async HTTPX clients. The worker loop is synchronous (for simpler `SELECT FOR UPDATE SKIP LOCKED` + single-thread claim semantics). The adapter:

```python
def _dispatch(task_type: str, payload: dict) -> None:
    handler = TASK_HANDLERS[task_type]
    if asyncio.iscoroutinefunction(handler):
        asyncio.run(handler(**payload))
    else:
        handler(**payload)
```

`asyncio.run()` per-task is acceptable for our scale (tens of tasks/minute). When we hit volumes that make per-task event-loop construction costly, switch to a dedicated `asyncio.Runner` with a persistent loop per worker thread — out of scope for the initial migration.

---

## Consequences

### Positive

- **No more silent data loss on deploy.** Tasks in `processing` state are released after the stale-lock window; tasks in `pending` state are picked up immediately by the next worker. Audit trail lives in `fsma.task_queue` rows.
- **Retry semantics.** `max_attempts` default 3, exponential backoff based on `attempts`. A transient eCFR 502 no longer fails silently.
- **Visibility.** Queue depth is `SELECT count(*) FROM fsma.task_queue WHERE status='pending'`. Stale-task detection is `WHERE status='processing' AND locked_until < now()`. Both go into Prometheus trivially.
- **Tenant isolation preserved.** The V050 RLS policy on `tenant_id` means a misconfigured worker can't drain another tenant's queue.
- **Idempotency at the task boundary.** `enqueue_task(idempotency_key="ingest:job-abc")` can deduplicate on a unique index (follow-up migration — not blocking this ADR).
- **Unblocks killing the Redis `ingest:status:{job_id}` hack.** Once every ingest has a real `fsma.task_queue.id`, the Redis row can become a thin cache over the authoritative table.

### Negative

- **New process per service replica.** The ingestion container grows from 1 process (uvicorn) to 2 (uvicorn + task_worker). Railway cost doubles for that service (~$5/mo extra at current tier).
- **Async handlers pay an `asyncio.run()` per task.** ~5ms overhead per dispatch. Negligible for our scale; real for anyone running this pattern at > 100 tasks/sec. A follow-up would swap to a persistent async runner.
- **One more schema we own.** `fsma.task_queue` is now on the critical path. Outages in that table directly block ingestion. Mitigation: the table is tiny (janitor purges rows > 30 days old), connection load is bounded, and it lives in the same Postgres instance we already depend on.
- **Migration churn.** 4 route files, 8 endpoints, new handler registry to keep consistent. Tests will need updating.

### Neutral

- **Response shape changes subtly.** Callers currently get `{"task_id": <uuid>, "status": "queued"}` (Redis string). They'll get `{"task_id": <bigserial>, "status": "pending"}` (DB row). `bigserial` is a number not a UUID. External integrations (if any) must tolerate this.
- **Worker deploys are coupled to the service repo.** No separate worker repo — the worker runs the same service image with a different entrypoint. Keeps deploy units simple.

---

## Migration plan

Proposed as 5 PRs. Each is independently revertible; later PRs depend on earlier ones but tolerate partial rollout.

| # | PR | Scope | Risk |
|---|---|---|---|
| 1 | **PR-A** — Build `services/shared/task_queue.py` | `enqueue_task`, `TaskWorker`, `TASK_HANDLERS` registry, pg_notify listener, polling fallback, tests against a real Postgres container | Medium — new infra code, but no calling services yet |
| 2 | **PR-B** — Migrate `routes_sources.py` (3 endpoints) | Federal Register, eCFR, FDA scrape routes use `enqueue_task`. Existing BackgroundTasks param removed. Worker handler registered. | Low — stateless handlers, tested in isolation |
| 3 | **PR-C** — Migrate `routes_scraping.py` (3 endpoints) | cppa, all-regulations, state/generic. Includes the scheduler-triggered nightly sync (highest-value durability win). | Medium — scheduler integration needs smoke testing |
| 4 | **PR-D** — Migrate `routes_discovery.py` (2 endpoints) | `/discovery/approve` both branches. | Low — similar shape to sources |
| 5 | **PR-E** — Migrate `routes.py` `/ingest/{name}` (1 endpoint, the big one) | The Redis status-row hack goes with this. Handler wraps the existing `process_regulation_ingestion` function. | High — main ingest hot path; needs canary tenant first |

### Rollout sequencing

- Each PR ships behind a per-endpoint env flag `USE_TASK_QUEUE_<endpoint>=true` so we can canary-enable one route at a time.
- Flag is read at request time, not at startup, so flipping it doesn't require a redeploy.
- Initial production rollout: enable on all routes with flags off → deploy → flip flags one route per day on a single tenant → watch queue depth + error rate → enable tenant-wide.
- Rollback path: flip flag off. BackgroundTasks code stays in place as the fallback until PR-E lands; at that point the old code is deleted.

---

## Open questions (deferred)

1. **Idempotency key enforcement on `fsma.task_queue`** — do we add a unique index on `(task_type, idempotency_key)` where `idempotency_key IS NOT NULL`? Probably yes, but that's a schema change that belongs in PR-A or a separate migration, not in this ADR.
2. **Cross-service task submission** — when admin-service wants to enqueue an ingestion task, it currently calls the ingestion HTTP API. Should admin be allowed to write directly to `fsma.task_queue`? The RLS policy allows it if the tenant context matches, but the architectural convention so far has been no cross-service DB writes. Resolve as part of PR-C or later.
3. **Metric naming convention** — `regengine_task_queue_depth{task_type,status}` vs splitting into `_pending_total` / `_processing_total`. Pick one before PR-A lands so the worker emits the right shape.
4. **Dead-letter inspection UI** — admin-service route to view `status='dead'` rows with the failure reason. Useful but not blocking. Ships after PR-E when there's enough signal to warrant it.

---

## References

- [Issue #1267 — ingestion: FastAPI BackgroundTasks used for durable ingestion work — lost on deploy](https://github.com/PetrefiedThunder/RegEngine/issues/1267)
- [V050 migration — `fsma.task_queue` table + pg_notify trigger](alembic/versions/20260329_task_queue_v050.py)
- [`services/scheduler/main.py:571-631` — existing janitor that purges dead task_queue rows](services/scheduler/main.py:571)
- [PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE)
- [PostgreSQL `LISTEN / NOTIFY`](https://www.postgresql.org/docs/current/sql-notify.html)
- [ADR-template.md](docs/architecture/decisions/ADR-template.md)
