#!/usr/bin/env python3
"""Fractal Agent Swarm — Orchestration Engine.

Central orchestrator for multi-agent chains, sweeps, and output validation.

Usage:
    # List all agents and their status
    python scripts/swarm_orchestrator.py --roster

    # Run a single agent
    python scripts/swarm_orchestrator.py --summon fsma --task "Implement TLC endpoint"

    # Run an agent chain
    python scripts/swarm_orchestrator.py --chain fsma,security,qa --task "New feature"

    # Run a predefined sweep
    python scripts/swarm_orchestrator.py --sweep security

    # Validate agent output
    python scripts/swarm_orchestrator.py --validate output.json
"""

import argparse
import json
import sys
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any

try:
    from swarm_handoff_relay import SwarmHandoffRelay
    RELAY_AVAILABLE = True
except ImportError:
    RELAY_AVAILABLE = False

REPO_ROOT = Path(__file__).resolve().parents[1]
PERSONAS_DIR = REPO_ROOT / ".agent" / "personas"
PROTOCOLS_DIR = REPO_ROOT / ".agent" / "protocols"
CONSTITUTION = REPO_ROOT / ".agent" / "CONSTITUTION.md"


# ── Agent Registry ────────────────────────────────────────

class Squad(Enum):
    BUILDERS = "A"
    GUARDIANS = "B"


@dataclass
class AgentRole:
    """Metadata for a single agent persona."""
    key: str
    label: str
    squad: Squad
    persona_file: str
    description: str
    domain_paths: List[str]

    @property
    def file_path(self) -> Path:
        return PERSONAS_DIR / self.persona_file

    @property
    def exists(self) -> bool:
        return self.file_path.exists()


# Full roster — dynamically extended by scanning personas dir
AGENT_REGISTRY: Dict[str, AgentRole] = {
    "fsma": AgentRole(
        key="fsma",
        label="Bot-FSMA",
        squad=Squad.BUILDERS,
        persona_file="fsma.md",
        description="FDA FSMA 204 Specialist — Traceability & CTE/KDE integrity",
        domain_paths=["services/compliance/", "services/graph/app/routers/fsma/"],
    ),
    "pcos": AgentRole(
        key="pcos",
        label="Bot-PCOS",
        squad=Squad.BUILDERS,
        persona_file="pcos.md",
        description="Union Payroll & Fringe Benefits — Accounting-grade precision",
        domain_paths=["services/admin/app/pcos/", "industry_plugins/production_ca_la/"],
    ),
    "security": AgentRole(
        key="security",
        label="Bot-Security",
        squad=Squad.GUARDIANS,
        persona_file="security.md",
        description="The CISO — Adversarial security auditor & tenant isolation enforcer",
        domain_paths=["shared/security/", "shared/auth.py", "shared/middleware/"],
    ),
    "infra": AgentRole(
        key="infra",
        label="Bot-Infra",
        squad=Squad.GUARDIANS,
        persona_file="infra.md",
        description="The SRE — Deterministic deployments, IaC, container hygiene",
        domain_paths=["infra/terraform/", "docker-compose*.yml", ".github/workflows/"],
    ),
    "ui": AgentRole(
        key="ui",
        label="Bot-UI",
        squad=Squad.GUARDIANS,
        persona_file="ui.md",
        description="Design System Guardian — Visual consistency & accessibility",
        domain_paths=["frontend/src/components/", "frontend/tailwind.config.ts"],
    ),
    "energy": AgentRole(
        key="energy",
        label="Bot-Energy",
        squad=Squad.BUILDERS,
        persona_file="energy.md",
        description="NERC CIP / Energy Regulation Specialist",
        domain_paths=["services/energy-api/", "industry_plugins/energy/"],
    ),
    "healthcare": AgentRole(
        key="healthcare",
        label="Bot-Health",
        squad=Squad.BUILDERS,
        persona_file="healthcare.md",
        description="HIPAA / Healthcare Compliance Specialist",
        domain_paths=["services/healthcare/", "industry_plugins/healthcare/"],
    ),
    "aerospace": AgentRole(
        key="aerospace",
        label="Bot-Aero",
        squad=Squad.BUILDERS,
        persona_file="aerospace.md",
        description="AS9100D / Aerospace Quality Specialist",
        domain_paths=["services/aerospace/", "industry_plugins/aerospace/"],
    ),
    "legal": AgentRole(
        key="legal",
        label="Bot-Legal",
        squad=Squad.BUILDERS,
        persona_file="legal.md",
        description="FDA 510(k) & Regulatory Counsel",
        domain_paths=["docs/compliance/legal/", "services/compliance/app/legal/"],
    ),
    "finance": AgentRole(
        key="finance",
        label="Bot-Finance",
        squad=Squad.BUILDERS,
        persona_file="finance.md",
        description="ROI & Monetization Engine",
        domain_paths=["services/admin/app/pcos/", "services/compliance/app/pricing/"],
    ),
    "devops": AgentRole(
        key="devops",
        label="Bot-DevOps",
        squad=Squad.GUARDIANS,
        persona_file="devops.md",
        description="CI/CD & Reliability Guardian",
        domain_paths=[".github/workflows/", "scripts/release/"],
    ),
    "qa": AgentRole(
        key="qa",
        label="Bot-QA",
        squad=Squad.GUARDIANS,
        persona_file="qa.md",
        description="Quality Assurance — Cross-cutting test coverage & regression guard",
        domain_paths=["services/*/tests/", "tests/"],
    ),
}


