from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "health_check.py"
_SUMMON_AGENT = Path(__file__).resolve().parents[2] / "scripts" / "summon_agent.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("health_check", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def test_agent_helper_health_check_passes_for_checked_in_specs() -> None:
    assert _MODULE.check_agent_helper() is True


def test_agent_helper_health_check_fails_when_helper_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_MODULE, "REPO_ROOT", tmp_path)

    assert _MODULE.check_agent_helper() is False


def test_agent_helper_health_check_rejects_unexpected_agent_specs(tmp_path, monkeypatch) -> None:
    scripts_dir = tmp_path / "scripts"
    agents_dir = tmp_path / ".github" / "agents"
    scripts_dir.mkdir(parents=True)
    agents_dir.mkdir(parents=True)

    (scripts_dir / "summon_agent.py").write_text(_SUMMON_AGENT.read_text(encoding="utf-8"))
    _write_agent_spec(agents_dir, "regengine-planner.agent.md")
    _write_agent_spec(agents_dir, "regengine-implementer.agent.md")
    _write_agent_spec(agents_dir, "regengine-security-review.agent.md")
    _write_agent_spec(agents_dir, "regengine-extra.agent.md")
    monkeypatch.setattr(_MODULE, "REPO_ROOT", tmp_path)

    assert _MODULE.check_agent_helper() is False


def _write_agent_spec(agents_dir: Path, filename: str) -> None:
    agents_dir.joinpath(filename).write_text(
        "---\n"
        "name: RegEngine Agent\n"
        "description: Keep the agent role scoped.\n"
        "tools: ['codebase']\n"
        "---\n\n"
        "Role instructions.\n",
        encoding="utf-8",
    )
