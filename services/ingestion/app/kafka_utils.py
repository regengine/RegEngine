"""Kafka helper utilities."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

import structlog
from fastapi import HTTPException
from kafka import KafkaProducer
from kafka.errors import KafkaTimeoutError

from .config import get_settings
from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
import os

logger = structlog.get_logger("kafka_utils")


@lru_cache(maxsize=1)
def get_schema_registry_client() -> SchemaRegistryClient:
    settings = get_settings()
    return SchemaRegistryClient({'url': 'http://schema-registry:8081'}) # Make configurable

def load_schema(schema_name: str) -> str:
    """Load Avro schema using standardized project path discovery."""
    from shared.paths import project_root, ensure_shared_importable
    ensure_shared_importable()
    
    repo_root = project_root()
    # Support both Docker (/app/schemas) and local development
    schema_paths = [
        repo_root / "schemas" / schema_name,
        Path("/app/schemas") / schema_name
    ]

    for path in schema_paths:
        if path.exists():
            return path.read_text()

    logger.error("schema_file_not_found", schema_name=schema_name, attempted=[str(p) for p in schema_paths])
    raise FileNotFoundError(f"Schema file not found: {schema_name}")

@lru_cache(maxsize=1)
def get_producer() -> SerializingProducer:
    """Return a configured Kafka producer with Avro support."""
    settings = get_settings()
    
    # schema_registry = get_schema_registry_client()
    # avro_serializer = AvroSerializer(
    #     schema_registry,
    #     load_schema("normalized_document.avsc"),
    # )

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


def send(topic: str, payload: dict, key: Optional[str] = None) -> None:
    """Send a message to Kafka."""
    try:
        producer = get_producer()
        producer.produce(topic=topic, key=key, value=payload)
        producer.flush()
    except KafkaTimeoutError as exc:
        logger.error("kafka_flush_timeout", topic=topic, error=str(exc))
        raise HTTPException(status_code=500, detail="Kafka flush timeout") from exc

