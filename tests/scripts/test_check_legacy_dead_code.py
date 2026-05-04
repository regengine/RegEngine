from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_legacy_dead_code.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_legacy_dead_code", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_legacy_dead_code"] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def test_manual_agent_sweep_guard_allows_dispatch_only(tmp_path: Path) -> None:
    _write_agent_sweep(
        tmp_path,
        "on:\n"
        "  workflow_dispatch:\n"
        "    inputs:\n"
        "      sweep_type:\n"
        "        required: true\n",
    )

    assert _MODULE.check_manual_agent_sweep(tmp_path) == []


def test_manual_agent_sweep_guard_blocks_scheduled_sweeps(tmp_path: Path) -> None:
    _write_agent_sweep(
        tmp_path,
        "on:\n"
        "  schedule:\n"
        "    - cron: '0 9 * * 1'\n"
        "  workflow_dispatch:\n",
    )

    findings = _MODULE.check_manual_agent_sweep(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "scheduled-agent-sweep"


def _write_agent_sweep(tmp_path: Path, text: str) -> None:
    workflow = tmp_path / ".github" / "workflows" / "agent-sweep.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(text, encoding="utf-8")
