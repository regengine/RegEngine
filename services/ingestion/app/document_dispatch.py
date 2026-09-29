"""Durably dispatch persisted documents to the PostgreSQL NLP worker."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import urlparse
from uuid import UUID

import structlog
from fastapi import HTTPException
from pydantic import HttpUrl
from shared.database import SessionLocal
from shared.event_backbone import kafka_enabled
from shared.task_queue import enqueue_task
from shared.tenant_context import tenant_scope
from sqlalchemy import text

from .models import NormalizedEvent
from .s3_utils import _validate_s3_key, get_raw_document

logger = structlog.get_logger("document_dispatch")


def _stored_normalized_payload(uri: str) -> dict:
    parsed = urlparse(uri)
    if (
        parsed.scheme != "s3"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid normalized object URI")
    key = parsed.path.removeprefix("/")
    _validate_s3_key(key)
    stored = get_raw_document(key, bucket=parsed.netloc)
    return json.loads(stored["content"])


def dispatch_document(event: NormalizedEvent, normalized_payload: dict | None = None) -> None:
    """Require committed, matching NLP work before reporting PG import success.

    A duplicate uses the persisted winner's object, not the retry's input.
    The persisted document ID remains authoritative for legacy objects whose
    historical normalized ID differs. Document and queue transactions are
    separate: dispatch failure leaves the document available for a safe retry.
    """
    if kafka_enabled():
        return

    db = None
    try:
        tenant_id = str(UUID(event.tenant_id))
        if not event.document_id.strip():
            raise ValueError("Missing persisted document identity")
        content_hash = event.content_sha256
        if (
            len(content_hash) != 64
            or any(char not in "0123456789abcdef" for char in content_hash)
            or event.document_hash != content_hash
        ):
            raise ValueError("Invalid persisted document hash")
        normalized = (
            normalized_payload
            if normalized_payload is not None
            else _stored_normalized_payload(event.normalized_s3_path)
        )
        if not isinstance(normalized, dict) or normalized.get("content_sha256") != content_hash:
            raise ValueError("Normalized document hash mismatch")
        document_text = normalized.get("text")
        if not isinstance(document_text, str) or not document_text.strip():
            raise ValueError("Missing normalized document text")
        source_url = str(HttpUrl(normalized["source_url"]))
        if source_url != str(event.source_url):
            raise ValueError("Normalized document provenance mismatch")

        payload = {
            "document_id": event.document_id,
            "document_hash": content_hash,
            "tenant_id": tenant_id,
            "text": document_text,
            "source_url": source_url,
            "normalized_s3_path": event.normalized_s3_path,
        }
        identity = f"{event.document_id}\0{content_hash}".encode()
        idempotency_key = f"nlp_extraction:{hashlib.sha256(identity).hexdigest()}"
        with tenant_scope(tenant_id):
            db = SessionLocal()
            task_id = enqueue_task(
                db,
                task_type="nlp_extraction",
                payload=payload,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
            )
            task = (
                db.execute(
                    text(
                        """
                    SELECT task_type, payload, tenant_id, status, idempotency_key
                    FROM fsma.task_queue
                    WHERE id = :task_id AND tenant_id = :tenant_id
                    """
                    ),
                    {"task_id": task_id, "tenant_id": tenant_id},
                )
                .mappings()
                .one_or_none()
            )
            if (
                task is None
                or str(task["tenant_id"]) != tenant_id
                or task["task_type"] != "nlp_extraction"
                or task["idempotency_key"] != idempotency_key
                or task["payload"] != payload
                or task["status"] not in {"pending", "processing", "completed"}
            ):
                raise ValueError("NLP task is unavailable or inconsistent")
            db.commit()
    except Exception as exc:
        if db is not None:
            try:
                db.rollback()
            except Exception as rollback_exc:
                logger.error("document_dispatch_rollback_failed", error_type=type(rollback_exc).__name__)
        logger.error("document_dispatch_failed", error_type=type(exc).__name__)
        # Route exception logging must not render SQL parameters or document text.
        raise HTTPException(status_code=503, detail="Document processing unavailable") from None
    finally:
        if db is not None:
            try:
                db.close()
            except Exception as close_exc:
                logger.error("document_dispatch_close_failed", error_type=type(close_exc).__name__)
