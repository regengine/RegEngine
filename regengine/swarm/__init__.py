"""RegEngine Autonomous Agent Swarm.

Autonomous multi-agent framework that builds on the existing
LLMClientFactory to create agents that think, act, and iterate.

Two execution layers coexist:
  Layer 1: summon_agent.py / swarm_orchestrator.py — prompt generation for IDE use
  Layer 2: regengine.swarm (this package) — autonomous execution with LLM brains

Usage:
    python -m regengine.swarm run --task "Add rate limiting to /api/ingest"
    python -m regengine.swarm solve --issue 42 --repo owner/repo
    python -m regengine.swarm label --repo owner/repo --dry-run
    python -m regengine.swarm status
"""

from regengine.swarm.base import (
    AgentMessage,
    AgentMemory,
    BaseAgent,
    MessageType,
)
from regengine.swarm.agents import (
    PlannerAgent,
    CoderAgent,
    ReviewerAgent,
    TesterAgent,
)
from regengine.swarm.coordinator import AgentSwarm

__all__ = [
    "AgentMessage",
    "AgentMemory",
    "BaseAgent",
    "MessageType",
    "PlannerAgent",
    "CoderAgent",
    "ReviewerAgent",
    "TesterAgent",
    "AgentSwarm",
]

__version__ = "0.1.0"
