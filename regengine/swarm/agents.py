"""Specialized agent implementations for the autonomous swarm.

Four agents form the core execution chain:
  PlannerAgent  → Breaks tasks into actionable steps
  CoderAgent    → Implements code based on plans
  ReviewerAgent → Reviews code for quality and security
  TesterAgent   → Generates and validates tests
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from regengine.swarm.base import BaseAgent

logger = structlog.get_logger("swarm.agents")


# ── Planner Agent ─────────────────────────────────────────

class PlannerAgent(BaseAgent):
    """Breaks tasks into structured, actionable implementation plans.

    Think: Analyze the task and decompose into ordered steps
    Act:   Produce a structured plan with file targets and acceptance criteria
    Reflect: Evaluate plan completeness and feasibility
    """

    SYSTEM_PROMPT = (
        "You are a Senior Software Architect and Tech Lead. "
        "Your job is to decompose coding tasks into clear, ordered implementation steps. "
        "Each step must specify: which files to modify/create, what changes to make, "
        "and acceptance criteria. Always consider security, testing, and backward compatibility.\n\n"
        "ALWAYS respond in valid JSON format with this structure:\n"
        '{"steps": [{"id": 1, "action": "...", "files": ["..."], "details": "...", '
        '"acceptance_criteria": "..."}], "risks": ["..."], "estimated_complexity": "low|medium|high"}'
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "PlannerAgent")
        kwargs.setdefault("role", "planner")
        kwargs.setdefault("system_prompt", self.SYSTEM_PROMPT)
        super().__init__(**kwargs)

    def think(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analyze the task and produce a decomposed plan."""
        prompt_parts = [f"TASK: {task}"]

        if context:
            if context.get("codebase_files"):
                prompt_parts.append(f"\nRELEVANT FILES:\n{json.dumps(context['codebase_files'], indent=2)}")
            if context.get("prior_feedback"):
                prompt_parts.append(f"\nFEEDBACK FROM PRIOR ITERATION:\n{context['prior_feedback']}")

        prompt_parts.append(
            "\nDecompose this task into ordered implementation steps. "
            "For each step, specify the files to modify, exact changes, and acceptance criteria."
        )

        return self._call_llm_json("\n".join(prompt_parts), "planning")

    def act(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """For PlannerAgent, the plan IS the action output."""
        steps = plan.get("steps", [])
        return {
            "plan": plan,
            "step_count": len(steps),
            "files_targeted": list({f for s in steps for f in s.get("files", [])}),
            "estimated_complexity": plan.get("estimated_complexity", "unknown"),
        }

    def reflect(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate plan quality."""
        plan = result.get("plan", {})
        steps = plan.get("steps", [])
        issues = []

        if not steps:
            issues.append("Plan has no steps")
        for step in steps:
            if not step.get("acceptance_criteria"):
                issues.append(f"Step {step.get('id', '?')} missing acceptance criteria")
            if not step.get("files"):
                issues.append(f"Step {step.get('id', '?')} has no target files")

        return {
            "status": "pass" if not issues else "needs_improvement",
            "issues": issues,
            "step_count": len(steps),
        }


# ── Coder Agent ───────────────────────────────────────────

class CoderAgent(BaseAgent):
    """Implements code based on structured plans.

    Think: Read the plan and relevant source files, decide implementation approach
    Act:   Generate code changes (stored as diffs or full file contents)
    Reflect: Verify code compiles/parses and follows conventions
    """

    SYSTEM_PROMPT = (
        "You are a Senior Software Engineer. You write clean, well-tested, production-quality code. "
        "Follow these rules:\n"
        "- Use type hints everywhere (Python)\n"
        "- Use structured logging (structlog), never print()\n"
        "- Parameterize all queries (SQL, Cypher)\n"
        "- Add docstrings to all public functions\n"
        "- Follow existing patterns in the codebase\n\n"
        "ALWAYS respond in valid JSON format with this structure:\n"
        '{"files": [{"path": "...", "action": "create|modify", "content": "...", '
        '"language": "python|typescript|..."}], "summary": "...", "dependencies_added": []}'
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "CoderAgent")
        kwargs.setdefault("role", "coder")
        kwargs.setdefault("system_prompt", self.SYSTEM_PROMPT)
        super().__init__(**kwargs)

    def think(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analyze the plan and prepare implementation approach."""
        prompt_parts = [f"TASK: {task}"]

        if context:
            if context.get("plan"):
                prompt_parts.append(f"\nPLAN:\n{json.dumps(context['plan'], indent=2)}")
            if context.get("existing_code"):
                prompt_parts.append(f"\nEXISTING CODE:\n{context['existing_code']}")
            if context.get("review_feedback"):
                prompt_parts.append(f"\nREVIEW FEEDBACK (fix these issues):\n{context['review_feedback']}")

        prompt_parts.append("\nImplement the code changes described above. Return the complete file contents.")

        return self._call_llm_json("\n".join(prompt_parts), "coding")

    def act(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Write generated code to disk (or return for review)."""
        files = plan.get("files", [])
        written = []

        for file_spec in files:
            path = file_spec.get("path", "")
            content = file_spec.get("content", "")
            action = file_spec.get("action", "create")

            # Safety: don't write outside the repo
            if ".." in path or path.startswith("/"):
                self.log.warning("unsafe_path_skipped", path=path)
                continue

            written.append({
                "path": path,
                "action": action,
                "lines": len(content.splitlines()),
                "content": content,
            })

        return {
            "files_written": written,
            "file_count": len(written),
            "summary": plan.get("summary", ""),
        }

    def reflect(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Basic quality checks on generated code."""
        files = result.get("files_written", [])
        issues = []

        for f in files:
            content = f.get("content", "")
            if "print(" in content and f.get("path", "").endswith(".py"):
                issues.append(f"{f['path']}: Uses print() instead of structlog")
            if "password" in content.lower() and "test" not in f.get("path", "").lower():
                issues.append(f"{f['path']}: Potential hardcoded credential")
            if not content.strip():
                issues.append(f"{f['path']}: Empty file generated")

        return {
            "status": "pass" if not issues else "needs_improvement",
            "issues": issues,
            "files_generated": len(files),
        }


# ── Reviewer Agent ────────────────────────────────────────

class ReviewerAgent(BaseAgent):
    """Reviews code for quality, security, and adherence to standards.

    Think: Analyze code against review criteria
    Act:   Produce structured review with line-level feedback
    Reflect: Assess review thoroughness
    """

    SYSTEM_PROMPT = (
        "You are a Senior Code Reviewer and Security Auditor for a regulatory compliance platform. "
        "Review code for:\n"
        "1. Security vulnerabilities (IDOR, injection, secrets, PII exposure)\n"
        "2. Tenant isolation (multi-tenant platform — every query MUST scope by tenant_id)\n"
        "3. Code quality (type hints, error handling, logging)\n"
        "4. Test coverage (are tests included?)\n"
        "5. Backward compatibility\n\n"
        "ALWAYS respond in valid JSON format with this structure:\n"
        '{"verdict": "approve|request_changes|reject", "score": 0.0-1.0, '
        '"issues": [{"severity": "critical|high|medium|low", "file": "...", '
        '"line": 0, "description": "...", "suggestion": "..."}], '
        '"strengths": ["..."], "summary": "..."}'
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "ReviewerAgent")
        kwargs.setdefault("role", "reviewer")
        kwargs.setdefault("system_prompt", self.SYSTEM_PROMPT)
        super().__init__(**kwargs)

    def think(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analyze code and produce review feedback."""
        prompt_parts = [f"REVIEW TASK: {task}"]

        if context:
            if context.get("code"):
                prompt_parts.append(f"\nCODE TO REVIEW:\n{context['code']}")
            if context.get("plan"):
                prompt_parts.append(f"\nORIGINAL PLAN:\n{json.dumps(context['plan'], indent=2)}")

        prompt_parts.append(
            "\nReview this code thoroughly. Focus on security, tenant isolation, "
            "code quality, and test coverage. Be specific with line-level feedback."
        )

        return self._call_llm_json("\n".join(prompt_parts), "reviewing")

    def act(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """The review output IS the action."""
        return {
            "review": plan,
            "verdict": plan.get("verdict", "unknown"),
            "score": plan.get("score", 0.0),
            "issue_count": len(plan.get("issues", [])),
            "critical_issues": [
                i for i in plan.get("issues", []) if i.get("severity") == "critical"
            ],
        }

    def reflect(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Assess review thoroughness."""
        review = result.get("review", {})
        issues = []

        if not review.get("issues") and not review.get("strengths"):
            issues.append("Review appears empty — no issues or strengths identified")
        if review.get("verdict") == "approve" and result.get("critical_issues"):
            issues.append("Approved despite critical issues — contradictory")

        return {
            "status": "pass" if not issues else "needs_improvement",
            "issues": issues,
            "verdict": result.get("verdict", "unknown"),
        }


# ── Tester Agent ──────────────────────────────────────────

class TesterAgent(BaseAgent):
    """Generates and validates test suites for code changes.

    Think: Analyze code to identify test scenarios (happy path, edge cases, security)
    Act:   Generate pytest test files
    Reflect: Verify test completeness against acceptance criteria
    """

    SYSTEM_PROMPT = (
        "You are a Senior QA Engineer specializing in Python test automation. "
        "Generate comprehensive pytest test suites covering:\n"
        "1. Happy path (successful execution)\n"
        "2. Edge cases (empty inputs, max limits, boundary values)\n"
        "3. Error conditions (invalid data, network failures)\n"
        "4. Security scenarios (missing auth, cross-tenant access, injection)\n\n"
        "Use pytest fixtures, mocks for external services, and descriptive test names.\n"
        "Test names must follow: test_<action>_<scenario>_<expected>\n\n"
        "ALWAYS respond in valid JSON format with this structure:\n"
        '{"test_files": [{"path": "...", "content": "...", "test_count": 0}], '
        '"scenarios_covered": ["..."], "coverage_estimate": "...", "summary": "..."}'
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("name", "TesterAgent")
        kwargs.setdefault("role", "tester")
        kwargs.setdefault("system_prompt", self.SYSTEM_PROMPT)
        super().__init__(**kwargs)

    def think(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Identify test scenarios for the given code."""
        prompt_parts = [f"TESTING TASK: {task}"]

        if context:
            if context.get("code"):
                prompt_parts.append(f"\nCODE TO TEST:\n{context['code']}")
            if context.get("plan"):
                prompt_parts.append(f"\nIMPLEMENTATION PLAN:\n{json.dumps(context['plan'], indent=2)}")
            if context.get("acceptance_criteria"):
                prompt_parts.append(f"\nACCEPTANCE CRITERIA:\n{context['acceptance_criteria']}")

        prompt_parts.append(
            "\nGenerate comprehensive pytest tests. Include happy path, edge cases, "
            "error conditions, and security scenarios. Use mocks for external services."
        )

        return self._call_llm_json("\n".join(prompt_parts), "test_generation")

    def act(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Return generated test files."""
        test_files = plan.get("test_files", [])

        return {
            "test_files": test_files,
            "test_file_count": len(test_files),
            "total_tests": sum(f.get("test_count", 0) for f in test_files),
            "scenarios_covered": plan.get("scenarios_covered", []),
            "coverage_estimate": plan.get("coverage_estimate", "unknown"),
        }

    def reflect(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Verify test quality and coverage."""
        issues = []

        if result.get("total_tests", 0) == 0:
            issues.append("No tests generated")
        if result.get("total_tests", 0) < 3:
            issues.append(f"Only {result.get('total_tests')} tests — need at least happy path, edge case, and security")

        scenarios = result.get("scenarios_covered", [])
        required = {"happy_path", "edge_case", "error_handling"}
        missing = required - {s.lower().replace(" ", "_") for s in scenarios}
        if missing:
            issues.append(f"Missing test scenarios: {missing}")

        return {
            "status": "pass" if not issues else "needs_improvement",
            "issues": issues,
            "test_count": result.get("total_tests", 0),
            "scenarios": scenarios,
        }
