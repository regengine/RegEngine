"""Tests for scripts/check_noqa_ratchet.py (WI-03)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "check_noqa_ratchet.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_noqa_ratchet", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _fake_repo(tmp_path: Path, baseline: int = 1) -> Path:
    _write(
        tmp_path,
        "services/shared/thing.py",
        "import os  # noqa: F401\nx = 1  # noqa: E501 -- long on purpose\ny = 2  # noqa\n",
    )
    _write(tmp_path, "services/shared/tests/test_thing.py", "import os  # noqa\n")
    _write(tmp_path, "services/shared/test_other.py", "import os  # noqa\n")
    _write(tmp_path, "services/shared/conftest.py", "import os  # noqa\n")
    _write(tmp_path, "scripts/noqa_baseline.txt", f"# count\n{baseline}\n")
    return tmp_path


def test_counts_only_markers_without_a_reason_in_production_code(tmp_path):
    markers = _mod.unexplained_markers(_fake_repo(tmp_path))
    assert [(m[0], m[1]) for m in markers] == [("services/shared/thing.py", 1), ("services/shared/thing.py", 3)]


def test_reason_after_double_dash_is_explained():
    assert "--" in _mod._NOQA.search("x = 1  # noqa: E501 -- why").group("rest")
    assert "--" not in _mod._NOQA.search("x = 1  # noqa: E501").group("rest")


def test_over_baseline_fails(tmp_path, capsys):
    assert _mod.main(["--repo-root", str(_fake_repo(tmp_path, baseline=1))]) == 1
    assert "noqa ratchet FAILED: 1 new marker" in capsys.readouterr().out


def test_at_baseline_passes(tmp_path, capsys):
    assert _mod.main(["--repo-root", str(_fake_repo(tmp_path, baseline=2))]) == 0
    assert "at the baseline" in capsys.readouterr().out


def test_under_baseline_asks_to_lower_it(tmp_path, capsys):
    assert _mod.main(["--repo-root", str(_fake_repo(tmp_path, baseline=5)), "--list"]) == 0
    out = capsys.readouterr().out
    assert "lower scripts/noqa_baseline.txt to 2" in out
    assert "services/shared/thing.py:1:" in out


def test_missing_layout_exits_2(tmp_path):
    assert _mod.main(["--repo-root", str(tmp_path)]) == 2


def test_real_repository_is_within_baseline():
    assert len(_mod.unexplained_markers(_REPO_ROOT)) <= _mod.read_baseline(_REPO_ROOT)
