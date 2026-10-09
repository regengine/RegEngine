"""Script credential hygiene (audit low).

The audit found passwords on command lines
(scripts/create_neo4j_indexes.sh, scripts/init-postgres.sh) and a shell
reinterpretation step in scripts/test-all.sh. Command-line arguments are
visible to every local user through `ps`, so a secret placed in argv leaks;
and re-parsing a command string with a shell lets data turn into commands.

Two sibling halves of the same audit line (the e2e fallback secret and the
validate_env credential echo) were already fixed by #3230 and are covered by
tests/scripts/test_security_lows_scripts.py; this file covers the rest.

Every credential-looking value below is a sentinel, never a real secret.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NEO4J_SCRIPT = REPO_ROOT / "scripts" / "create_neo4j_indexes.sh"
POSTGRES_SCRIPT = REPO_ROOT / "scripts" / "init-postgres.sh"
TEST_ALL_SCRIPT = REPO_ROOT / "scripts" / "test-all.sh"


def _code_lines(path: Path) -> list[str]:
    """Non-comment, non-blank lines of a shell script."""
    lines = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# create_neo4j_indexes.sh
# ---------------------------------------------------------------------------


def test_neo4j_password_never_on_command_line():
    """No argv may carry the Neo4j password.

    Fails against the old script, which ran
    `cypher-shell -u neo4j -p ${NEO4J_PASSWORD}`.
    """
    # Single-quoted segments are deferred to the container: the host shell
    # never expands them, so the approved `sh -c '... -p "$NEO4J_PASSWORD"'`
    # line must not count as a host command-line password.
    code = "\n".join(re.sub(r"'[^']*'", "", line) for line in _code_lines(NEO4J_SCRIPT))
    assert not re.search(r"-p\s+['\"]?\$", code), (
        "the Neo4j password is passed as a -p command-line argument, visible in `ps` output"
    )
    # The approved route: forward the already-exported variable into the
    # container with `-e NAME` (no `=value`, so the secret is not in argv).
    assert re.search(r"-e NEO4J_PASSWORD( |$|\\\n)", code), (
        "expected `-e NEO4J_PASSWORD` env passthrough into the container"
    )


def test_neo4j_password_not_visible_to_peer_processes(tmp_path):
    """A stub docker records its argv; the sentinel must not be in it.

    Fails against the old script: the stub would see
    `-p <sentinel>` in its arguments.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text("#!/usr/bin/env bash\nexit 0\n")
    (bin_dir / "docker").write_text('#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$ARGV_LOG"\ncat > "$STDIN_FILE"\n')
    for stub in ("curl", "docker"):
        (bin_dir / stub).chmod(0o755)

    argv_log = tmp_path / "argv.log"
    stdin_file = tmp_path / "stdin.txt"
    env = dict(
        os.environ,
        PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        ARGV_LOG=str(argv_log),
        STDIN_FILE=str(stdin_file),
        NEO4J_PASSWORD="sentinel-neo4j-pw-9z",
    )
    proc = subprocess.run(["bash", str(NEO4J_SCRIPT)], env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "sentinel-neo4j-pw-9z" not in argv_log.read_text(), (
        f"password leaked into docker argv:\n{argv_log.read_text()}"
    )
    assert "CREATE INDEX" in stdin_file.read_text(), "the Cypher commands never reached the container stdin"


def test_neo4j_script_refuses_to_run_without_password():
    """Unset NEO4J_PASSWORD must fail fast, not connect passwordless."""
    env = dict(os.environ)
    env.pop("NEO4J_PASSWORD", None)
    proc = subprocess.run(["bash", str(NEO4J_SCRIPT)], env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0, "script ran without NEO4J_PASSWORD set"
    assert "NEO4J_PASSWORD" in proc.stderr, proc.stderr


# ---------------------------------------------------------------------------
# init-postgres.sh
# ---------------------------------------------------------------------------


def test_postgres_password_never_on_command_line():
    """No `psql -v name=<secret>` may carry the Postgres password.

    Fails against the old script, which passed
    `-v runtime_pw="$POSTGRES_PASSWORD"`.
    """
    code = "\n".join(_code_lines(POSTGRES_SCRIPT))
    for line in _code_lines(POSTGRES_SCRIPT):
        if line.strip().startswith("\\getenv") or "getenv" in line:
            continue
        assert not re.search(r"-v\s+\w*=\S*POSTGRES_PASSWORD|-v\s+\w*=\"?\$", line), (
            f"password passed via psql -v argv: {line.strip()}"
        )
    # The approved route: psql reads the secret from its own environment.
    assert "\\getenv runtime_pw POSTGRES_PASSWORD" in code
    assert "\\getenv admin_runtime_pw POSTGRES_PASSWORD" in code


def test_postgres_password_not_visible_to_peer_processes(tmp_path):
    """A stub psql records its argv; the sentinel must not be in it.

    Fails against the old script: the stub would see
    `-v runtime_pw=<sentinel>` in its arguments.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "psql").write_text(
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$ARGV_LOG"\ncat >> "$STDIN_LOG"\nexit 0\n'
    )
    (bin_dir / "psql").chmod(0o755)

    argv_log = tmp_path / "argv.log"
    stdin_log = tmp_path / "stdin.log"
    argv_log.write_text("")
    stdin_log.write_text("")
    env = dict(
        os.environ,
        PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        ARGV_LOG=str(argv_log),
        STDIN_LOG=str(stdin_log),
        POSTGRES_USER="sentinel-owner",
        POSTGRES_DB="sentinel-db",
        POSTGRES_PASSWORD="sentinel-pg-pw-7q",
    )
    proc = subprocess.run(["bash", str(POSTGRES_SCRIPT)], env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "sentinel-pg-pw-7q" not in argv_log.read_text(), f"password leaked into psql argv:\n{argv_log.read_text()}"
    assert "\\getenv runtime_pw POSTGRES_PASSWORD" in stdin_log.read_text()


# ---------------------------------------------------------------------------
# test-all.sh
# ---------------------------------------------------------------------------


def test_test_all_runner_has_no_shell_reinterpretation():
    """run_test must execute argv directly, never re-parse a string.

    Fails against the old script, which ran its command through eval.
    """
    for line in _code_lines(TEST_ALL_SCRIPT):
        assert not re.match(r"\s*(if\s+)?eval[\s\"'$;(]", line), (
            f"shell reinterpretation step still present: {line.strip()}"
        )
    body = TEST_ALL_SCRIPT.read_text()
    assert re.search(r"^run_test\(\) \{$", body, re.M) is not None
    assert '"$@"' in body, "run_test must execute its arguments directly"


def test_run_test_counts_results_without_shell(tmp_path):
    """The real run_test honors pass/fail and leaves metacharacters literal.

    Against the old eval-based helper, the `; touch` probe below would have
    executed as a second command and created the marker file.
    """
    marker = tmp_path / "pwned_marker"
    harness = (
        "set -o pipefail\n"
        "RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''\n"
        "PASSED=0; FAILED=0\n"
        'eval "$(sed -n \'/^run_test() {/,/^}/p\' "$RUNNER")"\n'
        "run_test \"probe pass\" 5 printf '%s\\n' hello\n"
        "run_test \"probe fail\" 5 bash -c 'exit 3'\n"
        "run_test \"probe literal\" 3 printf '%s' 'a; touch \"$MARKER\"'\n"
        'echo "RESULT PASSED=$PASSED FAILED=$FAILED"\n'
    )
    env = dict(os.environ, RUNNER=str(TEST_ALL_SCRIPT), MARKER=str(marker))
    proc = subprocess.run(["bash", "-c", harness], env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "RESULT PASSED=2 FAILED=1" in proc.stdout, proc.stdout
    assert not marker.exists(), "command metacharacters were reinterpreted as commands"


# ---------------------------------------------------------------------------
# Sanity
# ---------------------------------------------------------------------------


def test_scripts_are_valid_bash():
    """All three scripts must still parse."""
    assert shutil.which("bash") is not None
    for script in (NEO4J_SCRIPT, POSTGRES_SCRIPT, TEST_ALL_SCRIPT):
        proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, f"{script.name}: {proc.stderr}"
