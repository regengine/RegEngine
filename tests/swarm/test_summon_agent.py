from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "summon_agent.py"
_SPEC = importlib.util.spec_from_file_location("summon_agent", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["summon_agent"] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_discovers_checked_in_github_agents() -> None:
    personas = _MODULE.discover_personas()

    assert {"planner", "implementer", "security_review"}.issubset(personas)
    assert personas["planner"].source == ".github/agents"


def test_build_prompt_includes_root_agent_guide_and_task() -> None:
    personas = _MODULE.discover_personas()

    prompt = _MODULE.build_prompt(
        "implementer",
        personas,
        task="Wire the FSMA export smoke test.",
        output_format="json",
    )

    assert "RegEngine Agent Guide" in prompt
    assert "Wire the FSMA export smoke test." in prompt
    assert "Return a valid JSON object" in prompt
