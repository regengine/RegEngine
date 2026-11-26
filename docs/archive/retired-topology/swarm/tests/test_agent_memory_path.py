"""AgentMemory must not let hostile agent names escape its directory.

The memory log path was built as ``base_dir / f"{agent_name}.jsonl"``,
so a name like ``../../evil`` wrote outside the memory directory. The
file stem is now sanitized; these tests pin the containment.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from regengine.swarm.base import AgentMemory, sanitize_agent_name


def test_plain_names_are_unchanged(tmp_path: Path):
    assert sanitize_agent_name("planner") == "planner"
    assert sanitize_agent_name("coder-2_x") == "coder-2_x"
    mem = AgentMemory("planner", base_dir=tmp_path)
    assert mem.log_file == tmp_path / "planner.jsonl"


@pytest.mark.parametrize(
    "name",
    ["../../evil", "..", ".", "", "a/b\\c", "../..", ".hidden", "a:b?c*d"],
    ids=["traversal", "dotdot", "dot", "empty", "separators", "double", "hidden", "reserved"],
)
def test_hostile_names_stay_inside_base_dir(tmp_path: Path, name: str):
    mem = AgentMemory(name, base_dir=tmp_path)
    assert os.sep not in mem.log_file.name
    assert mem.log_file.parent == tmp_path
    assert mem.log_file.resolve().is_relative_to(tmp_path.resolve())


def test_hostile_name_record_writes_inside_base_dir(tmp_path: Path):
    mem = AgentMemory("../../evil", base_dir=tmp_path)
    mem.record("task_received", {"task": "x"})
    assert mem.log_file.exists()
    assert mem.log_file.parent == tmp_path
    assert [p for p in tmp_path.iterdir()] == [mem.log_file]


def test_empty_and_dot_only_names_fall_back():
    assert sanitize_agent_name("") == "agent"
    assert sanitize_agent_name("..") == "agent"
    assert sanitize_agent_name("...") == "agent"
