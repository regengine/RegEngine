"""Canonical DLQ (Dead Letter Queue) entry point for RegEngine services.

#1228: This module re-exports the shared DLQProducer so services can import
from a stable top-level path:

    from shared.dlq import DLQProducer

The implementation lives in shared.observability.dlq_producer and handles both
confluent-kafka and kafka-python backends transparently.
"""

from shared.observability.dlq_producer import DLQProducer

__all__ = ["DLQProducer"]
