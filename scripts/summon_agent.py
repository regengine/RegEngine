#!/usr/bin/env python3
"""RegEngine agent prompt helper.

Discovers the supported editor-agent specs in .github/agents and prints a
role-specific prompt for a scoped engineering task.

Usage:
    python3 scripts/summon_agent.py --role planner
    python3 scripts/summon_agent.py --role security_review --task "Audit services/shared/auth.py"
    python3 scripts/summon_agent.py --list
    python3 scripts/summon_agent.py --role implementer --output json
"""

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = REPO_ROOT / ".github" / "agents"
ROOT_AGENT_GUIDE = REPO_ROOT / "AGENTS.md"
OPERATING_MODEL = REPO_ROOT / "docs" / "engineering" / "AGENT_OPERATING_MODEL.md"

SUPPORTED_AGENT_SPECS: Mapping[str, str] = {
    "planner": "regengine-planner.agent.md",
    "implementer": "regengine-implementer.agent.md",
    "security_review": "regengine-security-review.agent.md",
}
_REQUIRED_FRONTMATTER = ("name", "description", "tools")


@dataclass(frozen=True)
class AgentDefinition:
    """A supported agent role discovered from .github/agents."""

    key: str
    label: str
    path: Path


class AgentSpecError(RuntimeError):
    """Raised when the supported agent specs drift from the small-scale model."""


def _slug_to_role(slug: str) -> str:
    """Normalize a checked-in agent filename into a stable CLI role."""
    slug = slug.removeprefix("regengine-").removesuffix(".agent")
    return re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")


def _frontmatter_value(text: str, key: str) -> str | None:
    """Return a simple scalar value from YAML front matter."""
    if not text.startswith("---"):
        return None

    end = text.find("\n---", 3)
    if end == -1:
        return None

    frontmatter = text[3:end]
    match = re.search(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", frontmatter, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip().strip("'\"")
    return value or None


def agent_spec_errors(agents_dir: Path = AGENTS_DIR) -> list[str]:
    """Return validation errors for the supported agent specs."""
    if not agents_dir.exists():
        return [f"Missing agent specs directory: {agents_dir}"]

    expected_files = set(SUPPORTED_AGENT_SPECS.values())
    present_files = {path.name for path in agents_dir.glob("*.agent.md")}

    errors: list[str] = []
    for filename in sorted(expected_files - present_files):
        errors.append(f"Missing supported agent spec: {filename}")
    for filename in sorted(present_files - expected_files):
        errors.append(f"Unexpected agent spec: {filename}")

    for role, filename in SUPPORTED_AGENT_SPECS.items():
        path = agents_dir / filename
        if not path.exists():
            continue

        text = path.read_text(encoding="utf-8")
        frontmatter_end = text.find("\n---", 3) if text.startswith("---") else -1
        if frontmatter_end == -1:
            errors.append(f"{filename} must start with YAML front matter")
            continue

        for key in _REQUIRED_FRONTMATTER:
            if not _frontmatter_value(text, key):
                errors.append(f"{filename} missing front matter field: {key}")

        body = text[frontmatter_end + len("\n---") :].strip()
        if not body:
            errors.append(f"{filename} has no role instructions")

        expected_role = _slug_to_role(filename.removesuffix(".md"))
        if role != expected_role:
            errors.append(f"{filename} maps to {expected_role!r}, expected {role!r}")

    return errors


def validate_supported_agent_specs(agents_dir: Path = AGENTS_DIR) -> None:
    """Validate the checked-in agent specs before exposing them."""
    errors = agent_spec_errors(agents_dir)
    if errors:
        raise AgentSpecError("\n".join(errors))


def discover_agents() -> dict[str, AgentDefinition]:
    """Discover the supported checked-in GitHub agent specs."""
    validate_supported_agent_specs()
    agents: dict[str, AgentDefinition] = {}

    for key, filename in SUPPORTED_AGENT_SPECS.items():
        md_file = AGENTS_DIR / filename
        text = md_file.read_text(encoding="utf-8")
        label = _frontmatter_value(text, "name") or key.replace("_", " ").title()
        agents[key] = AgentDefinition(key=key, label=label, path=md_file)

    return agents


def load_file(path: Path, *, required: bool = True) -> str:
    """Read a file and return its contents."""
    if not path.exists():
        if not required:
            return ""
        print(f"ERROR: Missing file: {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def build_prompt(
    role: str,
    agents: dict[str, AgentDefinition],
    task: str | None = None,
    output_format: str = "text",
) -> str:
    """Assemble context for the given supported role."""
    role_info = agents[role]
    role_text = load_file(role_info.path)
    root_guide = load_file(ROOT_AGENT_GUIDE)
    operating_model = load_file(OPERATING_MODEL, required=False)

    sections = [
        f"## Agent Role - {role_info.label}",
        f"You are operating as {role_info.label} for RegEngine.",
        f"Source: {role_info.path.relative_to(REPO_ROOT)}",
    ]

    if task:
        sections.append(f"---\n\n### Assigned Task\n\n{task}")

    sections.append(f"---\n\n### Root Agent Guide\n\n{root_guide}")

    if operating_model:
        sections.append(f"---\n\n### Operating Model\n\n{operating_model}")

    sections.append(f"---\n\n### Role Instructions\n\n{role_text}")

    if output_format == "json":
        sections.append(
            "---\n\n### Output Format\n\n"
            "Return a valid JSON object with summary, files, tests, blocked_tests, production_spine_impact, and risks."
        )

    sections.append(
        "---\n\nBefore acting, verify referenced files and commands exist in this checkout. "
        "Call out stale assumptions before using them."
    )

    return "\n\n".join(sections)


def list_roles(agents: dict[str, AgentDefinition]) -> None:
    """Print available supported roles."""
    print("RegEngine Agent Helper - Supported Roles\n")
    print(f"   Agent specs: {AGENTS_DIR}\n")

    for key, info in agents.items():
        print(f"  --role {key:<18}  {info.label}")

    print(f"\n   {len(agents)} role(s) discovered.")
    print("   Supported roles are defined only by .github/agents/*.agent.md.\n")


def main() -> None:
    try:
        agents = discover_agents()
    except AgentSpecError as exc:
        print("ERROR: Supported agent specs are invalid:", file=sys.stderr)
        for line in str(exc).splitlines():
            print(f"  - {line}", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Summon a RegEngine agent prompt.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 scripts/summon_agent.py --role planner\n"
            "  python3 scripts/summon_agent.py --role security_review --task 'Audit services/shared/auth.py'\n"
            "  python3 scripts/summon_agent.py --list\n"
        ),
    )
    parser.add_argument("--role", choices=sorted(agents.keys()), help="Agent role to summon")
    parser.add_argument("--list", action="store_true", help="List available roles and exit")
    parser.add_argument("--task", metavar="DESC", help="Task description for the agent")
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    if args.list:
        list_roles(agents)
        return

    if not args.role:
        parser.print_help()
        sys.exit(1)

    prompt = build_prompt(args.role, agents, task=args.task, output_format=args.output)
    print(prompt)


if __name__ == "__main__":
    main()
