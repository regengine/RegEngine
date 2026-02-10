#!/usr/bin/env python3
"""Fractal Agent Swarm — Summoning Script.

Lightweight wrapper around swarm_orchestrator.py for quick single-agent prompts.
For chain execution and sweeps, use swarm_orchestrator.py directly.

Usage:
    python scripts/summon_agent.py --role fsma
    python scripts/summon_agent.py --role security --task "Audit shared/auth.py"
    python scripts/summon_agent.py --list
    python scripts/summon_agent.py --role fsma --output json
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PERSONAS_DIR = REPO_ROOT / ".agent" / "personas"
CONSTITUTION = REPO_ROOT / ".agent" / "CONSTITUTION.md"


def discover_personas() -> dict:
    """Dynamically discover all persona files in .agent/personas/."""
    personas = {}
    if not PERSONAS_DIR.exists():
        return personas

    for md_file in sorted(PERSONAS_DIR.glob("*.md")):
        key = md_file.stem  # e.g., "fsma", "security", "qa"
        # Read the first line to extract the label
        first_line = md_file.read_text(encoding="utf-8").split("\n")[0]
        label = first_line.lstrip("# ").strip() if first_line.startswith("#") else key.title()
        personas[key] = {
            "file": md_file.name,
            "label": label,
            "path": md_file,
        }

    return personas


def load_file(path: Path) -> str:
    """Read a file and return its contents."""
    if not path.exists():
        print(f"ERROR: Missing file: {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def build_prompt(role: str, personas: dict, task: str = None, output_format: str = "text") -> str:
    """Assemble the full context prompt for the given role."""
    role_info = personas[role]
    persona_text = load_file(role_info["path"])
    constitution_text = load_file(CONSTITUTION)

    sections = []
    sections.append(f"## 🔄 AGENT MODE SWITCH — {role_info['label']}")
    sections.append(f"\nYou are now operating as **{role_info['label']}** within the RegEngine Fractal Agent Swarm.")

    if task:
        sections.append(f"\n---\n\n### 🎯 ASSIGNED TASK\n\n{task}")

    sections.append(f"\n---\n\n### YOUR PERSONA\n\n{persona_text}")
    sections.append(f"\n---\n\n### GOVERNING CONSTITUTION (Immutable Rules)\n\n{constitution_text}")

    if output_format == "json":
        sections.append(
            "\n---\n\n### 📊 OUTPUT FORMAT\n\n"
            "Produce your output as a valid JSON object per `.agent/protocols/output_schema.md`.\n"
        )

    sections.append(
        "\n---\n\n**You are now in character. All responses must align with your persona "
        "directives and the constitution above. Begin by reviewing the files listed in your "
        "Context Priming section.**"
    )

    return "\n".join(sections)


def list_roles(personas: dict) -> None:
    """Print available roles with dynamic discovery."""
    print("🧬 RegEngine Fractal Agent Swarm — Available Agents\n")
    print(f"   Personas directory: {PERSONAS_DIR}\n")
    for key, info in personas.items():
        status = "✅" if info["path"].exists() else "❌"
        print(f"  {status}  --role {key:<14}  {info['label']}")
    print(f"\n   {len(personas)} persona(s) discovered.")
    print(f"   For chains and sweeps: python scripts/swarm_orchestrator.py --help\n")


def main() -> None:
    personas = discover_personas()

    parser = argparse.ArgumentParser(
        description="Summon a RegEngine agent persona.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/summon_agent.py --role fsma\n"
            "  python scripts/summon_agent.py --role security --task 'Audit auth module'\n"
            "  python scripts/summon_agent.py --list\n"
        ),
    )
    parser.add_argument("--role", choices=list(personas.keys()), help="Agent role to summon")
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
