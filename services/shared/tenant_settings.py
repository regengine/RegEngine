"""
Shared tenant settings persistence layer.

Provides get/set for tenant-scoped JSONB data stored in dedicated tables
(tenant_settings, tenant_notification_prefs, tenant_onboarding) or the
generic tenant_data table for ad-hoc namespaces.

All functions are synchronous and use the shared SessionLocal.
All functions catch exceptions and return fallback values — never crash the API.
"""

import json
import logging
from typing import Optional, Any

from sqlalchemy import text

logger = logging.getLogger("tenant_settings")


def _get_db():
    """Get database session. Returns None if unavailable."""
    try:
        from shared.database import SessionLocal
        return SessionLocal()
    except Exception as exc:
        logger.error("db_session_unavailable error=%s", str(exc))
        return None


# ── Dedicated JSONB table helpers ──────────────────────────────────────
# These are for the 3 tables with a single JSONB column per tenant:
#   fsma.tenant_settings   (column: settings)
#   fsma.tenant_notification_prefs (column: prefs)
#   fsma.tenant_onboarding (column: state)

_ALLOWED_JSONB_TABLES: dict[str, str] = {
    "tenant_settings": "settings",
    "tenant_notification_prefs": "prefs",
    "tenant_onboarding": "state",
}


def _validate_table_column(table: str, column: str) -> None:
    """Validate table/column against the allowlist to prevent SQL injection."""
    allowed_col = _ALLOWED_JSONB_TABLES.get(table)
    if allowed_col is None:
        raise ValueError(f"Table '{table}' is not in the JSONB allowlist: {list(_ALLOWED_JSONB_TABLES)}")
    if column != allowed_col:
        raise ValueError(f"Column '{column}' is not allowed for table '{table}' (expected '{allowed_col}')")


def get_jsonb(tenant_id: str, table: str, column: str) -> Optional[dict]:
    """Read JSONB data from a dedicated tenant table.

    Returns None if DB unavailable or row doesn't exist.
    """
    _validate_table_column(table, column)
    db = _get_db()
    if not db:
        return None
    try:
        row = db.execute(
            text(f"SELECT {column} FROM fsma.{table} WHERE tenant_id = :tid"),
            {"tid": tenant_id}
        ).fetchone()
        if not row or not row[0]:
            return None
        return json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except Exception as exc:
        logger.warning("get_jsonb_failed table=%s tenant=%s error=%s", table, tenant_id, str(exc))
        return None
    finally:
        db.close()


def set_jsonb(tenant_id: str, table: str, column: str, data: dict) -> bool:
    """Upsert JSONB data into a dedicated tenant table.

    Returns True on success, False on failure.
    """
    _validate_table_column(table, column)
    db = _get_db()
    if not db:
        logger.error("db_write_skipped table=%s tenant=%s reason=no_connection", table, tenant_id)
        return False
    try:
        data_json = json.dumps(data, default=str)
        db.execute(
            text(f"""
                INSERT INTO fsma.{table} (tenant_id, {column}, created_at, updated_at)
                VALUES (:tid, :data, now(), now())
                ON CONFLICT (tenant_id) DO UPDATE
                SET {column} = :data, updated_at = now()
            """),
            {"tid": tenant_id, "data": data_json}
        )
        db.commit()
        return True
    except Exception as exc:
        logger.error("set_jsonb_failed table=%s tenant=%s error=%s", table, tenant_id, str(exc))
        db.rollback()
        return False
    finally:
        db.close()


# ── Generic tenant_data helpers ────────────────────────────────────────
# For ad-hoc data that doesn't warrant its own table.
# Uses fsma.tenant_data(tenant_id, namespace, key, data JSONB).


def get_tenant_data(tenant_id: str, namespace: str, key: str) -> Optional[dict]:
    """Read a single keyed record from tenant_data."""
    db = _get_db()
    if not db:
        return None
    try:
        row = db.execute(
            text("SELECT data FROM fsma.tenant_data WHERE tenant_id = :tid AND namespace = :ns AND key = :k"),
            {"tid": tenant_id, "ns": namespace, "k": key}
        ).fetchone()
        if not row or not row[0]:
            return None
        return json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except Exception as exc:
        logger.warning("get_tenant_data_failed ns=%s key=%s error=%s", namespace, key, str(exc))
        return None
    finally:
        db.close()


def set_tenant_data(tenant_id: str, namespace: str, key: str, data: dict) -> bool:
    """Upsert a single keyed record into tenant_data."""
    db = _get_db()
    if not db:
        logger.error("tenant_data_write_skipped ns=%s key=%s reason=no_connection", namespace, key)
        return False
    try:
        data_json = json.dumps(data, default=str)
        db.execute(
            text("""
                INSERT INTO fsma.tenant_data (tenant_id, namespace, key, data, created_at, updated_at)
                VALUES (:tid, :ns, :k, :data, now(), now())
                ON CONFLICT (tenant_id, namespace, key) DO UPDATE
                SET data = :data, updated_at = now()
            """),
            {"tid": tenant_id, "ns": namespace, "k": key, "data": data_json}
        )
        db.commit()
        return True
    except Exception as exc:
        logger.error("set_tenant_data_failed ns=%s key=%s error=%s", namespace, key, str(exc))
        db.rollback()
        return False
    finally:
        db.close()


def list_tenant_data(tenant_id: str, namespace: str) -> list[dict]:
    """List all records for a tenant in a namespace."""
    db = _get_db()
    if not db:
        return []
    try:
        rows = db.execute(
            text("SELECT key, data FROM fsma.tenant_data WHERE tenant_id = :tid AND namespace = :ns ORDER BY created_at"),
            {"tid": tenant_id, "ns": namespace}
        ).fetchall()
        results = []
        for row in rows:
            d = json.loads(row[1]) if isinstance(row[1], str) else row[1]
            d["_key"] = row[0]
            results.append(d)
        return results
    except Exception as exc:
        logger.warning("list_tenant_data_failed ns=%s error=%s", namespace, str(exc))
        return []
    finally:
        db.close()


def delete_tenant_data(tenant_id: str, namespace: str, key: str) -> bool:
    """Delete a single keyed record from tenant_data."""
    db = _get_db()
    if not db:
        return False
    try:
        db.execute(
            text("DELETE FROM fsma.tenant_data WHERE tenant_id = :tid AND namespace = :ns AND key = :k"),
            {"tid": tenant_id, "ns": namespace, "k": key}
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning("delete_tenant_data_failed ns=%s key=%s error=%s", namespace, key, str(exc))
        db.rollback()
        return False
    finally:
        db.close()
