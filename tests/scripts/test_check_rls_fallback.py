"""Self-tests for the RLS fail-open migration guard (#2935).

Before #2935 ``scripts/check_rls_fallback.py`` could not detect the pattern
quoted in its own docstring, never opened ``alembic/sql/`` (23 live
``CREATE POLICY`` statements), and never inspected a ``WITH CHECK`` clause —
so the "RLS fail-open migration guard" hard gate was green on inputs it was
written to reject.

These tests pin all three holes shut. The fixtures under
``scripts/fixtures/rls_failopen/`` are the guard's known-bad corpus; a regex
refactor that stops matching one of them turns this suite red instead of
silently reopening the gap.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_rls_fallback.py"
_FIXTURES = _REPO_ROOT / "scripts" / "fixtures" / "rls_failopen"


def _load_guard():
    spec = importlib.util.spec_from_file_location("_check_rls_fallback", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


# The exact snippet the guard's own docstring names as the canonical
# fail-open form. Kept literal here, not read from the docstring, so that
# rewording the docstring cannot quietly weaken the test.
CANONICAL_FAIL_OPEN = """
CREATE POLICY tenant_isolation ON fsma.demo
    USING (tenant_id = COALESCE(
        NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
        '00000000-0000-0000-0000-000000000001'::UUID
    ));
"""


def _bad_fixtures() -> list[Path]:
    return sorted((_FIXTURES / "bad").iterdir())


def _good_fixtures() -> list[Path]:
    return sorted((_FIXTURES / "good").iterdir())


def test_canonical_docstring_snippet_is_detected():
    """The pattern the guard documents must be a pattern the guard matches.

    ``_PAT_FALLBACK_UUID`` used ``[^)]*`` between COALESCE and the UUID
    literal, which cannot span the nested ``NULLIF(current_setting(...))``
    call — so the pattern written for the canonical form never fired once.
    """
    assert guard._PAT_FALLBACK_UUID.search(CANONICAL_FAIL_OPEN), (
        "the guard's primary fail-open pattern does not match the canonical "
        "snippet in its own docstring — it is dead code again (#2935)"
    )
    assert guard.check_text(CANONICAL_FAIL_OPEN), "guard reported the canonical fail-open snippet as clean"


def test_with_check_arm_is_inspected():
    """WITH CHECK governs writes INTO another tenant and must be scanned."""
    write_arm = CANONICAL_FAIL_OPEN.replace("USING (", "FOR INSERT WITH CHECK (")
    assert guard.check_text(write_arm), (
        "a fail-open FOR INSERT ... WITH CHECK policy was reported clean — "
        "the guard is anchoring on USING only again (#2935)"
    )


def test_policy_predicate_patterns_alternate_using_and_with_check():
    """A bare constant tenant in the write arm, with no COALESCE to fall back on.

    The COALESCE patterns cannot see this one, so it fails only if the
    policy-predicate patterns really do alternate ``USING|WITH CHECK``. Without
    it, re-anchoring those patterns on ``USING\s*\(`` alone — the pre-#2935
    behaviour — passes the rest of this suite.
    """
    bare = (
        "CREATE POLICY tenant_isolation_write ON fsma.demo\n"
        "    FOR INSERT\n"
        f"    WITH CHECK (tenant_id = '{guard.FALLBACK_UUID}'::UUID);\n"
    )
    assert "COALESCE" not in bare
    assert guard.check_text(bare), (
        "a hardcoded constant tenant in a WITH CHECK arm was reported clean — "
        "the policy-predicate patterns are anchored on USING only again (#2935)"
    )


def test_any_constant_tenant_fallback_is_rejected():
    """A fallback to any fixed tenant is fail-open, not just the sandbox UUID."""
    other = CANONICAL_FAIL_OPEN.replace(guard.FALLBACK_UUID, "deadbeef-0000-0000-0000-00000000abcd")
    assert guard.FALLBACK_UUID not in other
    assert guard.check_text(other), "fallback to a non-sandbox constant tenant was reported clean"

    nil = CANONICAL_FAIL_OPEN.replace(guard.FALLBACK_UUID, "00000000-0000-0000-0000-000000000000")
    assert guard.check_text(nil), "fallback to the nil UUID was reported clean"


def test_alembic_sql_is_in_the_scan_surface():
    """alembic/sql holds live policies that a fresh `upgrade head` executes."""
    assert (_REPO_ROOT / "alembic" / "sql") in guard.SCAN_DIRS, (
        "alembic/sql dropped out of SCAN_DIRS — 23 live CREATE POLICY "
        "statements would go unscanned (#2935)"
    )
    for directory in guard.SCAN_DIRS:
        assert directory.is_dir(), f"configured scan directory does not exist: {directory}"


@pytest.mark.parametrize("fixture", _bad_fixtures(), ids=lambda p: p.name)
def test_known_bad_fixture_exits_nonzero(fixture: Path):
    assert guard.main([str(fixture)]) == 1, f"guard accepted known-bad fixture {fixture.name}"


@pytest.mark.parametrize("fixture", _good_fixtures(), ids=lambda p: p.name)
def test_fail_closed_fixture_exits_zero(fixture: Path):
    assert guard.main([str(fixture)]) == 0, f"guard rejected fail-closed fixture {fixture.name}"


def test_bad_fixture_directory_is_not_empty():
    """Guard against the corpus itself silently emptying out."""
    assert len(_bad_fixtures()) >= 5, "the known-bad fixture corpus shrank — see scripts/fixtures/rls_failopen/"


def test_guard_fails_when_it_reads_no_files(tmp_path: Path):
    """A guard that scans zero files must not report success."""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert guard.main([str(empty)]) == 1, "guard exited 0 after reading zero files"


def test_guard_fails_on_a_missing_path(tmp_path: Path):
    assert guard.main([str(tmp_path / "does-not-exist")]) == 1
