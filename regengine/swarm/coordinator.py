"""Agent Swarm Coordinator — orchestrates multi-agent chains with feedback loops.

The coordinator manages:
  - Agent registry and lifecycle
  - In-process message bus (deque-backed)
  - Sequential chain execution (plan → code → review → test)
  - Feedback loops (review → recode, max 3 iterations)
  - Structured final output per .agent/protocols/output_schema.md
"""

import asyncio
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from regengine.swarm.base import AgentMessage, BaseAgent, MessageType
from regengine.swarm.agents import PlannerAgent, CoderAgent, ReviewerAgent, TesterAgent, CIResilienceAgent, SecurityAgent, JanitorAgent
from regengine.swarm.llm import BaseLLMClient, LLMClientFactory

logger = structlog.get_logger("swarm.coordinator")

LEGACY_SWARM_ENV = "REGENGINE_ENABLE_LEGACY_SWARM"
_TRUE_VALUES = {"1", "true", "yes", "on"}


class LegacySwarmDisabledError(RuntimeError):
    """Raised when legacy autonomous swarm execution has not been opted into."""


def legacy_swarm_enabled() -> bool:
    """Return whether the legacy autonomous swarm runtime is explicitly enabled."""
    return os.getenv(LEGACY_SWARM_ENV, "").strip().lower() in _TRUE_VALUES


@dataclass
class SwarmResult:
    """Final structured output from a swarm execution."""
    task: str
    status: str  # completed | completed_with_warnings | failed
    agents_used: List[str]
    iterations: int
    duration_seconds: float
    plan: Optional[Dict[str, Any]] = None
    code: Optional[Dict[str, Any]] = None
    review: Optional[Dict[str, Any]] = None
    tests: Optional[Dict[str, Any]] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "status": self.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents_used": self.agents_used,
            "iterations": self.iterations,
            "duration_seconds": self.duration_seconds,
            "plan": self.plan,
            "code": self.code,
            "review": self.review,
            "tests": self.tests,
            "message_count": len(self.messages),
            "errors": self.errors,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


