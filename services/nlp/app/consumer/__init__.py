"""NLP Kafka consumer package.

This package replaces the former single-file ``app/consumer.py`` module.
The split is purely mechanical — no behavior changes:

- ``constants``          — topic names, producer identity, tuning constants
- ``tenancy``            — tenant resolution + tenant-scoped key helpers
- ``conversion``         — legacy entity → ExtractionPayload conversion
- ``thresholds``         — live confidence thresholds + CONFIDENCE_THRESHOLD proxy
- ``schema_validation``  — JSON-schema loading + eager inbound validator
- ``review_routing``     — three-tier confidence routing to graph / review
- ``dlq``                — dead-letter-queue helpers + FSMA-event detection
- ``health``             — shutdown event + HTTP liveness probe

The consumer loop, extractor wiring (feature flags + lazy getters), and the
Kafka runner stay HERE in ``__init__.py`` on purpose:

* tests patch module attributes on ``app.consumer`` /
  ``services.nlp.app.consumer`` (``KafkaConsumer``, ``KafkaProducer``,
  ``KafkaAdminClient``, ``_ensure_topic``, ``_get_fsma_extractor``,
  ``_get_llm_extractor``) and the functions that read those names must share
  this module's namespace for the patches to be visible;
* ``importlib.reload(app.consumer)`` must re-read the ``NLP_ENABLE_*`` env
  flags (test_extractor_wiring.py);
* the #1085 regression guard reads ``app.consumer.__file__`` and scans the
  consumer loop's DLQ/flush/commit windows, so the loop must live in the
  file that ``__file__`` points at.

Every public and private name from the original module is importable from
``app.consumer`` exactly as before.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean env flag ('1', 'true', 'yes' = True)."""

    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}

import structlog
from jsonschema import Draft7Validator, ValidationError
from confluent_kafka.admin import NewTopic
from shared.kafka_compat import (
    KafkaAdminClientCompat as KafkaAdminClient,
    KafkaConsumerCompat as KafkaConsumer,
    KafkaError,
    KafkaProducerCompat as KafkaProducer,
    KafkaTimeoutError,
    TopicAlreadyExistsError,
)
from opentelemetry import trace, propagate
from prometheus_client import Counter
from structlog.contextvars import get_contextvars

from pathlib import Path
import sys

# Standardized path discovery via shared utility
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from shared.schemas import (
    ExtractionPayload,
    GraphEvent,
    ObligationType,
    ReviewItem,
    Threshold,
)
from shared.observability.kafka_propagation import (
    bind_correlation_context,
    extract_correlation_headers,
    inject_correlation_headers_tuples,
)
from shared.kafka_auth import (
    KafkaAuthError,
    get_allowed_producers,
    sign_event,
    verify_event,
)

# Producer service identity used when this consumer re-emits events to
# downstream topics (graph.update, nlp.needs_review, nlp.extracted).
# Must match the value the downstream consumer expects in its
# KAFKA_ALLOWED_PRODUCERS_<TOPIC> env var (#1078).
from .constants import NLP_PRODUCER_SERVICE

from ..classification import SignalClassifier
from ..config import settings
from ..extractor import extract_entities
from ..extractors import FSMAExtractor, LLMGenerativeExtractor
from ..extractors.fsma_types import (
    TOPIC_GRAPH_UPDATE as FSMA_TOPIC_GRAPH_UPDATE,
    TOPIC_NEEDS_REVIEW as FSMA_TOPIC_NEEDS_REVIEW,
)
from ..resolution import EntityResolver
from ..s3_loader import parse_s3_uri
from ..s3_utils import get_bytes
from shared.url_validation import PathTraversalError

# ---------------------------------------------------------------------------
# Backward-compatible re-exports from the package submodules. Every name the
# original consumer.py defined at module level remains importable from
# ``app.consumer`` (and patchable as an attribute of this module).
# ---------------------------------------------------------------------------
from .constants import (
    MAX_RETRIES,
    TOPIC_DLQ,
    TOPIC_FSMA_DLQ,
    TOPIC_GRAPH_UPDATE,
    TOPIC_NEEDS_REVIEW,
    _LEGACY_HEURISTIC_CONFIDENCE_CAP,
    _LLM_EXTRACTION_CONFIDENCE_CAP,
)
from .tenancy import _kafka_key_for, _resolve_tenant_id, _retry_key_for
from .conversion import (
    CLASSIFIER,
    RESOLVER,
    _convert_entities_to_extraction,
    _convert_llm_results_to_extractions,
    _now_iso,
    _score_regulatory_date,
)
from .thresholds import CONFIDENCE_THRESHOLD, _ThresholdProxy, _current_thresholds
from .schema_validation import _INBOUND_VALIDATOR, _load_inbound_schema, _load_schema
from .review_routing import _build_review_reasons, _route_extraction
from .dlq import _collect_ftl_flags, _is_fsma_event, _retry_counts
from .dlq import _send_to_dlq, _send_to_fsma_dlq
from .health import (
    _HEALTH_PORT,
    _POLL_ERROR_UNHEALTHY_THRESHOLD,
    _HealthHandler,
    _shutdown_event,
    _start_health_server,
    consumer_health,
    mark_loop_started,
    mark_loop_stopped,
    record_poll_error,
    record_poll_success,
    record_topic_creation_failure,
    reset_consumer_health,
    stop_consumer,
)

