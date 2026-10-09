"""Regression tests for AgentMemory log-path sanitization.

The memory log file was built by interpolating the agent name straight into
a path (regengine/swarm/base.py). Names come from code today, but BaseAgent
accepts any string, so a hostile or accidental name such as "../../evil"
would write outside the memory directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from regengine.swarm.base import AgentMemory, safe_log_stem


def test_normal_names_unchanged() -> None:
    assert safe_log_stem("PlannerAgent") == "PlannerAgent"
    assert safe_log_stem("coder-1_v2") == "coder-1_v2"


def test_traversal_name_stays_inside_base_dir(tmp_path: Path) -> None:
    base = tmp_path / "mem"
    mem = AgentMemory("../../evil", base_dir=base)
    assert mem.log_file.parent == base
    assert mem.log_file.name == ".._.._evil.jsonl"
    assert "/" not in mem.log_file.name
    mem.record("probe", {"ok": True})
    assert mem.log_file.exists()
    assert not (tmp_path / "evil.jsonl").exists()


def test_absolute_path_name_stays_inside_base_dir(tmp_path: Path) -> None:
    base = tmp_path / "mem"
    mem = AgentMemory("/etc/passwd", base_dir=base)
    assert mem.log_file.parent == base
    mem.record("probe", {"ok": True})
    assert mem.log_file.exists()


def test_record_and_recall_use_sanitized_file(tmp_path: Path) -> None:
    mem = AgentMemory("a/b", base_dir=tmp_path / "mem")
    mem.record("task_received", {"task": "hi"})
    assert mem.recall() != []
    assert mem.recall()[0]["agent"] == "a/b"


@pytest.mark.parametrize("name", ["", "...", "---", "___", "/"])
def test_names_with_no_usable_characters_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        AgentMemory(name, base_dir=tmp_path / "mem")
