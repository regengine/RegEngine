"""Tests for scripts/check_docs_links.py (#2915, #2926).

The point of this guard is to fail when a document names a repo path that does
not exist. This repo already carries several findings about gates that report
green while checking nothing (#2936, #2935, #2924, #2876), so every test here
asserts a *failure* is produced for genuinely broken input, not merely that the
checker runs.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_docs_links.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_docs_links", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load_module()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "services" / "shared").mkdir(parents=True)
    (tmp_path / "services" / "shared" / "auth.py").write_text("# real module\n")
    (tmp_path / "docs").mkdir()
    return tmp_path


def _write(repo: Path, name: str, body: str) -> Path:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


# --- The core contract: broken references fail --------------------------------


def test_dangling_backtick_reference_is_reported(repo: Path) -> None:
    doc = _write(repo, "GUIDE.md", "See `services/shared/deleted_module.py` for details.\n")
    failures = mod.check(repo, [doc])
    assert len(failures) == 1
    assert "services/shared/deleted_module.py" in failures[0]


def test_dangling_markdown_link_is_reported(repo: Path) -> None:
    doc = _write(repo, "GUIDE.md", "See [the map](docs/CODEBASE_MAP.md).\n")
    failures = mod.check(repo, [doc])
    assert len(failures) == 1
    assert "docs/CODEBASE_MAP.md" in failures[0]


def test_existing_path_passes(repo: Path) -> None:
    doc = _write(repo, "GUIDE.md", "Auth lives in `services/shared/auth.py`.\n")
    assert mod.check(repo, [doc]) == []


def test_directory_reference_resolves(repo: Path) -> None:
    doc = _write(repo, "GUIDE.md", "Shared code is under `services/shared/`.\n")
    assert mod.check(repo, [doc]) == []


def test_missing_directory_reference_is_reported(repo: Path) -> None:
    doc = _write(repo, "GUIDE.md", "Kernel code is under `kernel/reporting/`.\n")
    assert len(mod.check(repo, [doc])) == 1


# --- A file that is deleted must flip the gate red ----------------------------


def test_gate_flips_red_when_a_referenced_file_is_deleted(repo: Path) -> None:
    """The regression this guard exists to catch: code moves, doc does not."""
    doc = _write(repo, "GUIDE.md", "Auth lives in `services/shared/auth.py`.\n")
    assert mod.check(repo, [doc]) == [], "precondition: passes while the file exists"

    (repo / "services" / "shared" / "auth.py").unlink()

    failures = mod.check(repo, [doc])
    assert len(failures) == 1
    assert "services/shared/auth.py" in failures[0]


# --- Line references and anchors are stripped before resolution ---------------


@pytest.mark.parametrize(
    "reference",
    ["services/shared/auth.py:42", "services/shared/auth.py:42-99", "services/shared/auth.py#usage"],
)
def test_line_and_anchor_suffixes_are_stripped(repo: Path, reference: str) -> None:
    doc = _write(repo, "GUIDE.md", f"See `{reference}`.\n")
    assert mod.check(repo, [doc]) == []


# --- Things that are not repo paths must not be flagged -----------------------


@pytest.mark.parametrize(
    "token",
    [
        "https://example.com/a/b.py",     # URL
        "/tmp/scratch.json",              # absolute filesystem path
        "~/.claude/CLAUDE.md",            # home-relative
        "postgresql+psycopg://host/db",   # connection URI
        "tests/shared/test_*_live.py",    # glob
        "/api/v1/",                       # API route, not a file
        "chore/",                         # git branch prefix
        "app/",                           # single bare segment
        "pytest",                         # no separator at all
    ],
)
def test_non_repo_paths_are_ignored(repo: Path, token: str) -> None:
    doc = _write(repo, "GUIDE.md", f"Reference: `{token}`\n")
    assert mod.check(repo, [doc]) == [], f"{token!r} should not be treated as a repo path"


# --- Allowlist ----------------------------------------------------------------


def test_allowlist_exempts_a_specific_document(repo: Path) -> None:
    doc = _write(repo, "GUIDE.md", "The old `services/shared/gone.py` was removed.\n")
    assert len(mod.check(repo, [doc])) == 1

    (repo / mod.ALLOWLIST_NAME).write_text(
        "# removed deliberately\nGUIDE.md::services/shared/gone.py\n"
    )
    assert mod.check(repo, [doc]) == []


def test_allowlist_entry_does_not_leak_to_other_documents(repo: Path) -> None:
    """An exemption is per-document; another doc's dangling ref still fails."""
    (repo / mod.ALLOWLIST_NAME).write_text("GUIDE.md::services/shared/gone.py\n")
    other = _write(repo, "OTHER.md", "See `services/shared/gone.py`.\n")
    assert len(mod.check(repo, [other])) == 1


def test_allowlist_comments_and_blank_lines_are_ignored(repo: Path) -> None:
    (repo / mod.ALLOWLIST_NAME).write_text("\n# just a comment\n\nGUIDE.md::services/shared/gone.py\n")
    doc = _write(repo, "GUIDE.md", "See `services/shared/gone.py`.\n")
    assert mod.check(repo, [doc]) == []


# --- Resolution relative to the document's own directory ----------------------


def test_path_relative_to_the_document_resolves(repo: Path) -> None:
    (repo / "docs" / "sibling.md").write_text("# sibling\n")
    doc = _write(repo, "docs/GUIDE.md", "See [sibling](sibling.md).\n")
    assert mod.check(repo, [doc]) == []


# --- Exit codes ---------------------------------------------------------------


def test_main_returns_nonzero_on_failure(repo: Path, capsys: pytest.CaptureFixture) -> None:
    _write(repo, "GUIDE.md", "See `services/shared/gone.py`.\n")
    assert mod.main(["--repo-root", str(repo), "GUIDE.md"]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_main_returns_zero_when_clean(repo: Path) -> None:
    _write(repo, "GUIDE.md", "See `services/shared/auth.py`.\n")
    assert mod.main(["--repo-root", str(repo), "GUIDE.md"]) == 0
