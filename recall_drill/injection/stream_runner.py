"""Kafka / Redpanda streaming injection runner for recall drill data.

Produces mutated CTE records to a configurable Kafka topic so the
RegEngine streaming ingestion pipeline can be stress-tested in
real-time with failure-injected events.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    """Kafka / Redpanda connection and topic configuration."""

    bootstrap_servers: str = "localhost:9092"
    topic: str = "regengine.cte.ingest"
    client_id: str = "recall-drill-producer"
    acks: str = "all"
    retries: int = 3
    linger_ms: int = 5
    batch_size: int = 16_384
    compression_type: str = "gzip"
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: str | None = None
    sasl_username: str | None = None
    sasl_password: str | None = None

    @classmethod
    def from_env(cls) -> StreamConfig:
        """Build configuration from environment variables."""
        return cls(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            topic=os.getenv("KAFKA_TOPIC", "regengine.cte.ingest"),
            client_id=os.getenv("KAFKA_CLIENT_ID", "recall-drill-producer"),
            security_protocol=os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
            sasl_mechanism=os.getenv("KAFKA_SASL_MECHANISM"),
            sasl_username=os.getenv("KAFKA_SASL_USERNAME"),
            sasl_password=os.getenv("KAFKA_SASL_PASSWORD"),
        )


@dataclass
class StreamResult:
    """Result of producing a single message to Kafka."""

    trace_id: str
    mutation_id: str | None
    topic: str
    partition: int | None
    offset: int | None
    latency_ms: float
    success: bool
    error: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class StreamBatchResult:
    """Aggregate result for a batch of stream injections."""

    total_messages: int
    success_count: int
    failure_count: int
    avg_latency_ms: float
    results: list[StreamResult]
    mutation_metadata: dict | None = None

    def to_dict(self) -> dict:
        return {
            "total_messages": self.total_messages,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_latency_ms": self.avg_latency_ms,
            "mutation": self.mutation_metadata,
        }


def _serialize_value(record: dict) -> bytes:
    """Serialize a CTE record to JSON bytes for Kafka."""
    return json.dumps(record, default=str, ensure_ascii=False).encode("utf-8")


def _serialize_key(record: dict) -> bytes | None:
    """Use the TLC as the message key for partition affinity."""
    tlc = record.get("traceability_lot_code")
    if tlc:
        return tlc.encode("utf-8")
    return None


class StreamRunner:
    """Produce mutated CTE records to Kafka / Redpanda.

    The runner uses ``confluent_kafka`` when available and falls back
    to a lightweight internal producer that logs messages for
    environments without a running broker.

    Parameters
    ----------
    config:
        Kafka connection and topic settings.  Defaults to
        ``StreamConfig.from_env()``.
    dry_run:
        When *True*, messages are serialized and timed but not
        actually sent to the broker.  Useful for local testing.
    """

    def __init__(
        self,
        config: StreamConfig | None = None,
        dry_run: bool = False,
    ):
        self._config = config or StreamConfig.from_env()
        self._dry_run = dry_run
        self._producer: Any = None

    # ------------------------------------------------------------------
    # Producer lifecycle
    # ------------------------------------------------------------------

    def _get_producer(self) -> Any:
        """Lazily create the Kafka producer."""
        if self._producer is not None:
            return self._producer

        if self._dry_run:
            logger.info("StreamRunner in dry-run mode — no broker connection")
            return None

        try:
            from confluent_kafka import Producer

            conf: dict[str, Any] = {
                "bootstrap.servers": self._config.bootstrap_servers,
                "client.id": self._config.client_id,
                "acks": self._config.acks,
                "retries": self._config.retries,
                "linger.ms": self._config.linger_ms,
                "batch.size": self._config.batch_size,
                "compression.type": self._config.compression_type,
                "security.protocol": self._config.security_protocol,
            }
            if self._config.sasl_mechanism:
                conf["sasl.mechanism"] = self._config.sasl_mechanism
            if self._config.sasl_username:
                conf["sasl.username"] = self._config.sasl_username
            if self._config.sasl_password:
                conf["sasl.password"] = self._config.sasl_password

            self._producer = Producer(conf)
            logger.info(
                "Kafka producer connected: %s topic=%s",
                self._config.bootstrap_servers,
                self._config.topic,
            )
            return self._producer

        except ImportError:
            logger.warning(
                "confluent_kafka not installed — falling back to dry-run mode"
            )
            self._dry_run = True
            return None

    def close(self) -> None:
        """Flush and close the producer."""
        if self._producer is not None:
            self._producer.flush(timeout=10)
            logger.info("Kafka producer flushed and closed")
            self._producer = None

    # ------------------------------------------------------------------
    # Produce messages
    # ------------------------------------------------------------------

    def produce_record(
        self,
        record: dict,
        mutation_id: str | None = None,
        topic: str | None = None,
    ) -> StreamResult:
        """Produce a single CTE record to Kafka.

        Attaches ``trace_id`` and optional ``mutation_id`` as message
        headers for downstream correlation.
        """
        trace_id = str(uuid.uuid4())
        target_topic = topic or self._config.topic

        headers = [
            ("trace_id", trace_id.encode()),
            ("source", b"recall_drill"),
        ]
        if mutation_id:
            headers.append(("mutation_id", mutation_id.encode()))

        value = _serialize_value(record)
        key = _serialize_key(record)

        start = time.perf_counter()

        if self._dry_run:
            # Simulate production latency
            latency = (time.perf_counter() - start) * 1000
            return StreamResult(
                trace_id=trace_id,
                mutation_id=mutation_id,
                topic=target_topic,
                partition=0,
                offset=0,
                latency_ms=round(latency, 2),
                success=True,
            )

        producer = self._get_producer()
        if producer is None:
            return StreamResult(
                trace_id=trace_id,
                mutation_id=mutation_id,
                topic=target_topic,
                partition=None,
                offset=None,
                latency_ms=0.0,
                success=False,
                error="No Kafka producer available",
            )

        delivery_result: dict[str, Any] = {}

        def _on_delivery(err: Any, msg: Any) -> None:
            if err is not None:
                delivery_result["error"] = str(err)
            else:
                delivery_result["partition"] = msg.partition()
                delivery_result["offset"] = msg.offset()

        try:
            producer.produce(
                topic=target_topic,
                key=key,
                value=value,
                headers=headers,
                on_delivery=_on_delivery,
            )
            producer.poll(0)  # trigger delivery callbacks
            latency = (time.perf_counter() - start) * 1000

            if "error" in delivery_result:
                return StreamResult(
                    trace_id=trace_id,
                    mutation_id=mutation_id,
                    topic=target_topic,
                    partition=None,
                    offset=None,
                    latency_ms=round(latency, 2),
                    success=False,
                    error=delivery_result["error"],
                )

            return StreamResult(
                trace_id=trace_id,
                mutation_id=mutation_id,
                topic=target_topic,
                partition=delivery_result.get("partition"),
                offset=delivery_result.get("offset"),
                latency_ms=round(latency, 2),
                success=True,
            )

        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            return StreamResult(
                trace_id=trace_id,
                mutation_id=mutation_id,
                topic=target_topic,
                partition=None,
                offset=None,
                latency_ms=round(latency, 2),
                success=False,
                error=str(exc),
            )

    def produce_batch(
        self,
        records: list[dict],
        mutation_id: str | None = None,
        topic: str | None = None,
    ) -> StreamBatchResult:
        """Produce a batch of CTE records to Kafka."""
        results: list[StreamResult] = []
        for record in records:
            result = self.produce_record(
                record, mutation_id=mutation_id, topic=topic
            )
            results.append(result)

        # Flush to ensure all messages are delivered
        if not self._dry_run and self._producer is not None:
            self._producer.flush(timeout=30)

        successes = [r for r in results if r.success]
        latencies = [r.latency_ms for r in results]

        return StreamBatchResult(
            total_messages=len(results),
            success_count=len(successes),
            failure_count=len(results) - len(successes),
            avg_latency_ms=round(sum(latencies) / max(len(latencies), 1), 2),
            results=results,
        )

    def produce_mutated_batch(
        self,
        records: list[dict],
        mutation_metadata: dict,
        topic: str | None = None,
    ) -> StreamBatchResult:
        """Produce a batch of already-mutated records with metadata linkage."""
        mutation_id = mutation_metadata.get("mutation_id")
        result = self.produce_batch(records, mutation_id=mutation_id, topic=topic)
        result.mutation_metadata = mutation_metadata
        return result
