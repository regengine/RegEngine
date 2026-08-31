"""Repo guard for #2920 — no checked-in SQL may mint a login role with a
literal password.

``services/admin/migrations/setup_app_user.sql`` created ``app_user`` with a
hardcoded ``LOGIN PASSWORD`` and then granted it ``ALL PRIVILEGES ON ALL
TABLES/SEQUENCES IN SCHEMA public``. It sat in a directory named
``migrations`` and carried an "already done in V6" comment, so it read like
part of a migration sequence, but nothing executed it: the only automated
consumer of that directory is
``scripts/railway/apply_sql_migrations.sh`` (via
``scripts/railway/run_phase1a_migrations.sh``), whose default glob is
``V*.sql`` — and no ``V*.sql`` file remains there, the raw SQL chain having
been consolidated into Alembic.

Anyone who ran it by hand would have undone the least-privilege role model
the repo's security thesis rests on: the maintained roles are NOLOGIN
(``alembic/sql/V002__fsma_cte_persistence.sql``) or take their password from
a psql variable (``runbooks/prod-least-privilege-db-role.sql``), never a
literal.

The script also duplicated migration-owned state:
``alembic/versions/20260505_5ac9e7b1d402_v078_orphan_migration_forward_ports.py``
already enables and forces RLS on ``public.review_items`` via
``_tenant_rls``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Fail loudly rather than vacuously passing if the layout ever moves.
assert (REPO_ROOT / "pyproject.toml").is_file(), f"repo root misdetected: {REPO_ROOT}"

_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}

# CREATE/ALTER ROLE|USER ... PASSWORD '<literal>'. A psql variable
# (PASSWORD :'app_pw') or a placeholder is deliberately not matched.
_LOGIN_CREDENTIAL = re.compile(
    r"\b(?:CREATE|ALTER)\s+(?:ROLE|USER)\b[^;]*?\bPASSWORD\s*'",
    re.IGNORECASE | re.DOTALL,
)

_REVIEW_ITEMS_RLS = re.compile(
    r"review_items\s+(?:ENABLE|FORCE)\s+ROW\s+LEVEL\s+SECURITY",
    re.IGNORECASE,
)


def _walk(suffixes: set[str]):
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if _SKIP_DIRS & set(path.relative_to(REPO_ROOT).parts):
            continue
        yield path


def test_orphaned_setup_app_user_sql_is_gone() -> None:
    """The script itself must not come back."""
    orphan = REPO_ROOT / "services" / "admin" / "migrations" / "setup_app_user.sql"
    assert not orphan.exists(), (
        "services/admin/migrations/setup_app_user.sql provisions a LOGIN role "
        "with a hardcoded password and ALL PRIVILEGES on schema public (#2920). "
        "If a verification role is needed for local RLS testing, bootstrap it "
        "from scripts/init-postgres.sh with the password read from the environment."
    )


def test_no_sql_file_creates_a_login_role_with_a_literal_password() -> None:
    """Least privilege is migration-owned: NOLOGIN roles, or a password
    supplied by psql variable / environment — never a literal in git."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _walk({".sql"})
        if _LOGIN_CREDENTIAL.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == [], f"SQL files mint a role with a hardcoded password (#2920): {offenders}"


def test_secrets_baseline_has_no_entry_for_the_deleted_script() -> None:
    """A stale baseline entry would silently re-allowlist the credential
    if the file were restored."""
    baseline_path = REPO_ROOT / ".secrets.baseline"
    if not baseline_path.is_file():
        pytest.skip(".secrets.baseline not present in this checkout")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert "services/admin/migrations/setup_app_user.sql" not in baseline.get("results", {})


def test_review_items_rls_is_owned_only_by_the_alembic_chain() -> None:
    """v078 ``_tenant_rls('public.review_items', ...)`` enables and forces
    RLS on the table; a second, unversioned copy is drift."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _walk({".sql", ".py", ".sh"})
        if not str(path.relative_to(REPO_ROOT)).startswith(("alembic/", "services/admin/tests/"))
        and _REVIEW_ITEMS_RLS.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == [], f"review_items RLS is declared outside the Alembic chain (#2920): {offenders}"
