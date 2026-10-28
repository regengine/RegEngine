"""Unit tests for the 30-day partner-file retention job (synthetic only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from services.ingestion.app import partner_file_retention as retention


class _FakeDB:
    def __init__(self, due_rows: Optional[List[tuple]] = None, prev_hash: Optional[str] = None):
        self.due_rows = due_rows or []
        self.prev_hash = prev_hash
        self.statements: List[str] = []
        self.params: List[Dict[str, Any]] = []
        self.gucs: List[str] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})

        class _R:
            def __init__(self, rows, prev):
                self._rows = rows
                self._prev = prev
                self._sql = sql

            def fetchall(self):
                return self._rows

            def fetchone(self):
                if "entry_hash" in self._sql and "partner_file_deletion_log" in self._sql:
                    return (self._prev,) if self._prev else None
                return None

        return _R(self.due_rows, self.prev_hash)

    def begin_nested(self):
        from contextlib import nullcontext

        return nullcontext()


def test_compute_entry_hash_stable() -> None:
    fields = {
        "partner_file_id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "22222222-2222-2222-2222-222222222222",
        "reason": "retention_30d",
    }
    h1 = retention.compute_entry_hash(prev_entry_hash=None, fields=fields)
    h2 = retention.compute_entry_hash(prev_entry_hash=None, fields=fields)
    assert h1 == h2
    assert len(h1) == 64
    h3 = retention.compute_entry_hash(prev_entry_hash=h1, fields=fields)
    assert h3 != h1


def test_delete_one_due_file_writes_log_and_audit(monkeypatch) -> None:
    tenant_id = str(uuid4())
    file_id = str(uuid4())
    engagement_id = str(uuid4())
    deletes: List[tuple] = []
    audits: List[Dict[str, Any]] = []

    import services.ingestion.app.s3_utils as s3_utils
    import services.ingestion.app.remediation.audit_utils as audit_utils
    import shared.tenant_context as tenant_context

    monkeypatch.setattr(s3_utils, "is_object_storage_configured", lambda: True)
    monkeypatch.setattr(
        s3_utils,
        "delete_object",
        lambda bucket, key: deletes.append((bucket, key)),
    )
    monkeypatch.setattr(audit_utils, "audit_event", lambda db, **kw: audits.append(kw))
    monkeypatch.setattr(tenant_context, "set_tenant_guc", lambda db, tid: None)

    row = {
        "id": file_id,
        "tenant_id": tenant_id,
        "engagement_id": engagement_id,
        "storage_bucket": "partner-uploads",
        "storage_path": f"tenants/{tenant_id}/engagements/{engagement_id}/obj-synth.csv",
        "content_sha256": "a" * 64,
        "ciphertext_sha256": None,
        "byte_size": 12,
        "report_delivered_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "delete_after": datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(days=30),
    }
    db = _FakeDB(prev_hash=None)
    result = retention.delete_one_due_file(db, row)

    assert deletes == [("partner-uploads", row["storage_path"])]
    assert any("INSERT INTO public.partner_file_deletion_log" in s for s in db.statements)
    assert any("SET status = 'deleted'" in s for s in db.statements)
    assert audits and audits[0]["event_type"] == "partner_file.retention_delete"
    assert audits[0]["metadata"]["reason"] == "retention_30d"
    assert result["entry_hash"]
    log_params = next(
        p
        for p, s in zip(db.params, db.statements)
        if "INSERT INTO public.partner_file_deletion_log" in s
    )
    assert log_params["actor"] == "retention_job"
    assert log_params["reason"] == "retention_30d"
    assert log_params["prev_entry_hash"] is None


def test_run_retention_pass_counts(monkeypatch) -> None:
    calls: List[str] = []

    def _due(db, *, limit=100):
        return [
            {
                "id": str(uuid4()),
                "tenant_id": str(uuid4()),
                "engagement_id": str(uuid4()),
                "storage_bucket": "partner-uploads",
                "storage_path": "tenants/t/engagements/e/x.csv",
                "content_sha256": "b" * 64,
                "ciphertext_sha256": None,
                "byte_size": 1,
                "report_delivered_at": None,
                "delete_after": datetime.now(timezone.utc) - timedelta(days=1),
            }
        ]

    monkeypatch.setattr(retention, "_due_rows", _due)
    monkeypatch.setattr(
        retention,
        "delete_one_due_file",
        lambda db, row: calls.append(row["id"]) or {"partner_file_id": row["id"]},
    )
    totals = retention.run_retention_pass(object())
    assert totals == {"due": 1, "deleted": 1, "errors": 0}
    assert len(calls) == 1
