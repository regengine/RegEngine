# Async & Background Processes

All background work in RegEngine. If it runs without a user clicking a button, it's listed here.

Production topology: a single consolidated FastAPI monolith (`server/main.py`, one Docker
image on Railway) plus a Next.js frontend on Vercel. There are no separately deployed
worker services. Everything below runs inside (or is enqueued for) the monolith process.

## PostgreSQL Task Queue (the async backbone)

Background work is driven by polling the `fsma.task_queue` table — not Kafka. Two workers
start in the FastAPI lifespan (`server/main.py`) and stop on graceful shutdown:

### 1. `server/workers/task_processor.py`

Daemon thread that polls `fsma.task_queue` every 500 ms (`TASK_POLL_INTERVAL`) using
`SELECT ... FOR UPDATE SKIP LOCKED`. Polling-only by design (#1185) — the LISTEN/NOTIFY
trigger was removed in migration v059.

| Task type | Handler | Visibility timeout | Replaces (Kafka era) |
|-----------|---------|--------------------|----------------------|
| `nlp_extraction` | `_handle_nlp_extraction` → `services.nlp.app.extractor.extract_entities` | 300s | topic `documents.ingested` |
| `review_item` | `_handle_review_item` → admin HallucinationTracker | 30s | topic `nlp.needs_review` |

`graph_update` was declared as a task type with a 120 s timeout but nothing enqueued it and
no handler existed; it was removed on 2026-10-30 (tech-debt WI-15). High-confidence
extractions are logged as `fsma_high_confidence_no_graph_sink` until a graph sink exists.

Mechanics:

- **Atomic claim** — `UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED)`,
  filtered to registered handler types and `scheduled_at <= NOW()`; steals rows whose
  `locked_until` expired.
- **Heartbeat** — a per-task daemon thread extends `locked_until` every 60s while the
  handler runs; extension is refused if another worker stole the lock.
- **Retries** — exponential backoff `60 * 2^(n-1)` capped at 3600s (#1181); after
  `max_attempts` the row goes to status `dead` with `last_error`.
- **Graceful drain** — on shutdown (30s budget, matches gunicorn graceful-timeout) an
  in-flight row is flipped back to `pending` and its attempt is refunded.
- **`NON_WORKER_TASK_TYPES`** — `{recall_drill, recall}` rows are state/history for the
  recall engine and are never claimed (#1199).
- Disable with `DISABLE_TASK_WORKER` (e.g. for tests).

### 2. `shared.task_queue.TaskWorker`

A second, parallel worker started in the same lifespan for ingestion and agent-bridge
task handlers. It polls the same `fsma.task_queue` table with a disjoint set of task
types. Producer side: ingestion routes call `shared.task_queue.enqueue_task` (note:
`task_processor.enqueue_task` is a different function with no production callers).

## Event Backbone: Postgres only

The `fsma.task_queue` table is the only event backbone. The Kafka path (the
`EVENT_BACKBONE` switch, the NLP and admin consumer threads, the ingestion and
scheduler producers, the HMAC event signing in `kafka_auth`, the DLQ producers
and the correlation-header propagation helpers) was retired on 2026-11-04
(tech-debt WI-05). The modules moved with `git mv` to
`docs/archive/retired-topology/kafka/`, where a README lists each one with its
former importers; `confluent-kafka` and `fastavro` left `requirements.lock`.

- `services/nlp/app/consumer/` now holds only the extraction helpers
  (`conversion`, `review_routing`, `thresholds`, `schema_validation`,
  `tenancy`, `events`) that `server/workers/task_processor.py` imports.
- `GET /health` (ingestion) still returns a `kafka` key for dashboards; its
  value is the constant `"retired"`. `GET /health/consumer` (admin) returns a
  static 200 for the same reason.
- `scripts/check_legacy_dead_code.py` fails CI on any new `confluent_kafka` or
  `shared.kafka_*` import.

## Scheduler (embedded in the monolith)

`services/scheduler/` runs **in-process in the monolith**: the `server/main.py` lifespan
starts a daemon thread via `server/workers/embedded_scheduler.py`, and PostgreSQL
advisory-lock leader election (`services/scheduler/app/distributed.py`) ensures exactly
one gunicorn worker across all workers/replicas executes jobs — the rest standby-poll and
re-enter election on leadership loss. The standalone entrypoint
(`services/scheduler/main.py`, stdlib health server on port 8600) is local-debug only and
refuses to run in production via `assert_legacy_entrypoint_not_in_production('scheduler')`.

| Job | Interval | What It Does | Idempotent? | On Failure |
|-----|----------|-------------|-------------|------------|
| FDA Warning Letters | 60 min | Polls FDA openFDA API for new warning letters | Yes (dedup via StateManager) | Logs warning, circuit opens after 5 failures |
| FDA Import Alerts | 120 min | Polls FDA for import alert updates | Yes | Same as above |
| FDA Recalls | 30 min | Polls FDA for recall announcements; matches recalls to tenant product profiles (compliance alerts) | Yes | Same as above |
| FSMA Nightly Sync | Daily 02:00 UTC | Runs the `/v1/ingest/all-regulations` sweep in-process (`run_all_regulations_ingest`) | Yes (dedup) | Logs error; continues next day |
| Deadline Monitor | 5 min | Checks approaching compliance deadlines | Yes (read-only) | Logs error; continues |
| State Cleanup | 24 hr | Prunes stale state entries | Yes | Logs warning; continues |
| Inactive Account Sweep | 24 hr | Flags inactive tenant accounts | Yes | Logs error; continues |
| KDE Retention Enforcement | 24 hr | Enforces data retention policies on KDE records | Yes | Logs error; continues |
| Data Archival | 24 hr | Archives old records per retention policy | Yes | Logs error; continues |
| Task Queue Purge | 24 hr | Deletes completed/dead `fsma.task_queue` rows older than 30 days | Yes | Logs error; continues |

(The former "Regulatory Discovery" job was removed — it duplicated the FSMA Nightly Sync
against the same endpoint with credentials the API never accepted. Scrape results
are acked after webhook + compliance processing; there is no emission step since
the Kafka producer was retired in WI-05.)

**Enable gate:** `SCHEDULER_EMBEDDED` (default: on in production, off elsewhere).
**Config:** `services/scheduler/app/config.py` — intervals, thresholds, timeouts. If
`REGENGINE_ENV=production` is set, `SCHEDULER_API_KEY` must also be set or the scheduler
refuses to construct (the API keeps serving).
**Service logic:** `services/scheduler/service.py:SchedulerService`.

The scheduler's safety mechanisms: advisory-lock leadership with heartbeat loss detection,
per-scraper circuit breakers, APScheduler `coalesce=True` + 1h misfire grace. Note: the
circuit breaker in `services/scheduler/app/circuit_breaker.py` is **in-memory**, not
Redis-backed.

## Other runtime background paths

- **Neo4j supplier sync** — `services/admin/app/supplier_graph_sync.py` mirrors supplier
  onboarding into Neo4j at runtime behind a circuit breaker; webhook ingest can enqueue
  CTE events to a Redis `neo4j-sync` list when enabled. **Nothing drains that
  list.** The draining worker this doc previously named
  (`services/graph/scripts/fsma_sync_worker.py`) no longer exists in the tree,
  so enqueued entries accumulate unread rather than merely going undeployed.
- **Neo4j is NOT on the deploy-gating path.** `/readiness` probes Neo4j only when the
  graph subsystem is actually mounted (`_subsystem_active("graph")`). Graph routers are
  experimental and auto-disabled in production, so on the production path Neo4j is
  reported `not_probed` and never contacted, even though `NEO4J_URI` is set there for the
  admin supplier-graph mirror (`server/main.py:1116-1140`, WS-6). When the graph
  subsystem *is* active the probe runs with bounded 2.0s connect/acquisition timeouts and
  a failure records status `error`, which degrades the payload but still returns 200.
  **Postgres is the only component that can return 503** (`server/main.py:1020-1034`).
  - *Operational consequence:* a Neo4j outage is **invisible in `/readiness`**. Do not
    look there during a Neo4j incident, and do not roll back a healthy deploy on its
    account. Neo4j health is observed through the `shared.circuit_breaker.neo4j_circuit`
    metrics instead.

## Health Checks

| Endpoint | Where | What It Monitors |
|----------|-------|------------------|
| `GET /health` | monolith | Liveness; always 200 |
| `GET /readiness` | monolith | Postgres (required; **only** component that 503s), Redis, background runners — all optional components report per-component status and degrade to 200 `degraded`. Neo4j only when the graph subsystem is mounted (never in production). Railway healthcheckPath |

There is no port-8600 scheduler health endpoint in production (standalone mode only).

## What Is NOT Background Work

These look async but are synchronous request-response:

- **Canonical persistence dual-write** (`canonical_persistence/writer.py:persist_event`) —
  writes to both the canonical table and the legacy table within the same request.
- **Identity resolution** — triggered synchronously during ingestion, not scheduled.
- **FDA export generation** — on-demand via API request, not pre-generated.
- **CTE lot tracing** — recursive SQL in `services/shared/cte_persistence/queries.py`,
  executed per request. (The `server/workers/lot_tracing.py` module this doc used to
  flag as dead code has since been deleted; there is no lot-tracing worker.)
