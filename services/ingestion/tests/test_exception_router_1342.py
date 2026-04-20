"""Coverage-sweep tests for ``app.exception_router._get_service`` (#1342).

``tests/test_exception_router.py`` patches ``_get_service`` wholesale
for every test so the real helper body (lines 46-49) is never
exercised. This file tests the helper directly to pick up the
``db_session is None -> 503`` branch and the happy-path return.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.exception_router import _get_service  # noqa: E402


class TestGetService:
    """Direct tests for the tiny DI helper at app/exception_router.py:45-49."""

    def test_returns_503_when_db_session_is_none(self) -> None:
        # Line 47: raise HTTPException(503) when the session dependency
        # yielded None (e.g. Postgres unavailable via get_db_session).
        with pytest.raises(HTTPException) as exc:
            _get_service(None)
        assert exc.value.status_code == 503
        assert exc.value.detail == "Database unavailable"

    def test_returns_service_instance_when_session_provided(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Lines 48-49: lazy-imports ExceptionQueueService and wraps the
        # session. We stub the shared module so the helper can succeed
        # without pulling in a real service dependency tree.
        captured: dict[str, object] = {}

        class _FakeExceptionQueueService:
            def __init__(self, db_session: object) -> None:
                captured["session"] = db_session

        fake_module = types.ModuleType("shared.exception_queue")
        fake_module.ExceptionQueueService = _FakeExceptionQueueService  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "shared.exception_queue", fake_module)

        fake_session = MagicMock()
        service = _get_service(fake_session)

        assert isinstance(service, _FakeExceptionQueueService)
        assert captured["session"] is fake_session
