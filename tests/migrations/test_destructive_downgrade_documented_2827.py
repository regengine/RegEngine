"""A downgrade that destroys pre-existing rows must be guarded and documented — #2827.

Most Alembic downgrades drop what their own upgrade added; losing a column you
just created is not data loss. A different and far more dangerous shape is a
downgrade that issues ``DELETE`` or ``TRUNCATE`` against rows it did **not**
create, in order to make an older constraint applicable again.

The v108 revision (``a43b0fb1edd0``) does exactly that::

    op.execute("DELETE FROM fsma.rule_evaluations WHERE result = 'error'")

``alembic/sql/V044__versioned_rules_engine.sql`` describes
``fsma.rule_evaluations`` as "the evidentiary record that a specific check was
run against a specific record with a specific outcome". Deleting the error
verdicts destroys precisely the evidence that a check ran and failed to
complete — and a downgrade is most likely during an incident, which is exactly
when those rows are most numerous and most valuable.

Two protections must both hold for every revision of this shape:

1. **A runtime guard.** The revision must refuse to run without an explicit
   two-variable acknowledgement, the same shape the baseline downgrade uses.
   Note that ``alembic/env.py:_guard_baseline_downgrade`` only covers
   ``downgrade base`` — a targeted ``alembic downgrade -1`` reaches v108
   without it, so the guard has to live in the revision itself.
2. **A runbook entry.** ``docs/runbooks/MIGRATION_ROLLBACK.md`` is what an
   operator reads *before* running the command. A guard that stops them with
   an unexplained ``RuntimeError`` is better than silent data loss, but it is
   not a substitute for telling them what the revision does and what the
   recovery path is.

Detection parses each revision with ``ast`` and inspects only the ``downgrade``
function body. An earlier line-based scan of these files reported four
``DELETE FROM`` statements in v078's downgrade; in fact v078's ``downgrade()``
is ``pass`` and those statements belong to *upgrade* helpers defined further
down the file. Anything less precise than an AST walk produces that false
positive.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS_DIR = _REPO_ROOT / "alembic" / "versions"
_RUNBOOK = _REPO_ROOT / "docs" / "runbooks" / "MIGRATION_ROLLBACK.md"

# Statements that destroy rows the revision's own upgrade did not create.
# DROP COLUMN / DROP TABLE are deliberately excluded: reversing an ADD COLUMN
# is the normal, correct shape of a downgrade.
_DESTRUCTIVE = re.compile(r"\bDELETE\s+FROM\b|\bTRUNCATE\s+TABLE\b", re.IGNORECASE)

# The acknowledgement pair the baseline downgrade established (#1264).
_ACK_VARS = ("REGENGINE_ENV", "REGENGINE_ALLOW_BASELINE_DOWNGRADE")


def _downgrade_node(tree: ast.Module) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "downgrade":
            return node
    return None


def _sql_strings(node: ast.AST) -> list[str]:
    """Every string literal lexically inside ``node``."""
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _revision_id(tree: ast.Module) -> str | None:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "revision":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    return None


def _destructive_revisions() -> list[tuple[str, str, str]]:
    """Return (filename, revision_id, offending_sql) for each such revision."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        downgrade = _downgrade_node(tree)
        if downgrade is None:
            continue
        for sql in _sql_strings(downgrade):
            if _DESTRUCTIVE.search(sql):
                found.append((path.name, _revision_id(tree) or "?", " ".join(sql.split())))
                break
    return found


_DESTRUCTIVE_REVISIONS = _destructive_revisions()


def test_detection_finds_the_known_case():
    """Guard the guard.

    If this returns nothing, every parametrised test below is skipped and the
    suite passes while checking nothing. v108 is the known member of this set;
    it must be detected. If v108 is ever legitimately removed or rewritten,
    update this assertion deliberately rather than letting the set empty out.
    """
    revisions = {rev for _, rev, _ in _DESTRUCTIVE_REVISIONS}
    assert "a43b0fb1edd0" in revisions, (
        f"v108 (a43b0fb1edd0) DELETEs fsma.rule_evaluations rows in its downgrade "
        f"but was not detected. Detected instead: {sorted(revisions)}. The AST walk "
        f"has probably drifted from the file's shape."
    )


@pytest.mark.parametrize(
    ("filename", "revision", "sql"),
    _DESTRUCTIVE_REVISIONS,
    ids=[f"{rev}" for _, rev, _ in _DESTRUCTIVE_REVISIONS] or None,
)
def test_destructive_downgrade_has_an_acknowledgement_guard(filename: str, revision: str, sql: str):
    """The revision must refuse to run without the explicit opt-in."""
    source = (_VERSIONS_DIR / filename).read_text(encoding="utf-8")
    missing = [var for var in _ACK_VARS if var not in source]
    assert not missing, (
        f"{filename} ({revision}) destroys pre-existing rows in its downgrade:\n"
        f"    {sql}\n"
        f"...but does not consult {missing}. A targeted `alembic downgrade -1` reaches "
        f"this revision without env.py's baseline guard, so the acknowledgement must "
        f"live in the revision itself (#2827)."
    )


@pytest.mark.parametrize(
    ("filename", "revision", "sql"),
    _DESTRUCTIVE_REVISIONS,
    ids=[f"{rev}" for _, rev, _ in _DESTRUCTIVE_REVISIONS] or None,
)
def test_destructive_downgrade_is_in_the_rollback_runbook(filename: str, revision: str, sql: str):
    """An operator reads the runbook before running the command, not after."""
    runbook = _RUNBOOK.read_text(encoding="utf-8")
    assert revision in runbook, (
        f"{filename} ({revision}) destroys pre-existing rows in its downgrade:\n"
        f"    {sql}\n"
        f"...but revision id {revision!r} appears nowhere in "
        f"{_RUNBOOK.relative_to(_REPO_ROOT)}. Its 'What Each Downgrade Does' table is "
        f"what an operator consults before rolling back; a revision that destroys FDA "
        f"evidentiary data must be listed there (#2827)."
    )