logger = structlog.get_logger("nlp-consumer")
_audit_logger = structlog.get_logger("nlp-consumer-audit")


# ---------------------------------------------------------------------------
# Structured extractor wiring (#1194)
# ---------------------------------------------------------------------------
#
# Until this wiring landed, FSMAExtractor and LLMGenerativeExtractor were
# imported but never instantiated from the consumer loop. All KDE-gating —
# the core reason the FSMAExtractor exists — was therefore bypassed for
# every inbound document, which meant FSMA 204 documents silently fell
# through to the regex-only pipeline and skipped the HITL gate.
#
# Two feature flags control activation so we can deploy carefully:
#
#   NLP_ENABLE_FSMA_EXTRACTOR (default true)
#     When on, every document passes through FSMAExtractor before the
#     legacy regex extractor. CTEs with both TLC and Event Date are
#     routed to ``graph.update``; everything else is routed to
#     ``nlp.needs_review`` for human-in-the-loop review.
#
#   NLP_ENABLE_LLM_EXTRACTOR (default false)
#     Opt-in — LLM inference has per-token cost and higher latency.
#     When on, documents that produce zero high-confidence FSMA CTEs
#     get an LLM pass as fallback. Results augment (do not replace)
#     the regex-based ExtractionPayload stream.
#
# The legacy regex extractor (extract_entities) remains live as a
# backstop so existing consumers continue to observe nlp.extracted
# events.
NLP_ENABLE_FSMA_EXTRACTOR = os.getenv("NLP_ENABLE_FSMA_EXTRACTOR", "true").lower() in (
    "true", "1", "yes", "on",
)
NLP_ENABLE_LLM_EXTRACTOR = os.getenv("NLP_ENABLE_LLM_EXTRACTOR", "false").lower() in (
    "true", "1", "yes", "on",
)

# Instantiate extractors lazily on first use so test imports don't pay
# the model-download cost and so flag flips at runtime are honored
# (flags are read once at module load — restarts of the consumer pick
# up new values).
_FSMA_EXTRACTOR: Optional[FSMAExtractor] = None
_LLM_EXTRACTOR: Optional[LLMGenerativeExtractor] = None


def _get_fsma_extractor() -> FSMAExtractor:
    global _FSMA_EXTRACTOR
    if _FSMA_EXTRACTOR is None:
        _FSMA_EXTRACTOR = FSMAExtractor()
    return _FSMA_EXTRACTOR


def _get_llm_extractor() -> LLMGenerativeExtractor:
    global _LLM_EXTRACTOR
    if _LLM_EXTRACTOR is None:
        _LLM_EXTRACTOR = LLMGenerativeExtractor()
    return _LLM_EXTRACTOR


class FSMARoutingError(RuntimeError):
    """Raised when ``_run_fsma_extractor`` reported ``status="error"`` (#2972).

    The extractor catches its own routing (flush timeout / connection error)
    and signing (``KafkaAuthError``) failures and returns an error status
    rather than raising, so the outer ``except (ValidationError,
    KafkaTimeoutError)`` handler never saw them and the record was committed
    as a success with its CTEs dropped. The consumer loop converts that
    status into this exception so the existing retry / DLQ escalation — the
    one every sibling failure path already uses — engages.
    """


def _run_fsma_extractor(
    text: str,
    doc_id: str,
    doc_hash: str,
    producer: KafkaProducer,
    tenant_id: str,
    kafka_headers: list,
) -> dict:
    """
    Run FSMAExtractor and route results to the appropriate Kafka topic.

    ``tenant_id`` is required (#1122) — the extractor and the Kafka key
    both need it, and the consumer-loop caller has already validated
    tenant resolution before we land here. Passing a falsy tenant_id
    indicates a caller bug and raises before any downstream state
    changes.

    Returns a summary dict with counts so the caller can emit a single
    structured log line.
    """
    if not tenant_id:
        # Defense in depth — the caller should have DLQ'd before reaching
        # this function. Surface as an error rather than silently emit.
        logger.error(
            "fsma_extractor_invoked_without_tenant",
            document_id=doc_id,
        )
        return {"status": "error", "cte_count": 0, "routed": None}
    extractor = _get_fsma_extractor()
    try:
        result = extractor.extract(text, doc_id, tenant_id=tenant_id)
    except Exception as exc:
        logger.exception(
            "fsma_extractor_error",
            document_id=doc_id,
            tenant_id=tenant_id,
            error=str(exc),
        )
        return {"status": "error", "cte_count": 0, "routed": None}

    routing = extractor.route_extraction(result)
    topic = routing["topic"]
    payload = {
        "tenant_id": tenant_id,
        "doc_hash": doc_hash,
        **routing["payload"],
    }
    # Sign the event so downstream consumers (graph, review UI) can
    # verify it came from this service and refuse forgeries (#1078).
    try:
        signed_payload, signed_headers = sign_event(
            payload,
            producer_service=NLP_PRODUCER_SERVICE,
            existing_headers=kafka_headers,
        )
    except KafkaAuthError as sign_exc:
        logger.error(
            "fsma_routing_sign_failed",
            document_id=doc_id,
            topic=topic,
            reason=sign_exc.reason,
        )
        return {"status": "error", "cte_count": len(result.ctes), "routed": topic}
    try:
        producer.send(
            topic,
            # #1122 — tenant-scoped partition key ensures two tenants
            # with the same doc_id cannot interleave on the same
            # partition. Prior format ``doc_id`` made cross-tenant
            # ordering collisions silently possible.
            key=_kafka_key_for(tenant_id, doc_id),
            value=signed_payload,
            headers=signed_headers,
        )
        producer.flush(timeout=1.0)
    except (KafkaTimeoutError, ConnectionError, OSError) as exc:
        logger.error(
            "fsma_routing_failed",
            document_id=doc_id,
            topic=topic,
            error=str(exc),
        )
        return {"status": "error", "cte_count": len(result.ctes), "routed": topic}

    logger.info(
        "fsma_extractor_routed",
        document_id=doc_id,
        cte_count=len(result.ctes),
        review_required=result.review_required,
        topic=topic,
    )
    return {
        "status": "ok",
        "cte_count": len(result.ctes),
        "review_required": result.review_required,
        "routed": topic,
        "high_confidence": topic == FSMA_TOPIC_GRAPH_UPDATE,
    }


