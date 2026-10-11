"""Regression tests for password handling in helper shell scripts.

The defect: scripts/create_neo4j_indexes.sh passed the Neo4j password with
`cypher-shell -p $NEO4J_PASSWORD` and scripts/init-postgres.sh passed the
Postgres password with `psql -v ...="$POSTGRES_PASSWORD"`. Both expose the
secret in the process list to anyone on the machine. The fixes pass the
Neo4j password through the environment by name (`docker exec -e`) and feed
the Postgres password to psql over stdin as a shell-quoted SQL literal.

These tests run the real scripts with stubbed `curl`/`docker`/`psql` on
PATH, so they need no live databases.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NEO4J_SCRIPT = REPO_ROOT / "scripts" / "create_neo4j_indexes.sh"
POSTGRES_SCRIPT = REPO_ROOT / "scripts" / "init-postgres.sh"

CURL_STUB = "#!/usr/bin/env bash\nexit 0\n"
DOCKER_STUB = """\
#!/usr/bin/env bash
# Log argv (one per line) and stdin separately for inspection.
printf '%s\\n' "$@" > "$DOCKER_ARGV_LOG"
cat > "$DOCKER_STDIN_LOG"
exit 0
"""
PSQL_STUB = """\
#!/usr/bin/env bash
# Append: init-postgres.sh calls psql several times; every call must be clean.
printf '%s\\n' "$@" >> "$PSQL_ARGV_LOG"
cat >> "$PSQL_STDIN_LOG"
echo "--- call boundary ---" >> "$PSQL_STDIN_LOG"
exit 0
"""


@pytest.fixture()
def fake_bin(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "curl").write_text(CURL_STUB)
    (bindir / "docker").write_text(DOCKER_STUB)
    (bindir / "psql").write_text(PSQL_STUB)
    for tool in ("curl", "docker", "psql"):
        (bindir / tool).chmod(0o755)
    return bindir


def _run(script, fake_bin, tmp_path, env):
    argv_log = tmp_path / "argv.log"
    stdin_log = tmp_path / "stdin.log"
    full_env = dict(os.environ)
    full_env["PATH"] = f"{fake_bin}{os.pathsep}{full_env['PATH']}"
    full_env["DOCKER_ARGV_LOG"] = str(argv_log)
    full_env["DOCKER_STDIN_LOG"] = str(stdin_log)
    full_env["PSQL_ARGV_LOG"] = str(argv_log)
    full_env["PSQL_STDIN_LOG"] = str(stdin_log)
    full_env.update(env)
    result = subprocess.run(
        ["bash", str(script)], env=full_env, capture_output=True, text=True, timeout=60
    )
    argv = argv_log.read_text() if argv_log.exists() else ""
    stdin = stdin_log.read_text() if stdin_log.exists() else ""
    return result, argv, stdin


NEO4J_SECRET = "s3cr3t-neo4j-pw-for-tests-only"


def test_neo4j_password_never_on_command_line(fake_bin, tmp_path):
    result, argv, stdin = _run(
        NEO4J_SCRIPT, fake_bin, tmp_path, {"NEO4J_PASSWORD": NEO4J_SECRET}
    )
    assert result.returncode == 0, result.stderr
    assert NEO4J_SECRET not in argv
    assert "-p" not in argv.split()
    assert "CREATE INDEX" in stdin


def test_neo4j_script_requires_password_env(fake_bin, tmp_path):
    env = dict(os.environ)
    env.pop("NEO4J_PASSWORD", None)
    full_env = dict(env)
    full_env["PATH"] = f"{fake_bin}{os.pathsep}{full_env['PATH']}"
    result = subprocess.run(
        ["bash", str(NEO4J_SCRIPT)], env=full_env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode != 0


# Nasty password: quote, dollar, backtick, bang and backslash together.
PG_SECRET = "p@ss'w0rd$`!\\tail"


def test_postgres_password_never_on_command_line(fake_bin, tmp_path):
    result, argv, stdin = _run(
        POSTGRES_SCRIPT,
        fake_bin,
        tmp_path,
        {"POSTGRES_USER": "u", "POSTGRES_DB": "d", "POSTGRES_PASSWORD": PG_SECRET},
    )
    assert result.returncode == 0, result.stderr
    assert PG_SECRET not in argv
    assert "POSTGRES_PASSWORD" not in argv
    # The single quote must be doubled for a valid SQL literal on stdin.
    assert "p@ss''w0rd" in stdin
    assert PG_SECRET not in stdin
    assert "CREATE ROLE regengine" in stdin


def test_postgres_script_requires_password_env(fake_bin, tmp_path):
    full_env = dict(os.environ)
    full_env["PATH"] = f"{fake_bin}{os.pathsep}{full_env['PATH']}"
    full_env["POSTGRES_USER"] = "u"
    full_env["POSTGRES_DB"] = "d"
    full_env.pop("POSTGRES_PASSWORD", None)
    result = subprocess.run(
        ["bash", str(POSTGRES_SCRIPT)],
        env=full_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
