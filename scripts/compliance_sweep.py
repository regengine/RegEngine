#!/usr/bin/env python3
"""
RegEngine legacy compliance sweep.

This script drives the legacy autonomous swarm runtime and is disabled by
default. Use scoped agent tasks from scripts/summon_agent.py for normal work.
"""

import os
import sys
import structlog
from regengine.swarm.coordinator import AgentSwarm, LEGACY_SWARM_ENV, legacy_swarm_enabled

log = structlog.get_logger("compliance-sweep")

SERVICES = [
    "admin", "compliance", "graph", "ingestion",
    "nlp", "scheduler"
]

async def roll_out_compliance(standard: str = "FSMA-204"):
    """Dispatch the swarm to roll out compliance headers to all services."""
    if not legacy_swarm_enabled():
        raise RuntimeError(
            "Legacy compliance sweep is disabled by default. "
            f"Set {LEGACY_SWARM_ENV}=1 only for an explicitly approved legacy run."
        )

    swarm = AgentSwarm()
    os.environ["REGENGINE_CI_AUTO_FIX"] = "true"
    
    header_spec = {
        "FSMA-204": "X-FSMA-204-Traceability: true",
        "Finance": "X-RegEngine-Financial-Audit: active"
    }.get(standard, "X-RegEngine-Compliance: standard")

    log.info("compliance_rollout_started", standard=standard, fleet_size=len(SERVICES))

    tasks = []
    for service in SERVICES:
        task = (
            f"Proactive Compliance Rollout: {standard}\n"
            f"Service: services/{service}\n"
            f"Requirement: Ensure all API responses include the compliance header `{header_spec}`. "
            f"Add this to the FastAPI main.py middleware or global response headers."
        )
        tasks.append(task)

    log.info("launching_fleet_sweep", task_count=len(tasks))
    results = await swarm.sweep(tasks, concurrency=10)
    
    for i, result in enumerate(results):
        service = SERVICES[i]
        log.info("service_processed", service=service, status=result.status)

if __name__ == "__main__":
    import asyncio
    standard = sys.argv[1] if len(sys.argv) > 1 else "FSMA-204"
    asyncio.run(roll_out_compliance(standard))
