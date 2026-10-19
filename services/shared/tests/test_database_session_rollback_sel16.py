"""Session providers roll back before close so a failed transaction cannot
poison the connection pool (SEL-16). Mirrors admin get_session (PR #1892).

``get_db_safe`` is not covered: it has no finally block. The caller owns
commit, rollback, and close.
"""

from __future__ import annotations

import pytest
from shared import database as db_mod


class _RecordingSession:
    def __init__(self) -> None:
        self.events: list[str] = []

    def execute(self, *_args, **_kwargs):
        self.events.append("execute")
        return self

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> _RecordingSession:
    recorded = _RecordingSession()
    monkeypatch.setattr(db_mod, "SessionLocal", lambda: recorded)
    return recorded


def test_get_db_rolls_back_before_close_on_success(session: _RecordingSession) -> None:
    with db_mod.get_db() as db:
        assert db is session

    assert session.events[0] == "execute"  # connection health check
    assert session.events[-2:] == ["rollback", "close"]


def test_get_db_rolls_back_before_close_on_handler_error(session: _RecordingSession) -> None:
    with pytest.raises(RuntimeError, match="handler failed"):
        with db_mod.get_db():
            raise RuntimeError("handler failed")

    assert session.events[-2:] == ["rollback", "close"]


def test_get_db_rolls_back_before_close_when_health_check_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _RecordingSession()

    def _boom(*_args, **_kwargs):
        recorded.events.append("execute")
        raise RuntimeError("select 1 failed")

    recorded.execute = _boom  # type: ignore[method-assign]
    monkeypatch.setattr(db_mod, "SessionLocal", lambda: recorded)

    with pytest.raises(RuntimeError, match="select 1 failed"):
        with db_mod.get_db():
            pass

    assert recorded.events == ["execute", "rollback", "close"]


async def test_get_db_async_rolls_back_before_close_on_success(session: _RecordingSession) -> None:
    async with db_mod.get_db_async() as db:
        assert db is session

    assert session.events[0] == "execute"
    assert session.events[-2:] == ["rollback", "close"]


async def test_get_db_async_rolls_back_before_close_on_handler_error(session: _RecordingSession) -> None:
    with pytest.raises(RuntimeError, match="handler failed"):
        async with db_mod.get_db_async():
            raise RuntimeError("handler failed")

    assert session.events[-2:] == ["rollback", "close"]


def test_get_db_session_commits_then_rolls_back_before_close(session: _RecordingSession) -> None:
    gen = db_mod.get_db_session()
    assert next(gen) is session

    with pytest.raises(StopIteration):
        next(gen)

    # commit lands first. rollback() after a completed commit is a no-op
    # in SQLAlchemy when no transaction is active; it must not precede commit.
    assert session.events == ["commit", "rollback", "close"]


def test_get_db_session_rolls_back_before_close_on_handler_error(session: _RecordingSession) -> None:
    gen = db_mod.get_db_session()
    next(gen)

    with pytest.raises(RuntimeError, match="handler failed"):
        gen.throw(RuntimeError("handler failed"))

    assert "commit" not in session.events
    assert session.events[-2:] == ["rollback", "close"]


def test_get_db_session_rolls_back_before_close_on_base_exception(session: _RecordingSession) -> None:
    """Client disconnect injects BaseException, which skips ``except Exception``."""

    class _Disconnect(BaseException):
        pass

    gen = db_mod.get_db_session()
    next(gen)

    with pytest.raises(_Disconnect):
        gen.throw(_Disconnect("client gone"))

    assert session.events == ["rollback", "close"]
