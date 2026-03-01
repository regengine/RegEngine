#!/usr/bin/env python3
"""
🧬 RegEngine Founder's Health Check
A unified diagnostic tool for solo builders to verify the entire stack.
Checks: Ports, Database connectivity, Redis (Distributed Rate Limiting), and Agent Swarm.
"""

import os
import socket
import sys
import time
import requests
import structlog
from typing import Dict, List

# Configure pretty logging for the founder
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger("health-check")

SERVICES = {
    "Gateway": 80,
    "Admin API": 8400,
    "Ingestion Service": 8002,
    "Graph Service": 8200,
    "Compliance API": 8500,
    "Opportunity API": 8300,
    "Energy API": 8700,
    "Finance API": 8900,
    "Billing Service": 8800,
    "Postgres": 5433,
    "Redis": 6379,
    "Neo4j": 7687,
    "MinIO": 9000,
    "Redpanda (Kafka)": 9092,
}

def check_port(port: int, host: str = "localhost") -> bool:
    """Check if a port is open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0

def check_redis_distributed() -> bool:
    """Check if Redis is reachable and usable for rate limiting."""
    try:
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(url)
        return r.ping()
    except Exception:
        return False

def check_agent_swarm() -> bool:
    """Verify the agent swarm can initialize."""
    try:
        from regengine.swarm.coordinator import AgentSwarm
        swarm = AgentSwarm()
        return swarm is not None
    except Exception:
        return False

def run_diagnostics():
    print("\n" + "═" * 60)
    print("🚀 REGENGINE FOUNDER'S HEALTH CHECK")
    print("═" * 60 + "\n")

    failure_count = 0
    
    # 1. Port Check
    log.info("DIAGNOSTIC: Port Scan")
    for name, port in SERVICES.items():
        status = "✅ OPEN" if check_port(port) else "❌ CLOSED"
        if "❌" in status:
            failure_count += 1
            log.warning(f"  {name:<20}: {status} (Port {port})")
        else:
            log.info(f"  {name:<20}: {status} (Port {port})")

    # 2. Redis Distributed Check
    print("")
    log.info("DIAGNOSTIC: Distributed Rate Limiting (Redis)")
    if check_redis_distributed():
        log.info("  Redis connectivity: ✅ OK")
    else:
        failure_count += 1
        log.error("  Redis connectivity: ❌ FAIL (Rate limiting will fall back to memory)")

    # 3. Agent Swarm Check
    print("")
    log.info("DIAGNOSTIC: Autonomous Swarm Initialization")
    if check_agent_swarm():
        log.info("  Swarm Factory: ✅ OK")
    else:
        failure_count += 1
        log.error("  Swarm Factory: ❌ FAIL (Check dependencies)")

    print("\n" + "═" * 60)
    if failure_count == 0:
        print("🎉 ALL SYSTEMS OPERATIONAL — READY FOR SCALE")
    else:
        print(f"⚠️  {failure_count} ISSUES DETECTED — CHECK LOGS ABOVE")
    print("═" * 60 + "\n")

if __name__ == "__main__":
    run_diagnostics()
