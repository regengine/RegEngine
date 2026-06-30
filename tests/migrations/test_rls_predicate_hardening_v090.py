"""Static regression guard — v090 RLS predicate convergence (#2526).

v090 forward-ports the last live ``current_setting('app.tenant_id', ...)``
text-compare RLS policies onto the fail-hard ``tenant_id =
get_tenant_context()`` predicate. This test asserts the migration emits
the right SQL and the CI guard rejects new fail-open policies — all by
file/AST inspection, so it runs in CI without Docker. The behavioral
contract (a real Postgres session under each tenant context) is covered
by ``test_rls_predicate_hardening_v090_pg.py``, which skips when Docker
is unavailable.

Run via:
    pytest tests/migrations/test_rls_predicate_hardening_v090.py -v
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
V090_PATH = REPO_ROOT / "alembic" / "versions" / "20260629_a128f7f95db8_v090_rls_predicate_hardening.py"
GUARD_PATH = REPO_ROOT / "scripts" / "check_tenant_id_uuid_only.py"

# The 8 V042 tenant_* feature tables whose v051 split policies v090 replaces.
EXPECTED_FEATURE_TABLES = {
    "tenant_suppliers",
    "tenant_products",
    "tenant_team_members",
    "tenant_notification_prefs",
    "tenant_settings",
    "tenant_onboarding",
    "tenant_exchanges",
    "tenant_portal_links",
}


def _load_v090():
    spec = importlib.util.spec_from_file_location("v090_rls_predicate_hardening", V090_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def v090():
    assert V090_PATH.exists(), f"v090 migration not found at {V090_PATH}"
    return _load_v090()


def _feature_sql(v090) -> str:
    return "\n".join(v090._converge_feature_table(t) for t in v090._TENANT_FEATURE_TABLES)


def _operational_sql(v090) -> str:
    return "\n".join(v090._converge_operational_table(t, p) for t, p in v090._OPERATIONAL_TABLES)


def test_revision_chains_off_current_head(v090) -> None:
    """v090 RLS hardening must extend the current single head so it lands as
    the new single head. Re-chained onto the v090-heads merge revision
    (d1bdfe74d1fd) after #2544/#2546 each added a parallel v090 head."""
    assert v090.revision == "a128f7f95db8"
    assert v090.down_revision == "d1bdfe74d1fd", (
        f"v090 RLS hardening must revise the merge head (d1bdfe74d1fd); got {v090.down_revision!r}"
    )


def test_all_eight_feature_tables_covered(v090) -> None:
    assert set(v090._TENANT_FEATURE_TABLES) == EXPECTED_FEATURE_TABLES, (
        "v090 must convert exactly the 8 V042 tenant_* feature tables flagged in #2526"
    )


def test_feature_tables_drop_v051_split_policies(v090) -> None:
    """Each feature table must drop all four v051 text-compare policies."""
    sql = _feature_sql(v090)
    for table in EXPECTED_FEATURE_TABLES:
        for action in ("select", "insert", "update", "delete"):
            needle = f"DROP POLICY IF EXISTS tenant_isolation_{action} ON fsma.{table}"
            assert needle in sql, f"v090 must drop {table}'s v051 tenant_isolation_{action} policy"


def test_feature_tables_install_fail_hard_policy(v090) -> None:
    """Each feature table gets one fail-hard FOR ALL policy using
    get_tenant_context() (USING + WITH CHECK)."""
    sql = _feature_sql(v090)
    for table in EXPECTED_FEATURE_TABLES:
        assert f"CREATE POLICY tenant_isolation_{table}" in sql
    # Predicate is the canonical fail-hard helper, with both USING and CHECK.
    assert "tenant_id = get_tenant_context()" in v090._TENANT_POLICY
    assert "USING (" in sql and "WITH CHECK (" in sql


