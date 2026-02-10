#!/usr/bin/env python3
"""Fractal Agent Swarm — Summoning Script.

Generates a context-rich prompt for activating a specific agent persona.
Usage:
    python scripts/summon_agent.py --role fsma
    python scripts/summon_agent.py --role pcos
    python scripts/summon_agent.py --role security
    python scripts/summon_agent.py --role infra
    python scripts/summon_agent.py --list
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PERSONAS_DIR = REPO_ROOT / ".agent" / "personas"
CONSTITUTION = REPO_ROOT / ".agent" / "CONSTITUTION.md"

AVAILABLE_ROLES = {
    "fsma": {
        "file": "fsma.md",
        "label": "Bot-FSMA (FDA FSMA 204 Specialist)",
    },
    "pcos": {
        "file": "pcos.md",
        "label": "Bot-PCOS (Union Payroll & Fringe Benefits)",
    },
    "security": {
        "file": "security.md",
        "label": "Bot-Security (The CISO)",
    },
    "infra": {
        "file": "infra.md",
        "label": "Bot-Infra (The SRE)",
    },
    "ui": {
        "file": "ui.md",
        "label": "Bot-UI (Design System Guardian)",
    },
}


def load_file(path: Path) -> str:
    """Read a file and return its contents."""
    if not path.exists():
        print(f"ERROR: Missing file: {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def build_prompt(role: str) -> str:
    """Assemble the full context prompt for the given role."""
    role_info = AVAILABLE_ROLES[role]
    persona_text = load_file(PERSONAS_DIR / role_info["file"])
    constitution_text = load_file(CONSTITUTION)

    return f"""## 🔄 AGENT MODE SWITCH — {role_info['label']}

You are now operating as **{role_info['label']}** within the RegEngine Fractal Agent Swarm.

---

### YOUR PERSONA

{persona_text}

---

### GOVERNING CONSTITUTION (Immutable Rules)

{constitution_text}

---

**You are now in character. All responses must align with your persona directives and the constitution above. Begin by reviewing the files listed in your Context Priming section.**
"""


def list_roles() -> None:
    """Print available roles."""
    print("Available agent roles:\n")
    for key, info in AVAILABLE_ROLES.items():
        marker = PERSONAS_DIR / info["file"]
        status = "✅" if marker.exists() else "❌"
        print(f"  {status}  --role {key:<10}  {info['label']}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summon a RegEngine agent persona.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python scripts/summon_agent.py --role fsma",
    )
    parser.add_argument(
        "--role",
        choices=list(AVAILABLE_ROLES.keys()),
        help="Agent role to summon",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available roles and exit",
    )

    args = parser.parse_args()

    if args.list:
        list_roles()
        return

    if not args.role:
        parser.print_help()
        sys.exit(1)

    prompt = build_prompt(args.role)
    print(prompt)


if __name__ == "__main__":
    main()
