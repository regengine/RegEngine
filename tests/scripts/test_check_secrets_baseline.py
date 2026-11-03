"""Exit-mapping and argv-safety coverage for scripts/ci/check_secrets_baseline.sh.

Uses a stub detect-secrets-hook on PATH so we never need a real scanner install.
Sentinel values only — no real secrets.
"""

from __future__ import annotations

import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_secrets_baseline.sh"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".secrets.baseline").write_text(
        textwrap.dedent(
            """            {
              "version": "1.5.0",
              "plugins_used": [],
              "filters_used": [],
              "results": {},
              "generated_at": "2026-01-01T00:00:00Z"
            }
            """
        )
    )
    (tmp_path / "tracked.txt").write_text("ok\n")
    return tmp_path


def _write_hook(bin_dir: Path, body: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    hook = bin_dir / "detect-secrets-hook"
    hook.write_text("#!/usr/bin/env bash\n" + body)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook


def _run(
    repo: Path,
    bin_dir: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def test_exit_0_passes(repo: Path, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    _write_hook(bin_dir, "exit 0\n")
    result = _run(repo, bin_dir, "tracked.txt")
    assert result.returncode == 0, result.stderr + result.stdout


def test_exit_3_baseline_drift_treated_as_pass(repo: Path, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    _write_hook(bin_dir, 'echo "The baseline file was updated."; exit 3\n')
    result = _run(repo, bin_dir, "tracked.txt")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "baseline line-number/metadata drift" in result.stdout


def test_exit_1_new_finding_fails_gate(repo: Path, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    _write_hook(
        bin_dir,
        'echo "ERROR: Potential secrets about to be committed to git repo!"; exit 1\n',
    )
    result = _run(repo, bin_dir, "tracked.txt")
    assert result.returncode == 1, result.stderr + result.stdout
    assert "found secrets not in .secrets.baseline" in result.stdout + result.stderr


def test_exit_1_baseline_setup_error_is_not_reported_as_finding(
    repo: Path, tmp_path: Path
) -> None:
    bin_dir = tmp_path / "bin"
    _write_hook(
        bin_dir,
        'echo "Your baseline file (.secrets.baseline) is unstaged."; exit 1\n',
    )
    result = _run(repo, bin_dir, "tracked.txt")
    assert result.returncode == 2, result.stderr + result.stdout
    combined = result.stdout + result.stderr
    assert "baseline/setup error" in combined
    assert "found secrets not in .secrets.baseline" not in combined


def test_missing_hook_exits_127(repo: Path, tmp_path: Path) -> None:
    bin_dir = tmp_path / "empty-bin"
    bin_dir.mkdir()
    result = subprocess.run(
        ["bash", str(SCRIPT), "tracked.txt"],
        cwd=repo,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin"},
    )
    assert result.returncode == 127
    assert "detect-secrets-hook not found" in result.stderr + result.stdout


def test_filenames_are_forwarded_after_option_terminator(
    repo: Path, tmp_path: Path
) -> None:
    bin_dir = tmp_path / "bin"
    argv_log = tmp_path / "argv.log"
    _write_hook(
        bin_dir,
        textwrap.dedent(
            f"""\
            printf '%s\\n' "$@" > "{argv_log}"
            exit 0
            """
        ),
    )
    dash_file = repo / "--version"
    dash_file.write_text("not-an-option\n")
    result = _run(repo, bin_dir, "--version", "tracked.txt")
    assert result.returncode == 0, result.stderr + result.stdout
    argv = argv_log.read_text().splitlines()
    assert "--" in argv
    after = argv[argv.index("--") + 1 :]
    assert "--version" in after
    assert "tracked.txt" in after


def test_missing_baseline_exits_2(repo: Path, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    _write_hook(bin_dir, "exit 0\n")
    (repo / ".secrets.baseline").unlink()
    result = _run(repo, bin_dir, "tracked.txt")
    assert result.returncode == 2
    assert "setup-error" in result.stderr + result.stdout


def test_other_hook_exit_is_passed_through(repo: Path, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    _write_hook(bin_dir, "exit 99\n")
    result = _run(repo, bin_dir, "tracked.txt")
    assert result.returncode == 99
    assert "exit code 99" in result.stderr + result.stdout


def test_exit_1_unable_to_read_baseline_is_setup_error(
    repo: Path, tmp_path: Path
) -> None:
    """detect-secrets 1.5.0 prints this for malformed baseline JSON."""
    bin_dir = tmp_path / "bin"
    _write_hook(
        bin_dir,
        'echo "detect-secrets-hook: error: Unable to read baseline."; exit 1\n',
    )
    result = _run(repo, bin_dir, "tracked.txt")
    assert result.returncode == 2, result.stderr + result.stdout
    combined = result.stdout + result.stderr
    assert "baseline/setup error" in combined
    assert "found secrets not in .secrets.baseline" not in combined


def test_exit_1_finding_in_baseline_error_path_is_still_finding(
    repo: Path, tmp_path: Path
) -> None:
    """A finding whose path contains 'baseline-error' must not look like setup."""
    bin_dir = tmp_path / "bin"
    _write_hook(
        bin_dir,
        textwrap.dedent(
            """\
            echo "ERROR: Potential secrets about to be committed to git repo!"
            echo "baseline-error.txt:1:fake-token"
            exit 1
            """
        ),
    )
    result = _run(repo, bin_dir, "tracked.txt")
    assert result.returncode == 1, result.stderr + result.stdout
    combined = result.stdout + result.stderr
    assert "found secrets not in .secrets.baseline" in combined
    assert "baseline/setup error" not in combined


def test_ls_files_nonzero_during_collection_exits_2(
    repo: Path, tmp_path: Path
) -> None:
    """A failing git ls-files -z must not pass a partial list to the hook."""
    bin_dir = tmp_path / "bin"
    _write_hook(bin_dir, "exit 0\n")
    fake_git = bin_dir / "git"
    fake_git.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            # Emit one path then fail — old process-sub loop would keep the path.
            if [[ " $* " == *" -z "* ]]; then
              printf 'partial.txt\\0'
              exit 1
            fi
            exit 0
            """
        )
    )
    fake_git.chmod(fake_git.stat().st_mode | 0o111)
    (repo / "partial.txt").write_text("x\n")
    # No filename args → wrapper collects via git ls-files -z.
    result = _run(repo, bin_dir)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "git ls-files failed" in result.stderr + result.stdout
