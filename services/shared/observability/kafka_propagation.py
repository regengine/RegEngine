"""Correlation-ID propagation across the Kafka async boundary.

When a producer emits a message, it should attach the current request's
correlation_id (and tenant_id when present) as Kafka headers so the
consumer can re-seed its contextvars before invoking the handler. Without
this, a trace that starts as an HTTP request (admin → produce) ends at the
first broker hop — downstream logs in graph / nlp / admin-review-consumer
have no way to stitch back to the originating request.

Usage on the producer side (legacy producer API)::

    from shared.observability.kafka_propagation import inject_correlation_headers

    headers = inject_correlation_headers({"source": "ingestion"})
    producer.send(topic, key=key, value=payload, headers=headers)

Or on the `confluent-kafka` producer (list of tuples form)::

    headers = inject_correlation_headers_tuples()
    producer.produce(topic, key=key, value=payload, headers=headers)

Usage on the consumer side::

    from shared.observability.kafka_propagation import extract_correlation_headers, bind_correlation_context

    with bind_correlation_context(record.headers):
        handler(record)
"""

from __future__ import annotations

import contextlib
from typing import Any, Iterable, Iterator, List, Optional, Tuple

import structlog

from shared.observability.correlation import (
    CORRELATION_ID_HEADER,
    correlation_id_ctx,
    generate_correlation_id,
    get_correlation_id,
)

logger = structlog.get_logger("kafka.correlation")

# Extra headers we propagate alongside the correlation ID. Tenant header is
# read from structlog contextvars (set by TenantContextMiddleware).
_TENANT_HEADER = "X-RegEngine-Tenant-ID"

KafkaHeader = Tuple[str, bytes]


def _current_tenant_id() -> Optional[str]:
    """Best-effort tenant lookup from structlog contextvars.

    TenantContextMiddleware binds ``tenant_id`` on every request. Kafka
    producers that run inside a request handler will see it here; workers
    that emit without a tenant will simply skip the header.
    """
    try:
        from structlog.contextvars import get_contextvars

        ctx = get_contextvars()
        tid = ctx.get("tenant_id")
        if tid:
            return str(tid)
    except Exception:
        pass
    return None


def inject_correlation_headers(
    existing: Optional[dict] = None,
    *,
    correlation_id: Optional[str] = None,
    mint_if_missing: bool = True,
) -> List[KafkaHeader]:
    """Return Kafka headers augmented with the current correlation ID.

    Args:
        existing: An optional dict of header name → string value that should
            be preserved. Values are utf-8 encoded before being returned.
        correlation_id: Explicit ID to attach. Defaults to the current
            ``correlation_id_ctx`` value.
        mint_if_missing: If True and no correlation ID is set, mint a UUIDv4
            so downstream consumers still have something to log. Callers
            that prefer strict propagation (drop messages without a trace
            ID) can pass False.

    Returns:
        A list of ``(name, utf-8-bytes)`` tuples compatible with both the
        the legacy and ``confluent-kafka`` producer APIs.
    """
    headers: List[KafkaHeader] = []
    # Preserve pre-existing headers first
    if existing:
        for name, value in existing.items():
            headers.append((name, _to_bytes(value)))

    cid = correlation_id or get_correlation_id()
    if not cid and mint_if_missing:
        cid = generate_correlation_id()
    if cid:
        headers.append((CORRELATION_ID_HEADER, cid.encode("utf-8")))

    tid = _current_tenant_id()
    if tid:
        headers.append((_TENANT_HEADER, tid.encode("utf-8")))

    return headers


def inject_correlation_headers_tuples(
    existing: Optional[Iterable[KafkaHeader]] = None,
    *,
    correlation_id: Optional[str] = None,
    mint_if_missing: bool = True,
) -> List[KafkaHeader]:
    """Like ``inject_correlation_headers`` but accepts existing headers as a list of tuples."""
    headers: List[KafkaHeader] = []
    if existing:
        for name, value in existing:
            headers.append((name, _to_bytes(value)))

    cid = correlation_id or get_correlation_id()
    if not cid and mint_if_missing:
        cid = generate_correlation_id()
    if cid:
        headers.append((CORRELATION_ID_HEADER, cid.encode("utf-8")))

    tid = _current_tenant_id()
    if tid:
        headers.append((_TENANT_HEADER, tid.encode("utf-8")))

    return headers


def extract_correlation_headers(
    headers: Optional[Iterable[Any]],
) -> Tuple[Optional[str], Optional[str]]:
    """Pull ``(correlation_id, tenant_id)`` out of a Kafka message's headers.

    Handles the Kafka list-of-tuples header format used by Confluent.
    Values may be bytes or strings; we decode utf-8 tolerantly.
    """
    if not headers:
        return None, None

    correlation_id: Optional[str] = None
    tenant_id: Optional[str] = None

    for entry in headers:
        if entry is None:
            continue
        if isinstance(entry, tuple) and len(entry) == 2:
            name, value = entry
        else:
            # Unrecognized shape — skip defensively.
            continue

        try:
            name_str = name.decode("utf-8") if isinstance(name, (bytes, bytearray)) else str(name)
        except UnicodeDecodeError:
            continue

        if name_str == CORRELATION_ID_HEADER:
            correlation_id = _decode_value(value)
        elif name_str == _TENANT_HEADER:
            tenant_id = _decode_value(value)

    return correlation_id, tenant_id


@contextlib.contextmanager
def bind_correlation_context(
    headers: Optional[Iterable[Any]],
    *,
    mint_if_missing: bool = True,
) -> Iterator[Optional[str]]:
    """Context manager that re-seeds correlation_id (and tenant_id when present).

    Reads the Kafka headers produced by ``inject_correlation_headers`` and
    rebinds the corresponding contextvars for the duration of the ``with``
    block. Yields the correlation ID so callers can log it immediately.

    Example::

        with bind_correlation_context(record.headers) as cid:
            logger.info("processing", correlation_id=cid)
            handler(record)

    On exit the contextvars are restored so callers can process multiple
    records in a single loop iteration without leakage.
    """
    cid, tid = extract_correlation_headers(headers)
    if not cid and mint_if_missing:
        cid = generate_correlation_id()

    cid_token = None
    structlog_bindings: dict = {}
    if cid:
        cid_token = correlation_id_ctx.set(cid)
        structlog_bindings["correlation_id"] = cid
    if tid:
        structlog_bindings["tenant_id"] = tid

    # Apply structlog contextvars if there's anything to bind
    if structlog_bindings:
        try:
            import structlog.contextvars as _sc

            _sc.bind_contextvars(**structlog_bindings)
        except Exception:
            pass

    try:
        yield cid
    finally:
        if cid_token is not None:
            try:
                correlation_id_ctx.reset(cid_token)
            except Exception:
                pass
        if structlog_bindings:
            try:
                import structlog.contextvars as _sc

                _sc.unbind_contextvars(*structlog_bindings.keys())
            except Exception:
                pass


def _to_bytes(value: Any) -> bytes:
    """Encode a header value to bytes, tolerating strings."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return str(value).encode("utf-8")


def _decode_value(value: Any) -> Optional[str]:
    """Decode a header value to a string, returning None on failure."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return str(value)


__all__ = [
    "KafkaHeader",
    "bind_correlation_context",
    "extract_correlation_headers",
    "inject_correlation_headers",
    "inject_correlation_headers_tuples",
]
