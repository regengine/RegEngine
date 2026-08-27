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

import structlog
from confluent_kafka import Consumer, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

logger = structlog.get_logger("kafka_compat")

try:
    from confluent_kafka.error import KafkaError as ConfluentKafkaError
except (ImportError, ModuleNotFoundError):
    # Some tests stub ``confluent_kafka`` with a lightweight module/MagicMock
    # that exposes ``KafkaError`` at the package root but not as a real
    # ``confluent_kafka.error`` submodule.
    from confluent_kafka import KafkaError as ConfluentKafkaError


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


# Legacy ``KafkaProducer`` kwarg -> librdkafka property (#2977). The old code
# translated four keys and dropped the rest of ``**config`` silently, so the
# scheduler's ``max_in_flight_requests_per_connection=5`` never reached
# librdkafka (which kept its default of 1000000).
_PRODUCER_CONFIG_TRANSLATION: dict[str, str] = {
    "acks": "acks",
    "retries": "message.send.max.retries",
    "retry_backoff_ms": "retry.backoff.ms",
    "request_timeout_ms": "request.timeout.ms",
    "max_in_flight_requests_per_connection": "max.in.flight.requests.per.connection",
    "enable_idempotence": "enable.idempotence",
    "linger_ms": "linger.ms",
    "compression_type": "compression.type",
}

# Options the legacy client accepted that librdkafka has no equivalent for.
# Recognised on purpose so they are warned about rather than either dropped
# in silence or treated as a typo.
_PRODUCER_CONFIG_NO_LIBRDKAFKA_EQUIVALENT: dict[str, str] = {
    "max_block_ms": (
        "librdkafka's produce() raises BufferError immediately instead of "
        "blocking, so there is no equivalent property"
    ),
}


class DeliveryHandle:
    """Future-like handle returned by :meth:`KafkaProducerCompat.send` (#2969).

    Legacy call sites do ``producer.send(...).add_errback(cb)`` to learn about
    *delivery* failures — enqueueing is not delivery. ``send()`` used to
    return ``None``, so every such registration raised ``AttributeError`` and
    the failure counter it fed never moved off zero.

    confluent-kafka reports delivery asynchronously through the
    ``on_delivery`` callback handed to ``produce()``; this object bridges that
    callback to the legacy errback API. Because librdkafka may report delivery
    before the caller has registered anything (``produce()`` is followed by
    ``poll(0)``), a callback registered after the fact is invoked immediately
    with the recorded outcome.
    """

    __slots__ = ("topic", "_errbacks", "_callbacks", "_error", "_resolved")

    def __init__(self, topic: str) -> None:
        self.topic = topic
        self._errbacks: list[Callable[[BaseException], Any]] = []
        self._callbacks: list[Callable[[Any], Any]] = []
        self._error: Optional[BaseException] = None
        self._resolved = False

    def add_errback(self, errback: Callable[[BaseException], Any]) -> "DeliveryHandle":
        if self._resolved:
            if self._error is not None:
                _invoke_delivery_callback(errback, self._error)
        else:
            self._errbacks.append(errback)
        return self

    def add_callback(self, callback: Callable[[Any], Any]) -> "DeliveryHandle":
        if self._resolved:
            if self._error is None:
                _invoke_delivery_callback(callback, self.topic)
        else:
            self._callbacks.append(callback)
        return self

    def _on_delivery(self, err: Any, msg: Any) -> None:
        """librdkafka delivery report — ``err`` is None on success."""
        self._resolved = True
        if err is not None:
            self._error = KafkaError(str(err))
            for errback in self._errbacks:
                _invoke_delivery_callback(errback, self._error)
        else:
            for callback in self._callbacks:
                _invoke_delivery_callback(callback, msg)
        self._errbacks.clear()
        self._callbacks.clear()


