"""Run the real review workflow gate against changed historical migrations."""

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/pr-gate.yml").read_text())
GATE = next(
    step["run"]
    for job in WORKFLOW["jobs"].values()
    for step in job["steps"]
    if step.get("name") == "New migrations enable RLS on new tables"
)


@pytest.mark.parametrize(
    "addition,expected",
    [
        ('\nop.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")\n', 0),
        ('\nop.create_table("new_unprotected_table")\n', 1),
        (
            '\nop.create_table("new_protected_table")\nop.execute("ALTER TABLE new_protected_table ENABLE ROW LEVEL SECURITY")\n',
            0,
        ),
    ],
)
def test_checks_new_table_operations_without_blocking_old_backfill_repairs(tmp_path, addition, expected):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init")
    git("config", "user.email", "ci@example.test")
    git("config", "user.name", "CI fixture")
    migration = tmp_path / "alembic/versions/historical.py"
    migration.parent.mkdir(parents=True)
    migration.write_text('op.create_table("historical_table")\n')
    git("add", ".")
    git("commit", "-m", "fixture base")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    migration.write_text(migration.read_text() + addition)
    git("add", ".")
    git("commit", "-m", "fixture change")
    result = subprocess.run(["bash", "-e", "-c", GATE], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == expected, result.stdout + result.stderr
    if expected:
        assert "creates a table without enabling RLS" in result.stdout
