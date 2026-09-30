"""Guard: no ``:param::type`` inside SQL string literals.

SQLAlchemy's ``text()`` bind parser (``(?<![:\\w\\\\]):(\\w+)(?!:)``) refuses
to treat ``:data`` as a bind when it is followed by a ``::`` cast, so the
statement reaches Postgres with the literal token ``:data::jsonb`` and fails
with ``syntax error at or near ":"`` on every driver.  This shipped five
times (incident create/update, tenant obligation seeding, three exchange
package lookups); the stubbed-session unit tests never see the database,
so only a source scan catches the next one.

Write ``CAST(:param AS type)`` instead — the form the rest of the codebase
already uses.

Static AST scan of string literals; no DB, no network, no imports of the
scanned modules.  Comments are not scanned, so prose may mention the trap.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ("services", "server", "alembic/versions", "scripts")
EXCLUDED_DIR_NAMES = {"tests", "__pycache__", "node_modules", "venv", ".venv"}

# A bind name directly followed by a ``::`` cast.  The lookbehind mirrors
# SQLAlchemy's own: a leading ``:`` (the cast itself, ``x::regclass::text``)
# or word character is not a bind.
_BIND_THEN_CAST = re.compile(r"(?<![:\w\\]):[A-Za-z_]\w*::[A-Za-z_]")


def _production_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if EXCLUDED_DIR_NAMES.intersection(path.relative_to(REPO_ROOT).parts):
                continue
            files.append(path)
    return files


def _string_literals(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def _offenders() -> list[str]:
    found: list[str] = []
    for path in _production_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # pragma: no cover - the lint gate owns this
            raise AssertionError(f"{path}: {exc}") from exc
        for lineno, value in _string_literals(tree):
            for match in _BIND_THEN_CAST.finditer(value):
                offset = value.count("\n", 0, match.start())
                found.append(f"{path.relative_to(REPO_ROOT)}:{lineno + offset}: {match.group(0)}")
    return found


def test_scan_covers_production_code():
    files = _production_python_files()
    assert len(files) > 200, f"scan collapsed to {len(files)} files"
    assert not any("tests" in p.relative_to(REPO_ROOT).parts for p in files)


def test_no_bind_parameter_is_followed_by_a_double_colon_cast():
    offenders = _offenders()
    assert not offenders, (
        "':param::type' is never bound by SQLAlchemy text(); use CAST(:param AS type):\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    ("literal", "hit"),
    [
        ("VALUES (:id, :tid, :data::jsonb)", True),
        ("WHERE id = :package_id::uuid", True),
        ("SELECT seed_obligations_for_tenant(:tid::uuid)", True),
        ("WHERE id = CAST(:package_id AS uuid)", False),
        ("'shared catalog ' || sd.classid::regclass::text", False),
        ("SELECT '{\"a\":1}'::jsonb", False),
        ("SET LOCAL app.tenant_id = :tid", False),
    ],
)
def test_pattern_matches_only_bind_then_cast(literal, hit):
    assert bool(_BIND_THEN_CAST.search(literal)) is hit