# ── Predefined Sweeps ─────────────────────────────────────

SWEEP_DEFINITIONS = {
    "security": {
        "label": "🔒 Security Sweep",
        "chain": ["security"],
        "description": "Full security audit: secrets scan, IDOR review, RLS verification, PII leak check",
    },
    "ui-drift": {
        "label": "🎨 UI Drift Check",
        "chain": ["ui"],
        "description": "Scan for inline styles, hardcoded colors, missing design tokens, accessibility gaps",
    },
    "infra-health": {
        "label": "🏗️ Infrastructure Health",
        "chain": ["infra"],
        "description": "Verify Dockerfiles, health checks, pinned versions, resource limits",
    },
    "full-audit": {
        "label": "🔍 Full Platform Audit",
        "chain": ["security", "ui", "infra", "qa"],
        "description": "Complete platform audit across all Guardian agents",
    },
    "feature": {
        "label": "🚀 Feature Pipeline",
        "chain": ["security", "ui", "qa"],
        "description": "Standard review chain for new features (security → UI → QA)",
    },
}


# ── Agent Output ──────────────────────────────────────────

@dataclass
class AgentRisk:
    severity: str  # critical | high | medium | low
    description: str
    mitigation: Optional[str] = None


@dataclass
class AgentFileChange:
    path: str
    action: str  # created | modified | deleted
    lines_added: int = 0
    lines_removed: int = 0


@dataclass
class AgentTestResult:
    added: int = 0
    modified: int = 0
    all_passing: bool = True
    coverage_delta: Optional[str] = None


@dataclass
class AgentHandoff:
    to_agent: str
    priority: str  # critical | high | medium | low
    action_required: str


@dataclass
class AgentOutput:
    """Structured output conforming to .agent/protocols/output_schema.md"""
    agent: str
    task: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "completed"
    confidence: float = 1.0
    files_changed: List[AgentFileChange] = field(default_factory=list)
    tests: AgentTestResult = field(default_factory=AgentTestResult)
    risks: List[AgentRisk] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    handoff: Optional[AgentHandoff] = None

    def to_dict(self) -> dict:
        result = asdict(self)
        if self.handoff is None:
            result["handoff"] = None
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ── Prompt Builder ────────────────────────────────────────

