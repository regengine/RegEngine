"""Regression tests for scripts/backup_postgres.sh (#2937).

The defect: the script wrote a `pg_dump --format=custom` archive (binary,
magic `PGDMP`, readable only by `pg_restore`) under a `.sql.gz` filename,
while the only documented PostgreSQL restore procedure in the repo is

    gunzip -c backups/postgres/regengine_YYYY-MM-DD.sql.gz | psql ... regengine

(docs/runbooks/disaster-recovery.md).  Every backup the script produced was
therefore unrestorable by the documented command.

These tests exercise the script's real shell pipeline with a stubbed `pg_dump`
on PATH, so they need no live PostgreSQL.  The stub reproduces the part of
pg_dump's contract that matters here: `--format=custom` emits a binary PGDMP
archive, plain (default) format emits a SQL text stream.  A real end-to-end
round trip against a live server is additionally exercised by
``test_live_roundtrip_restores_seeded_rows`` when one is reachable.
"""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "backup_postgres.sh"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "disaster-recovery.md"

# What real `pg_dump` writes in plain format; the marker the runbook's
# `psql` consumer implicitly relies on being SQL text.
PLAIN_SQL_DUMP = """\
--
-- PostgreSQL database dump
--
CREATE TABLE public.traceability_lot (id integer NOT NULL, lot_code text);
INSERT INTO public.traceability_lot VALUES (1, 'LOT-A-001');
--
-- PostgreSQL database dump complete
--
"""

# Real pg_dump custom-format archives begin with this magic. Not gzip, not SQL.
PGDMP_MAGIC = b"PGDMP\x01\x0f\x00"

_STUB_TEMPLATE = """\
#!/usr/bin/env bash
# Stub pg_dump: mimics the format contract of the real tool.
{failure_block}
for arg in "$@"; do
  case "$arg" in
    --format=custom|-Fc)
      # Real pg_dump emits a binary PGDMP archive here - not gzip, not SQL.
      printf '{magic}'
      exit 0
      ;;
  esac
done
cat <<'SQLEOF'
{sql}
SQLEOF
"""


def _write_pg_dump_stub(bin_dir: Path, *, fail: bool = False) -> None:
    """Install a fake `pg_dump` in *bin_dir* that honours --format=custom."""
    failure_block = ""
    if fail:
        failure_block = (
            'echo "pg_dump: error: connection to server failed" >&2\n' "exit 1\n"
        )
    magic = "".join(f"\\x{b:02x}" for b in PGDMP_MAGIC)
    stub = bin_dir / "pg_dump"
    stub.write_text(
        _STUB_TEMPLATE.format(
            failure_block=failure_block, magic=magic, sql=PLAIN_SQL_DUMP
        )
    )
    stub.chmod(0o755)


def _run_backup(tmp_path: Path, *, fail: bool = False, env_extra=None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_pg_dump_stub(bin_dir, fail=fail)

    backup_dir = tmp_path / "backups"
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["BACKUP_DIR"] = str(backup_dir)
    env["PGDATABASE"] = "regengine"
    env.pop("S3_BUCKET", None)
    env.pop("RETENTION_DAYS", None)
    if env_extra:
        env.update(env_extra)

    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
    )
    return proc, backup_dir


def test_backup_artifact_is_real_gzip_not_a_custom_archive(tmp_path):
    """The `.sql.gz` the script writes must actually be gzip.

    Fails against the pre-#2937 script, which wrote a PGDMP archive here.
    """
    proc, backup_dir = _run_backup(tmp_path)
    assert proc.returncode == 0, proc.stderr

    dumps = sorted(backup_dir.glob("regengine_*.sql.gz"))
    assert len(dumps) == 1, f"expected one backup, got {dumps}"
    blob = dumps[0].read_bytes()

    assert not blob.startswith(
        PGDMP_MAGIC
    ), "backup is a pg_dump custom archive named .sql.gz - unrestorable by the runbook"
    assert blob[:2] == b"\x1f\x8b", "backup is not gzip-compressed data"


def test_documented_restore_pipeline_recovers_the_sql(tmp_path):
    """`gunzip -c <backup>` must yield the SQL stream psql is fed.

    This is the runbook's restore pipeline (docs/runbooks/disaster-recovery.md)
    reduced to the part that does not need a live server: decompress, and check
    that what comes out is the SQL psql would replay.
    """
    proc, backup_dir = _run_backup(tmp_path)
    assert proc.returncode == 0, proc.stderr
    dump = next(iter(sorted(backup_dir.glob("regengine_*.sql.gz"))))

    # Exactly what `gunzip -c` does, and it must not raise.
    recovered = gzip.decompress(dump.read_bytes()).decode()

    assert "PostgreSQL database dump" in recovered
    assert "CREATE TABLE public.traceability_lot" in recovered
    assert "INSERT INTO public.traceability_lot" in recovered


def test_failed_dump_leaves_no_decoy_file(tmp_path):
    """A failed pg_dump must exit non-zero and leave no plausible 'backup'.

    Fails against the pre-#2937 script: `> "${DUMP_FILE}"` created and
    truncated the target before pg_dump ran, so a failure left a zero-byte
    file with a correct-looking name.
    """
    proc, backup_dir = _run_backup(tmp_path, fail=True)

    assert proc.returncode != 0, "script reported success despite pg_dump failing"
    leftovers = list(backup_dir.glob("*")) if backup_dir.exists() else []
    assert leftovers == [], f"failed run left a decoy backup: {leftovers}"


