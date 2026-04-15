# Async & Background Processes

All background work in RegEngine. If it runs without a user clicking a button, it's listed here.

## Scheduler Service (port 8600)

Uses APScheduler with BlockingScheduler. All jobs protected by distributed leadership election
(only one replica executes per interval) and circuit breakers (5 failures → 300s recovery).

| Job | Interval | What It Does | Idempotent? | On Failure |
|-----|----------|-------------|-------------|------------|
| FDA Warning Letters | 60 min | Polls FDA openFDA API for new warning letters | Yes (dedup via StateManager) | Logs warning, circuit opens after 5 failures |
| FDA Import Alerts | 120 min | Polls FDA for import alert updates | Yes | Same as above |
| FDA Recalls | 30 min | Polls FDA for recall announcements | Yes | Same as above |
| FSMA Nightly Sync | Daily 02:00 UTC | POST to `/v1/ingest/all-regulations` on ingestion service | Yes (dedup) | HTTP retry; logs error; continues next day |
| Regulatory Discovery | 1440 min (daily) | Bulk sync of regulatory sources | Yes | 300s timeout; logs error; continues |
| Deadline Monitor | 5 min | Checks approaching compliance deadlines | Yes (read-only) | Logs error; continues |
| State Cleanup | 24 hr | Prunes stale state entries | Yes | Logs warning; continues |
| Inactive Account Sweep | 24 hr | Flags inactive tenant accounts | Yes | Logs error; continues |
| KDE Retention Enforcement | 24 hr | Enforces data retention policies on KDE records | Yes | Logs error; continues |
| Data Archival | 24 hr | Archives old records per retention policy | Yes | Logs error; continues |

**Config:** `services/scheduler/app/config.py` — intervals, thresholds, timeouts.
**Entry point:** `services/scheduler/main.py:SchedulerService.start()`.

### Safety mechanisms

- **Circuit breaker:** Per-scraper. 5 failures → OPEN for 300s → half-open probe.
  State stored in Redis (`services/scheduler/app/circuit_breaker.py`).
- **Distributed leadership:** Only one scheduler replica runs jobs.
  `services/scheduler/app/distributed.py`.
- **Coalesce:** Multiple missed executions roll into one (APScheduler `coalesce=True`).
- **Misfire grace:** 1 hour window before a missed job is skipped entirely.

## Kafka Consumers

| Consumer | Topic | Service | What It Does | Error Handling |
|----------|-------|---------|-------------|----------------|
| NLP Entity Extractor | `ingest.normalized` | nlp | Extracts entities from normalized events, classifies, routes to `graph.update` or `nlp.needs_review` | Schema validation → DLQ (`nlp.extracted.dlq`); retry 3x with exponential backoff; poison pill detection |
| Review Consumer | `nlp.needs_review` | admin | Records low-confidence extractions via HallucinationTracker for human review | Retry 3x exponential backoff; failed → `nlp.needs_review.dlq` |
| FSMA Graph Consumer | `fsma.events.extracted` | graph | Ingests FSMA trace events into Neo4j graph | `services/graph/app/consumers/fsma_consumer.py` |

**DLQ pattern:** Failed messages routed to `<topic>.dlq`. DLQManager is a thread-safe singleton
with lazy producer initialization (`services/shared/kafka_consumer_base.py`).

**Retry tracking:** TTLCache-based counter per message_id prevents unbounded retry memory growth.

**Graceful shutdown:** Consumers commit pending offsets, DLQ producer flushes, then exit.

## Health Checks

| Endpoint | Port | What It Monitors |
|----------|------|-----------------|
| Scheduler HTTP | 8600 | APScheduler alive, seconds since last poll, circuit breaker states |
| Kafka Consumer health | per-service | Consumer liveness, stale threshold detection |

All services expose `/health` via FastAPI. Railway uses these for liveness probes.

## What Is NOT Background Work

These look async but are synchronous request-response:

- **Canonical persistence dual-write** (`canonical_persistence/writer.py:persist_event`) —
  writes to both canonical table and legacy table within the same request. Not async,
  but the Neo4j graph sync (`migration.publish_graph_sync`) is fire-and-forget via Kafka.
- **Identity resolution** — triggered synchronously during ingestion, not scheduled.
- **FDA export generation** — on-demand via API request, not pre-generated.