def load_file(path: Path) -> str:
    """Read a file and return its contents."""
    if not path.exists():
        print(f"ERROR: Missing file: {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def build_prompt(
    role_key: str,
    task_description: Optional[str] = None,
    chain_context: Optional[List[dict]] = None,
    output_format: str = "text",
) -> str:
    """Assemble the full context prompt for the given role."""
    role = AGENT_REGISTRY[role_key]
    persona_text = load_file(role.file_path)
    constitution_text = load_file(CONSTITUTION)

    sections = []

    # Header
    sections.append(f"## 🔄 AGENT MODE SWITCH — {role.label}")
    sections.append(f"\nYou are now operating as **{role.label}** within the RegEngine Fractal Agent Swarm.")

    # Task (if provided)
    if task_description:
        sections.append(f"\n---\n\n### 🎯 ASSIGNED TASK\n\n{task_description}")

    # Chain context from prior agents
    if chain_context:
        sections.append("\n---\n\n### 📋 PRIOR AGENT CONTEXT (Chain Handoffs)\n")
        for i, ctx in enumerate(chain_context, 1):
            sections.append(f"#### Handoff #{i}: {ctx.get('agent', 'Unknown')}")
            sections.append(f"```json\n{json.dumps(ctx, indent=2)}\n```")

    # Persona
    sections.append(f"\n---\n\n### YOUR PERSONA\n\n{persona_text}")

    # Constitution
    sections.append(f"\n---\n\n### GOVERNING CONSTITUTION (Immutable Rules)\n\n{constitution_text}")

    # Output instructions
    if output_format == "json":
        sections.append(
            "\n---\n\n### 📊 OUTPUT FORMAT\n\n"
            "You MUST produce your output as a valid JSON object conforming to the Agent Output Schema "
            "defined in `.agent/protocols/output_schema.md`. Include all required fields.\n"
        )

    # Activation
    sections.append(
        "\n---\n\n**You are now in character. All responses must align with your persona "
        "directives and the constitution above. Begin by reviewing the files listed in your "
        "Context Priming section.**"
    )

    return "\n".join(sections)


# ── Output Validator ──────────────────────────────────────

VALID_STATUSES = {"completed", "completed_with_warnings", "blocked", "handoff", "failed"}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_ACTIONS = {"created", "modified", "deleted"}
VALID_AGENTS = {role.label for role in AGENT_REGISTRY.values()}


def validate_output(output: dict) -> List[str]:
    """Validate agent output against the schema. Returns list of errors."""
    errors = []

    # Required fields
    for field_name in ["agent", "task", "timestamp", "status", "confidence", "files_changed", "tests"]:
        if field_name not in output:
            errors.append(f"Missing required field: '{field_name}'")

    # Agent name
    if output.get("agent") not in VALID_AGENTS:
        errors.append(f"Invalid agent '{output.get('agent')}'. Must be one of: {VALID_AGENTS}")

    # Status
    if output.get("status") not in VALID_STATUSES:
        errors.append(f"Invalid status '{output.get('status')}'. Must be one of: {VALID_STATUSES}")

    # Confidence
    conf = output.get("confidence", 0)
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        errors.append(f"Confidence must be a number between 0.0 and 1.0, got: {conf}")

    # Status-specific validation
    status = output.get("status")
    if status == "blocked":
        risks = output.get("risks", [])
        if not any(r.get("severity") == "critical" for r in risks):
            errors.append("Status 'blocked' requires at least one risk with severity 'critical'")

    if status == "handoff" and not output.get("handoff"):
        errors.append("Status 'handoff' requires a 'handoff' object")

    if status == "completed" and output.get("handoff") is not None:
        errors.append("Status 'completed' should have 'handoff: null' (chain terminates)")

    # Tests
    tests = output.get("tests", {})
    if status == "completed" and not tests.get("all_passing", False):
        errors.append("Status 'completed' requires 'tests.all_passing' to be true")

    # File changes
    for fc in output.get("files_changed", []):
        if fc.get("action") not in VALID_ACTIONS:
            errors.append(f"Invalid file action '{fc.get('action')}' for {fc.get('path')}")

    # Low confidence auto-handoff warning
    if conf < 0.7 and status not in ("handoff", "blocked", "failed"):
        errors.append(f"Confidence {conf} < 0.7 should trigger automatic handoff to Bot-QA")

    return errors


