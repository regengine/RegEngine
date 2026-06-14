# Scheduler Service

A production-grade job scheduler for automated regulatory change monitoring.

## Deployment Reality

The scheduler runs **embedded in the production monolith**. It contributes no routers;
its jobs (FDA scraping, recall alerting, deadline monitoring, retention/archival,
nightly FSMA sync) are started from the `server/main.py` lifespan via
`server/workers/embedded_scheduler.py`, with PostgreSQL advisory-lock leader election
(`app/distributed.py`) keeping execution single-flight across gunicorn workers and
replicas. Enable gate: `SCHEDULER_EMBEDDED` (default on in production, off elsewhere).

- The standalone entrypoint (`main.py`, health server on port 8600) is local-debug
  only — blocked in production by `assert_legacy_entrypoint_not_in_production('scheduler')`.
  The service logic lives in `service.py:SchedulerService`, shared by both modes.
- `api.py` (the FastAPI management API) is dead code: never mounted, never served.
- The circuit breaker (`app/circuit_breaker.py`) is **in-memory**, not Redis-backed.
- Kafka emission is gated on `EVENT_BACKBONE=kafka` (#1159); under the production
  default (`pg`) emission is skipped and scraped items are acked after webhook +
  compliance-alert processing.

## Features

- **FDA Warning Letters**: Automated scraping from FDA RSS feeds
- **Import Alerts**: Monitor FDA import alerts and detentions
- **Recall Notices**: Track FDA recall announcements
- **Circuit Breaker**: Resilient execution with automatic recovery
- **Deduplication**: State persistence to prevent duplicate processing
- **Webhooks**: Real-time notifications on changes
- **Prometheus Metrics**: Full observability

## Architecture

```
scheduler/
├── service.py           # SchedulerService — jobs + APScheduler setup (both modes)
├── main.py              # Standalone local-debug entry point (health server, signals)
├── app/
│   ├── __init__.py
│   ├── config.py        # Configuration management
│   ├── models.py        # Data models and schemas
│   ├── scrapers/        # Source-specific scrapers
│   │   ├── __init__.py
│   │   ├── base.py      # Base scraper interface
│   │   ├── fda_warning_letters.py
│   │   ├── fda_import_alerts.py
│   │   └── fda_recalls.py
│   ├── state.py         # Deduplication and state management
│   ├── circuit_breaker.py
│   ├── notifications.py # Webhook delivery
│   ├── kafka_producer.py
│   └── metrics.py       # Prometheus metrics
├── Dockerfile
└── requirements.txt
```

## Configuration

Environment variables:
- `DATABASE_URL`: PostgreSQL connection string
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker addresses
- `REDIS_URL`: Redis connection (circuit breaker state itself is in-memory)
- `WEBHOOK_URLS`: Comma-separated webhook endpoints
- `FDA_SCRAPE_INTERVAL_MINUTES`: Polling interval (default: 60)

## Running

```bash
# Development
python main.py

# Docker
docker build -t regengine-scheduler .
docker run -e DATABASE_URL=... regengine-scheduler
```
