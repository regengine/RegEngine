"""Regression tests for the re-platform-2-ops audit finding against
scripts/test/init-test-dbs.sql and scripts/ci/check_repo_freshness.sh.

The defects: the SQL file used bare CREATE DATABASE statements (PostgreSQL
has no CREATE DATABASE IF NOT EXISTS), so any re-run failed; the freshness
script passed the FRESHNESS_MAX_BEHIND env value into a numeric comparison
without validation; and a missing local main branch silently fell back to
origin/main as the baseline, always reporting fresh.

Each *_fails_* test below fails against the pre-fix files and passes with
the fix. All freshness tests run with --skip-fetch in throwaway git repos,
so they need no network. The live SQL re-run test additionally exercises a
real server when one is reachable and skips otherwise.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRESHNESS_SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_repo_freshness.sh"
INIT_DBS_SQL = REPO_ROOT / "scripts" / "test" / "init-test-dbs.sql"

EXPECTED_DATABASES = ("regengine_admin", "energy", "test_db")


def _git(repo: Path, *args: str, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        # Generous: this Mac is shared by ~90 fleet instances, so even a
        # local git command can stall for a while under load.
        timeout=180,
    )


def _make_repo(path: Path, branch: str = "main", commits: int = 1) -> Path:
    """Create a throwaway git repo with `commits` commits on `branch`."""
    path.mkdir(parents=True, exist_ok=True)
    assert _git(path, "init", "-b", branch, "-q").returncode == 0
    for n in range(commits):
        (path / "file.txt").write_text(f"content {n}\n")
        assert _git(path, "add", "file.txt").returncode == 0
        commit = _git(
            path,
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=test",
            "commit",
            "-qm",
            f"commit {n}",
        )
        assert commit.returncode == 0, commit.stderr
    return path


def _run_freshness(repo: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("FRESHNESS_MAX_BEHIND", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(FRESHNESS_SCRIPT), *args, "--skip-fetch"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _point_origin_main_at(repo: Path, rev: str = "HEAD") -> None:
    sha = _git(repo, "rev-parse", rev)
    assert sha.returncode == 0, sha.stderr
    update = _git(repo, "update-ref", "refs/remotes/origin/main", sha.stdout.strip())
    assert update.returncode == 0, update.stderr


# Freshness threshold validation -------------------------------------------


def test_negative_env_threshold_is_rejected(tmp_path: Path) -> None:
    """FRESHNESS_MAX_BEHIND=-5 must exit 2, not mis-compare against it.

    Fails against the pre-fix script: the env value bypassed the arg loop's
    digit check, so `[ 0 -gt -5 ]` ran and a fully fresh repo was reported
    stale (exit 1).
    """
    repo = _make_repo(tmp_path / "repo")
    _point_origin_main_at(repo)
    proc = _run_freshness(repo, env_extra={"FRESHNESS_MAX_BEHIND": "-5"})
    assert proc.returncode == 2, f"expected usage error, got {proc.returncode}: {proc.stdout}{proc.stderr}"
    assert "MAX_BEHIND" in proc.stderr


def test_non_numeric_env_threshold_is_rejected_with_a_clear_message(
    tmp_path: Path,
) -> None:
    """FRESHNESS_MAX_BEHIND=abc must name the bad value, not report fresh.

    Fails against the pre-fix script: the broken `[ 0 -gt abc ]` comparison
    sits in an `if` condition, so its failure just takes the else branch and
    the script prints FRESHNESS OK (exit 0) with a stray `integer expected`
    error on stderr and no mention of MAX_BEHIND.
    """
    repo = _make_repo(tmp_path / "repo")
    _point_origin_main_at(repo)
    proc = _run_freshness(repo, env_extra={"FRESHNESS_MAX_BEHIND": "abc"})
    assert proc.returncode == 2, f"expected usage error, got {proc.returncode}: {proc.stdout}{proc.stderr}"
    assert "MAX_BEHIND" in proc.stderr


# Missing local main baseline ----------------------------------------------


def test_missing_local_main_fails_instead_of_reporting_fresh(
    tmp_path: Path,
) -> None:
    """Without a local main branch the script must exit 2, not exit 0.

    Fails against the pre-fix script: `... || git rev-parse origin/main`
    substituted the remote as the baseline, so BEHIND was always 0.
    """
    repo = _make_repo(tmp_path / "repo", branch="work")
    _point_origin_main_at(repo)
    assert _git(repo, "rev-parse", "--verify", "--quiet", "main").returncode != 0
    proc = _run_freshness(repo)
    assert proc.returncode == 2, f"expected usage error, got {proc.returncode}: {proc.stdout}{proc.stderr}"
    assert "no local main" in proc.stderr


# No-regression guards (pass before and after the fix) ----------------------


def test_fresh_repo_still_passes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    _point_origin_main_at(repo)
    proc = _run_freshness(repo)
    assert proc.returncode == 0, f"{proc.stdout}{proc.stderr}"
    assert "FRESHNESS OK" in proc.stdout


def test_stale_repo_still_fails_with_exit_1(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo", commits=2)
    _point_origin_main_at(repo)
    reset = _git(repo, "reset", "--hard", "-q", "HEAD~1")
    assert reset.returncode == 0, reset.stderr
    proc = _run_freshness(repo, "0")
    assert proc.returncode == 1, f"expected stale, got {proc.returncode}: {proc.stdout}{proc.stderr}"
    assert "FRESHNESS FAIL" in proc.stderr


# init-test-dbs.sql existence guards ----------------------------------------


def test_init_test_dbs_guards_every_create_database() -> None:
    """Every database the file creates must be guarded by an existence check.

    Fails against the pre-fix file, which ran bare CREATE DATABASE
    statements that error on re-run.
    """
    sql = INIT_DBS_SQL.read_text()
    for db in EXPECTED_DATABASES:
        assert db in sql, f"database {db} missing from {INIT_DBS_SQL}"
    bare = [line for line in sql.splitlines() if re.match(r"\s*CREATE DATABASE", line, re.IGNORECASE)]
    assert bare == [], f"unguarded CREATE DATABASE fails on re-run: {bare}"
    assert "pg_database" in sql, "expected a pg_database existence guard"


def _server_reachable() -> bool:
    if not shutil.which("pg_isready") or not shutil.which("psql"):
        return False
    return subprocess.run(["pg_isready"], capture_output=True, timeout=15).returncode == 0


@pytest.mark.skipif(not _server_reachable(), reason="no reachable PostgreSQL server for re-run")
def test_init_test_dbs_reruns_cleanly_against_live_postgres() -> None:
    """Running the file twice must succeed both times (exit 0).

    Fails against the pre-fix file: the second run errors with
    'database ... already exists'. Leaves the created databases in place,
    exactly as CI setup would.
    """
    for run in (1, 2):
        proc = subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=1", "-d", "postgres", "-f", str(INIT_DBS_SQL)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, f"run {run} failed:\n{proc.stdout}\n{proc.stderr}"