def _run_llm_extractor(
    text: str,
    doc_id: str,
    jurisdiction: str,
) -> list:
    """Run LLMGenerativeExtractor; return its structured results."""
    try:
        extractor = _get_llm_extractor()
        return extractor.extract(
            text=text,
            jurisdiction=jurisdiction,
            correlation_id=doc_id,
        )
    except Exception as exc:
        logger.exception(
            "llm_extractor_error",
            document_id=doc_id,
            error=str(exc),
        )
        return []

try:
    MESSAGES_COUNTER = Counter("nlp_messages_total", "NLP messages processed", ["status"])
    POISON_PILL_COUNTER = Counter("nlp_poison_pill_total", "Count of malformed Kafka messages")
    # #1176 — surface tenant-resolution outcomes so SRE can spot a
    # spike in messages missing tenant context (producer regression)
    # or with mismatched header vs payload (injection attempt).
    TENANT_RESOLUTION_COUNTER = Counter(
        "nlp_tenant_resolution_total",
        "NLP per-message tenant resolution outcome",
        ["outcome"],
    )
except ValueError:
    # Metric already registered (happens during test re-imports)
    from prometheus_client import REGISTRY
    MESSAGES_COUNTER = REGISTRY._names_to_collectors.get("nlp_messages_total")
    POISON_PILL_COUNTER = REGISTRY._names_to_collectors.get("nlp_poison_pill_total")
    TENANT_RESOLUTION_COUNTER = REGISTRY._names_to_collectors.get(
        "nlp_tenant_resolution_total"
    )

# Legacy ``nlp.extracted`` topic feature flag (#1218).
# The legacy publish sent the raw ``entities`` list with no confidence filtering,
# defeating the gating at the ``graph.update`` / ``nlp.needs_review`` boundary.
# Default: OFF. Any operator who flips this on MUST accept that downstream
# subscribers see ungated data.
EMIT_LEGACY_EXTRACTED_TOPIC = _env_flag("NLP_EMIT_LEGACY_TOPIC", default=False)


def _ensure_topic(topic: str) -> None:
    admin = None
    try:
        admin = KafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap)
        admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
    except TopicAlreadyExistsError:
        pass
    except (ConnectionError, TimeoutError, RuntimeError, OSError) as exc:
        # #2979 — a swallowed creation failure surfaces later as the
        # UNKNOWN_TOPIC_OR_PART poll error that used to kill the loop, so
        # record it on the liveness probe rather than only logging it.
        logger.warning("topic_creation_failed", topic=topic, error=str(exc))
        record_topic_creation_failure(topic)
    finally:
        if admin is not None:
            try:
                admin.close()
            except (RuntimeError, OSError):  # pragma: no cover
                pass


from shared.observability import setup_standalone_observability
tracer = setup_standalone_observability("nlp-consumer")

def run_consumer() -> None:
    # Start health endpoint before first Kafka poll so probes succeed at startup
    _start_health_server()

    # Ensure topics exist
    _ensure_topic(TOPIC_GRAPH_UPDATE)
    _ensure_topic(TOPIC_NEEDS_REVIEW)
    _ensure_topic(TOPIC_FSMA_DLQ)
    _ensure_topic(TOPIC_DLQ)

    # Use raw consumer to handle poison pills manually
    consumer = KafkaConsumer(
        settings.topic_in,
        bootstrap_servers=settings.kafka_bootstrap,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        group_id=settings.consumer_group_id,
    )
    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap,
        key_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        acks="all",
    )

    try:
        _run_consumer_loop(consumer, producer)
        mark_loop_stopped()
    except BaseException as exc:
        # #2979 — the loop used to propagate out of a daemon thread and simply
        # vanish: no restart, no supervision, and /health still 200. Record the
        # fatal condition so the liveness probe reports the consumer dead and
        # an orchestrator can restart the process, then re-raise so the death
        # is visible to threading.excepthook rather than swallowed.
        logger.exception("nlp_consumer_loop_died", error=str(exc))
        mark_loop_stopped(exc)
        raise
    finally:
        # #1220 — explicitly flush the producer before close so buffered
        # DLQ messages are persisted on SIGTERM. librdkafka's internal
        # buffer is asynchronous; without flush, in-flight dead-letters
        # (including FSMA extraction failures we keep for forensic
        # analysis) can be silently dropped when the process exits.
        _graceful_producer_shutdown(producer)
        try:
            consumer.close()
        except (RuntimeError, OSError) as exc:  # pragma: no cover - infra
            logger.warning("consumer_close_error", error=str(exc))


