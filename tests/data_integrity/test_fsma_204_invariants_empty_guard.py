"""Empty-corpus guards for the FSMA 204 phase 2a invariant checks.

These tests use a fake DB connection, so they run without Postgres. Each
invariant test in ``test_fsma_204_invariants_phase2a`` must skip explicitly
when its table is empty instead of passing vacuously; a silent pass on an
empty corpus gives false assurance that the corpus was checked.
"""

import importlib.util
from pathlib import Path

import pytest

_INVARIANTS_PATH = Path(__file__).with_name("test_fsma_204_invariants_phase2a.py")

_spec = importlib.util.spec_from_file_location("fsma_204_invariants_phase2a_under_test", _INVARIANTS_PATH)
_invariants = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_invariants)
# Keep the imported class out of module level under a non-Test name so
# pytest does not collect it from this module.
_invariants_class = _invariants.TestFSMA204Invariants

SKIPPED = pytest.skip.Exception


class _FakeCursor:
    """Minimal stand-in for a psycopg dict-row cursor over canned counts."""

    def __init__(self, table_counts):
        self._table_counts = table_counts
        self._last_sql = ""

    def execute(self, sql):
        self._last_sql = sql

    def fetchall(self):
        # An empty corpus has no violations to report.
        return []

    def fetchone(self):
        for table, count in self._table_counts.items():
            if table in self._last_sql:
                return {"count": count}
        raise AssertionError(f"unexpected query: {self._last_sql}")


class _FakeConnection:
    """Minimal stand-in for a DB connection returning canned row counts."""

    def __init__(self, table_counts):
        self._table_counts = table_counts

    def cursor(self, row_factory=None):
        return _FakeCursor(self._table_counts)


EMPTY_CORPUS = {
    "pcos_authority_documents": 0,
    "pcos_extracted_facts": 0,
    "compliance_snapshots": 0,
}

INVARIANT_TESTS = [
    _invariants_class.test_authority_documents_have_required_metadata,
    _invariants_class.test_extracted_facts_polymorphic_consistency,
    _invariants_class.test_compliance_snapshots_integrity,
    _invariants_class.test_authority_lineage_linkage,
]


@pytest.mark.parametrize("invariant", INVARIANT_TESTS, ids=[fn.__name__ for fn in INVARIANT_TESTS])
def test_empty_table_skips_explicitly(invariant):
    """Each invariant must skip, not pass silently, on an empty corpus."""
    try:
        invariant(_invariants_class(), _FakeConnection(dict(EMPTY_CORPUS)))
    except SKIPPED:
        return
    pytest.fail(f"{invariant.__name__} passed silently on an empty corpus; expected an explicit skip.")


def test_nonempty_corpus_without_violations_is_not_skipped():
    """Control: populated tables with no violations still pass normally."""
    conn = _FakeConnection({table: 3 for table in EMPTY_CORPUS})
    for invariant in INVARIANT_TESTS:
        invariant(_invariants_class(), conn)
