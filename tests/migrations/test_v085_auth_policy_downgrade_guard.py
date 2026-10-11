"""v085 downgrade must not silently rewrite live auth policy rows.

``f8a9b0c1d2e3`` (v085) normalises unrecognised
``public.organizations.enforced_auth_policy`` values to ``standard`` on the
way up, but on the way down it sets every ``standard`` and ``sso_only`` row
back to ``passwordless_email_code``, including organisations that already
carried those values before the revision ran. A rollback therefore silently
lifts SSO enforcement and re-upgrading cannot restore it. Like v108 (#2827),
the downgrade must refuse to run without the explicit two-variable
acknowledgement, and the rollback runbook must name the revision.

These tests fail on the pre-fix revision (no guard, no runbook entry).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "alembic/versions/20260623_f8a9b0c1d2e3_v085_enterprise_sso_policy.py"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "MIGRATION_ROLLBACK.md"
REVISION = "f8a9b0c1d2e3"  # pragma: allowlist secret


def _load():
    spec = importlib.util.spec_from_file_location("v085", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downgrade_consults_both_ack_variables() -> None:
    """The guard must read the same two variables the baseline guard uses."""
    source = MIGRATION.read_text(encoding="utf-8")
    missing = [var for var in ("REGENGINE_ENV", "REGENGINE_ALLOW_BASELINE_DOWNGRADE") if var not in source]
    assert not missing, (
        f"v085 ({REVISION}) rewrites auth policy rows it did not create in its downgrade but does not consult {missing}"
    )


def test_downgrade_refuses_without_acknowledgement(monkeypatch) -> None:
    """No variables, no downgrade. This is the incident-time default."""
    migration = _load()
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    monkeypatch.delenv("REGENGINE_ALLOW_BASELINE_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError):
        migration._require_destructive_downgrade_ack()


def test_downgrade_acknowledgement_matrix(monkeypatch) -> None:
    """Both variables together open only non-production environments."""
    migration = _load()
    require = migration._require_destructive_downgrade_ack

    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("REGENGINE_ALLOW_BASELINE_DOWNGRADE", "1")
    require()

    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("REGENGINE_ALLOW_BASELINE_DOWNGRADE", "1")
    with pytest.raises(RuntimeError):
        require()

    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("REGENGINE_ALLOW_BASELINE_DOWNGRADE", "0")
    with pytest.raises(RuntimeError):
        require()


def test_downgrade_calls_the_guard_first() -> None:
    """The guard must run before any downgrade statement, not after."""
    import ast

    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    downgrade = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "downgrade"
    )
    first = downgrade.body[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call), (
        "v085 downgrade() must call the acknowledgement guard as its first statement"
    )
    func = first.value.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    assert "ack" in name.lower(), f"v085 downgrade() must call the acknowledgement guard first, found {name!r}"


def test_runbook_names_the_revision() -> None:
    """An operator reads the runbook before rolling back, not after."""
    assert REVISION in RUNBOOK.read_text(encoding="utf-8"), (
        f"v085 ({REVISION}) rewrites live auth policy rows on downgrade but appears nowhere "
        f"in {RUNBOOK.relative_to(REPO_ROOT)}"
    )
