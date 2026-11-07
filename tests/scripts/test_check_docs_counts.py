"""Tests for scripts/check_docs_counts.py (WI-07)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "check_docs_counts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_docs_counts", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()

_MAP = """# Map

| `.github/workflows/` | {wf} workflows (see §7). |

`server/routers_mount.py` makes {routers} `include_owned_router` calls.
`EXPERIMENTAL_ROUTERS` names domains that are auto-disabled:

```
{experimental}
```

CI is {wf} workflows under `.github/workflows/`.
"""

_ARCH = """# Architecture

### Large Modules

| File | Lines | Area | Likely split direction |
| --- | ---: | --- | --- |
{rows}

## Next
"""


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _fake_repo(
    tmp_path: Path, *, wf: int = 2, routers: int = 2, experimental: str = "alpha beta", rows: str | None = None
):
    for i in range(wf):
        _write(tmp_path, f".github/workflows/w{i}.yml", "name: w\n")
    _write(tmp_path, "server/routers_mount.py", "include_owned_router(app, r1)\ninclude_owned_router(app, r2)\n")
    _write(
        tmp_path,
        "server/router_policy.py",
        'EXPERIMENTAL_ROUTERS = frozenset(\n    {\n        "alpha",\n        "beta",\n    }\n)\n',
    )
    _write(tmp_path, "services/big/app/huge.py", "x = 1\n" * 1001)
    _write(tmp_path, "services/big/app/small.py", "x = 1\n" * 10)
    _write(tmp_path, "services/big/tests/test_huge.py", "x = 1\n" * 1001)
    if rows is None:
        rows = "| `services/big/app/huge.py` | 1001 | big | split |"
    _write(tmp_path, "docs/CODEBASE_MAP.md", _MAP.format(wf=wf, routers=routers, experimental=experimental))
    _write(tmp_path, "ARCHITECTURE.md", _ARCH.format(rows=rows))
    return tmp_path


def test_consistent_repo_passes(tmp_path):
    assert _mod.scan(_fake_repo(tmp_path)) == []


def test_workflow_count_mismatch_reports_both_places(tmp_path):
    repo = _fake_repo(tmp_path, wf=2)
    _write(repo, ".github/workflows/w9.yml", "name: w\n")
    problems = _mod.scan(repo)
    assert len(problems) == 2
    assert all("document says 2, tree has 3" in p for p in problems)


def test_router_call_count_mismatch(tmp_path):
    repo = _fake_repo(tmp_path, routers=5)
    problems = _mod.scan(repo)
    assert problems == ["docs/CODEBASE_MAP.md: §4 include_owned_router count: document says 5, tree has 2"]


def test_experimental_list_mismatch_renders_replacement(tmp_path):
    repo = _fake_repo(tmp_path, experimental="alpha gamma")
    problems = _mod.scan(repo)
    assert len(problems) == 1
    assert "['gamma']" in problems[0] and "['beta']" in problems[0]
    assert problems[0].endswith("```\nalpha  beta\n```")


def test_large_module_table_mismatch(tmp_path):
    repo = _fake_repo(tmp_path, rows="| `services/big/app/small.py` | 10 | big | split |")
    problems = _mod.scan(repo)
    assert len(problems) == 1
    assert "not listed ['services/big/app/huge.py']" in problems[0]
    assert "['services/big/app/small.py']" in problems[0]


def test_missing_sentence_is_reported(tmp_path):
    repo = _fake_repo(tmp_path)
    (repo / "docs" / "CODEBASE_MAP.md").write_text("# Map\n\nnothing here\n```\nalpha beta\n```\n")
    problems = _mod.scan(repo)
    assert sum("no sentence matches" in p for p in problems) == 3
    assert any("no fenced block follows" in p for p in problems)


def test_large_modules_skip_tests_and_count_newlines(tmp_path):
    repo = _fake_repo(tmp_path)
    assert _mod.large_modules(repo) == {"services/big/app/huge.py": 1001}


def test_render_experimental_block_wraps_sorted():
    block = _mod.render_experimental_block({"zeta", "alpha", "mid"}, width=12)
    assert block == "```\nalpha  mid\nzeta\n```"


def test_main_exit_codes(tmp_path, capsys):
    repo = _fake_repo(tmp_path)
    assert _mod.main(["--repo-root", str(repo)]) == 0
    assert "OK" in capsys.readouterr().out
    _write(repo, ".github/workflows/w9.yml", "name: w\n")
    assert _mod.main(["--repo-root", str(repo)]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_real_repository_is_consistent():
    assert _mod.scan(_REPO_ROOT) == []
