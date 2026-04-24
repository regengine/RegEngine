"""Confluent-backed compatibility helpers for legacy Kafka call sites.

The repo used to depend on a pure-Python client whose public package name was
``kafka``. A few deprecated consumers still use that style of API. This module
keeps their small surface area stable while the only runtime client underneath
is ``confluent-kafka``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from confluent_kafka import Consumer, KafkaException, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.error import KafkaError as ConfluentKafkaError


class KafkaError(Exception):
    """Compatibility exception for legacy producer/consumer handlers."""


class KafkaTimeoutError(KafkaError):
    """Raised when a Kafka operation times out."""


class TopicAlreadyExistsError(KafkaError):
    """Raised when topic creation races an existing topic."""


@dataclass(frozen=True)
class TopicPartitionKey:
    """Hashable poll-batch key mirroring the legacy TopicPartition shape."""

    topic: str
    partition: int


@dataclass
class ConsumerRecord:
    """Small record object matching the fields used by legacy handlers."""

    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes | None
    headers: list[tuple[str, bytes | None]]


class KafkaProducerCompat:
    """Subset of the legacy ``KafkaProducer`` API implemented with Confluent."""

    def __init__(
        self,
        *,
        bootstrap_servers: str | Iterable[str],
        value_serializer: Optional[Callable[[Any], bytes]] = None,
        key_serializer: Optional[Callable[[Any], bytes]] = None,
        **config: Any,
    ) -> None:
        bootstrap = (
            ",".join(bootstrap_servers)
            if not isinstance(bootstrap_servers, str)
            else bootstrap_servers
        )
        producer_config: dict[str, Any] = {"bootstrap.servers": bootstrap}
        if "acks" in config:
            producer_config["acks"] = config["acks"]
        if "retries" in config:
            producer_config["message.send.max.retries"] = config["retries"]
        if "retry_backoff_ms" in config:
            producer_config["retry.backoff.ms"] = config["retry_backoff_ms"]
        if "request_timeout_ms" in config:
            producer_config["request.timeout.ms"] = config["request_timeout_ms"]

        self._producer = Producer(producer_config)
        self._value_serializer = value_serializer or _json_serializer
        self._key_serializer = key_serializer or _optional_str_serializer

    def send(
        self,
        topic: str,
        *,
        key: Any = None,
        value: Any = None,
        headers: Optional[list[tuple[str, bytes | None]]] = None,
    ) -> None:
        try:
            self._producer.produce(
                topic,
                key=self._key_serializer(key),
                value=self._value_serializer(value),
                headers=headers,
            )
            self._producer.poll(0)
        except BufferError as exc:
            raise KafkaError(str(exc)) from exc
        except KafkaException as exc:
            raise KafkaError(str(exc)) from exc

    def flush(self, timeout: Optional[float] = None) -> None:
        remaining = self._producer.flush(timeout if timeout is not None else -1)
        if remaining:
            raise KafkaTimeoutError(f"{remaining} Kafka message(s) still buffered")

    def close(self, timeout: Optional[float] = None) -> None:
        self.flush(timeout=timeout)

    def bootstrap_connected(self) -> bool:
        try:
            self._producer.list_topics(timeout=2.0)
            return True
        except KafkaException:
            return False


class KafkaConsumerCompat:
    """Subset of the legacy ``KafkaConsumer`` API implemented with Confluent."""

    def __init__(
        self,
        *topics: str,
        bootstrap_servers: str | Iterable[str],
        group_id: Optional[str] = None,
        enable_auto_commit: bool = True,
        auto_offset_reset: str = "latest",
        **_: Any,
    ) -> None:
        bootstrap = (
            ",".join(bootstrap_servers)
            if not isinstance(bootstrap_servers, str)
            else bootstrap_servers
        )
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap,
                "group.id": group_id or "regengine-default",
                "enable.auto.commit": enable_auto_commit,
                "auto.offset.reset": auto_offset_reset,
            }
        )
        if topics:
            self._consumer.subscribe(list(topics))

    def poll(self, timeout_ms: int = 0) -> dict[TopicPartitionKey, list[ConsumerRecord]]:
        msg = self._consumer.poll(timeout_ms / 1000.0)
        if msg is None:
            return {}
        err = msg.error()
        if err is not None:
            raise KafkaError(str(err))
        record = ConsumerRecord(
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            key=msg.key(),
            value=msg.value(),
            headers=msg.headers() or [],
        )
        return {TopicPartitionKey(record.topic, record.partition): [record]}

    def commit(self) -> None:
        self._consumer.commit(asynchronous=False)

    def close(self) -> None:
        self._consumer.close()


class KafkaAdminClientCompat:
    """Small admin-client wrapper for legacy ``create_topics`` calls."""

    def __init__(self, *, bootstrap_servers: str | Iterable[str], **_: Any) -> None:
        bootstrap = (
            ",".join(bootstrap_servers)
            if not isinstance(bootstrap_servers, str)
            else bootstrap_servers
        )
        self._admin = AdminClient({"bootstrap.servers": bootstrap})

    def create_topics(self, topics: list[NewTopic]) -> None:
        futures = self._admin.create_topics(topics)
        for topic, future in futures.items():
            try:
                future.result()
            except Exception as exc:
                code = getattr(getattr(exc, "args", [None])[0], "code", lambda: None)()
                if code == ConfluentKafkaError.TOPIC_ALREADY_EXISTS:
                    raise TopicAlreadyExistsError(topic) from exc
                raise KafkaError(str(exc)) from exc

    def close(self) -> None:
        # confluent-kafka AdminClient has no close method.
        return None


def _json_serializer(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return json.dumps(value).encode("utf-8")


def _optional_str_serializer(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")
