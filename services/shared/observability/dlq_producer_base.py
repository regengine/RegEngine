"""
BaseDLQProducer — consolidated Dead Letter Queue producer interface.

#1228: DLQ producer singletons were duplicated across services/graph/app/consumer.py,
services/graph/app/consumers/fsma_consumer.py, and services/admin/app/review_consumer.py.
This module provides a single ``BaseDLQProducer`` class that all services should import.

Usage::

    from shared.observability.dlq_producer_base import BaseDLQProducer

    dlq = BaseDLQProducer(
        bootstrap_servers="redpanda:9092",
        topic="my.service.dlq",
        service_name="my-service",
    )
    dlq.send(original_bytes, reason="deserialization_error", detail="<traceback>")
    dlq.flush()
    dlq.close()
"""

from shared.observability.dlq_producer import DLQProducer as BaseDLQProducer  # noqa: F401

__all__ = ["BaseDLQProducer"]
