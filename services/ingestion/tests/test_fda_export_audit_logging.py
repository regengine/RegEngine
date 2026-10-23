"""Data-free FDA export audit failure and identity checks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.authz import IngestionPrincipal  # noqa: E402
from app.fda_export.queries import AuditLogWriteError, log_recall_export  # noqa: E402
from app.fda_export.router import _audit_identity  # noqa: E402


class _FailingSession:
    def __init__(self) -> None:
        self.rolled_back = False

    def execute(self, *_args, **_kwargs):
        raise RuntimeError("audit write unavailable")

    def rollback(self) -> None:
        self.rolled_back = True


def test_audit_identity_is_empty_without_key() -> None:
    request = Request({"type": "http", "headers": []})
    principal = IngestionPrincipal(key_id="", scopes=[])
    assert _audit_identity(request, principal)["user_id"] == ""


def test_1215_log_recall_export_raises_audit_log_write_error() -> None:
    session = _FailingSession()
    with pytest.raises(AuditLogWriteError):
        log_recall_export(session, "", [], "", "csv", None, None, None)
    assert session.rolled_back