def _graceful_producer_shutdown(producer: KafkaProducer) -> None:
    """Flush buffered messages then close the producer (#1220).

    Called from ``run_consumer``'s ``finally`` block on graceful shutdown.
    The flush happens BEFORE close so any in-flight DLQ events — which
    carry forensic context for failed FSMA extractions — are delivered
    to the broker before the process exits. Exceptions are logged but
    never re-raised: we still want ``close()`` to run even if the broker
    is unreachable during shutdown.
    """
    try:
        producer.flush(timeout=5.0)
        logger.info("nlp_producer_flushed_on_shutdown")
    except Exception as exc:  # pragma: no cover - infra dependent
        logger.exception("dlq_flush_on_shutdown_failed", error=str(exc))
    try:
        producer.close(timeout=5.0)
    except (RuntimeError, OSError) as exc:  # pragma: no cover - infra
        logger.warning("producer_close_error", error=str(exc))


# #2979 — poll-error backoff. A transient broker/topic error must not end
# message processing for the life of the process; it backs off and retries,
# and the liveness probe reports unhealthy while the errors persist.
_POLL_ERROR_BACKOFF_SECONDS = float(os.getenv("NLP_POLL_ERROR_BACKOFF_SECONDS", "1.0"))
_POLL_ERROR_BACKOFF_MAX_SECONDS = float(os.getenv("NLP_POLL_ERROR_BACKOFF_MAX_SECONDS", "30.0"))


def _wait_backoff(seconds: float) -> None:
    """Interruptible sleep — a shutdown during backoff exits immediately."""
    _shutdown_event.wait(seconds)


