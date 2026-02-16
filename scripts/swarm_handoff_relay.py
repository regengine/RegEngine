#!/usr/bin/env python3
"""
Swarm Handoff Relay.

Handles agent-to-agent task delegation via Redpanda (Kafka).
Conforms to the Fractal Swarm handoff protocol.
"""
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from kafka import KafkaProducer, KafkaConsumer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

# Configuration
KAFKA_BROKER = "localhost:9092"
HANDOFF_TOPIC = "swarm.handoffs"
LOG_FILE = "swarm_handoffs.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger("swarm-relay")

class SwarmHandoffRelay:
    """
    Relay for autonomous agent handoffs.
    
    Principles:
    - Asynchronous delegation via Redpanda
    - Standardized handoff schema
    - Priority-based processing
    """
    
    def __init__(self, broker: str = KAFKA_BROKER):
        self.broker = broker
        self.producer = None
        if KAFKA_AVAILABLE:
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=[self.broker],
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    retries=3
                )
                logger.info(f"Connected to Redpanda at {self.broker}")
            except Exception as e:
                logger.warning(f"Failed to connect to Redpanda: {e}. Falling back to file-based relay.")

    def emit_handoff(self, agent_output: Dict[str, Any]):
        """Publishes a handoff message from an agent's output."""
        handoff = agent_output.get("handoff")
        if not handoff:
            logger.info(f"No handoff required for agent {agent_output.get('agent')}")
            return

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_agent": agent_output.get("agent"),
            "target_agent": handoff.get("to_agent"),
            "priority": handoff.get("priority", "medium"),
            "action_required": handoff.get("action_required"),
            "original_task": agent_output.get("task"),
            "context": {
                "files_changed": agent_output.get("files_changed", []),
                "risks": agent_output.get("risks", [])
            }
        }

        logger.info(f"EMITTING HANDOFF: {payload['source_agent']} -> {payload['target_agent']} ({payload['priority']})")
        
        # 1. Attempt Redpanda dispatch
        if self.producer:
            try:
                self.producer.send(HANDOFF_TOPIC, payload)
                self.producer.flush()
                logger.info("Successfully dispatched handoff to Redpanda")
            except Exception as e:
                logger.error(f"Redpanda dispatch failed: {e}")

        # 2. Always write to local record for audit/fallback
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(payload) + "\n")

    def listen(self):
        """Infinite loop listening for handoff messages (Daemon Mode)."""
        if not KAFKA_AVAILABLE:
            logger.error("Kafka library not installed. Cannot run in listen mode.")
            return

        try:
            consumer = KafkaConsumer(
                HANDOFF_TOPIC,
                bootstrap_servers=[self.broker],
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='swarm-orchestrator',
                value_deserializer=lambda x: json.loads(x.decode('utf-8'))
            )
            logger.info(f"Swarm Relay listening on {HANDOFF_TOPIC}...")
            
            for message in consumer:
                payload = message.value
                logger.info(f"📥 RECEIVED HANDOFF: {payload['source_agent']} -> {payload['target_agent']}")
                self._process_handoff(payload)
                
        except Exception as e:
            logger.error(f"Consumer loop crashed: {e}")

    def _process_handoff(self, payload: Dict[str, Any]):
        """Triggers the next agent in the swarm."""
        target = payload["target_agent"]
        action = payload["action_required"]
        
        logger.info(f"🚀 TRIGGERING {target}: '{action}'")
        # In a real swarm, this would call scripts/swarm_orchestrator.py --summon
        # For now, we log the intent.
        
if __name__ == "__main__":
    relay = SwarmHandoffRelay()
    if len(sys.argv) > 1 and sys.argv[1] == "--listen":
        relay.listen()
    else:
        logger.info("Swarm Handoff Relay initialized. Use --listen to run as daemon.")
