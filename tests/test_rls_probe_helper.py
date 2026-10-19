"""Offline regression tests for the RLS probe helper.

``tests/rls_probe.py::_rls_unfiltered_rows`` (used by
``tests/test_e2e_tenant_isolation.py``) is the sole
proof that an unfiltered read as the app role surfaces exactly one
tenant's rows. Two earlier defects made that proof vacuous: on any
``SET ROLE`` failure the helper rolled back the caller's transaction
(dropping uncommitted scenario rows) and then ``pytest.skip``ped, so the
job stayed green with the proof unexecuted. These tests pin the fixed
behavior with a fake session: no database is touched.
"""

import pytest

from tests.rls_probe import _rls_unfiltered_rows


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows


class _FakeSession:
    """Minimal stand-in for a SQLAlchemy session recording every statement."""

    def __init__(self, fail_on=()):
        self.statements = []
        self.rollbacks = 0
        self._fail_on = tuple(fail_on)

    def execute(self, statement, params=None):
        text = str(statement)
        self.statements.append(text)
        for needle in self._fail_on:
            if needle in text:
                raise RuntimeError(f"boom: {needle}")
        if "FROM fsma.traceability_events" in text:
            return _FakeResult([("tenant-a", "PROD-1")])
        return _FakeResult([])

    def rollback(self):
        self.rollbacks += 1


def test_probe_fails_without_rolling_back_when_role_switch_fails():
    """A failed SET ROLE fails the test and leaves the txn alone."""
    session = _FakeSession(fail_on=("SET ROLE regengine",))

    # pytest.fail raises Failed, which inherits BaseException (not
    # Exception), so the match must catch BaseException.
    with pytest.raises(BaseException, match="cannot SET ROLE regengine"):
        _rls_unfiltered_rows(session, "fsma.traceability_events", "tenant-a")

    assert session.rollbacks == 0, (
        "the helper must not roll back the caller's transaction; "
        "uncommitted scenario rows would be dropped before the failure output"
    )


def test_probe_failure_is_a_failure_not_a_skip():
    """The failure must be pytest.fail (red), never pytest.skip (green)."""
    from _pytest.outcomes import Failed, Skipped

    session = _FakeSession(fail_on=("SET ROLE regengine",))
    try:
        _rls_unfiltered_rows(session, "fsma.traceability_events", "tenant-a")
    except Skipped as exc:
        pytest.fail(f"RLS probe skipped instead of failing: {exc}")
    except Failed:
        pass
    else:
        pytest.fail("RLS probe did not raise when SET ROLE failed")


def test_probe_success_returns_rows_and_resets_role():
    """Happy path still reads rows and restores role and GUC."""
    session = _FakeSession()

    rows = _rls_unfiltered_rows(session, "fsma.traceability_events", "tenant-a")

    assert rows == [("tenant-a", "PROD-1")]
    assert any("SET ROLE regengine" in s for s in session.statements)
    assert any("RESET app.tenant_id" in s for s in session.statements)
    assert any("RESET ROLE" in s for s in session.statements)


def test_probe_rejects_tables_outside_the_allowlist():
    """Table names never come from test input; unknown tables raise."""
    session = _FakeSession()

    with pytest.raises(ValueError, match="allowlist"):
        _rls_unfiltered_rows(session, "public.users", "tenant-a")