class AgentSwarm:
    """Coordinates multiple agents to solve tasks through chained execution.

    Usage:
        swarm = AgentSwarm()
        result = swarm.solve("Add rate limiting to /api/ingest")
        print(result.to_json())
    """

    MAX_FEEDBACK_ITERATIONS = 3

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        max_iterations: int = 3,
    ):
        if not legacy_swarm_enabled():
            raise LegacySwarmDisabledError(
                "Legacy autonomous swarm execution is disabled by default. "
                f"Set {LEGACY_SWARM_ENV}=1 only for an explicitly approved legacy run; "
                "use scripts/summon_agent.py for the supported small-scale operating model."
            )

        self.llm = llm_client or LLMClientFactory.create()
        self.max_iterations = max_iterations
        self.message_bus: deque[AgentMessage] = deque(maxlen=1000)
        self.log = logger.bind(component="coordinator")

        # Initialize agents with shared LLM client
        self.planner = PlannerAgent(llm_client=self.llm)
        self.coder = CoderAgent(llm_client=self.llm)
        self.reviewer = ReviewerAgent(llm_client=self.llm)
        self.tester = TesterAgent(llm_client=self.llm)
        self.sre = CIResilienceAgent(llm_client=self.llm)
        self.security = SecurityAgent(llm_client=self.llm)
        self.janitor = JanitorAgent(llm_client=self.llm)

        self.agents: Dict[str, BaseAgent] = {
            "planner": self.planner,
            "coder": self.coder,
            "reviewer": self.reviewer,
            "tester": self.tester,
            "sre": self.sre,
            "security": self.security,
            "janitor": self.janitor,
        }

    def _post_message(self, msg: AgentMessage) -> None:
        """Post a message to the bus."""
        self.message_bus.append(msg)
        self.log.info(
            "message_posted",
            sender=msg.sender,
            receiver=msg.receiver,
            type=msg.message_type.value,
        )

    def _get_messages_for(self, agent_name: str) -> List[AgentMessage]:
        """Get all messages addressed to a specific agent."""
        return [m for m in self.message_bus if m.receiver == agent_name]

    async def _create_auto_fix_pr(self, task: str, coder_output: Dict[str, Any]):
        """Helper to create a GitHub PR for autonomous CI fixes."""
        try:
            from regengine.swarm.github_integration import GitHubClient
            import subprocess

            gh = GitHubClient()
            branch_name = f"auto-fix/{int(time.time())}"
            
            # Use git CLI for local operations (CI environment has git)
            subprocess.run(["git", "config", "user.name", "RegEngine Bot"], check=True)
            subprocess.run(["git", "config", "user.email", "bot@regengine.co"], check=True)
            subprocess.run(["git", "checkout", "-b", branch_name], check=True)
            
            # Assuming coder_output contains file changes that need to be staged
            # This part might need more specific logic based on coder_output structure
            # For now, a simple 'git add .'
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", f"🤖 Autonomous Fix: {task[:50]}"], check=True)
            subprocess.run(["git", "push", "origin", branch_name], check=True)

            pr_body = (
                f"## 🤖 Autonomous CI Self-Healing\n\n"
                f"**Task:** {task}\n"
                f"**Status:** completed\n" # Always completed if this is called
                f"**Agents Used:** PlannerAgent, CoderAgent, ReviewerAgent, TesterAgent\n\n" # Simplified for now
                f"### Code Changes\n"
                f"```json\n{json.dumps(coder_output.get('files_written', []), indent=2)}\n```\n"
            )
            
            gh.create_pr(
                title=f"🤖 Fix: {task[:50]}",
                body=pr_body,
                head=branch_name,
                labels=["agent:self-healing"]
            )
            self.log.info("ci_pr_created", branch=branch_name)
        except Exception as e:
            self.log.error("ci_auto_fix_failed", error=str(e))
            raise # Re-raise to be caught by the solve method's error handling

    async def troubleshoot(self, log_snippet: str, context: Optional[Dict[str, Any]] = None) -> SwarmResult:
        """Execute the self-healing chain to fix CI failures.
        
        Chain: SRE (Analysis) → Planner → Coder → Reviewer
        """
        start = time.perf_counter()
        self.log.info("troubleshoot_started", logs=log_snippet[:100])
        
        agents_used = []
        errors = []
        
        # ── Step 1: Analyze ───────────────────────────────
        try:
            self.log.info("phase_started", phase="troubleshooting")
            sre_output = await self.sre.run(log_snippet, context)
            sre_result = sre_output.get("result", {})
            agents_used.append("CIResilienceAgent")
            
            analysis = sre_result.get("analysis", {})
            remediation = sre_result.get("remediation", {})
            
            task = f"Fix CI failure: {analysis.get('root_cause')}. Remediation: {remediation.get('immediate_fix')}"
            
            # Now call standard solve chain with this new specific task
            return await self.solve(task, context)
            
        except Exception as e:
            self.log.error("troubleshooting_failed", error=str(e))
            errors.append(f"CIResilienceAgent failed: {e}")
            return self._build_result(
                "Troubleshoot", "failed", agents_used, 0,
                time.perf_counter() - start, errors=errors,
            )

    async def sweep(self, tasks: List[str], context: Optional[Dict[str, Any]] = None, concurrency: int = 5) -> List[SwarmResult]:
        """Execute a batch sweep of multiple similar tasks in parallel.
        
        Optimizes for horizontal productivity by processing related tasks in a fleet.
        Uses asyncio.gather with concurrency control.
        """
        self.log.info("fleet_sweep_started", task_count=len(tasks), concurrency=concurrency)
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def wrapped_solve(task_item):
            async with semaphore:
                return await self.solve(task_item, context)

        results = await asyncio.gather(*[wrapped_solve(t) for t in tasks])
        return results

    async def solve(self, task: str, context: Optional[Dict[str, Any]] = None) -> SwarmResult:
        """Execute the full agent chain to solve a task.

        Chain: Planner → Coder → Reviewer → (feedback loop) → Tester

        Args:
            task: Natural language task description
            context: Optional additional context (file contents, constraints)

        Returns:
            SwarmResult with the aggregated output from all agents
        """
        start = time.perf_counter()
        self.log.info("swarm_started", task=task[:100])

        agents_used = []
        errors = []
        plan_result = None
        code_result = None
        review_result = None
        test_result = None
        iteration = 0

        # ── Step 1: Plan ──────────────────────────────────
        try:
            self.log.info("phase_started", phase="planning")
            plan_output = await self.planner.run(task, context)
            plan_result = plan_output.get("result", {})
            agents_used.append("PlannerAgent")

            self._post_message(AgentMessage(
                sender="PlannerAgent",
                receiver="CoderAgent",
                message_type=MessageType.PLAN,
                content=plan_result,
            ))
        except Exception as e:
            self.log.error("planning_failed", error=str(e))
            errors.append(f"PlannerAgent failed: {e}")
            return self._build_result(
                task, "failed", agents_used, 0,
                time.perf_counter() - start, errors=errors,
            )

        # ── Step 2: Code → Review → Feedback Loop ────────
        review_feedback = None
        for iteration in range(1, self.max_iterations + 1):
            self.log.info("iteration_started", iteration=iteration)

            # Code
            try:
                self.log.info("phase_started", phase="coding", iteration=iteration)
                code_context = {
                    "plan": plan_result.get("plan", plan_result),
                }
                if review_feedback:
                    code_context["review_feedback"] = review_feedback

                code_output = await self.coder.run(task, code_context)
                code_result = code_output.get("result", {})
                if "CoderAgent" not in agents_used:
                    agents_used.append("CoderAgent")

                self._post_message(AgentMessage(
                    sender="CoderAgent",
                    receiver="ReviewerAgent",
                    message_type=MessageType.CODE,
                    content=code_result,
                    iteration=iteration,
                ))
            except Exception as e:
                self.log.error("coding_failed", error=str(e), iteration=iteration)
                errors.append(f"CoderAgent failed (iteration {iteration}): {e}")
                break

            # Review
            try:
                self.log.info("phase_started", phase="reviewing", iteration=iteration)
                review_context = {
                    "code": json.dumps(code_result.get("files_written", []), indent=2),
                    "plan": plan_result,
                }
                review_output = await self.reviewer.run(task, review_context)
                review_result = review_output.get("result", {})
                if "ReviewerAgent" not in agents_used:
                    agents_used.append("ReviewerAgent")

                verdict = review_result.get("verdict", "unknown")
                self.log.info("review_verdict", verdict=verdict, iteration=iteration)

                # Check if we can proceed
                if verdict == "approve":
                    self.log.info("review_approved", iteration=iteration)
                    break
                elif verdict == "reject":
                    self.log.warning("review_rejected", iteration=iteration)
                    errors.append("ReviewerAgent rejected the code")
                    break
                else:
                    # request_changes — feed back to coder
                    if iteration < self.max_iterations:
                        review_feedback = json.dumps(review_result.get("review", {}), indent=2)
                        self._post_message(AgentMessage(
                            sender="ReviewerAgent",
                            receiver="CoderAgent",
                            message_type=MessageType.FEEDBACK,
                            content=review_result,
                            iteration=iteration,
                        ))
                        self.log.info("feedback_loop", iteration=iteration)
                    else:
                        self.log.warning("max_iterations_reached")
                        errors.append(f"Max feedback iterations ({self.max_iterations}) reached")

            except Exception as e:
                self.log.error("reviewing_failed", error=str(e), iteration=iteration)
                errors.append(f"ReviewerAgent failed (iteration {iteration}): {e}")
                break

        # ── Step 3: Test ──────────────────────────────────
        if code_result and not errors:
            try:
                self.log.info("phase_started", phase="testing")
                test_context = {
                    "code": json.dumps(code_result.get("files_written", []), indent=2),
                    "plan": plan_result,
                }
                test_output = await self.tester.run(task, test_context)
                test_result = test_output.get("result", {})
                agents_used.append("TesterAgent")
            except Exception as e:
                self.log.error("testing_failed", error=str(e))
                errors.append(f"TesterAgent failed: {e}")

        # ── Build Result ──────────────────────────────────
        duration = time.perf_counter() - start
        status = "failed" if errors else (
            "completed_with_warnings" if review_result and review_result.get("critical_issues") else "completed"
        )

        result = self._build_result(
            task, status, agents_used, iteration, duration,
            plan=plan_result, code=code_result,
            review=review_result, tests=test_result,
            errors=errors,
        )

        # ── Autonomous CI Auto-Fix ───────────────────────
        if os.getenv("REGENGINE_CI_AUTO_FIX") == "true" and status == "completed":
            self.log.info("ci_auto_fix_triggered")
            try:
                await self._create_auto_fix_pr(task, code_result)
            except Exception as e:
                self.log.error("ci_auto_fix_failed_final", error=str(e))
                result.errors.append(f"CI Auto-Fix failed: {e}")

        return result

    def _build_result(
        self,
        task: str,
        status: str,
        agents_used: List[str],
        iterations: int,
        duration: float,
        plan: Optional[Dict] = None,
        code: Optional[Dict] = None,
        review: Optional[Dict] = None,
        tests: Optional[Dict] = None,
        errors: Optional[List[str]] = None,
    ) -> SwarmResult:
        """Construct the final SwarmResult."""
        result = SwarmResult(
            task=task,
            status=status,
            agents_used=agents_used,
            iterations=iterations,
            duration_seconds=round(duration, 2),
            plan=plan,
            code=code,
            review=review,
            tests=tests,
            messages=[m.to_dict() for m in self.message_bus],
            errors=errors or [],
        )
        self.log.info(
            "swarm_completed",
            status=status,
            agents=len(agents_used),
            iterations=iterations,
            duration=f"{duration:.2f}s",
        )
        return result

    def status(self) -> Dict[str, Any]:
        """Return current swarm status."""
        return {
            "agents": {name: {"role": agent.role, "name": agent.name} for name, agent in self.agents.items()},
            "llm_provider": self.llm.model,
            "max_iterations": self.max_iterations,
            "message_bus_size": len(self.message_bus),
        }