def _invoke_delivery_callback(fn: Callable[..., Any], arg: Any) -> None:
    """Run a delivery callback without letting it escape into librdkafka."""
    try:
        fn(arg)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("kafka_delivery_callback_failed", error=str(exc))


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
        bootstrap = ",".join(bootstrap_servers) if not isinstance(bootstrap_servers, str) else bootstrap_servers
        producer_config: dict[str, Any] = {"bootstrap.servers": bootstrap}
        unknown: list[str] = []
        for key, value in config.items():
            librdkafka_key = _PRODUCER_CONFIG_TRANSLATION.get(key)
            if librdkafka_key is not None:
                producer_config[librdkafka_key] = value
            elif key in _PRODUCER_CONFIG_NO_LIBRDKAFKA_EQUIVALENT:
                logger.warning(
                    "kafka_producer_option_not_supported",
                    option=key,
                    reason=_PRODUCER_CONFIG_NO_LIBRDKAFKA_EQUIVALENT[key],
                )
            else:
                unknown.append(key)
        if unknown:
            # #2977: unrecognised kwargs used to be dropped with no warning
            # and no error, so a typo'd or unimplemented option was a no-op.
            raise TypeError(
                "KafkaProducerCompat received unsupported keyword argument(s): "
                + ", ".join(sorted(unknown))
                + " — add an explicit librdkafka translation in "
                "shared/kafka_compat.py rather than passing it blindly."
            )

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
    ) -> DeliveryHandle:
        """Enqueue a record and return a handle for its delivery report.

        The returned handle is what makes ``send(...).add_errback(...)`` work
        (#2969); enqueueing successfully here says nothing about whether the
        broker ever acknowledged the record.
        """
        handle = DeliveryHandle(topic)
        try:
            self._producer.produce(
                topic,
                key=self._key_serializer(key),
                value=self._value_serializer(value),
                headers=headers,
                on_delivery=handle._on_delivery,
            )
            self._producer.poll(0)
        except BufferError as exc:
            raise KafkaError(str(exc)) from exc
        except KafkaException as exc:
            raise KafkaError(str(exc)) from exc
        return handle

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
    """Subset of the legacy ``KafkaConsumer`` API implemented with Confluent.

    Offset semantics (#2971)
    ------------------------
    Callers that pass ``enable_auto_commit=False`` manage offsets by hand:
    they process a record and call :meth:`commit`, or they deliberately
    *skip* the commit to force redelivery of a record they could not
    process. Two librdkafka defaults used to break that contract:

    * ``enable.auto.offset.store`` defaults to ``true`` and is independent
      of ``enable.auto.commit`` — the offset is stored the instant
      ``poll()`` hands the message to the application.
    * ``Consumer.commit()`` with neither ``message=`` nor ``offsets=``
      commits the whole assignment's *stored* offsets.

    Together they meant a skipped record's offset was committed by the next
    record's ``commit()``, so it was never redelivered and never retried.
    In manual mode this class now turns the auto-store off, acknowledges
    exactly the record passed to (or last returned by) :meth:`commit`, and
    rewinds to any record that was delivered but never acknowledged so the
    "force redelivery" contract is real.
    """

    def __init__(
        self,
        *topics: str,
        bootstrap_servers: str | Iterable[str],
        group_id: Optional[str] = None,
        enable_auto_commit: bool = True,
        auto_offset_reset: str = "latest",
        enable_auto_offset_store: Optional[bool] = None,
        **unsupported: Any,
    ) -> None:
        if unsupported:
            # #2971: ``**_: Any`` used to swallow every unrecognised kwarg,
            # so a typo'd or unimplemented option vanished without a trace.
            raise TypeError(
                "KafkaConsumerCompat received unsupported keyword argument(s): "
                + ", ".join(sorted(unsupported))
                + " — add an explicit librdkafka translation in "
                "shared/kafka_compat.py rather than passing it blindly."
            )
        if enable_auto_offset_store is None:
            # Manual-commit callers must decide when an offset becomes
            # eligible for commit; auto-storing at poll time is what let a
            # later commit() ack records they deliberately skipped.
            enable_auto_offset_store = enable_auto_commit

        bootstrap = ",".join(bootstrap_servers) if not isinstance(bootstrap_servers, str) else bootstrap_servers
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap,
                "group.id": group_id or "regengine-default",
                "enable.auto.commit": enable_auto_commit,
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.offset.store": enable_auto_offset_store,
            }
        )
        # Only manage offsets by hand when the caller opted out of BOTH
        # auto-commit and auto-store; otherwise librdkafka owns them.
        self._manual_offsets = not enable_auto_commit and not enable_auto_offset_store
        self._pending: Any = None
        self._pending_record: Optional[ConsumerRecord] = None
        if topics:
            self._consumer.subscribe(list(topics))

    def poll(self, timeout_ms: int = 0) -> dict[TopicPartitionKey, list[ConsumerRecord]]:
        if self._manual_offsets and self._pending is not None:
            # The previous record was delivered but never acknowledged: the
            # caller skipped the commit to force redelivery (#2971). Rewind
            # instead of advancing past it.
            self._rewind_to_pending()
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
        if self._manual_offsets:
            self._pending = msg
            self._pending_record = record
        return {TopicPartitionKey(record.topic, record.partition): [record]}

    def _rewind_to_pending(self) -> None:
        record = self._pending_record
        self._pending = None
        self._pending_record = None
        if record is None:
            return
        logger.warning(
            "kafka_offset_rewind_uncommitted_record",
            topic=record.topic,
            partition=record.partition,
            offset=record.offset,
            reason="record delivered but never committed — forcing redelivery",
        )
        try:
            self._consumer.seek(
                TopicPartition(record.topic, record.partition, record.offset)
            )
        except Exception as exc:  # pragma: no cover - requires a live broker
            # A revoked partition makes seek() fail; the offset was never
            # committed, so the broker redelivers from the last commit anyway.
            logger.warning(
                "kafka_offset_rewind_failed",
                topic=record.topic,
                partition=record.partition,
                offset=record.offset,
                error=str(exc),
            )

    def commit(self, record: Optional[ConsumerRecord] = None) -> None:
        """Acknowledge a single record.

        With manual offsets this commits ``record.offset + 1`` for that one
        partition — never the assignment's stored offsets, which would ack
        records the caller skipped on purpose (#2971). ``record`` defaults
        to the record most recently returned by :meth:`poll`.
        """
        if not self._manual_offsets:
            self._consumer.commit(asynchronous=False)
            return
        target = record if record is not None else self._pending_record
        if target is None:
            # Nothing delivered since the last commit. Committing here would
            # fall back to the assignment's stored offsets.
            logger.warning("kafka_commit_without_record", reason="no record to acknowledge")
            return
        self._consumer.commit(
            offsets=[TopicPartition(target.topic, target.partition, target.offset + 1)],
            asynchronous=False,
        )
        if self._pending_record is not None and (
            (target.topic, target.partition, target.offset)
            == (
                self._pending_record.topic,
                self._pending_record.partition,
                self._pending_record.offset,
            )
        ):
            self._pending = None
            self._pending_record = None

    def close(self) -> None:
        self._consumer.close()


class KafkaAdminClientCompat:
    """Small admin-client wrapper for legacy ``create_topics`` calls."""

    def __init__(self, *, bootstrap_servers: str | Iterable[str], **_: Any) -> None:
        bootstrap = ",".join(bootstrap_servers) if not isinstance(bootstrap_servers, str) else bootstrap_servers
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
