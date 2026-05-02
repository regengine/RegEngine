from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, MetaData, String
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.dialects.postgresql import TEXT, UUID
from sqlalchemy.orm import declarative_base

from services.admin.app.sqlalchemy_models import GUID
from shared import db_type_assertions as dta


class _FakeDialect:
    name = "postgresql"


class _FakeEngine:
    dialect = _FakeDialect()


class _FakeInspector:
    def __init__(self, columns_by_table):
        self.columns_by_table = columns_by_table

    def get_columns(self, table_name, schema=None):
        columns = self.columns_by_table.get((schema, table_name))
        if columns is None:
            columns = self.columns_by_table[(None, table_name)]
        return columns


class _MissingTableInspector:
    def get_columns(self, table_name, schema=None):
        raise NoSuchTableError(table_name)


class _CapturingLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.errors = []

    def info(self, event, **kwargs):
        self.infos.append((event, kwargs))

    def warning(self, event, **kwargs):
        self.warnings.append((event, kwargs))

    def error(self, event, **kwargs):
        self.errors.append((event, kwargs))


def _base():
    return declarative_base(metadata=MetaData())


def test_tenant_id_text_drift_is_critical(monkeypatch):
    Base = _base()

    class TenantScoped(Base):
        __tablename__ = "tenant_scoped"

        id = Column(Integer, primary_key=True)
        tenant_id = Column(GUID(), nullable=False)

    monkeypatch.setattr(
        dta,
        "inspect",
        lambda _engine: _FakeInspector(
            {
                (None, "tenant_scoped"): [
                    {"name": "id", "type": Integer()},
                    {"name": "tenant_id", "type": TEXT()},
                ]
            }
        ),
    )
    log = _CapturingLogger()

    with pytest.raises(dta.CriticalSchemaDriftError) as exc_info:
        dta.verify_orm_db_type_alignment(_FakeEngine(), Base, log=log)

    assert "tenant_scoped.tenant_id" in str(exc_info.value)
    assert log.errors[0][1]["drift_detected"] is True
    assert log.errors[0][1]["drifts"][0]["reason"] == "tenant_id_uuid_column"


def test_missing_audit_hash_input_columns_are_critical(monkeypatch):
    Base = _base()

    class AuditLog(Base):
        __tablename__ = "audit_logs"

        id = Column(Integer, primary_key=True)
        tenant_id = Column(GUID(), nullable=False)
        severity = Column(String, nullable=False)
        endpoint = Column(String)
        request_id = Column(GUID())
        prev_hash = Column(String)
        integrity_hash = Column(String, nullable=False)

    monkeypatch.setattr(
        dta,
        "inspect",
        lambda _engine: _FakeInspector(
            {
                (None, "audit_logs"): [
                    {"name": "id", "type": Integer()},
                    {"name": "tenant_id", "type": UUID()},
                    {"name": "integrity_hash", "type": TEXT()},
                ]
            }
        ),
    )
    log = _CapturingLogger()

    with pytest.raises(dta.CriticalSchemaDriftError) as exc_info:
        dta.verify_orm_db_type_alignment(_FakeEngine(), Base, log=log)

    message = str(exc_info.value)
    assert "audit_logs.severity" in message
    assert "audit_logs.endpoint" in message
    assert "audit_logs.prev_hash" in message
    assert all(
        drift["reason"] == "audit_hash_chain_column"
        for drift in log.errors[0][1]["drifts"]
    )


def test_noncritical_drift_is_warned_and_returned(monkeypatch):
    Base = _base()

    class Widget(Base):
        __tablename__ = "widgets"

        id = Column(Integer, primary_key=True)
        display_name = Column(String, nullable=False)

    monkeypatch.setattr(
        dta,
        "inspect",
        lambda _engine: _FakeInspector(
            {
                (None, "widgets"): [
                    {"name": "id", "type": Integer()},
                ]
            }
        ),
    )
    log = _CapturingLogger()

    drifts = dta.verify_orm_db_type_alignment(_FakeEngine(), Base, log=log)

    assert [drift.column for drift in drifts] == ["display_name"]
    assert log.warnings[0][0] == "orm_db_type_alignment_drift"
    assert log.warnings[0][1]["drift_detected"] is True
    assert not log.errors


def test_missing_audit_logs_table_is_critical(monkeypatch):
    Base = _base()

    class AuditLog(Base):
        __tablename__ = "audit_logs"

        id = Column(Integer, primary_key=True)
        tenant_id = Column(GUID(), nullable=False)
        integrity_hash = Column(String, nullable=False)

    monkeypatch.setattr(dta, "inspect", lambda _engine: _MissingTableInspector())
    log = _CapturingLogger()

    with pytest.raises(dta.CriticalSchemaDriftError, match="audit_logs"):
        dta.verify_orm_db_type_alignment(_FakeEngine(), Base, log=log)

    assert log.errors[0][1]["drifts"][0]["reason"] == "audit_hash_chain_table_missing"


def test_non_postgres_engines_are_skipped():
    class _SQLiteDialect:
        name = "sqlite"

    class _SQLiteEngine:
        dialect = _SQLiteDialect()

    log = _CapturingLogger()

    assert dta.verify_orm_db_type_alignment(_SQLiteEngine(), _base(), log=log) == []
    assert log.infos[0][0] == "orm_db_type_alignment_skipped"
