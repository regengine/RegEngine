"""Tests for scripts/check_schema_channels.py.

Each test builds a tiny repository layout in a temp directory (an
``alembic/versions`` file plus channel files) and calls the module's
functions directly, so the suite stays fast and needs no git or database.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "check_schema_channels.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_schema_channels", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()

_REV = "0a329588b824"
_REV_FILE = "20261016_0a329588b824_v131_tool_leads_utm.py"


def _fake_repo(tmp_path: Path) -> Path:
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / _REV_FILE).write_text(f'revision = "{_REV}"\ndown_revision = "a5e7c9b2d341"\n')
    (tmp_path / "supabase" / "migrations").mkdir(parents=True)
    (tmp_path / "sql" / "prod-apply").mkdir(parents=True)
    return tmp_path


def _write(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


_GOOD_HEADER = f"-- alembic-revision: {_REV}\n-- rendered-from: alembic/versions/{_REV_FILE} (upgrade)\n"


def test_headered_render_passes(tmp_path):
    repo = _fake_repo(tmp_path)
    body = _GOOD_HEADER + "ALTER TABLE public.tool_leads ADD COLUMN utm_source VARCHAR(100);\n"
    _write(repo, "sql/prod-apply/apply_v131_tool_leads_utm.sql", body)
    problems, scanned = _mod.scan(repo)
    assert scanned == 1
    assert problems == []


def test_missing_both_headers_fails(tmp_path):
    repo = _fake_repo(tmp_path)
    _write(repo, "supabase/migrations/20261101000000_new_thing.sql", "CREATE TABLE public.new_thing (id int);\n")
    problems, _ = _mod.scan(repo)
    assert len(problems) == 2
    assert "missing '-- alembic-revision" in problems[0]
    assert "missing '-- rendered-from" in problems[1]


def test_unknown_revision_fails(tmp_path):
    repo = _fake_repo(tmp_path)
    _write(
        repo,
        "sql/prod-apply/apply_mystery.sql",
        "-- alembic-revision: ffffffffffff\n"
        + f"-- rendered-from: alembic/versions/{_REV_FILE} (upgrade)\nSELECT 1;\n",
    )
    problems, _ = _mod.scan(repo)
    assert any("does not exist in alembic/versions" in p for p in problems)


def test_rendered_from_must_match_revision_file(tmp_path):
    repo = _fake_repo(tmp_path)
    _write(
        repo,
        "sql/prod-apply/apply_v131_tool_leads_utm.sql",
        f"-- alembic-revision: {_REV}\n-- rendered-from: alembic/versions/20260101_other.py (upgrade)\nSELECT 1;\n",
    )
    problems, _ = _mod.scan(repo)
    assert len(problems) == 1
    assert "rendered-from names" in problems[0]


def test_precheck_and_downgrade_kinds_accepted(tmp_path):
    repo = _fake_repo(tmp_path)
    for kind in ("precheck", "downgrade"):
        _write(
            repo,
            f"sql/prod-apply/{kind}_v131.sql",
            f"-- alembic-revision: {_REV}\n-- rendered-from: alembic/versions/{_REV_FILE} ({kind})\nSELECT 1;\n",
        )
    problems, scanned = _mod.scan(repo)
    assert scanned == 2
    assert problems == []


def test_header_outside_window_is_missing(tmp_path):
    repo = _fake_repo(tmp_path)
    body = "-- filler\n" * _mod.HEADER_WINDOW_LINES + _GOOD_HEADER
    _write(repo, "sql/prod-apply/late_header.sql", body)
    problems, _ = _mod.scan(repo)
    assert len(problems) == 2


def test_exempt_reconcile_precheck_needs_no_header(tmp_path):
    repo = _fake_repo(tmp_path)
    _write(repo, "sql/prod-apply/PRECHECK_alembic_version_reconcile.sql", "BEGIN READ ONLY;\nSELECT 1;\nROLLBACK;\n")
    problems, _ = _mod.scan(repo)
    assert problems == []


def test_grandfathered_file_needs_no_header(tmp_path):
    repo = _fake_repo(tmp_path)
    name = sorted(_mod.GRANDFATHERED)[0]
    _write(repo, name, "SELECT 1;\n")
    problems, scanned = _mod.scan(repo)
    assert scanned == 1
    assert problems == []


def test_stale_grandfathered_entries_are_reported(tmp_path):
    repo = _fake_repo(tmp_path)
    name = sorted(_mod.GRANDFATHERED)[0]
    _write(repo, name, "SELECT 1;\n")
    stale = _mod.stale_grandfathered(repo)
    assert name not in stale
    assert len(stale) == len(_mod.GRANDFATHERED) - 1


def test_main_fails_on_stale_grandfather_entry(tmp_path, capsys):
    repo = _fake_repo(tmp_path)
    assert _mod.main(["--repo-root", str(repo)]) == 1
    assert "no longer exists" in capsys.readouterr().out


def test_grandfather_list_matches_tree():
    """Every grandfathered name exists, and no grandfathered file carries a header
    (if one gains a header, drop it from the list)."""
    for name in _mod.GRANDFATHERED:
        path = _REPO_ROOT / name
        assert path.exists(), f"stale GRANDFATHERED entry: {name}"
        revision, rendered, _ = _mod.read_headers(path)
        assert revision is None and rendered is None, f"{name} has a header; remove it from GRANDFATHERED"


def test_real_repository_is_clean():
    problems, scanned = _mod.scan(_REPO_ROOT)
    assert scanned >= 50
    assert problems == [], "\n".join(problems)
    assert _mod.stale_grandfathered(_REPO_ROOT) == []


def test_revision_regex_matches_both_assignment_styles():
    assert _mod._REVISION_ASSIGNMENT.search('revision: str = "abc123abc123"').group(1) == "abc123abc123"
    assert _mod._REVISION_ASSIGNMENT.search("revision = 'abc123abc123'").group(1) == "abc123abc123"
    assert re.fullmatch(r"[0-9a-f]{12}", _REV)


@pytest.mark.parametrize(
    "line,expected",
    [
        ("-- alembic-revision: 0a329588b824", "0a329588b824"),
        ("--   alembic-revision:   0A329588B824  ", "0a329588b824"),
        ("-- alembic-revision: 0a32", None),
        ("# alembic-revision: 0a329588b824", None),
    ],
)
def test_revision_header_regex(line, expected, tmp_path):
    path = tmp_path / "f.sql"
    path.write_text(line + "\n")
    revision, _, _ = _mod.read_headers(path)
    assert revision == expected