def _run_consumer_loop(consumer: KafkaConsumer, producer: KafkaProducer) -> None:
    mark_loop_started()
    consecutive_poll_errors = 0
    while not _shutdown_event.is_set():
        try:
            messages = consumer.poll(timeout_ms=500)
        except (KafkaError, ConnectionError, OSError) as poll_exc:
            # #2979 — KafkaConsumerCompat.poll() raises on any message-level
            # error (e.g. UNKNOWN_TOPIC_OR_PART). Without this the exception
            # left the loop, killed the daemon thread and stopped processing
            # permanently with no signal.
            consecutive_poll_errors += 1
            record_poll_error(str(poll_exc))
            backoff = min(
                _POLL_ERROR_BACKOFF_SECONDS * (2 ** (consecutive_poll_errors - 1)),
                _POLL_ERROR_BACKOFF_MAX_SECONDS,
            )
            logger.error(
                "kafka_poll_failed",
                error=str(poll_exc),
                consecutive_errors=consecutive_poll_errors,
                backoff_seconds=backoff,
                unhealthy=consecutive_poll_errors >= _POLL_ERROR_UNHEALTHY_THRESHOLD,
            )
            _wait_backoff(backoff)
            continue
        consecutive_poll_errors = 0
        record_poll_success()
        if not messages:
            continue
        for records in messages.values():
            for record in records:
                # Re-hydrate correlation_id (and tenant_id) from the inbound
                # message's Kafka headers so every log record inside this
                # iteration carries the originator's trace ID (#1318).
                with bind_correlation_context(record.headers or []):
                    # #1176 — explicit header-tenant extraction separate from
                    # the contextvar bind so the raw value survives the
                    # `bind_correlation_context` exit and can be compared
                    # against the payload tenant_id below (injection check).
                    _, header_tenant_id = extract_correlation_headers(
                        record.headers or []
                    )
                    # Standardized Trace Injection
                    with tracer.start_as_current_span(
                        "nlp.process_message",
                        attributes={"kafka.topic": record.topic, "kafka.offset": record.offset}
                    ) as span:
                        # Capture trace context for DLQ headers (OTel W3C)
                        otel_headers: list = []
                        propagate.inject(otel_headers)
                        # Merge OTel headers + correlation headers for DLQ so
                        # dead-lettered messages can still be traced back.
                        merged_otel = [(k, v.encode("utf-8")) for k, v in otel_headers]
                        kafka_headers = inject_correlation_headers_tuples(existing=merged_otel)

                        raw_value = record.value
                        try:
                            evt = json.loads(raw_value.decode("utf-8")) if raw_value else {}
                        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                            logger.error("poison_pill_detected", error=str(exc), offset=record.offset)
                            POISON_PILL_COUNTER.inc()
                            _send_to_dlq(producer, raw_value, f"Deserialization failed: {str(exc)}", headers=kafka_headers)
                            # #1085 — flush DLQ producer BEFORE committing the
                            # inbound offset. producer.send() only buffers; a
                            # crash between buffer and broker-ack would advance
                            # the offset while the DLQ record is still sitting
                            # in the producer buffer — silent data loss and an
                            # FSMA 204 audit-trail gap. On timeout, refuse to
                            # commit so Kafka redelivers the message.
                            try:
                                producer.flush(timeout=5.0)
                            except KafkaTimeoutError:
                                logger.error(
                                    "dlq_flush_timeout",
                                    offset=record.offset,
                                    topic=record.topic,
                                    stage="poison_pill",
                                )
                                continue  # do NOT commit — force redelivery
                            consumer.commit()
                            continue

                        if not evt:
                            # #2971 — an empty payload (tombstone / null
                            # value) carries nothing to process, but skipping
                            # the commit now means real redelivery, which
                            # would spin this record forever and block the
                            # partition. Nothing can be lost by acking it, so
                            # ack it — same as the other "nothing to do"
                            # skips below.
                            logger.warning(
                                "skipping_empty_event",
                                offset=record.offset,
                                topic=record.topic,
                            )
                            MESSAGES_COUNTER.labels(status="skipped").inc()
                            consumer.commit()
                            continue

                        # --- HMAC producer authentication (#1078) ---
                        # Before routing by ``tenant_id``, verify that
                        # the message was signed by a service we trust
                        # to publish to this topic. Without this, any
                        # actor that can publish to ingest.normalized
                        # can tag a forged event with any tenant_id
                        # they choose — the audit log records the
                        # *claimed* tenant, so cross-tenant injection
                        # has no audit signal. On failure the message
                        # is DLQ'd and the offset is committed so the
                        # partition is not blocked by retries that
                        # will never succeed.
                        try:
                            evt, _verified_producer = verify_event(
                                evt,
                                record.headers,
                                topic=settings.topic_in,
                                allowed_producers=get_allowed_producers(settings.topic_in),
                            )
                        except KafkaAuthError as auth_exc:
                            logger.error(
                                "kafka_auth_failed",
                                reason=auth_exc.reason,
                                topic=settings.topic_in,
                                offset=record.offset,
                                **auth_exc.fields,
                            )
                            POISON_PILL_COUNTER.inc()
                            doc_id_for_dlq = (
                                evt.get("document_id") if isinstance(evt, dict) else None
                            ) or "unknown"
                            _send_to_fsma_dlq(
                                producer,
                                evt if isinstance(evt, dict) else raw_value,
                                f"kafka_auth_failed: {auth_exc}",
                                doc_id_for_dlq,
                                kafka_headers,
                            )
                            MESSAGES_COUNTER.labels(status="unauthorized").inc()
                            # #1085 — flush DLQ producer before committing.
                            try:
                                producer.flush(timeout=5.0)
                            except KafkaTimeoutError:
                                logger.error(
                                    "dlq_flush_timeout",
                                    offset=record.offset,
                                    topic=record.topic,
                                    stage="kafka_auth_failed",
                                )
                                continue  # do NOT commit — force redelivery
                            consumer.commit()
                            continue

                        # Extract doc_id early for logging (before validation)
                        doc_id = evt.get("document_id") or evt.get("doc_id") or "unknown"
                        span.set_attribute("document_id", doc_id)

                        # --- Inbound schema validation (OWASP API10:2023) ---
                        if _INBOUND_VALIDATOR is not None:
                            errors = list(_INBOUND_VALIDATOR.iter_errors(evt))
                            if errors:
                                error_msg = "; ".join(e.message for e in errors[:5])
                                logger.error(
                                    "inbound_schema_invalid",
                                    document_id=doc_id,
                                    error=error_msg,
                                    offset=record.offset,
                                )
                                # tenant_id has not been resolved yet — this
                                # reject may or may not have a usable tenant
                                # context; pass the raw payload value as a
                                # best-effort hint for DLQ partitioning
                                # (#1122). ``None`` is safe — _send_to_fsma_dlq
                                # falls back to the NO_TENANT sentinel key.
                                _send_to_fsma_dlq(
                                    producer, evt,
                                    f"Inbound schema invalid: {error_msg}",
                                    doc_id, headers=kafka_headers,
                                    tenant_id=evt.get("tenant_id") if isinstance(evt, dict) else None,
                                )
                                MESSAGES_COUNTER.labels(status="rejected").inc()
                                # #1085 — flush DLQ producer before committing.
                                try:
                                    producer.flush(timeout=5.0)
                                except KafkaTimeoutError:
                                    logger.error(
                                        "dlq_flush_timeout",
                                        offset=record.offset,
                                        topic=record.topic,
                                        stage="inbound_schema_invalid",
                                    )
                                    continue  # do NOT commit — force redelivery
                                consumer.commit()
                                continue

                        try:
                            doc_hash = evt.get("document_hash") or evt.get("content_hash") or doc_id
                            norm_path = evt.get("normalized_s3_path")
                            inline_text = evt.get("text_clean")
                            # #1176 / RE-SEC-001 — resolve tenant_id from the
                            # SIGNED payload field (authoritative). The Kafka
                            # header is passed in only so the resolver can
                            # defensively detect header/body mismatches; it is
                            # NOT trusted (Kafka headers are outside the HMAC).
                            # Fail-fast DLQ on missing / invalid / mismatched
                            # values so downstream writes can never happen
                            # without tenant context.
                            tenant_id, _tenant_reject_reason = _resolve_tenant_id(
                                header_tenant_id=header_tenant_id,
                                payload_tenant_id=evt.get("tenant_id"),
                            )
                            provenance = evt.get("provenance") or {}
                        except (KeyError, TypeError, ValueError, AttributeError) as field_exc:
                            logger.error(
                                "malformed_event_fields",
                                error=str(field_exc),
                                offset=record.offset,
                            )
                            _send_to_fsma_dlq(
                                producer, evt, f"Field extraction failed: {field_exc}",
                                doc_id, kafka_headers,
                                tenant_id=evt.get("tenant_id") if isinstance(evt, dict) else None,
                            )
                            MESSAGES_COUNTER.labels(status="error").inc()
                            # #1085 — flush DLQ producer before committing.
                            try:
                                producer.flush(timeout=5.0)
                            except KafkaTimeoutError:
                                logger.error(
                                    "dlq_flush_timeout",
                                    offset=record.offset,
                                    topic=record.topic,
                                    stage="malformed_event_fields_pre_tenant",
                                )
                                continue  # do NOT commit — force redelivery
                            consumer.commit()
                            continue

                        # #1176/#1122 — if tenant resolution failed, send to FSMA
                        # DLQ and skip processing. An NLP extraction with no
                        # tenant context cannot safely reach the graph / review
                        # queue because downstream stores all assume tenant
                        # scoping. The sentinel ``E_MISSING_TENANT_ID`` is
                        # included in the DLQ reason so SRE can grep across
                        # services for a consistent signal.
                        if tenant_id is None:
                            logger.error(
                                "nlp_message_rejected_missing_tenant",
                                document_id=doc_id,
                                reason=_tenant_reject_reason,
                                error_code="E_MISSING_TENANT_ID",
                                offset=record.offset,
                            )
                            TENANT_RESOLUTION_COUNTER.labels(outcome="rejected").inc()
                            _send_to_fsma_dlq(
                                producer,
                                evt,
                                f"E_MISSING_TENANT_ID: {_tenant_reject_reason}",
                                doc_id,
                                headers=kafka_headers,
                                tenant_id=None,
                            )
                            MESSAGES_COUNTER.labels(status="rejected").inc()
                            # #1085 — flush DLQ producer before committing.
                            try:
                                producer.flush(timeout=5.0)
                            except KafkaTimeoutError:
                                logger.error(
                                    "dlq_flush_timeout",
                                    offset=record.offset,
                                    topic=record.topic,
                                    stage="tenant_resolution_failed",
                                )
                                continue  # do NOT commit — force redelivery
                            consumer.commit()
                            continue

                        TENANT_RESOLUTION_COUNTER.labels(
                            outcome="from_header" if header_tenant_id else "from_payload"
                        ).inc()

                    try:
                        doc_hash = evt.get("document_hash") or evt.get("content_hash") or doc_id
                        norm_path = evt.get("normalized_s3_path")
                        inline_text = evt.get("text_clean")
                        # #1176 — resolver already ran above; reuse the
                        # validated tenant_id. Do not re-read from payload
                        # here because that would defeat the header-priority
                        # and mismatch-rejection checks.
                        provenance = evt.get("provenance") or {}
                    except (KeyError, TypeError, ValueError, AttributeError) as field_exc:
                        logger.error(
                            "malformed_event_fields",
                            error=str(field_exc),
                            tenant_id=tenant_id,
                            offset=record.offset,
                        )
                        _send_to_fsma_dlq(
                            producer, evt, f"Field extraction failed: {field_exc}",
                            doc_id, kafka_headers,
                            tenant_id=tenant_id,
                        )
                        MESSAGES_COUNTER.labels(status="error").inc()
                        # #1085 — flush DLQ producer before committing.
                        try:
                            producer.flush(timeout=5.0)
                        except KafkaTimeoutError:
                            logger.error(
                                "dlq_flush_timeout",
                                offset=record.offset,
                                topic=record.topic,
                                stage="malformed_event_fields_post_tenant",
                            )
                            continue  # do NOT commit — force redelivery
                        consumer.commit()
                        continue

                    if not doc_id or (not norm_path and not inline_text):
                        logger.warning("skipping_event_missing_keys", event=evt)
                        MESSAGES_COUNTER.labels(status="skipped").inc()
                        consumer.commit()
                        continue

                    try:
                        if inline_text:
                            text = str(inline_text)[:2_000_000]
                            source_url = provenance.get(
                                "source_url", evt.get("source_url", "unknown")
                            )
                        else:
                            # #1127 — use validated parse instead of inline
                            # partition(). parse_s3_uri() → validate_s3_uri()
                            # rejects path traversal and malformed URIs.
                            try:
                                bucket, key = parse_s3_uri(norm_path)
                            except (ValueError, PathTraversalError) as parse_err:
                                logger.warning(
                                    "s3_uri_rejected",
                                    norm_path=norm_path,
                                    doc_id=doc_id,
                                    tenant_id=tenant_id,
                                    err=str(parse_err),
                                )
                                MESSAGES_COUNTER.labels(status="skipped").inc()
                                consumer.commit()
                                continue
                            payload = json.loads(get_bytes(bucket, key))
                            text = payload.get("text", "")[:2_000_000]
                            source_url = payload.get("source_url", "unknown")

                        # --- Structured extractor pass (#1194) ---
                        # FSMAExtractor runs first for every document when the
                        # feature flag is on. It owns KDE-minimum gating for
                        # FSMA 204 and routes qualifying CTEs to
                        # ``graph.update`` or ``nlp.needs_review``. When the
                        # flag is off, this block is a no-op and the legacy
                        # regex pipeline below is the only path.
                        fsma_summary: Optional[dict] = None
                        if NLP_ENABLE_FSMA_EXTRACTOR:
                            fsma_summary = _run_fsma_extractor(
                                text=text,
                                doc_id=doc_id,
                                doc_hash=doc_hash,
                                producer=producer,
                                tenant_id=tenant_id,
                                kafka_headers=kafka_headers,
                            )
                            # #2972 — the extractor swallows its own routing
                            # and signing failures and reports them as a
                            # status. Ignoring that status committed the
                            # source offset, skipped the DLQ and counted the
                            # record as a success, so the CTEs were dropped
                            # with only a log line. Raise so the retry /
                            # max-retries-to-DLQ escalation below handles it
                            # exactly like every sibling failure path.
                            if fsma_summary.get("status") == "error":
                                raise FSMARoutingError(
                                    "fsma_routing_failed "
                                    f"(cte_count={fsma_summary.get('cte_count')}, "
                                    f"topic={fsma_summary.get('routed')})"
                                )

                        # --- Legacy regex extractor (backstop) ---
                        entities = extract_entities(text)

                        # Convert to canonical ExtractionPayload format
                        extractions = _convert_entities_to_extraction(
                            entities, doc_id, source_url
                        )

                        # --- LLM fallback pass (#1194) ---
                        # Only invoked when the regex+FSMA passes yielded
                        # NO high-confidence extractions and the operator
                        # has explicitly opted in to LLM spend.
                        if NLP_ENABLE_LLM_EXTRACTOR:
                            produced_high_conf = (
                                fsma_summary is not None
                                and fsma_summary.get("high_confidence")
                            ) or any(
                                e.confidence_score >= settings.extraction_confidence_high
                                for e in extractions
                            )
                            if not produced_high_conf:
                                jurisdiction = "US-FDA" if _is_fsma_event(evt) else "unknown"
                                llm_results = _run_llm_extractor(
                                    text=text,
                                    doc_id=doc_id,
                                    jurisdiction=jurisdiction,
                                )
                                # #2947 — bridge the results into the
                                # canonical extraction list. Without this the
                                # paid provider call produced nothing but a
                                # count in the log line below: the routing
                                # loop iterates ``extractions``, which only
                                # the regex path fed. Every LLM item is
                                # capped below the medium threshold inside
                                # the bridge, so it can only reach HITL.
                                llm_extractions = (
                                    _convert_llm_results_to_extractions(
                                        llm_results, doc_id, source_url
                                    )
                                )
                                extractions.extend(llm_extractions)
                                logger.info(
                                    "llm_extractor_run",
                                    document_id=doc_id,
                                    result_count=len(llm_results),
                                    routed_count=len(llm_extractions),
                                )

                        # Route each extraction based on confidence
                        for extraction in extractions:
                            _route_extraction(
                                extraction,
                                doc_id,
                                doc_hash,
                                source_url,
                                producer,
                                tenant_id,
                            )

                        # Legacy ``nlp.extracted`` topic — OFF by default (#1218).
                        # The legacy publish sent the raw ``entities`` list with
                        # zero confidence filtering, defeating the gating at the
                        # Kafka boundary. Operators may re-enable via env
                        # ``NLP_EMIT_LEGACY_TOPIC=1`` during a migration window;
                        # each emit logs a deprecation warning so migration
                        # progress is observable.
                        if EMIT_LEGACY_EXTRACTED_TOPIC:
                            # Annotate each entity with its (capped) confidence
                            # so downstream subscribers at minimum see the tier.
                            high_t, medium_t = _current_thresholds()
                            annotated_entities = []
                            for ent in entities:
                                # Attach a placeholder confidence if absent;
                                # the regex path has no per-entity score.
                                annotated = dict(ent)
                                annotated.setdefault(
                                    "confidence_score",
                                    min(0.50, _LEGACY_HEURISTIC_CONFIDENCE_CAP),
                                )
                                annotated_entities.append(annotated)
                            legacy_out = {
                                "event_id": str(uuid.uuid4()),
                                "document_id": doc_id,
                                "tenant_id": tenant_id,
                                "source_url": source_url,
                                "timestamp": _now_iso(),
                                "entities": annotated_entities,
                                "deprecated": True,
                                "deprecation_notice": (
                                    "nlp.extracted is deprecated; migrate to "
                                    "graph.update / nlp.needs_review. Set "
                                    "NLP_EMIT_LEGACY_TOPIC=0 to disable."
                                ),
                            }
                            try:
                                _load_schema().validate(legacy_out)
                                # Sign the legacy emit too — subscribers
                                # that have verification wired on will
                                # refuse to accept unsigned messages on
                                # any topic (#1078).
                                signed_legacy, signed_legacy_headers = sign_event(
                                    legacy_out,
                                    producer_service=NLP_PRODUCER_SERVICE,
                                )
                                producer.send(
                                    settings.topic_out,
                                    # #1122 — tenant-scoped Kafka key.
                                    key=_kafka_key_for(tenant_id, doc_id),
                                    value=signed_legacy,
                                    headers=signed_legacy_headers,
                                )
                                logger.warning(
                                    "nlp_legacy_topic_emitted",
                                    document_id=doc_id,
                                    topic=settings.topic_out,
                                    reason="NLP_EMIT_LEGACY_TOPIC=1 set",
                                )
                            except ValidationError as legacy_exc:
                                logger.error(
                                    "nlp_legacy_topic_schema_invalid",
                                    document_id=doc_id,
                                    error=str(legacy_exc),
                                )

                        producer.flush(timeout=1.0)

                        # Use live thresholds for logging counts so metrics
                        # agree with _route_extraction behavior (#1260).
                        high_t_log, medium_t_log = _current_thresholds()
                        logger.info(
                            "nlp_extraction_complete",
                            document_id=doc_id,
                            tenant_id=tenant_id,
                            extraction_count=len(extractions),
                            high_confidence=sum(
                                1 for e in extractions
                                if e.confidence_score >= high_t_log
                            ),
                            medium_confidence=sum(
                                1 for e in extractions
                                if medium_t_log <= e.confidence_score < high_t_log
                            ),
                            low_confidence=sum(
                                1 for e in extractions
                                if e.confidence_score < medium_t_log
                            ),
                        )
                        MESSAGES_COUNTER.labels(status="success").inc()

                        # Synchronous audit logging for FSMA compliance (#982)
                        try:
                            _audit_logger.info(
                                "nlp_extraction_audited",
                                extra={
                                    "document_id": doc_id,
                                    "tenant_id": tenant_id,
                                    "source_url": source_url,
                                    "extraction_count": len(extractions),
                                    "timestamp": _now_iso(),
                                },
                            )
                        except Exception as _audit_exc:
                            logger.error("nlp_audit_logging_failed", document_id=doc_id, error=str(_audit_exc))

                        consumer.commit()
                    # KafkaError (not just KafkaTimeoutError) retries here:
                    # producer.send() raises the base KafkaError on
                    # produce-time failures (buffer full, unknown topic)
                    # while flush() raises KafkaTimeoutError. Catching only
                    # the timeout sent transient send failures straight to
                    # the DLQ with no retry, skipping the retry budget that
                    # every sibling Kafka failure path uses. KafkaAuthError
                    # deliberately stays out: a bad signature never verifies
                    # no matter how often it is retried.
                    except (ValidationError, KafkaError, FSMARoutingError) as exc:
                        # #1122 — tenant-scoped retry-count key. Prior code
                        # keyed only by doc_id which meant two tenants with
                        # the same doc_id shared a retry bucket (e.g.
                        # tenant A's 3rd retry DLQ'd tenant B's first
                        # attempt).
                        retry_key = _retry_key_for(tenant_id, doc_id or "unknown")
                        _retry_counts[retry_key] = _retry_counts.get(retry_key, 0) + 1

                        if _retry_counts[retry_key] >= MAX_RETRIES:
                            logger.error(
                                "nlp_max_retries_exceeded_sending_to_dlq",
                                document_id=doc_id,
                                tenant_id=tenant_id,
                                retries=_retry_counts[retry_key],
                                error=str(exc),
                            )
                            _send_to_fsma_dlq(
                                producer,
                                evt,
                                str(exc),
                                doc_id,
                                headers=kafka_headers,
                                tenant_id=tenant_id,
                            )
                            _retry_counts.pop(retry_key, None)
                            # #1085 — flush DLQ producer before committing.
                            try:
                                producer.flush(timeout=5.0)
                            except KafkaTimeoutError:
                                logger.error(
                                    "dlq_flush_timeout",
                                    offset=record.offset,
                                    topic=record.topic,
                                    stage="max_retries_exceeded",
                                )
                                # Restore retry counter so redelivery doesn't
                                # reset the retry budget on this message.
                                _retry_counts[retry_key] = MAX_RETRIES
                                continue  # do NOT commit — force redelivery
                            consumer.commit()
                        else:
                            logger.warning(
                                "nlp_validation_or_kafka_error_will_retry",
                                document_id=doc_id,
                                tenant_id=tenant_id,
                                retry=_retry_counts[retry_key],
                                error=str(exc),
                            )
                        MESSAGES_COUNTER.labels(status="error").inc()
                    except Exception as exc:  # pragma: no cover - requires infra
                        logger.exception(
                            "nlp_processing_error_sending_to_dlq",
                            document_id=doc_id,
                            tenant_id=tenant_id,
                            error=str(exc),
                        )
                        _send_to_fsma_dlq(
                            producer,
                            evt,
                            str(exc),
                            doc_id,
                            headers=kafka_headers,
                            tenant_id=tenant_id,
                        )
                        try:
                            producer.flush(timeout=5.0)
                        except KafkaTimeoutError:
                            logger.error(
                                "dlq_flush_timeout",
                                offset=record.offset,
                                topic=record.topic,
                                stage="processing_error",
                            )
                            continue  # do NOT commit — force redelivery
                        consumer.commit()
                        MESSAGES_COUNTER.labels(status="error").inc()