def validate_output_file(filepath: str, relay_mode: bool = False) -> None:
    """Load and validate an agent output JSON file."""
    path = Path(filepath)
    if not path.exists():
        print(f"❌ File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    errors = validate_output(data)

    if errors:
        print(f"❌ Validation FAILED ({len(errors)} error(s)):\n")
        for i, err in enumerate(errors, 1):
            print(f"  {i}. {err}")
        sys.exit(1)
    else:
        print(f"✅ Output from {data.get('agent', '?')} is valid.")
        print(f"   Status: {data.get('status')}")
        print(f"   Confidence: {data.get('confidence')}")
        print(f"   Files changed: {len(data.get('files_changed', []))}")
        print(f"   Tests added: {data.get('tests', {}).get('added', 0)}")
        
        # Handoff Logic
        handoff = data.get("handoff")
        if handoff:
            print(f"   Handoff → {handoff.get('to_agent')} (Priority: {handoff.get('priority')})")
            
            # Emit to Redpanda if relay_mode is active
            if relay_mode and RELAY_AVAILABLE:
                relay = SwarmHandoffRelay()
                relay.emit_handoff(data)
                print("   📡 Handoff emitted to Redpanda")
        else:
            print("   Handoff: None (chain complete)")


# ── CLI Commands ──────────────────────────────────────────

def cmd_roster() -> None:
    """Print the full agent roster with status."""
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           🧬 RegEngine Fractal Agent Swarm — Roster        ║")
    print("╠══════════════════════════════════════════════════════════════╣")

    for squad in Squad:
        squad_label = "🔨 Squad A: Builders" if squad == Squad.BUILDERS else "🛡️ Squad B: Guardians"
        print(f"║  {squad_label:<57} ║")
        print("║  ─────────────────────────────────────────────────────────  ║")

        for role in AGENT_REGISTRY.values():
            if role.squad == squad:
                status = "✅" if role.exists else "❌"
                label = f"{status} {role.label}"
                desc = role.description[:42]
                print(f"║  {label:<18} {desc:<39} ║")

        print("║                                                              ║")

    print("╠══════════════════════════════════════════════════════════════╣")

    total = len(AGENT_REGISTRY)
    active = sum(1 for r in AGENT_REGISTRY.values() if r.exists)
    print(f"║  Agents: {active}/{total} active    Personas: .agent/personas/       ║")
    print(f"║  Constitution: .agent/CONSTITUTION.md                        ║")
    print(f"║  Protocols: .agent/protocols/                                ║")
    print("╚══════════════════════════════════════════════════════════════╝")


def cmd_summon(role: str, task: Optional[str], output_format: str) -> None:
    """Generate a context prompt for a specific agent."""
    if role not in AGENT_REGISTRY:
        print(f"ERROR: Unknown role '{role}'. Use --roster to see available roles.", file=sys.stderr)
        sys.exit(1)

    prompt = build_prompt(role, task_description=task, output_format=output_format)
    print(prompt)


def cmd_chain(roles_csv: str, task: Optional[str], output_format: str) -> None:
    """Generate chained prompts for multiple agents."""
    roles = [r.strip() for r in roles_csv.split(",")]

    for role in roles:
        if role not in AGENT_REGISTRY:
            print(f"ERROR: Unknown role '{role}'. Use --roster to see available roles.", file=sys.stderr)
            sys.exit(1)

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           🔗 Agent Chain Execution Plan                     ║")
    print("╠══════════════════════════════════════════════════════════════╣")

    for i, role in enumerate(roles, 1):
        agent = AGENT_REGISTRY[role]
        arrow = " → " if i < len(roles) else " ✓ "
        print(f"║  Step {i}: {agent.label:<20} [{agent.squad.value}]{arrow:<14} ║")

    print("╚══════════════════════════════════════════════════════════════╝\n")

    # Generate prompt for the first agent (others require prior output)
    chain_context: List[dict] = []
    prompt = build_prompt(
        roles[0],
        task_description=task,
        chain_context=chain_context if chain_context else None,
        output_format=output_format,
    )
    print(f"### 🔗 Chain Step 1/{len(roles)}: {AGENT_REGISTRY[roles[0]].label}\n")
    print(prompt)

    if len(roles) > 1:
        print("\n" + "═" * 60)
        print(f"📌 After {AGENT_REGISTRY[roles[0]].label} completes, feed its output as chain context")
        print(f"   to the next agent: {AGENT_REGISTRY[roles[1]].label}")
        print(f"   Remaining chain: {' → '.join(AGENT_REGISTRY[r].label for r in roles[1:])}")


def cmd_sweep(sweep_type: str, output_format: str) -> None:
    """Execute a predefined sweep pattern."""
    if sweep_type not in SWEEP_DEFINITIONS:
        print(f"ERROR: Unknown sweep '{sweep_type}'. Available sweeps:", file=sys.stderr)
        for key, sw in SWEEP_DEFINITIONS.items():
            print(f"  {key:<15}  {sw['label']}  —  {sw['description']}", file=sys.stderr)
        sys.exit(1)

    sweep = SWEEP_DEFINITIONS[sweep_type]
    chain_csv = ",".join(sweep["chain"])

    print(f"🔄 Executing sweep: {sweep['label']}\n")
    print(f"   {sweep['description']}\n")

    cmd_chain(chain_csv, task=sweep["description"], output_format=output_format)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RegEngine Fractal Agent Swarm — Orchestration Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/swarm_orchestrator.py --roster\n"
            "  python scripts/swarm_orchestrator.py --summon fsma --task 'Add TLC endpoint'\n"
            "  python scripts/swarm_orchestrator.py --chain fsma,security,qa --task 'New feature'\n"
            "  python scripts/swarm_orchestrator.py --sweep security\n"
            "  python scripts/swarm_orchestrator.py --validate output.json\n"
        ),
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--roster", action="store_true", help="Show the full agent roster")
    group.add_argument("--summon", metavar="ROLE", help="Summon a specific agent persona")
    group.add_argument("--chain", metavar="ROLES", help="Run agents in chain (comma-separated)")
    group.add_argument("--sweep", metavar="TYPE", help="Run a predefined sweep pattern")
    group.add_argument("--validate", metavar="FILE", help="Validate an agent output JSON file")
    group.add_argument("--daemon", action="store_true", help="Run in daemon mode, listening for Redpanda handoffs")

    parser.add_argument("--relay", action="store_true", help="Emit handoffs to Redpanda during validation")
    parser.add_argument("--task", metavar="DESC", help="Task description for the agent(s)")
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format: text (default) or json (structured)",
    )

    args = parser.parse_args()

    if args.roster:
        cmd_roster()
    elif args.summon:
        cmd_summon(args.summon, args.task, args.output)
    elif args.chain:
        cmd_chain(args.chain, args.task, args.output)
    elif args.sweep:
        cmd_sweep(args.sweep, args.output)
    elif args.validate:
        validate_output_file(args.validate, relay_mode=args.relay)
    elif args.daemon:
        if RELAY_AVAILABLE:
            relay = SwarmHandoffRelay()
            relay.listen()
        else:
            print("ERROR: SwarmHandoffRelay not available. Check dependencies.", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
