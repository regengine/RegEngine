from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "summon_agent.py"
_SPEC = importlib.util.spec_from_file_location("summon_agent", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["summon_agent"] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_discovers_checked_in_github_agents() -> None:
    agents = _MODULE.discover_agents()

    assert set(agents) == {"planner", "implementer", "security_review"}
    assert agents["planner"].path.name == "regengine-planner.agent.md"


def test_supported_agent_specs_are_valid() -> None:
    assert _MODULE.agent_spec_errors() == []


def test_agent_spec_validation_rejects_unexpected_roles(tmp_path: Path) -> None:
    _write_agent_spec(tmp_path, "regengine-planner.agent.md")
    _write_agent_spec(tmp_path, "regengine-implementer.agent.md")
    _write_agent_spec(tmp_path, "regengine-security-review.agent.md")
    _write_agent_spec(tmp_path, "regengine-extra.agent.md")

    errors = _MODULE.agent_spec_errors(tmp_path)

    assert "Unexpected agent spec: regengine-extra.agent.md" in errors


def test_agent_spec_validation_requires_frontmatter_fields(tmp_path: Path) -> None:
    _write_agent_spec(tmp_path, "regengine-planner.agent.md", name="")
    _write_agent_spec(tmp_path, "regengine-implementer.agent.md")
    _write_agent_spec(tmp_path, "regengine-security-review.agent.md")

    with pytest.raises(_MODULE.AgentSpecError, match="regengine-planner.agent.md"):
        _MODULE.validate_supported_agent_specs(tmp_path)


def test_build_prompt_includes_root_agent_guide_and_task() -> None:
    agents = _MODULE.discover_agents()

    prompt = _MODULE.build_prompt(
        "implementer",
        agents,
        task="Wire the FSMA export smoke test.",
        output_format="json",
    )

    assert "RegEngine Agent Guide" in prompt
    assert "Agent Operating Model" in prompt
    assert "Wire the FSMA export smoke test." in prompt
    assert "Return a valid JSON object" in prompt


def _write_agent_spec(tmp_path: Path, filename: str, name: str = "RegEngine Agent") -> None:
    tmp_path.mkdir(exist_ok=True)
    tmp_path.joinpath(filename).write_text(
        "---\n"
        f"name: {name}\n"
        "description: Keep the agent role scoped.\n"
        "tools: ['codebase']\n"
        "---\n\n"
        "Role instructions.\n",
        encoding="utf-8",
    )
