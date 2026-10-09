"""Regression tests for scripts/railway/apply_sql_migrations.sh (audit-medium).

The audit found three defects in the raw SQL migration runner:

1. Zero matched migration files exited 0, so a wrong directory or glob
   deployed as success.
2. Files applied with no ledger, so a mid-batch failure left a half-applied
   state with no record of how far the batch got.
3. The database URL travelled as a process argument (``$1``), visible in
   process listings and shell history.

The fixed script fails on an empty match, records every applied file in
``public.schema_migration_files`` (reruns skip recorded files), and reads
the URL from ``MIGRATIONS_DATABASE_URL`` (or ``DATABASE_URL``),
rejecting a URL-looking positional argument.

These tests run the real script with a stubbed ``psql`` on PATH, so they
need no live PostgreSQL. The stub reproduces the part of psql's contract
that matters here: ``-c`` SQL statements succeed, ``-f`` applies a file
(unless ``PSQL_STUB_FAIL_ON`` names it), and ledger state persists in a
plain file. Set ``APPLY_SQL_UNDER_TEST`` to point these tests at a
different copy of the script (for example the pre-fix version) to confirm
they fail on the old code.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(
    os.environ.get(
        "APPLY_SQL_UNDER_TEST",
        REPO_ROOT / "scripts" / "railway" / "apply_sql_migrations.sh",
    )
)

FAKE_URL = "postgresql://migrator:stub-secret@example:5432/regengine"

_PSQL_STUB = """\
#!/usr/bin/env bash
# Stub psql: honours -c SQL and -f file, keeps ledger state in a file.
set -u
: "${PSQL_STUB_LOG:?}"
: "${PSQL_STUB_STATE:?}"
printf 'psql-invocation: %s\\n' "$*" >> "$PSQL_STUB_LOG"
sql=""
file=""
ledger_file=""
prev=""
for arg in "$@"; do
  if [[ "$prev" == "-c" ]]; then sql="$arg"; prev=""; continue; fi
  if [[ "$prev" == "-f" ]]; then file="$arg"; prev=""; continue; fi
  if [[ "$prev" == "-v" ]]; then
    if [[ "$arg" == ledger_file=* ]]; then ledger_file="${arg#ledger_file=}"; fi
    prev=""
    continue
  fi
  if [[ "$arg" == "-c" || "$arg" == "-f" || "$arg" == "-v" ]]; then prev="$arg"; continue; fi
done
touch "$PSQL_STUB_STATE"
if [[ "$sql" == *"current_user"* ]]; then
  echo "migrator"
  exit 0
fi
if [[ "$sql" == *"SELECT 1 FROM"* ]]; then
  if grep -qxF "$ledger_file" "$PSQL_STUB_STATE" 2>/dev/null; then
    echo "1"
  fi
  exit 0
fi
if [[ "$sql" == *"INSERT INTO"* ]]; then
  if ! grep -qxF "$ledger_file" "$PSQL_STUB_STATE" 2>/dev/null; then
    printf '%s\\n' "$ledger_file" >> "$PSQL_STUB_STATE"
  fi
  printf 'LEDGER_INSERT: %s\\n' "$ledger_file" >> "$PSQL_STUB_LOG"
  exit 0
fi
if [[ -n "$file" ]]; then
  base="$(basename "$file")"
  if [[ "${PSQL_STUB_FAIL_ON:-}" == "$base" ]]; then
    echo "psql: error: simulated failure applying $base" >&2
    exit 1
  fi
  printf 'APPLIED: %s\\n' "$base" >> "$PSQL_STUB_LOG"
  exit 0
