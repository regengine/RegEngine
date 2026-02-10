"""Base agent framework for the autonomous swarm.

Provides:
  - AgentMessage: typed message envelope for inter-agent communication
  - AgentMemory: JSON append-log for decision persistence
  - BaseAgent: abstract base with think/act/reflect lifecycle
"""

import abc
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from regengine.swarm.llm import BaseLLMClient, LLMClientFactory

logger = structlog.get_logger("swarm.agent")


# ── Message Types ─────────────────────────────────────────

class MessageType(Enum):
    """Types of messages that flow between agents."""
    TASK = "task"                    # New task assignment
    PLAN = "plan"                    # Structured plan from PlannerAgent
    CODE = "code"                    # Code output from CoderAgent
    REVIEW = "review"               # Review feedback from ReviewerAgent
    TEST_RESULT = "test_result"     # Test results from TesterAgent
    FEEDBACK = "feedback"           # Improvement request (triggers loop)
    HANDOFF = "handoff"             # Agent-to-agent handoff
    STATUS = "status"               # Status update
    ERROR = "error"                 # Error report


@dataclass
class AgentMessage:
    """Typed message envelope for inter-agent communication."""
    sender: str
    receiver: str
    message_type: MessageType
    content: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: Optional[str] = None
    iteration: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["message_type"] = self.message_type.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMessage":
        data["message_type"] = MessageType(data["message_type"])
        return cls(**data)


# ── Agent Memory ──────────────────────────────────────────

class AgentMemory:
    """Persistent memory via JSON append-log.

    Each agent maintains a `.swarm_memory/{agent_name}.jsonl` file
    that records all decisions, actions, and outcomes for learning.
    """

    def __init__(self, agent_name: str, base_dir: Optional[Path] = None):
        self.agent_name = agent_name
        self.base_dir = base_dir or Path.cwd() / ".swarm_memory"
        self.log_file = self.base_dir / f"{agent_name}.jsonl"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def record(self, event_type: str, data: Dict[str, Any]) -> None:
        """Append a structured event to the agent's memory log."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": self.agent_name,
            "event": event_type,
            "data": data,
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def recall(self, event_type: Optional[str] = None, limit: int = 10) -> List[dict]:
        """Read recent events from memory, optionally filtered by type."""
        if not self.log_file.exists():
            return []

        events = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if event_type is None or entry.get("event") == event_type:
                        events.append(entry)
                except json.JSONDecodeError:
                    continue

        return events[-limit:]

    def clear(self) -> None:
        """Clear all memory for this agent."""
        if self.log_file.exists():
            self.log_file.unlink()


# ── Base Agent ────────────────────────────────────────────

class BaseAgent(abc.ABC):
    """Abstract base for all autonomous agents.

    Lifecycle: think → act → reflect
      - think(): Use LLM to reason about the task and produce a plan
      - act(): Execute the plan (write files, make API calls, etc.)
      - reflect(): Self-evaluate the result and decide next steps

    Subclasses must implement all three methods.
    """

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        llm_client: Optional[BaseLLMClient] = None,
        memory_dir: Optional[Path] = None,
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.llm = llm_client or LLMClientFactory.create()
        self.memory = AgentMemory(name, base_dir=memory_dir)
        self.log = logger.bind(agent=name, role=role)

    @abc.abstractmethod
    def think(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Reason about the task using the LLM. Returns a structured plan."""

    @abc.abstractmethod
    def act(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the plan. Returns structured results."""

    @abc.abstractmethod
    def reflect(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Self-evaluate results. Returns assessment with pass/fail + feedback."""

    def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Full lifecycle: think → act → reflect with timing and memory."""
        start = time.perf_counter()
        self.log.info("agent_started", task=task[:100])
        self.memory.record("task_received", {"task": task})

        # Think
        self.log.info("thinking")
        plan = self.think(task, context)
        self.memory.record("plan_created", plan)

        # Act
        self.log.info("acting")
        result = self.act(plan)
        self.memory.record("action_completed", result)

        # Reflect
        self.log.info("reflecting")
        assessment = self.reflect(result)
        self.memory.record("reflection", assessment)

        duration = time.perf_counter() - start
        self.log.info("agent_completed", duration=f"{duration:.2f}s", status=assessment.get("status"))

        return {
            "agent": self.name,
            "role": self.role,
            "task": task,
            "plan": plan,
            "result": result,
            "assessment": assessment,
            "duration_seconds": round(duration, 2),
        }

    def _call_llm(self, prompt: str, context_label: str = "") -> str:
        """Convenience method to call the LLM with structured logging."""
        self.log.info("llm_call", context=context_label, model=self.llm.model)
        try:
            response = self.llm.generate(prompt, self.system_prompt)
            self.log.info("llm_response", length=len(response), context=context_label)
            return response
        except Exception as e:
            self.log.error("llm_call_failed", error=str(e), context=context_label)
            raise

    def _call_llm_json(self, prompt: str, context_label: str = "") -> dict:
        """Call LLM and parse response as JSON with auto-retry."""
        self.log.info("llm_json_call", context=context_label, model=self.llm.model)
        try:
            response = self.llm.generate_json(prompt, self.system_prompt)
            self.log.info("llm_json_response", keys=list(response.keys()), context=context_label)
            return response
        except Exception as e:
            self.log.error("llm_json_failed", error=str(e), context=context_label)
            return {"error": str(e)}
