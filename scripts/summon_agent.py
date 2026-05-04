#!/usr/bin/env python3
"""RegEngine agent prompt helper.

Discovers the current editor-agent specs in .github/agents and the legacy
.agent/personas tree when it exists. The helper prints a role-specific prompt
that can be pasted into an agent runner or used for local planning.

Usage:
    python3 scripts/summon_agent.py --role planner
    python3 scripts/summon_agent.py --role security_review --task "Audit services/shared/auth.py"
    python3 scripts/summon_agent.py --list
    python3 scripts/summon_agent.py --role implementer --output json
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_PERSONAS_DIR = REPO_ROOT / ".agent" / "personas"
LEGACY_CONSTITUTION = REPO_ROOT / ".agent" / "CONSTITUTION.md"
GITHUB_AGENTS_DIR = REPO_ROOT / ".github" / "agents"
ROOT_AGENT_GUIDE = REPO_ROOT / "AGENTS.md"
OUTPUT_SCHEMA = REPO_ROOT / ".agent" / "protocols" / "output_schema.md"


@dataclass(frozen=True)
class AgentDefinition:
    """A promptable agent definition discovered from the repo."""

    key: str
    label: str
    path: Path
    source: str


def _slug_to_role(slug: str) -> str:
    """Normalize a file slug into a stable CLI role."""
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
    match = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", frontmatter, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip().strip("'\"")


def discover_personas() -> dict[str, AgentDefinition]:
    """Discover legacy personas and current GitHub agent specs."""
    personas: dict[str, AgentDefinition] = {}

    if LEGACY_PERSONAS_DIR.exists():
        for md_file in sorted(LEGACY_PERSONAS_DIR.glob("*.md")):
            key = _slug_to_role(md_file.stem)
            first_line = md_file.read_text(encoding="utf-8").split("\n", 1)[0]
            label = first_line.lstrip("# ").strip() if first_line.startswith("#") else key.replace("_", " ").title()
            personas[key] = AgentDefinition(
                key=key,
                label=label,
                path=md_file,
                source="legacy .agent/personas",
            )

    if GITHUB_AGENTS_DIR.exists():
        for md_file in sorted(GITHUB_AGENTS_DIR.glob("*.agent.md")):
            text = md_file.read_text(encoding="utf-8")
            key = _slug_to_role(md_file.name.removesuffix(".md"))
            label = _frontmatter_value(text, "name") or key.replace("_", " ").title()
            personas[key] = AgentDefinition(
                key=key,
                label=label,
                path=md_file,
                source=".github/agents",
            )

    return personas


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
    personas: dict[str, AgentDefinition],
    task: str | None = None,
    output_format: str = "text",
) -> str:
    """Assemble context for the given role."""
    role_info = personas[role]
    persona_text = load_file(role_info.path)
    root_guide = load_file(ROOT_AGENT_GUIDE, required=False)
    legacy_constitution = load_file(LEGACY_CONSTITUTION, required=False)

    sections = [
        f"## Agent Mode - {role_info.label}",
        f"You are operating as {role_info.label} for RegEngine.",
        f"Source: {role_info.path.relative_to(REPO_ROOT)}",
    ]

    if task:
        sections.append(f"---\n\n### Assigned Task\n\n{task}")

    if root_guide:
        sections.append(f"---\n\n### Root Agent Guide\n\n{root_guide}")

    if legacy_constitution:
        sections.append(f"---\n\n### Legacy Swarm Constitution\n\n{legacy_constitution}")

    sections.append(f"---\n\n### Role Instructions\n\n{persona_text}")

    if output_format == "json":
        schema_text = load_file(OUTPUT_SCHEMA, required=False)
        if schema_text:
            sections.append(f"---\n\n### Output Schema\n\n{schema_text}")
        else:
            sections.append("---\n\n### Output Format\n\nReturn a valid JSON object with summary, findings, files, tests, and risks.")

    sections.append(
        "---\n\nBegin by verifying that referenced files and commands exist in this checkout. "
        "Call out stale assumptions before acting on them."
    )

    return "\n\n".join(sections)


def list_roles(personas: dict[str, AgentDefinition]) -> None:
    """Print available roles with dynamic discovery."""
    print("RegEngine Agent Helper - Available Agents\n")
    print(f"   GitHub agents: {GITHUB_AGENTS_DIR}")
    print(f"   Legacy personas: {LEGACY_PERSONAS_DIR}\n")

    for key, info in personas.items():
        print(f"  --role {key:<18}  {info.label} ({info.source})")

    print(f"\n   {len(personas)} agent(s) discovered.")
    print("   For chained execution, use python3 -m regengine.swarm when its LLM configuration is available.\n")


def main() -> None:
    personas = discover_personas()

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
    parser.add_argument("--role", choices=sorted(personas.keys()), help="Agent role to summon")
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
        list_roles(personas)
        return

    if not args.role:
        parser.print_help()
        sys.exit(1)

    prompt = build_prompt(args.role, personas, task=args.task, output_format=args.output)
    print(prompt)


if __name__ == "__main__":
    main()
