"""Shared tenant resolution — single source of truth.

Resolves tenant_id from explicit parameter, header, or API key lookup.
Replaces duplicate implementations in edi_ingestion, epcis_ingestion, and exchange_api.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _get_db_session():
    from shared.database import SessionLocal

    return SessionLocal()


def resolve_tenant_id(
    explicit_tenant_id: Optional[str],
    x_tenant_id: Optional[str],
    x_regengine_api_key: Optional[str],
) -> Optional[str]:
    """Resolve tenant context from explicit ID, header, or API-key lookup.

    Priority: explicit_tenant_id > x_tenant_id header > API-key DB lookup.
    """
    if explicit_tenant_id:
        return explicit_tenant_id
    if x_tenant_id:
        return x_tenant_id
    if not x_regengine_api_key:
        return None

    db = _get_db_session()
    try:
        row = db.execute(
            text(
                """
                SELECT tenant_id
                FROM api_keys
                WHERE key_hash = encode(sha256(:raw::bytea), 'hex')
                LIMIT 1
                """
            ),
            {"raw": x_regengine_api_key},
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception as exc:
        logger.warning("tenant_lookup_failed error=%s", str(exc))
    finally:
        db.close()

    return None