fi
exit 0
"""


def _write_psql_stub(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "psql"
    stub.write_text(_PSQL_STUB)
    stub.chmod(0o755)


def _make_migrations(parent: Path, names: list[str]) -> Path:
    migrations = parent / "migrations"
    migrations.mkdir(parents=True, exist_ok=True)
    for name in names:
        (migrations / name).write_text(f"-- {name}\nSELECT 1;\n")
    return migrations


def _run(
    migrations_dir: Path,
    tmp_path: Path,
    *,
    args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    log_name: str = "psql.log",
    state_name: str = "ledger.state",
    unset_url: bool = False,
    seed_state: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    _write_psql_stub(tmp_path / "bin")
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    log = workdir / log_name
    state = workdir / state_name
    log.write_text("")
    if seed_state is not None:
        state.write_text(seed_state)
    env = dict(os.environ)
    env["PATH"] = f"{tmp_path / 'bin'}{os.pathsep}{env['PATH']}"
    env.pop("MIGRATIONS_DATABASE_URL", None)
    env.pop("DATABASE_URL", None)
    if not unset_url:
        env["MIGRATIONS_DATABASE_URL"] = FAKE_URL
    env["PSQL_STUB_LOG"] = str(log)
    env["PSQL_STUB_STATE"] = str(state)
    env.pop("PSQL_STUB_FAIL_ON", None)
    if extra_env:
        env.update(extra_env)
    cmd = ["bash", str(SCRIPT)]
    cmd += args if args is not None else [str(migrations_dir)]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return proc, log, state


def _applied(log: Path) -> list[str]:
    return [line.split("APPLIED: ", 1)[1] for line in log.read_text().splitlines() if line.startswith("APPLIED: ")]


def test_empty_match_fails(tmp_path: Path) -> None:
    """A wrong directory or glob must not deploy as success."""
    empty_dir = tmp_path / "migrations"
    empty_dir.mkdir()
    (empty_dir / "README.md").write_text("no sql here\n")
    proc, _, _ = _run(empty_dir, tmp_path / "work")
    assert proc.returncode != 0, (
        f"zero migration files exited {proc.returncode}; stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "No migration files" in proc.stderr + proc.stdout


def test_missing_url_env_fails(tmp_path: Path) -> None:
    """Without MIGRATIONS_DATABASE_URL (or DATABASE_URL) the run must stop."""
    migrations = _make_migrations(tmp_path, ["V001__a.sql"])
    proc, _, _ = _run(migrations, tmp_path / "work", unset_url=True)
    assert proc.returncode != 0
    assert "MIGRATIONS_DATABASE_URL" in proc.stderr + proc.stdout


def test_url_as_argument_is_rejected(tmp_path: Path) -> None:
    """The URL must travel via environment, never as a process argument."""
    migrations = _make_migrations(tmp_path, ["V001__a.sql"])
    proc, log, _ = _run(
        migrations,
        tmp_path / "work",
        args=[FAKE_URL, str(migrations)],
        unset_url=True,
    )
    assert proc.returncode != 0, f"a URL positional argument was accepted (exit {proc.returncode})"
    assert "environment variable" in proc.stderr
    assert "psql-invocation" not in log.read_text(), "the script connected with a URL taken from argv"


def test_applied_files_are_recorded_and_skipped_on_rerun(tmp_path: Path) -> None:
    """Each applied file is recorded; a rerun applies nothing twice."""
    migrations = _make_migrations(tmp_path, ["V001__a.sql", "V002__b.sql"])
    proc, log, state = _run(migrations, tmp_path / "run1", log_name="run1.log", state_name="ledger.state")
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert _applied(log) == ["V001__a.sql", "V002__b.sql"]
    recorded = state.read_text().split()
    assert recorded == ["V001__a.sql", "V002__b.sql"], recorded

    proc2, log2, _ = _run(
        migrations,
        tmp_path / "run2",
        seed_state=state.read_text(),
    )
    assert proc2.returncode == 0, f"stdout={proc2.stdout!r} stderr={proc2.stderr!r}"
    assert _applied(log2) == [], f"rerun reapplied files: {_applied(log2)}"
    assert "skipping" in proc2.stdout


def test_mid_batch_failure_records_prefix_and_resumes(tmp_path: Path) -> None:
    """A failure stops the batch with the prefix recorded; resume finishes it."""
    migrations = _make_migrations(tmp_path, ["V001__a.sql", "V002__b.sql", "V003__c.sql"])
    proc, log, state = _run(
        migrations,
        tmp_path / "run1",
        log_name="run1.log",
        state_name="ledger.state",
        extra_env={"PSQL_STUB_FAIL_ON": "V002__b.sql"},
    )
    assert proc.returncode != 0, "a failing migration file must fail the batch"
    assert _applied(log) == ["V001__a.sql"]
    assert state.read_text().split() == ["V001__a.sql"]

    proc2, log2, state2 = _run(
        migrations,
        tmp_path / "run2",
        seed_state=state.read_text(),
    )
    assert proc2.returncode == 0, f"stdout={proc2.stdout!r} stderr={proc2.stderr!r}"
    assert _applied(log2) == ["V002__b.sql", "V003__c.sql"]
    assert state2.read_text().split() == ["V001__a.sql", "V002__b.sql", "V003__c.sql"]


def test_database_url_fallback_env(tmp_path: Path) -> None:
    """DATABASE_URL is honoured when MIGRATIONS_DATABASE_URL is unset."""
    migrations = _make_migrations(tmp_path, ["V001__a.sql"])
    proc, log, _ = _run(
        migrations,
        tmp_path / "work",
        unset_url=True,
        extra_env={"DATABASE_URL": FAKE_URL},
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert _applied(log) == ["V001__a.sql"]
