"""RegEngine legacy autonomous agent swarm.

This package is retained for compatibility with older tooling. Autonomous
execution is disabled by default; set REGENGINE_ENABLE_LEGACY_SWARM=1 only for
an explicitly approved legacy run.

The supported small-scale operating model uses checked-in editor-agent specs
and prompt generation:

Usage:
    python -m regengine.swarm status
    python3 scripts/summon_agent.py --list
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
