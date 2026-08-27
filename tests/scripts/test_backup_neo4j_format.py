"""Regression tests for scripts/backup_neo4j.sh (#2939).

The defect: the script hand-rolled a gzipped Cypher export (`.cypher.gz`),
but the only documented Neo4j restore in the repo is

    neo4j-admin database load neo4j --from-path=<dir> --overwrite-destination=true

(docs/runbooks/disaster-recovery.md), which reads a binary `neo4j-admin`
dump and cannot ingest Cypher text at all.  The generated Cypher was also
unsound on its own terms:

  * node identity was discarded (`elementId` was selected, then dropped), so
    relationships were rebuilt by MATCHing `id`/`gln`/`lot_code`/`name`/`uid`
    — none enforced unique — fabricating edges where a match was ambiguous
    and losing them where it matched nothing;
  * temporal values were emitted as bare unquoted literals, e.g.
    `shipped_at: 2026-01-02T03:04:05+00:00`, a Cypher syntax error;
  * a blanket `.replace("(", "")` rewrote property values, turning
    `Acme (US)` into `Acme US` so the MATCH found no node.

The fix replaces the exporter with a thin `neo4j-admin database dump`
wrapper — the producer the runbook already documents.  These tests stub
`neo4j-admin` on PATH so they need no Neo4j installation.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "backup_neo4j.sh"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "disaster-recovery.md"

# Stub that mirrors the real tool's contract: `dump` writes <database>.dump
# into --to-path; `load` reads <database>.dump from --from-path and fails on
# anything that is not a neo4j-admin dump.
_NEO4J_ADMIN_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
sub="$2"; db="$3"; shift 3
path=""
for a in "$@"; do
  case "$a" in --to-path=*|--from-path=*) path="${a#*=}";; esac
done
case "$sub" in
  dump)
    if [ "${STUB_FAIL:-0}" = "1" ]; then
      echo "Dump failed: database is in use" >&2
      exit 1
    fi
    printf 'NEO4JDUMP\x01\x00binary-store-files' > "${path}/${db}.dump"
    echo "Done: dumped ${db}" ;;
  load)
    if [ ! -f "${path}/${db}.dump" ]; then
      echo "Load failed: '${path}/${db}.dump' does not exist" >&2
      exit 1
    fi
    head -c 9 "${path}/${db}.dump" | grep -q NEO4JDUMP \
      || { echo "Load failed: not a neo4j-admin dump" >&2; exit 1; }
    echo "Done: loaded ${db}" ;;
esac
"""


def _harness(tmp_path: Path, *, fail: bool = False):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "neo4j-admin"
    stub.write_text(_NEO4J_ADMIN_STUB)
    stub.chmod(0o755)

    backup_dir = tmp_path / "backups"
    env = dict(os.environ)
    # Put the stub first, and drop any real docker from PATH so the script
    # cannot silently take the container path during tests.
    env["PATH"] = f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin"
    env["BACKUP_DIR"] = str(backup_dir)
    env["SKIP_SERVICE_CONTROL"] = "1"
    env["NEO4J_DATABASE"] = "neo4j"
    if fail:
        env["STUB_FAIL"] = "1"
    return env, backup_dir


def _run(tmp_path: Path, *, fail: bool = False, env_extra=None):
    env, backup_dir = _harness(tmp_path, fail=fail)
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


def test_produces_a_neo4j_admin_dump_not_a_cypher_export(tmp_path):
    """The artifact must be `<database>.dump`, not `.cypher.gz`."""
    proc, backup_dir = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr

    assert not list(
        backup_dir.rglob("*.cypher.gz")
    ), "script still emits a Cypher export the documented restore cannot read"

    dumps = list(backup_dir.rglob("neo4j.dump"))
    assert len(dumps) == 1, f"expected one neo4j.dump, found {dumps}"
    assert dumps[0].read_bytes().startswith(b"NEO4JDUMP")


def test_documented_restore_command_consumes_the_artifact(tmp_path):
    """`neo4j-admin database load --from-path=<dir>` must accept the output.

    This is the runbook's restore command run against the backup the script
    just produced - the round trip that was impossible before #2939.
    """
    env, backup_dir = _harness(tmp_path)
    proc = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True,
        cwd=tmp_path, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr

    run_dirs = [p for p in backup_dir.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1, run_dirs

    restore = subprocess.run(
        [
            "neo4j-admin", "database", "load", "neo4j",
            f"--from-path={run_dirs[0]}", "--overwrite-destination=true",
        ],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert restore.returncode == 0, (
        f"documented restore rejected the backup: {restore.stderr}"
    )


def test_no_hand_rolled_cypher_generation_remains(tmp_path):
    """The unsound exporter must be gone, not merely bypassed."""
    script = SCRIPT.read_text()
    for fragment, why in [
        ("CREATE (:", "emits CREATE statements with no correlating node identity"),
        ("match_clause", "rebuilds edges by matching non-unique node properties"),
        ('replace("(", "")', "mangles property values containing parentheses"),
        ("lot_code", "treats lot_code as a unique node identifier"),
    ]:
        assert fragment not in script, f"script still {why}"


def test_failed_dump_leaves_no_decoy(tmp_path):
    """A failed dump must exit non-zero and retain nothing."""
    proc, backup_dir = _run(tmp_path, fail=True)

    assert proc.returncode != 0, "script reported success despite a failed dump"
    leftovers = list(backup_dir.rglob("*")) if backup_dir.exists() else []
    assert not [p for p in leftovers if p.is_file()], (
        f"failed run left a decoy backup: {leftovers}"
    )


def test_retention_keeps_only_the_requested_number_of_runs(tmp_path):
    """Old run directories are pruned; the newest survive."""
    env, backup_dir = _harness(tmp_path)
    env["RETAIN_BACKUPS"] = "2"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for stamp in ("20200101_000000", "20200102_000000", "20200103_000000"):
        d = backup_dir / stamp
        d.mkdir()
        (d / "neo4j.dump").write_bytes(b"NEO4JDUMPold")

    proc = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True,
        cwd=tmp_path, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr

    remaining = sorted(p.name for p in backup_dir.iterdir() if p.is_dir())
    assert len(remaining) == 2, f"expected 2 retained runs, got {remaining}"
    # The freshly created run (today's timestamp) must be among the survivors.
    assert remaining[-1] not in {"20200101_000000", "20200102_000000"}


def test_script_and_runbook_agree_on_the_neo4j_format():
    """Producer and consumer must not diverge again (the root of #2939)."""
    script = SCRIPT.read_text()
    runbook = RUNBOOK.read_text()

    assert "neo4j-admin database dump" in script
    assert "neo4j-admin database load" in runbook, (
        "runbook restore changed; re-check it still matches the script"
    )
    assert ".cypher" not in script.replace("`.cypher.gz`", ""), (
        "script references a Cypher artifact outside its explanatory header"
    )
    # The header must no longer claim APOC is used - it never was.
    assert "using APOC" not in script
