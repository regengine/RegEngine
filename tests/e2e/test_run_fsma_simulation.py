"""Regression tests for the FSMA simulation runner exit status.

The runner records a skip (ok=None) when a service is unreachable. Before
the fix, SimResult.summary() only exited nonzero on failures, so a run
where every step was skipped (dead stack) exited zero and looked like
success. Summary must now exit nonzero when nothing passed.
"""

import pytest

from tests.e2e.run_fsma_simulation import SimResult


def make_result(outcomes):
    result = SimResult()
    for i, outcome in enumerate(outcomes):
        result.record(f"step {i}", outcome, "detail")
    return result


def test_all_skipped_exits_nonzero(capsys):
    result = make_result([None, None, None])
    with pytest.raises(SystemExit) as excinfo:
        result.summary()
    assert excinfo.value.code != 0
    out = capsys.readouterr().out
    assert "skipped" in out


def test_no_steps_exits_nonzero():
    with pytest.raises(SystemExit) as excinfo:
        SimResult().summary()
    assert excinfo.value.code != 0


def test_failure_still_exits_nonzero():
    result = make_result([True, False, None])
    with pytest.raises(SystemExit) as excinfo:
        result.summary()
    assert excinfo.value.code != 0


def test_pass_with_skips_still_exits_zero(capsys):
    result = make_result([True, None])
    result.summary()
    out = capsys.readouterr().out
    assert "1 passed" in out
