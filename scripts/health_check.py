#!/usr/bin/env python3
"""
🧬 RegEngine Founder's Health Check
A unified diagnostic tool for solo builders to verify the entire stack.
Checks: Ports, Database connectivity, Redis (Distributed Rate Limiting), and the supported agent helper.
"""

import importlib.util
import os
import socket
from pathlib import Path
import structlog

# Configure pretty logging for the founder
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger("health-check")

REPO_ROOT = Path(__file__).resolve().parents[1]

SERVICES = {
    "Gateway": 80,
    "Admin API": 8400,
    "Ingestion Service": 8002,
    "Graph Service": 8200,
    "Compliance API": 8500,
    "NLP Service": 8001,
    "Scheduler": 8600,
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

def check_agent_helper() -> bool:
    """Verify the supported small-scale agent helper is present."""
    helper = REPO_ROOT / "scripts" / "summon_agent.py"
    if not helper.exists():
        return False

    try:
        spec = importlib.util.spec_from_file_location("summon_agent", helper)
        if spec is None or spec.loader is None:
            return False
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.validate_supported_agent_specs(REPO_ROOT / ".github" / "agents")
    except Exception:
        return False

    return True

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

    # 3. Supported Agent Helper Check
    print("")
    log.info("DIAGNOSTIC: Supported Agent Helper")
    if check_agent_helper():
        log.info("  summon_agent.py + role specs: ✅ OK")
    else:
        failure_count += 1
        log.error("  summon_agent.py + role specs: ❌ FAIL (Check .github/agents)")

    print("\n" + "═" * 60)
    if failure_count == 0:
        print("🎉 ALL SYSTEMS OPERATIONAL — READY FOR SCALE")
    else:
        print(f"⚠️  {failure_count} ISSUES DETECTED — CHECK LOGS ABOVE")
    print("═" * 60 + "\n")

if __name__ == "__main__":
    run_diagnostics()
