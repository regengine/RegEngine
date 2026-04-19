"""Kafka helper utilities."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Mapping, Optional

import structlog
from fastapi import HTTPException

from shared.kafka_auth import KafkaAuthError, sign_event
from shared.observability.kafka_propagation import inject_correlation_headers_tuples

from .config import get_settings


# Producer service identity used when this service publishes to Kafka.
# Must match the value downstream consumers expect in their
# KAFKA_ALLOWED_PRODUCERS_<TOPIC> allowlists (#1078).
INGESTION_PRODUCER_SERVICE = "ingestion-service"

try:
    from confluent_kafka import SerializingProducer
except ModuleNotFoundError:  # pragma: no cover - optional in local/test environments
    SerializingProducer = None  # type: ignore[assignment]

# NOTE: confluent_kafka.schema_registry (SchemaRegistryClient, AvroSerializer) is not
# imported because Kafka Avro schema validation is deferred until a Confluent Schema
# Registry instance is provisioned. See get_producer() below for details.

logger = structlog.get_logger("kafka_utils")

@lru_cache(maxsize=1)
def get_producer() -> SerializingProducer:
    """Return a configured Kafka producer using JSON serialization.

    NOTE: Kafka Avro validation via a schema registry is deferred until a
    Confluent Schema Registry instance is provisioned in the deployment.
    The task_queue V050 migration (alembic/versions/20260329_task_queue_v050.py)
    serves as the interim durable-queue replacement for Kafka-based workflows.
    When a schema registry is available, re-enable by configuring
    SCHEMA_REGISTRY_URL and wiring get_schema_registry_client() +
    AvroSerializer here in place of the json.dumps fallback.
    """
    if SerializingProducer is None:
        raise RuntimeError("confluent_kafka producer is not installed")
    settings = get_settings()

    return SerializingProducer({
        'bootstrap.servers': settings.kafka_bootstrap_servers,
        'key.serializer': KeySerializer(),
        'value.serializer': lambda v, ctx: json.dumps(v).encode("utf-8")
    })


class KeySerializer:
    """Callable class for key serialization to match Confluent Kafka interface."""
    def __call__(self, obj, ctx=None):
        if obj is None:
            return None
        if isinstance(obj, bytes):
            return obj
        return str(obj).encode("utf-8")


def send(
    topic: str,
    payload: dict,
    key: Optional[str] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> None:
    """Send a message to Kafka with correlation-ID propagation.

    The ``correlation_id`` (and ``tenant_id`` when set on the current
    structlog context) is attached as a Kafka header so downstream
    consumers can re-hydrate the trace context. Callers can pass ``headers``
    to add custom headers alongside correlation metadata (#1318).
    """
    # Extract extra headers (non-correlation ones) from caller so the
    # propagation helper can merge them with the auto-injected ones.
    extra: list = []
    if headers:
        for name, value in headers.items():
            if not isinstance(value, (bytes, bytearray)):
                value = str(value).encode("utf-8")
            extra.append((name, value))

    kafka_headers = inject_correlation_headers_tuples(existing=extra)

    # HMAC-sign the event body so NLP / graph / admin consumers can
    # verify this message came from the ingestion service and refuse
    # forged tenant_id claims (#1078). Signing fails loudly when the
    # key is missing in production; callers get a 500 rather than
    # unsigned traffic entering the bus.
    try:
        signed_payload, signed_headers = sign_event(
            payload,
            producer_service=INGESTION_PRODUCER_SERVICE,
            existing_headers=kafka_headers,
        )
    except KafkaAuthError as sign_exc:
        logger.error(
            "kafka_sign_failed",
            topic=topic,
            reason=sign_exc.reason,
        )
        raise HTTPException(
            status_code=500,
            detail="Kafka message signing unavailable",
        ) from sign_exc

    try:
        producer = get_producer()
        producer.produce(topic=topic, key=key, value=signed_payload, headers=signed_headers)
        producer.flush()
    except RuntimeError as exc:
        logger.warning("kafka_client_unavailable", topic=topic, error=str(exc))
        raise HTTPException(status_code=503, detail="Kafka client unavailable") from exc
    except (OSError, IOError, TypeError, ValueError, AttributeError) as exc:
        logger.error("kafka_send_failed", topic=topic, error=str(exc))
        raise HTTPException(status_code=500, detail="Kafka publish failed") from exc