def test_default_retention_covers_the_fsma_24_month_window(tmp_path):
    """Default retention must not destroy the record inside FSMA 204's window.

    Fails against the pre-#2937 script, whose default was 30 days while its
    own header cited a 24-month requirement.
    """
    proc, _ = _run_backup(tmp_path)
    assert proc.returncode == 0, proc.stderr

    import re

    match = re.search(r"older than (\d+) days", proc.stdout)
    assert match, f"could not find retention line in output:\n{proc.stdout}"
    assert int(match.group(1)) >= 730, (
        "default RETENTION_DAYS is shorter than the 24 months the script's own "
        "header cites for FSMA 204"
    )


def test_script_and_runbook_describe_the_same_format():
    """Producer and consumer must not diverge again (the root of #2937)."""
    runbook = RUNBOOK.read_text()
    # Executable lines only - the script's header deliberately *names*
    # --format=custom to explain why it must not be used.
    script = "\n".join(
        line
        for line in SCRIPT.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )

    assert (
        "--format=custom" not in script and "-Fc" not in script
    ), "script emits a custom archive; the runbook restore uses `gunzip -c | psql`"
    assert "| gzip" in script, "script must pipe plain SQL through gzip"
    assert (
        "gunzip -c backups/postgres/regengine_YYYY-MM-DD.sql.gz" in runbook
    ), "runbook restore command changed; re-check it still matches the script"
    assert ".sql.gz" in script


# ---------------------------------------------------------------------------
# Full end-to-end round trip. Runs only where a PostgreSQL server is reachable.
# ---------------------------------------------------------------------------


def _server_reachable() -> bool:
    if not shutil.which("pg_isready") or not shutil.which("psql"):
        return False
    return (
        subprocess.run(
            ["pg_isready"], capture_output=True, timeout=15
        ).returncode
        == 0
    )


@pytest.mark.skipif(
    not _server_reachable(), reason="no reachable PostgreSQL server for round trip"
)
def test_live_roundtrip_restores_seeded_rows(tmp_path):
    """Back up a seeded DB, then restore it with the runbook's exact command."""
    src, dst = "regengine_bkuptest_src", "regengine_bkuptest_dst"

    def psql(db, sql, **kw):
        return subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=1", "-d", db, "-c", sql],
            capture_output=True,
            text=True,
            timeout=60,
            **kw,
        )

    for db in (src, dst):
        subprocess.run(["dropdb", "--if-exists", db], capture_output=True, timeout=60)
        assert (
            subprocess.run(["createdb", db], capture_output=True, timeout=60).returncode
            == 0
        )
    try:
        psql(src, "CREATE TABLE traceability_lot (id serial primary key, lot_code text)")
        psql(src, "INSERT INTO traceability_lot (lot_code) VALUES ('LOT-A-001'), ('O''Brien (US)')")

        backup_dir = tmp_path / "backups"
        env = dict(os.environ, BACKUP_DIR=str(backup_dir), PGDATABASE=src)
        env.pop("S3_BUCKET", None)
        proc = subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=300
        )
        assert proc.returncode == 0, proc.stderr

        dump = next(iter(sorted(backup_dir.glob(f"{src}_*.sql.gz"))))

        # The runbook's restore pipeline, verbatim apart from the docker wrapper.
        restore = subprocess.run(
            f'gunzip -c "{dump}" | psql -v ON_ERROR_STOP=1 -d {dst}',
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert restore.returncode == 0, restore.stderr

        out = subprocess.run(
            ["psql", "-tA", "-d", dst, "-c", "select count(*) from traceability_lot"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert out.stdout.strip() == "2", out.stderr
    finally:
        for db in (src, dst):
            subprocess.run(["dropdb", "--if-exists", db], capture_output=True, timeout=60)


def test_verification_survives_a_realistically_sized_dump(tmp_path):
    """A real dump must not be destroyed by its own integrity check.

    Found by review, not by the tests above: the verification step piped
    `gunzip -c` into `head -n 20`. Under `set -o pipefail`, head closes the pipe
    after 20 lines, gunzip dies of SIGPIPE (141), and pipefail propagates that
    status -- so verification failed and the EXIT trap deleted a perfectly good
    backup. Every test above used a fixture small enough that gunzip finished
    before head exited, so none of them could catch it. This one emits enough
    output that gunzip is still writing when head is done.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "pg_dump"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "echo '--'\n"
        "echo '-- PostgreSQL database dump'\n"
        "echo '--'\n"
        # ~200k lines: far past head's 20-line cutoff and past the pipe buffer.
        "for i in $(seq 1 200000); do\n"
        "  echo \"INSERT INTO traceability_lot VALUES ($i, 'padding padding padding');\"\n"
        "done\n"
    )
    stub.chmod(0o755)

    backup_dir = tmp_path / "backups"
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["BACKUP_DIR"] = str(backup_dir)
    env["PGDATABASE"] = "regengine"
    env.pop("S3_BUCKET", None)
    env.pop("RETENTION_DAYS", None)

    proc = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True,
        cwd=tmp_path, timeout=300,
    )

    assert proc.returncode == 0, (
        f"backup of a realistically-sized database failed:\n{proc.stdout}\n{proc.stderr}"
    )

    dumps = list(backup_dir.rglob("*.sql.gz"))
    assert dumps, (
        "verification deleted a valid backup -- the EXIT trap fired on a "
        f"SIGPIPE from the integrity check.\n{proc.stdout}\n{proc.stderr}"
    )

    # And it is genuinely the dump, not a truncated artifact.
    with gzip.open(dumps[0], "rt") as handle:
        head = "".join(next(handle) for _ in range(3))
    assert "PostgreSQL database dump" in head
