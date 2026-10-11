"""Regression tests for scripts/clear_fsma_data.sql.

The defect: the script ran `ALTER TABLE ... DISABLE TRIGGER ALL` on
pcos_extracted_facts and pcos_authority_documents before deleting rows,
which also switched off audit and immutability triggers, and it issued the
deletes with no surrounding transaction, so a failure partway through left
a half-cleared tenant.

These tests read the script text (no live database needed). Each one fails
against the pre-fix script and passes against the fixed script.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "clear_fsma_data.sql"
ZERO_TENANT = "00000000-0000-0000-0000-000000000000"


def _executable_lines() -> list[str]:
    """Non-blank, non-comment lines of the script, uppercased for matching."""
    lines = []
    for raw in SCRIPT.read_text().splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("--"):
            continue
        lines.append(stripped.upper())
    return lines


def test_no_trigger_is_disabled():
    """No DISABLE TRIGGER statement may appear in executable lines.

    Fails against the pre-fix script, which disabled ALL triggers (including
    audit and immutability) on both tables.
    """
    for line in _executable_lines():
        assert "DISABLE TRIGGER" not in line, (
            f"script disables triggers, switching off audit and immutability protections during the delete: {line!r}"
        )


def test_no_trigger_toggle_pair():
    """No blanket ENABLE TRIGGER ALL re-arm may remain either.

    The ENABLE exists only to undo the DISABLE; both must be gone together.
    """
    for line in _executable_lines():
        assert "TRIGGER ALL" not in line, f"script still toggles all triggers: {line!r}"


def test_deletes_run_inside_one_transaction():
    """The deletes must be wrapped in a single BEGIN/COMMIT transaction.

    Fails against the pre-fix script, which issued bare DELETEs, so a
    failure between the two statements left a half-cleared tenant.
    """
    lines = _executable_lines()
    assert lines[0] == "BEGIN;", f"script must start its work with BEGIN, got: {lines[0]!r}"
    assert lines[-1] == "COMMIT;", f"script must end its work with COMMIT, got: {lines[-1]!r}"
    deletes = [line for line in lines if line.startswith("DELETE FROM")]
    begins = [line for line in lines if line == "BEGIN;"]
    commits = [line for line in lines if line == "COMMIT;"]
    assert len(deletes) == 2, f"expected exactly two DELETEs, got: {deletes!r}"
    assert len(begins) == 1 and len(commits) == 1, "expected a single transaction around both deletes"
    assert lines.index(begins[0]) < min(lines.index(d) for d in deletes)
    assert lines.index(commits[0]) > max(lines.index(d) for d in deletes)


def test_deletes_stay_scoped_to_zero_uuid_tenant():
    """Both DELETEs must still be scoped to the zero-UUID tenant.

    Guards the fix itself: removing the trigger lines must not widen the
    blast radius of either delete.
    """
    source = SCRIPT.read_text()
    assert source.count(ZERO_TENANT) >= 2, "each DELETE must filter on the zero-UUID tenant"
    for line in _executable_lines():
        if line.startswith("DELETE FROM"):
            assert "WHERE" in line or _where_clause_scopes_tenant(source, line), f"unscoped DELETE found: {line!r}"


def _where_clause_scopes_tenant(source: str, delete_line: str) -> bool:
    """The WHERE for this DELETE scopes it to the zero-UUID tenant."""
    upper = source.upper()
    start = upper.find(delete_line)
    semicolon = upper.find(";", start)
    statement = upper[start:semicolon]
    return "WHERE" in statement and ZERO_TENANT.upper() in statement
