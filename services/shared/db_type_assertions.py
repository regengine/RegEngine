"""Runtime ORM/live database type assertions.

These checks catch schema drift that Alembic text scans cannot see once the
application is connected to a real database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import inspect
from sqlalchemy.exc import NoSuchTableError

logger = structlog.get_logger("shared.db_type_assertions")


_AUDIT_PROTECTED_COLUMNS = {
    "tenant_id",
    "timestamp",
    "actor_id",
    "actor_email",
    "event_type",
    "action",
    "severity",
    "resource_id",
    "endpoint",
    "metadata",
    "request_id",
    "prev_hash",
    "integrity_hash",
}


@dataclass(frozen=True)
class SchemaDrift:
    table: str
    column: str
    expected: str
    actual: str
    critical: bool
    reason: str
    schema: str | None = None

    @property
    def qualified_column(self) -> str:
        prefix = f"{self.schema}." if self.schema else ""
        return f"{prefix}{self.table}.{self.column}"

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "table": f"{self.schema}.{self.table}" if self.schema else self.table,
            "column": self.column,
            "expected": self.expected,
            "actual": self.actual,
            "critical": self.critical,
            "reason": self.reason,
        }


class CriticalSchemaDriftError(RuntimeError):
    """Raised when protected live DB columns do not match ORM metadata."""

    def __init__(self, drifts: list[SchemaDrift]):
        self.drifts = drifts
        summary = ", ".join(
            f"{drift.qualified_column}: expected {drift.expected}, got {drift.actual}"
            for drift in drifts
        )
        super().__init__(f"Critical ORM/database schema drift detected: {summary}")


def verify_orm_db_type_alignment(engine: Any, base: Any, *, log: Any = logger) -> list[SchemaDrift]:
    """Verify live PostgreSQL column types against SQLAlchemy metadata.

    Protected mismatches fail startup:
    - any ORM ``tenant_id`` column declared as UUID but not live as UUID
    - audit-log hash-chain/hash-input columns missing or type-mismatched

    Other missing or mismatched ORM columns are logged as structured warnings
    with ``drift_detected=true`` and returned to the caller.
    """

    dialect_name = getattr(getattr(engine, "dialect", None), "name", "")
    if dialect_name != "postgresql":
        log.info(
            "orm_db_type_alignment_skipped",
            dialect=dialect_name or "unknown",
            reason="postgresql_only",
            drift_detected=False,
        )
        return []

    inspector = inspect(engine)
    drifts: list[SchemaDrift] = []
    checked_tables = 0

    for table in base.metadata.sorted_tables:
        checked_tables += 1
        schema = table.schema
        try:
            live_columns = {
                column["name"]: _normalize_type(column["type"])
                for column in inspector.get_columns(table.name, schema=schema)
            }
        except NoSuchTableError:
            critical = table.name == "audit_logs"
            drifts.append(
                SchemaDrift(
                    schema=schema,
                    table=table.name,
                    column="*",
                    expected="table",
                    actual="missing",
                    critical=critical,
                    reason="audit_hash_chain_table_missing" if critical else "table_missing",
                )
            )
            continue

        for column in table.columns:
            expected = _normalize_type(column.type)
            actual = live_columns.get(column.name)
            critical = _is_protected_column(table.name, column.name, expected)

            if actual is None:
                drifts.append(
                    SchemaDrift(
                        schema=schema,
                        table=table.name,
                        column=column.name,
                        expected=expected,
                        actual="missing",
                        critical=critical,
                        reason=_reason(table.name, column.name, critical),
                    )
                )
                continue

            if not _types_compatible(expected, actual):
                drifts.append(
                    SchemaDrift(
                        schema=schema,
                        table=table.name,
                        column=column.name,
                        expected=expected,
                        actual=actual,
                        critical=critical,
                        reason=_reason(table.name, column.name, critical),
                    )
                )

    critical_drifts = [drift for drift in drifts if drift.critical]
    if critical_drifts:
        log.error(
            "orm_db_type_alignment_failed",
            drift_detected=True,
            critical_count=len(critical_drifts),
            drifts=[drift.to_log_dict() for drift in critical_drifts],
        )
        raise CriticalSchemaDriftError(critical_drifts)

    for drift in drifts:
        log.warning(
            "orm_db_type_alignment_drift",
            drift_detected=True,
            **drift.to_log_dict(),
        )

    log.info(
        "orm_db_type_alignment_ok",
        drift_detected=bool(drifts),
        checked_tables=checked_tables,
        warning_count=len(drifts),
    )
    return drifts


def _reason(table_name: str, column_name: str, critical: bool) -> str:
    if table_name == "audit_logs" and column_name in _AUDIT_PROTECTED_COLUMNS:
        return "audit_hash_chain_column"
    if critical:
        return "tenant_id_uuid_column"
    return "orm_db_column_drift"


def _is_protected_column(table_name: str, column_name: str, expected: str) -> bool:
    if column_name == "tenant_id" and expected == "uuid":
        return True
    return table_name == "audit_logs" and column_name in _AUDIT_PROTECTED_COLUMNS


def _normalize_type(sqltype: Any) -> str:
    type_name = sqltype.__class__.__name__.lower()
    rendered = str(sqltype).lower()

    if "guid" in type_name or "uuid" in type_name or "uuid" in rendered:
        return "uuid"
    if "json" in type_name or "json" in rendered:
        return "json"
    if any(token in rendered for token in ("timestamp", "datetime")) or "datetime" in type_name:
        return "timestamp"
    if "bool" in type_name or "boolean" in rendered:
        return "boolean"
    if "float" in type_name or "double" in rendered or "numeric" in rendered:
        return "float"
    if "bigint" in rendered or "biginteger" in type_name:
        return "bigint"
    if "int" in type_name or "integer" in rendered:
        return "integer"
    if any(token in rendered for token in ("text", "varchar", "character varying", "char")):
        return "text"
    if "string" in type_name:
        return "text"
    return rendered


def _types_compatible(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    if {expected, actual} <= {"integer", "bigint"}:
        return True
    if {expected, actual} <= {"text"}:
        return True
    if expected == "json" and actual == "json":
        return True
    return False
