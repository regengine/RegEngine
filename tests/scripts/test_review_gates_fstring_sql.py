"""The f-string SQL gate must catch both quote styles (f"..." and f'...')."""

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/review-gates.yml").read_text())
GATE = next(
    step["run"]
    for job in WORKFLOW["jobs"].values()
    for step in job["steps"]
    if step.get("name") == "No f-string SQL in Python services"
)


def run_gate(tmp_path):
    return subprocess.run(["bash", "-c", GATE], cwd=tmp_path, text=True, capture_output=True)


def write_service(tmp_path, content):
    service = tmp_path / "services" / "mod.py"
    service.parent.mkdir(parents=True, exist_ok=True)
    service.write_text(content + "\n")


@pytest.mark.parametrize(
    "offending_line",
    [
        'query = f"SELECT * FROM users WHERE id = {user_id}"',
        "query = f'SELECT * FROM users WHERE id = {user_id}'",
        'query = f"INSERT INTO users VALUES ({name})"',
        "query = f'UPDATE users SET name = {name}'",
        'query = f"DELETE FROM users WHERE id = {user_id}"',
        "query = f'DROP TABLE {table}'",
    ],
)
def test_gate_flags_fstring_sql_in_both_quote_styles(tmp_path, offending_line):
    write_service(tmp_path, offending_line)
    result = run_gate(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "f-string SQL" in result.stdout


def test_gate_allows_parameterized_queries(tmp_path):
    write_service(
        tmp_path,
        'result = await session.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id})',
    )
    result = run_gate(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_allows_non_sql_fstrings(tmp_path):
    write_service(tmp_path, 'message = f"hello {name}"')
    result = run_gate(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
