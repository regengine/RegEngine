"""Intent parser for natural language swarm commands.

Parses @swarm commands from GitHub comments into structured intents.
Supports both simple keyword matching (fast, no LLM) and LLM-powered
natural language understanding (richer, slower).

Supported commands:
  @swarm solve this           → solve the issue
  @swarm analyze              → analyze without coding
  @swarm review PR #42        → review a pull request
  @swarm label                → auto-label the issue
  @swarm security audit       → run security scan
  @swarm help                 → show available commands
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("swarm.intent")


class SwarmCommand(Enum):
    """Recognized swarm commands."""
    SOLVE = "solve"
    ANALYZE = "analyze"
    REVIEW = "review"
    LABEL = "label"
    SECURITY_AUDIT = "security_audit"
    TROUBLESHOOT = "troubleshoot"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class SwarmIntent:
    """Parsed intent from a @swarm comment."""
    command: SwarmCommand
    raw_comment: str
    target_issue: Optional[int] = None
    target_pr: Optional[int] = None
    extra_context: str = ""
    confidence: float = 1.0
    triggered_by: str = ""

    def to_dict(self) -> dict:
        return {
            "command": self.command.value,
            "target_issue": self.target_issue,
            "target_pr": self.target_pr,
            "extra_context": self.extra_context,
            "confidence": self.confidence,
            "triggered_by": self.triggered_by,
        }


# ── Authorized Users ──────────────────────────────────────

# Only these GitHub usernames can trigger the swarm.
# Add collaborators as needed. Prevents abuse on public repos.
AUTHORIZED_USERS = {
    "christophersellers",
    # Add trusted collaborators here
}


def is_authorized(username: str) -> bool:
    """Check if a GitHub user is authorized to trigger the swarm."""
    return username.lower() in {u.lower() for u in AUTHORIZED_USERS}


# ── Keyword Parser (fast, no LLM) ────────────────────────

# Pattern: @swarm <command> [extra context]
SWARM_PATTERN = re.compile(
    r"@swarm\s+(solve\s+this|solve|analyze|review|label|security\s+audit|audit|troubleshoot|help)"
    r"(?:\s+(.+))?",
    re.IGNORECASE | re.DOTALL,
)

# PR reference: #123 or PR #123
PR_PATTERN = re.compile(r"(?:PR\s*)?#(\d+)", re.IGNORECASE)

COMMAND_MAP = {
    "solve this": SwarmCommand.SOLVE,
    "solve": SwarmCommand.SOLVE,
    "analyze": SwarmCommand.ANALYZE,
    "review": SwarmCommand.REVIEW,
    "label": SwarmCommand.LABEL,
    "security audit": SwarmCommand.SECURITY_AUDIT,
    "audit": SwarmCommand.SECURITY_AUDIT,
    "troubleshoot": SwarmCommand.TROUBLESHOOT,
    "help": SwarmCommand.HELP,
}


def parse_intent(
    comment_body: str,
    issue_number: Optional[int] = None,
    comment_author: str = "",
) -> SwarmIntent:
    """Parse a @swarm comment into a structured intent.

    Uses fast keyword matching. Falls back to UNKNOWN if
    no recognized command is found.

    Args:
        comment_body: The full comment text
        issue_number: The issue/PR number the comment is on
        comment_author: GitHub username of the commenter

    Returns:
        SwarmIntent with parsed command and context
    """
    # Check for @swarm trigger
    if "@swarm" not in comment_body.lower():
        return SwarmIntent(
            command=SwarmCommand.UNKNOWN,
            raw_comment=comment_body,
            triggered_by=comment_author,
            confidence=0.0,
        )

    match = SWARM_PATTERN.search(comment_body)
    if not match:
        # Has @swarm but no recognized command
        return SwarmIntent(
            command=SwarmCommand.UNKNOWN,
            raw_comment=comment_body,
            target_issue=issue_number,
            triggered_by=comment_author,
            confidence=0.3,
            extra_context=comment_body,
        )

    cmd_text = match.group(1).lower().strip()
    extra = (match.group(2) or "").strip()

    command = COMMAND_MAP.get(cmd_text, SwarmCommand.UNKNOWN)

    # Extract PR reference if reviewing
    target_pr = None
    if command == SwarmCommand.REVIEW and extra:
        pr_match = PR_PATTERN.search(extra)
        if pr_match:
            target_pr = int(pr_match.group(1))

    return SwarmIntent(
        command=command,
        raw_comment=comment_body,
        target_issue=issue_number,
        target_pr=target_pr,
        extra_context=extra,
        confidence=1.0,
        triggered_by=comment_author,
    )


# ── Response Formatter ────────────────────────────────────

def format_swarm_response(
    intent: SwarmIntent,
    result: Dict[str, Any],
    error: Optional[str] = None,
) -> str:
    """Format a swarm result as a GitHub comment.

    Returns:
        Markdown-formatted comment body ready to post
    """
    if error:
        return (
            "## 🤖 Agent Swarm — Error\n\n"
            f"**Command:** `{intent.command.value}`\n"
            f"**Triggered by:** @{intent.triggered_by}\n\n"
            f"❌ **Error:** {error}\n\n"
            "---\n"
            "*Use `@swarm help` for available commands.*"
        )

    status = result.get("status", "unknown")
    status_emoji = {"completed": "✅", "completed_with_warnings": "⚠️", "failed": "❌"}.get(status, "❓")

    agents = result.get("agents_used", [])
    duration = result.get("duration_seconds", 0)
    iterations = result.get("iterations", 0)
    errors = result.get("errors", [])

    lines = [
        f"## 🤖 Agent Swarm — {status_emoji} {status.replace('_', ' ').title()}",
        "",
        f"**Command:** `@swarm {intent.command.value}`",
        f"**Triggered by:** @{intent.triggered_by}",
        "",
        "### Execution Summary",
        f"- **Agents:** {', '.join(agents)}",
        f"- **Iterations:** {iterations}",
        f"- **Duration:** {duration}s",
    ]

    # Plan summary
    plan = result.get("plan", {})
    if plan:
        steps = plan.get("plan", {}).get("steps", plan.get("steps", []))
        if steps:
            lines.append("")
            lines.append("### 📋 Plan")
            for step in steps[:5]:  # Cap at 5 for readability
                lines.append(f"1. {step.get('action', 'Unknown step')}")

    # Code output
    code = result.get("code", {})
    if code:
        files = code.get("files_written", [])
        if files:
            lines.append("")
            lines.append("### 💻 Code Changes")
            for f in files[:10]:
                lines.append(f"- `{f.get('path', '?')}` ({f.get('lines', '?')} lines, {f.get('action', '?')})")

    # Review
    review = result.get("review", {})
    if review:
        verdict = review.get("verdict", "unknown")
        score = review.get("score", 0)
        verdict_emoji = {"approve": "✅", "request_changes": "🔄", "reject": "❌"}.get(verdict, "❓")
        lines.append("")
        lines.append(f"### 🔍 Review: {verdict_emoji} {verdict} (score: {score:.0%})")

    # Tests
    tests = result.get("tests", {})
    if tests:
        test_count = tests.get("total_tests", 0)
        coverage = tests.get("coverage_estimate", "unknown")
        lines.append("")
        lines.append(f"### 🧪 Tests: {test_count} generated (est. coverage: {coverage})")

    # Errors
    if errors:
        lines.append("")
        lines.append("### ❌ Errors")
        for err in errors:
            lines.append(f"- {err}")

    lines.append("")
    lines.append("---")
    lines.append("*Powered by RegEngine Autonomous Agent Swarm v0.1.0*")

    return "\n".join(lines)


def format_help_response() -> str:
    """Format the help message for @swarm help."""
    return (
        "## 🤖 Agent Swarm — Available Commands\n\n"
        "| Command | Description |\n"
        "|---------|-------------|\n"
        "| `@swarm solve this` | Analyze + code + review + test a solution |\n"
        "| `@swarm analyze` | Analyze the issue without writing code |\n"
        "| `@swarm review PR #42` | Review a pull request |\n"
        "| `@swarm label` | Auto-label this issue |\n"
        "| `@swarm security audit` | Run a security scan |\n"
        "| `@swarm troubleshoot` | Analyze and heal CI/CD failures |\n"
        "| `@swarm help` | Show this help message |\n\n"
        "### How it works\n"
        "1. You comment `@swarm solve this` on any open issue\n"
        "2. The swarm dispatches 4 agents: Planner → Coder → Reviewer → Tester\n"
        "3. Agents iterate (up to 3 rounds) until the reviewer approves\n"
        "4. Results are posted back as a comment on this issue\n\n"
        "---\n"
        "*Powered by RegEngine Autonomous Agent Swarm v0.1.0*"
    )
