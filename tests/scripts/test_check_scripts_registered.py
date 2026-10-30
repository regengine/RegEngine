"""Tests for scripts/check_scripts_registered.py.

Each test builds a tiny ``scripts/`` tree plus a registry in a temp directory
and calls the module's functions directly, so the suite needs no git.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "check_scripts_registered.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_scripts_registered", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()

_REGISTRY = """# scripts/ registry

| Script | Status | Purpose / invoked by |
|---|---|---|
| `alpha.py` | used | invoked by `.github/workflows/x.yml` |
| `beta.sh` | manual | run by hand |

## Subdirectories

| Directory | Purpose |
|---|---|
| `scripts/ci/` | workflow helpers |
"""


def _fake_repo(tmp_path: Path, registry: str = _REGISTRY) -> Path:
    scripts = tmp_path / "scripts"
    (scripts / "ci").mkdir(parents=True)
    (scripts / "alpha.py").write_text("print(1)\n")
    (scripts / "beta.sh").write_text("echo 1\n")
    (scripts / "README.md").write_text(registry)
    return tmp_path


def test_clean_tree_passes(tmp_path):
    assert _mod.scan(_fake_repo(tmp_path)) == []


def test_unregistered_file_fails(tmp_path):
    repo = _fake_repo(tmp_path)
    (repo / "scripts" / "gamma.py").write_text("print(3)\n")
    problems = _mod.scan(repo)
    assert len(problems) == 1
    assert problems[0].startswith("scripts/gamma.py: no row")


def test_unregistered_directory_fails(tmp_path):
    repo = _fake_repo(tmp_path)
    (repo / "scripts" / "newdir").mkdir()
    problems = _mod.scan(repo)
    assert problems == ["scripts/newdir/: no row in the Subdirectories table of scripts/README.md"]


def test_stale_file_row_fails(tmp_path):
    repo = _fake_repo(tmp_path, _REGISTRY + "| `gone.py` | used | nothing |\n")
    problems = _mod.scan(repo)
    assert len(problems) == 1
    assert "lists `gone.py`, which is not in scripts/" in problems[0]


def test_stale_directory_row_fails(tmp_path):
    repo = _fake_repo(tmp_path, _REGISTRY + "| `scripts/gone/` | nothing |\n")
    problems = _mod.scan(repo)
    assert len(problems) == 1
    assert "lists `scripts/gone/`, which does not exist" in problems[0]


def test_ignored_entries_need_no_row(tmp_path):
    repo = _fake_repo(tmp_path)
    (repo / "scripts" / "__pycache__").mkdir()
    (repo / "scripts" / "_archive").mkdir()
    (repo / "scripts" / ".hidden").write_text("")
    assert _mod.scan(repo) == []


def test_files_inside_subdirectories_are_not_checked(tmp_path):
    repo = _fake_repo(tmp_path)
    (repo / "scripts" / "ci" / "helper.py").write_text("print(1)\n")
    assert _mod.scan(repo) == []


def test_main_reports_and_fails(tmp_path, capsys):
    repo = _fake_repo(tmp_path)
    (repo / "scripts" / "gamma.py").write_text("print(3)\n")
    assert _mod.main(["--repo-root", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "registry guard FAILED" in out
    assert "scripts/gamma.py" in out


def test_main_passes_on_clean_tree(tmp_path, capsys):
    assert _mod.main(["--repo-root", str(_fake_repo(tmp_path))]) == 0
    assert "OK" in capsys.readouterr().out


def test_missing_layout_exits_2(tmp_path):
    import pytest

    with pytest.raises(SystemExit) as excinfo:
        _mod.scan(tmp_path)
    assert excinfo.value.code == 2


def test_real_repository_is_clean():
    assert _mod.scan(_REPO_ROOT) == []
