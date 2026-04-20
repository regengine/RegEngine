"""Event backbone selector — see #1159.

Gates legacy Kafka consumers behind ``EVENT_BACKBONE`` so they don't run in
parallel with the PostgreSQL ``task_processor`` (split-brain risk). Default
is ``pg`` (PostgreSQL task_processor). Set ``EVENT_BACKBONE=kafka`` to opt
into legacy Kafka consumers.

Usage::

    from shared.event_backbone import kafka_enabled

    if kafka_enabled():
        start_kafka_consumer()
    else:
        logger.info("event_backbone_active", backbone="pg")
"""

from __future__ import annotations

import os


def kafka_enabled() -> bool:
    """Return True only when ``EVENT_BACKBONE=kafka`` (case-insensitive).

    Any other value (including the default empty string) is treated as ``pg``,
    keeping the PostgreSQL task_processor as the sole active consumer and
    preventing the Kafka/PG split-brain described in #1159.
    """
    return os.getenv("EVENT_BACKBONE", "pg").lower() == "kafka"
