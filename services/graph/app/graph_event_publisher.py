import json
import logging
import os

from kafka import KafkaProducer

# In prod, import from shared.schemas
# from shared.schemas import GraphEvent, ControlPayload, MappingPayload

logger = logging.getLogger(__name__)
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
TOPIC_GRAPH_AUDIT = "graph.audit"  # New topic for audit log


class GraphEventPublisher:
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers=KAFKA_BROKER,
            value_serializer=lambda x: json.dumps(x).encode("utf-8"),
        )

    def publish_control_event(self, tenant_id: str, control_data: dict):
        """Emits an audit event after a control is upserted."""
        try:
            payload = {
                "event_type": "control",
                "tenant_id": tenant_id,
                "control": control_data,
                "status": "COMMITTED",
            }
            self.producer.send(TOPIC_GRAPH_AUDIT, value=payload)
        except Exception as e:
            logger.error(f"Failed to publish control audit event: {e}")

    def publish_mapping_event(self, tenant_id: str, mapping_data: dict):
        """Emits an audit event after a mapping is created."""
        try:
            payload = {
                "event_type": "mapping",
                "tenant_id": tenant_id,
                "mapping": mapping_data,
                "status": "COMMITTED",
            }
            self.producer.send(TOPIC_GRAPH_AUDIT, value=payload)
        except Exception as e:
            logger.error(f"Failed to publish mapping audit event: {e}")
