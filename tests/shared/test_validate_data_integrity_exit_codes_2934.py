"""Regression tests for #2934 — the integrity script must not self-certify.

``scripts/validate_data_integrity.py`` is the compensating control the
dual-write cutover runbooks cite (``docs/persistence/dual-write-cutover.md``).
Before this fix, an unreachable database — wrong ``DATABASE_URL``, DB down,
broken pooler, missing driver — made it print ``Result: PASS`` and exit 0
without running a single query, contradicting its own docstring, which
reserves exit code 2 for "could not connect to database".

These tests execute ``main()`` with a patched connection helper, so they
need no live Postgres.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any

import pytest

# Load the standalone script module by path (scripts/ is not a package).
_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "validate_data_integrity.py",
)
_spec = importlib.util.spec_from_file_location("validate_data_integrity", _SCRIPT_PATH)
assert _spec and _spec.loader
validate_data_integrity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_data_integrity)


@pytest.fixture(autouse=True)
def _bare_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() parses sys.argv; under pytest that carries pytest's own flags."""
    monkeypatch.setattr(sys, "argv", ["validate_data_integrity.py"])


class _AllZeroResult:
    """Every integrity query answers "nothing wrong found"."""

    def fetchone(self) -> tuple[int, int]:
        return (0, 0)

    def scalar(self) -> int:
        return 0


class _HealthyConn:
    def __init__(self) -> None:
        self.closed = False

    def execute(self, stmt: Any) -> _AllZeroResult:
        return _AllZeroResult()

    def close(self) -> None:
        self.closed = True


def _text_fn(s: str) -> str:
    return s


class TestNoDatabaseIsNotAPass_Issue2934:
    def test_main_returns_nonzero_when_helper_yields_none(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A (None, None) connection means nothing was verified, not "fine"."""
        monkeypatch.setattr(validate_data_integrity, "get_db_connection", lambda: (None, None))

        code = validate_data_integrity.main()

        captured = capsys.readouterr()
        assert code != 0
        assert code == validate_data_integrity.EXIT_NO_DATABASE
        assert "PASS" not in captured.out + captured.err

    def test_database_url_unset_exits_nonzero_without_claiming_pass(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        pytest.importorskip("sqlalchemy")
        monkeypatch.delenv("DATABASE_URL", raising=False)

        code = validate_data_integrity.main()

        captured = capsys.readouterr()
        assert code != 0
        assert "PASS" not in captured.out + captured.err
        assert code == validate_data_integrity.EXIT_USAGE
        assert "DATABASE_URL" in captured.out + captured.err

    def test_unreachable_host_exits_nonzero_and_prints_the_cause(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sqlalchemy = pytest.importorskip("sqlalchemy")
        monkeypatch.setenv("DATABASE_URL", "postgresql://u@db.invalid:5432/regengine")

        def _unreachable(*args: Any, **kwargs: Any) -> Any:
            raise OSError('could not translate host name "db.invalid" to address')

        monkeypatch.setattr(sqlalchemy, "create_engine", _unreachable)

        code = validate_data_integrity.main()

        captured = capsys.readouterr()
        assert code != 0
        assert "PASS" not in captured.out + captured.err
        assert "db.invalid" in captured.out + captured.err
        assert code == validate_data_integrity.EXIT_NO_DATABASE

    def test_get_db_connection_reports_the_cause_instead_of_none_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The three causes must stay distinguishable by the caller."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(validate_data_integrity.DatabaseUnavailable) as excinfo:
            validate_data_integrity.get_db_connection()
        assert excinfo.value.exit_code == validate_data_integrity.EXIT_USAGE

    def test_healthy_database_with_clean_checks_still_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The fix must not turn a genuinely clean run into a failure."""
        conn = _HealthyConn()
        monkeypatch.setattr(validate_data_integrity, "get_db_connection", lambda: (conn, _text_fn))

        code = validate_data_integrity.main()

        captured = capsys.readouterr()
        assert code == validate_data_integrity.EXIT_OK
        assert "Overall: PASS" in captured.out
        assert conn.closed is True
