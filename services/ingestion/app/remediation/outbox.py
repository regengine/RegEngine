"""Local notification outbox — preview only, never delivers.

Enqueue runs in the caller's transaction (transactional-outbox shape from
webhook_outbox.py); there is deliberately no drainer. When
REGENGINE_E2E_EMAIL_OUTBOX is set the record is also appended to that file
(dev/e2e parity with the invite-email recorder).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger("remediation.outbox")


def enqueue_preview(
    db,
    *,
    tenant_id: str,
    case_id: Optional[str],
    recipient: Optional[str],
    subject: str,
    body: str,
    payload: Optional[Dict[str, Any]] = None,
) -> str:
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO fsma.notification_outbox
                (tenant_id, case_id, recipient, subject, body, payload)
            VALUES
                (CAST(:tenant_id AS uuid), CAST(:case_id AS uuid), :recipient,
                 :subject, :body, CAST(:payload AS jsonb))
            RETURNING id
            """
        ),
        {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "payload": json.dumps(payload or {}),
        },
    ).fetchone()
    outbox_path = os.environ.get("REGENGINE_E2E_EMAIL_OUTBOX")
    if outbox_path:
        try:
            with open(outbox_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"recipient": recipient, "subject": subject, "body": body}) + "\n")
        except OSError as exc:  # pragma: no cover
            logger.warning("e2e_outbox_write_failed error=%s", exc)
    return str(row[0])


def list_previews(db, *, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    rows = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT id, case_id, channel, recipient, subject, body, payload, status, created_at
            FROM fsma.notification_outbox
            WHERE tenant_id = CAST(:tenant_id AS uuid)
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "limit": limit},
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "case_id": str(r[1]) if r[1] else None,
            "channel": r[2],
            "recipient": r[3],
            "subject": r[4],
            "body": r[5],
            "payload": r[6],
            "status": r[7],
            "created_at": r[8].isoformat() if r[8] else None,
        }
        for r in rows
    ]
