# Scheduler Service

A production-grade job scheduler for automated regulatory change monitoring.

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
├── main.py              # Entry point and APScheduler setup
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
- `REDIS_URL`: Redis for circuit breaker state
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
