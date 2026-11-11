# Retired Kafka event backbone (archive)

**Archived:** 2026-11-04, tech-debt work item WI-05 (PR #3699).
**Loaded by:** nothing. No build, test, deploy or CI workflow imports anything
under this directory; `pyproject.toml` `testpaths` does not include it. Files
were moved with `git mv` so `git log --follow` reaches their history.

## Why

`EVENT_BACKBONE` has defaulted to `pg` since #1159. Production (one FastAPI
process on Railway) ran no Kafka consumer and no producer: every path below was
gated behind `EVENT_BACKBONE=kafka` or wrote to a broker nothing read. The
modules still shipped `confluent-kafka[schema-registry,avro]` and `fastavro` in
the production image (113 lock lines) and kept 3,500 lines of code and 33 test
files alive. The PostgreSQL task queue (`services/shared/task_queue.py`,
`server/workers/task_processor.py`) is the only backbone.

## Call graph at archive time

Importers outside the Kafka set, and what replaced each import:

| Archived module (original path) | Former importers on the live path | What the live path does now |
|---|---|---|
| `services/shared/event_backbone.py` (`kafka_enabled()`) | `services/scheduler/service.py`, `services/admin/main.py`, `services/shared/secrets_manager.py` | Branches removed; pg is the only backbone. `validate_production_secrets` requires `DATABASE_URL` only. |
| `services/shared/kafka_auth.py` (HMAC event signing, `KAFKA_EVENT_SIGNING_KEY`) | `services/nlp/app/consumer/{__init__,review_routing}.py`, `services/ingestion/app/kafka_utils.py` | Nothing signs events; task rows are written and read inside one database under RLS. |
| `services/shared/kafka_compat.py`, `services/shared/kafka_consumer_base.py` | `services/ingestion/app/routes_health_metrics.py` (`kafka_health_check`), the consumers | `/health` returns `"kafka": "retired"`. |
| `services/shared/dlq.py`, `services/shared/observability/dlq_producer.py` | `services/nlp/app/consumer/dlq.py` | Failed tasks go to `fsma.task_queue` dead rows (visibility timeout + retry policy in the task processor). |
| `services/shared/observability/kafka_propagation.py` | the consumers and `graph_event_publisher.py` only; `server/main.py` reads `shared.observability.correlation`, not this module | Correlation ids propagate through `CorrelationIdMiddleware` and the task payload. |
| `services/ingestion/app/kafka_utils.py` (`send`) | `services/ingestion/app/routes_ingest.py` (`_process_and_emit`, dedup path) | `_process_and_emit` returns the `NormalizedEvent`; the claim-check for >1MB text stays. |
| `services/scheduler/app/kafka_producer.py` | `services/scheduler/service.py` (`emit_batch`, `emit_fsma_batch`, `close`) | `_process_new_items` acks on webhook delivery + compliance alerting; `get_fsma_transformer` is no longer imported by the service (the transformer module stays in tree, unused by production). |
| `services/admin/app/review_consumer.py` | `services/admin/main.py` (`_start/_stop_review_consumer`), `services/admin/app/routes.py` (`/health/consumer`) | Review items reach `HallucinationTracker` through the task processor; `/health/consumer` returns a static `{"status": "retired"}`. |
| `services/graph/app/graph_event_publisher.py` | `services/graph/app/overlay_writer.py` | Control and mapping commits log `tenant_control_committed` / `control_mapping_committed`. |
| `services/nlp/app/consumer/__init__.py` (consumer loop, Kafka runner), `dlq.py`, `health.py`, `review_routing.py` (`_route_extraction`) | `services/nlp/main.py` (consumer thread) | The live `__init__.py` keeps the extractor flags and lazy getters; `_is_fsma_event` / `_collect_ftl_flags` moved to `services/nlp/app/consumer/events.py`; `review_routing.py` keeps `_build_review_reasons`. |

Pure helpers that the pg path still uses were left in place:
`services/nlp/app/consumer/{conversion,thresholds,schema_validation,tenancy,constants}.py`
(`tenancy._kafka_key_for` is a string helper with no client dependency).

## Tests moved here

33 files that only exercised the modules above, listed in the PR: every
`test_kafka_*`, `test_consumer*`, `test_dlq_producer_1228`,
`test_event_backbone_1159`, `test_review_consumer_shutdown_flush_1220`,
`test_review_hardening`, `test_qa5_consumer_health`, `test_kafka_utils_1342`,
`test_routes_health_metrics_1342`, `test_pipeline_hardening`,
`test_poison_pill_flush_before_commit_1085`, `test_qa_commit_retry_gaps`,
`test_retrieval_tenant_scope`, `test_empty_record_ack_2971`,
`test_fsma_routing_status_2972`, `test_break_kafka_failure_injection`.
Four mixed files were copied here in full and trimmed in place:
`services/nlp/tests/test_extractor_wiring.py`,
`services/scheduler/tests/test_scheduler_hardening.py`,
`tests/shared/test_observability_correlation.py`, plus the archived consumer
`__init__.py` and `review_routing.py` themselves.

## Environment variables no longer read

`EVENT_BACKBONE`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_USERNAME`,
`KAFKA_PASSWORD`, `KAFKA_SECURITY_PROTOCOL`, `KAFKA_TOPIC_NORMALIZED`,
`KAFKA_TOPIC_NLP`, `KAFKA_TOPIC_DLQ`, `KAFKA_CONSUMER_GROUP_ID`,
`KAFKA_EVENT_SIGNING_KEY`, `KAFKA_ALLOWED_PRODUCERS_<TOPIC>`,
`KAFKA_MAX_SIGNATURE_AGE_SECONDS`, `ENABLE_REVIEW_CONSUMER`,
`NLP_EMIT_LEGACY_TOPIC`, `SCHEMA_REGISTRY_URL`. They can be removed from
Railway; nothing fails if they stay set.

## Restoring something

Open an issue naming the module and the reader that needs it. Restoring the
backbone means re-adding `confluent-kafka` to `requirements.in`, recompiling
the lock, moving the module back with `git mv`, and removing the matching
pattern from `scripts/check_legacy_dead_code.py`.
