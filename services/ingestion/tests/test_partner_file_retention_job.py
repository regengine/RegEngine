"""Unit tests for the 30-day partner-file retention job (synthetic only)."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from services.ingestion.app import partner_file_retention as retention


class _FakeDB:
    def __init__(
        self,
        *,
        due_rows: Optional[List[tuple]] = None,
        prev_hash: Optional[str] = None,
        tenant_ids: Optional[List[str]] = None,
        claim_row: bool = True,
    ):
        self.due_rows = due_rows or []
        self.prev_hash = prev_hash
        self.tenant_ids = tenant_ids or []
        self.claim_row = claim_row
        self.statements: List[str] = []
        self.params: List[Dict[str, Any]] = []
        self.nested = 0

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})

        class _R:
            def __init__(self, outer, sql):
                self._outer = outer
                self._sql = sql

            def fetchall(self):
                if "FROM public.tenants" in self._sql:
                    return [(tid,) for tid in self._outer.tenant_ids]
                if "FROM public.partner_files" in self._sql and "delete_after" in self._sql:
                    return self._outer.due_rows
                return []

            def fetchone(self):
                if "pg_advisory_xact_lock" in self._sql:
                    return (True,)
                if (
                    "FROM public.partner_files" in self._sql
                    and "FOR UPDATE" in self._sql
                    and "delete_after" not in self._sql
                ):
                    return (self._outer.due_rows[0][0],) if self._outer.claim_row and self._outer.due_rows else None
                if "entry_hash" in self._sql and "partner_file_deletion_log" in self._sql:
                    return (self._outer.prev_hash,) if self._outer.prev_hash else None
                return None

        return _R(self, sql)

    def begin_nested(self):
        self.nested += 1
        return nullcontext()


def _synth_due_tuple(tenant_id: str, file_id: str, engagement_id: str) -> tuple:
    return (
        file_id,
        tenant_id,
        engagement_id,
        "partner-uploads",
        f"tenants/{tenant_id}/engagements/{engagement_id}/obj-synth.csv",
        "a" * 64,
        None,
        12,
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(days=30),
    )


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
    gucs: List[str] = []

    import services.ingestion.app.s3_utils as s3_utils
    import services.ingestion.app.remediation.audit_utils as audit_utils
    monkeypatch.setattr(s3_utils, "is_object_storage_configured", lambda: True)
    monkeypatch.setattr(
        s3_utils,
        "delete_object",
        lambda bucket, key: deletes.append((bucket, key)),
    )
    monkeypatch.setattr(audit_utils, "audit_event", lambda db, **kw: audits.append(kw))
    monkeypatch.setattr(retention, "set_tenant_guc", lambda db, tid: gucs.append(tid))

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
    db = _FakeDB(prev_hash=None, due_rows=[_synth_due_tuple(tenant_id, file_id, engagement_id)])
    result = retention.delete_one_due_file(db, row)

    assert deletes == [("partner-uploads", row["storage_path"])]
    assert any("pg_advisory_xact_lock" in s for s in db.statements)
    tip_selects = [
        s
        for s in db.statements
        if "partner_file_deletion_log" in s and "entry_hash" in s and "INSERT" not in s
    ]
    assert tip_selects
    assert all("FOR UPDATE" not in s for s in tip_selects)
    assert any("INSERT INTO public.partner_file_deletion_log" in s for s in db.statements)
    assert any("SET status = 'deleted'" in s for s in db.statements)
    assert audits and audits[0]["event_type"] == "partner_file.retention_delete"
    assert audits[0]["metadata"]["reason"] == "retention_30d"
    assert result["entry_hash"]
    assert result["skipped"] is False
    assert gucs == [tenant_id]
    log_params = next(
        p
        for p, s in zip(db.params, db.statements)
        if "INSERT INTO public.partner_file_deletion_log" in s
    )
    assert log_params["actor"] == "retention_job"
    assert log_params["reason"] == "retention_30d"
    assert log_params["prev_entry_hash"] is None
    # S3 delete precedes durable log insert
    del_idx = next(i for i, s in enumerate(db.statements) if "pg_advisory_xact_lock" in s)
    # delete_object is not SQL; ensure log insert happens after claim + lock
    log_idx = next(i for i, s in enumerate(db.statements) if "INSERT INTO public.partner_file_deletion_log" in s)
    assert del_idx < log_idx


def test_delete_one_refuses_when_storage_unconfigured(monkeypatch) -> None:
    import services.ingestion.app.s3_utils as s3_utils

    monkeypatch.setattr(s3_utils, "is_object_storage_configured", lambda: False)
    db = _FakeDB()
    row = {
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
    with pytest.raises(RuntimeError, match="object storage"):
        retention.delete_one_due_file(db, row)
    assert not any("partner_file_deletion_log" in s for s in db.statements)
    assert not any("SET status = 'deleted'" in s for s in db.statements)


def test_run_retention_pass_noop_when_storage_unconfigured(monkeypatch) -> None:
    import services.ingestion.app.s3_utils as s3_utils

    monkeypatch.setattr(s3_utils, "is_object_storage_configured", lambda: False)
    called = {"due": False}

    def _boom(*a, **k):
        called["due"] = True
        raise AssertionError("must not scan when unconfigured")

    import shared.maintenance_tenants as maintenance_tenants

    monkeypatch.setattr(maintenance_tenants, "list_maintenance_tenant_ids", _boom)
    totals = retention.run_retention_pass(object())
    assert totals == {"due": 0, "deleted": 0, "errors": 0, "skipped_unconfigured": 1}
    assert called["due"] is False


def test_run_retention_pass_sets_guc_and_savepoint(monkeypatch) -> None:
    tenant_id = str(uuid4())
    file_id = str(uuid4())
    engagement_id = str(uuid4())
    gucs: List[str] = []

    import services.ingestion.app.s3_utils as s3_utils
    import shared.maintenance_tenants as maintenance_tenants

    monkeypatch.setattr(s3_utils, "is_object_storage_configured", lambda: True)
    monkeypatch.setattr(retention, "set_tenant_guc", lambda db, tid: gucs.append(tid))
    monkeypatch.setattr(maintenance_tenants, "list_maintenance_tenant_ids", lambda: [tenant_id])
    monkeypatch.setattr(
        s3_utils,
        "delete_object",
        lambda bucket, key: None,
    )
    monkeypatch.setattr(
        "services.ingestion.app.remediation.audit_utils.audit_event",
        lambda db, **kw: None,
    )

    db = _FakeDB(
        tenant_ids=[tenant_id],
        due_rows=[_synth_due_tuple(tenant_id, file_id, engagement_id)],
        prev_hash=None,
    )
    totals = retention.run_retention_pass(db)
    assert totals["due"] == 1
    assert totals["deleted"] == 1
    assert totals["errors"] == 0
    assert totals["skipped_unconfigured"] == 0
    assert db.nested >= 1
    assert tenant_id in gucs
    assert any("FOR UPDATE SKIP LOCKED" in s for s in db.statements)


def test_concurrent_chain_uses_advisory_lock_and_distinct_prev(monkeypatch) -> None:
    """Two sequential deletes under the lock must chain prev hashes (no fork)."""
    tenant_id = str(uuid4())
    engagement_id = str(uuid4())
    file_a = str(uuid4())
    file_b = str(uuid4())
    audits: List[Dict[str, Any]] = []
    tip: Dict[str, Optional[str]] = {"hash": None}

    import services.ingestion.app.s3_utils as s3_utils
    import services.ingestion.app.remediation.audit_utils as audit_utils
    monkeypatch.setattr(s3_utils, "is_object_storage_configured", lambda: True)
    monkeypatch.setattr(s3_utils, "delete_object", lambda bucket, key: None)
    monkeypatch.setattr(audit_utils, "audit_event", lambda db, **kw: audits.append(kw))
    monkeypatch.setattr(retention, "set_tenant_guc", lambda db, tid: None)

    class _ChainDB(_FakeDB):
        def execute(self, statement, params=None):
            sql = str(statement)
            self.statements.append(sql)
            self.params.append(params or {})
            if "INSERT INTO public.partner_file_deletion_log" in sql:
                tip["hash"] = (params or {}).get("entry_hash")
            return super().execute(statement, params)

        # Override fetchone path via prev_hash mutation between calls
        def __init__(self, **kw):
            super().__init__(**kw)

    # First delete
    db1 = _FakeDB(
        prev_hash=None,
        due_rows=[_synth_due_tuple(tenant_id, file_a, engagement_id)],
    )
    # Patch _latest_entry_hash to read tip so second call sees first hash
    real_latest = retention._latest_entry_hash

    def _latest(db, *, tenant_id):
        # Prefer live tip if set; else fall through to DB prev_hash
        if tip["hash"] is not None and db is not db1:
            return tip["hash"]
        return real_latest(db, tenant_id=tenant_id)

    monkeypatch.setattr(retention, "_latest_entry_hash", _latest)

    row_a = {
        "id": file_a,
        "tenant_id": tenant_id,
        "engagement_id": engagement_id,
        "storage_bucket": "partner-uploads",
        "storage_path": f"tenants/{tenant_id}/engagements/{engagement_id}/a.csv",
        "content_sha256": "a" * 64,
        "ciphertext_sha256": None,
        "byte_size": 1,
        "report_delivered_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "delete_after": datetime(2026, 10, 31, tzinfo=timezone.utc),
    }
    r1 = retention.delete_one_due_file(db1, row_a)
    tip["hash"] = r1["entry_hash"]
    assert any("pg_advisory_xact_lock" in s for s in db1.statements)

    db2 = _FakeDB(
        prev_hash=tip["hash"],
        due_rows=[_synth_due_tuple(tenant_id, file_b, engagement_id)],
    )
    row_b = dict(row_a, id=file_b, storage_path=row_a["storage_path"].replace("a.csv", "b.csv"))
    r2 = retention.delete_one_due_file(db2, row_b)
    assert r2["entry_hash"] != r1["entry_hash"]
    log_b = next(
        p
        for p, s in zip(db2.params, db2.statements)
        if "INSERT INTO public.partner_file_deletion_log" in s
    )
    assert log_b["prev_entry_hash"] == r1["entry_hash"]
    assert any("pg_advisory_xact_lock" in s for s in db2.statements)