def test_operational_tables_converted(v090) -> None:
    """The two v048 operational tables are forward-ported too."""
    tables = {t for t, _ in v090._OPERATIONAL_TABLES}
    assert tables == {"fda_sla_requests", "chain_verification_log"}
    sql = _operational_sql(v090)
    assert "DROP POLICY IF EXISTS tenant_isolation_sla ON fsma.fda_sla_requests" in sql
    assert "DROP POLICY IF EXISTS tenant_isolation_chain_log ON fsma.chain_verification_log" in sql
    assert "tenant_id = get_tenant_context()" in v090._TENANT_POLICY


def _emitted_sql(v090) -> str:
    """SQL the migration actually runs — feature + operational helper output
    plus the literal task_queue block in ``upgrade``. Excludes the module
    docstring, which legitimately quotes the old patterns to explain the fix.
    """
    import inspect

    return "\n".join(
        (
            _feature_sql(v090),
            _operational_sql(v090),
            inspect.getsource(v090.upgrade),
        )
    )


def test_task_queue_policy_drops_fail_open_or_clause(v090) -> None:
    """task_queue's recreated policy must NOT carry the v050/v063
    ``OR current_setting('app.tenant_id', true) = ''`` clause — that is the
    exact cross-tenant leak #2526 calls out — and must use the fail-hard
    predicate instead."""
    sql = _emitted_sql(v090)
    # The empty-string OR clause must not appear in any emitted SQL.
    assert "= ''" not in sql, "v090 must not emit the fail-open empty-string OR clause"
    assert "CREATE POLICY tenant_isolation_tasks ON fsma.task_queue" in sql
    assert "USING (tenant_id = get_tenant_context())" in sql


def test_v090_introduces_no_text_compare_in_create_policy(v090) -> None:
    """The only current_setting() v090 may emit is the sysadmin bypass
    (regengine.is_sysadmin). It must never compare against app.tenant_id
    inside emitted policy SQL — that's the fail-open style being eliminated."""
    sql = _emitted_sql(v090)
    assert "current_setting('app.tenant_id'" not in sql, (
        "v090 must not emit a current_setting('app.tenant_id', ...) text-compare"
    )
    # The sysadmin bypass branch (the only legitimate current_setting use) is present.
    assert "regengine.is_sysadmin" in sql


def test_downgrade_is_forward_only(v090) -> None:
    """Downgrade must be a no-op — reverting would re-open the leak."""
    # Should not raise and should do nothing (pass body).
    import inspect

    src = inspect.getsource(v090.downgrade)
    assert "pass" in src


# ---------------------------------------------------------------------------
# CI guard (scripts/check_tenant_id_uuid_only.py) — Check B behavior.
# ---------------------------------------------------------------------------


def _run_guard() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD_PATH)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_guard_passes_on_clean_tree() -> None:
    """With every legacy file grandfathered and v090 clean, the guard
    exits 0 on the working tree."""
    result = _run_guard()
    assert result.returncode == 0, f"guard failed unexpectedly:\n{result.stdout}\n{result.stderr}"


def test_guard_flags_new_fail_open_policy(tmp_path) -> None:
    """A NEW migration that introduces a current_setting('app.tenant_id', ...)
    text-compare inside CREATE POLICY must trip Check B (exit 1)."""
    versions_dir = REPO_ROOT / "alembic" / "versions"
    offender = versions_dir / "zzz_v090_guardtest_tmp.py"
    offender.write_text(
        "from alembic import op\n"
        "def upgrade():\n"
        '    op.execute("""\n'
        "        CREATE POLICY tenant_isolation_bad ON fsma.something\n"
        "            USING (tenant_id::text = current_setting('app.tenant_id', true));\n"
        '    """)\n',
        encoding="utf-8",
    )
    try:
        result = _run_guard()
        assert result.returncode == 1, "guard should reject a new fail-open CREATE POLICY"
        assert "RLS predicate" in result.stdout
        assert "zzz_v090_guardtest_tmp.py" in result.stdout
    finally:
        offender.unlink(missing_ok=True)
