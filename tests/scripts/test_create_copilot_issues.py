"""Regression tests for scripts/create_copilot_issues.sh.

The defect: the script had no strict shell options, piped the result of
`gh issue create` through `tail -1` (which hides the real exit status, so a
failed call still looked like success and the script always ended with
"All issues created!"), and accepted a `labels` argument it never passed to
`gh issue create`.

These tests run the script's real shell code with a stubbed `gh` on PATH,
so they need no network access and create no real issues. Set
CREATE_COPILOT_ISSUES_SCRIPT to point at another copy of the script (for
example the pre-fix version) to check the tests against it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(os.environ.get("CREATE_COPILOT_ISSUES_SCRIPT", REPO_ROOT / "scripts" / "create_copilot_issues.sh"))


def _write_stub(bin_dir: Path, name: str, body: str) -> None:
    stub = bin_dir / name
    stub.write_text("#!/usr/bin/env bash\n" + body)
    stub.chmod(0o755)


def _stub_env(tmp_path: Path, gh_body: str) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_stub(bin_dir, "gh", gh_body)
    _write_stub(bin_dir, "sleep", "exit 0\n")
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    return env


def _extract_create_issue(script_text: str) -> str:
    match = re.search(r"^create_issue\(\) \{.*?\n\}", script_text, re.DOTALL | re.MULTILINE)
    assert match, "could not find the create_issue function in the script"
    return match.group(0)


def test_script_enables_strict_mode():
    """The script must opt into strict error handling.

    Fails against the pre-fix script, whose shebang line is bare `#!/bin/bash`.
    """
    assert "set -euo pipefail" in SCRIPT.read_text(), "script does not enable strict mode (set -euo pipefail)"


def test_gh_result_is_not_masked_by_a_pipe():
    """The `gh issue create` call must expose its real exit status.

    Fails against the pre-fix script, which pipes gh through `tail -1`,
    so the pipeline status is tail's (success) even when gh fails.
    """
    lines = [line for line in SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#")]
    gh_lines = [line for line in lines if "gh issue create" in line]
    assert gh_lines, "no `gh issue create` invocation found in the script"
    # A single `|` pipes gh output into another command whose status then
    # hides gh failures; `||` (status check) is fine and expected.
    pipe = re.compile(r"(?<!\|)\|(?!\|)")
    for line in gh_lines:
        assert not pipe.search(line), f"gh result is masked by a pipe, hiding failures: {line.strip()}"


def test_labels_argument_is_passed_through():
    """The `labels` argument must reach `gh issue create` as --label.

    Fails against the pre-fix script, which reads `$3` into `labels`
    but never uses it.
    """
    lines = [line for line in SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#")]
    assert any("--label" in line and "labels" in line for line in lines), (
        "the labels argument is never passed to `gh issue create --label`"
    )


def test_failing_gh_reports_failure_not_success(tmp_path):
    """A failing `gh` must produce a non-zero exit and no success message.

    Fails against the pre-fix script, which exits 0 and prints
    "All issues created!" even when every `gh` call fails.
    """
    env = _stub_env(tmp_path, 'echo "simulated gh failure" >&2\nexit 1\n')
    proc = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, cwd=tmp_path, timeout=120)

    assert proc.returncode != 0, "script reported success despite every `gh issue create` failing"
    assert "All issues created!" not in proc.stdout, "script claims success despite failing `gh` calls"


def test_successful_run_still_reports_success(tmp_path):
    """The happy path must keep working: exit 0 and the success message."""
    log = tmp_path / "gh-args.log"
    env = _stub_env(
        tmp_path, f'printf "%s\\n" "$@" >> "{log}"\necho "https://github.com/regengine/RegEngine/issues/1"\n'
    )
    proc = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, cwd=tmp_path, timeout=120)

    assert proc.returncode == 0, proc.stderr
    assert "All issues created!" in proc.stdout
    assert log.exists(), "expected the stubbed `gh` to be called at least once"


def _run_create_issue_with_args(tmp_path: Path, *issue_args: str) -> list:
    """Run the script's own create_issue function with a logging stub `gh`."""
    func = _extract_create_issue(SCRIPT.read_text())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "gh-args.log"
    _write_stub(bin_dir, "gh", f'printf "%s\\n" "$@" >> "{log}"\n')
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

    quoted = " ".join(f'"{arg}"' for arg in issue_args)
    harness = tmp_path / "harness.sh"
    harness.write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\nREPO="regengine/RegEngine"\nFAILED=0\n'
        + func
        + f"\ncreate_issue {quoted}\n"
    )
    proc = subprocess.run(["bash", str(harness)], env=env, capture_output=True, text=True, cwd=tmp_path, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return log.read_text().splitlines()


def test_labels_value_reaches_gh_as_label_flag(tmp_path):
    """Calling create_issue with labels must add `--label <value>` to gh args.

    Fails against the pre-fix function, which drops the third argument.
    """
    args = _run_create_issue_with_args(tmp_path, "some title", "some body", "bug,help wanted")

    assert "--label" in args, f"`--label` was not passed to gh; gh saw: {args}"
    label_pos = args.index("--label")
    assert args[label_pos + 1] == "bug,help wanted", f"wrong --label value; gh saw: {args}"


def test_missing_labels_omits_the_label_flag(tmp_path):
    """Calling create_issue without labels must not pass an empty --label."""
    args = _run_create_issue_with_args(tmp_path, "some title", "some body")

    assert "--label" not in args, f"empty `--label` flag passed to gh; gh saw: {args}"
