"""Prometheus metrics and hallucination tracking utilities for the admin service."""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional
from uuid import UUID

import httpx
import structlog
from prometheus_client import Counter, Gauge, REGISTRY
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .database import SessionLocal
from .sqlalchemy_models import ReviewItemModel

# Webhook security - optional, gracefully degrade if not available
try:
    from shared.webhook_security import generate_signature, get_signature_header_name
    WEBHOOK_SIGNING_AVAILABLE = True
except ImportError:
    WEBHOOK_SIGNING_AVAILABLE = False

try:  # Optional dependency for local dev
    import redis  # type: ignore
    RedisType = redis.Redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore
    RedisType = None  # type: ignore

logger = structlog.get_logger("hallucination-tracker")

def _get_or_create_counter(name, documentation, labelnames):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    try:
        return Counter(name, documentation, labelnames)
    except ValueError:
        return REGISTRY._names_to_collectors[name]

def _get_or_create_gauge(name, documentation, labelnames):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    try:
        return Gauge(name, documentation, labelnames)
    except ValueError:
        return REGISTRY._names_to_collectors[name]

hallucination_events_total = _get_or_create_counter(
    "hallucination_events_total",
    "Total hallucinations routed to human review",
    ["tenant_id", "extractor"],
)

hallucination_active_reviews = _get_or_create_gauge(
    "hallucination_active_reviews",
    "Active hallucination review items awaiting decision",
    ["tenant_id"],
)

hallucination_duplicates_total = _get_or_create_counter(
    "hallucination_duplicates_total",
    "Duplicate hallucination submissions detected",
    ["tenant_id"],
)

hallucination_webhook_calls_total = _get_or_create_counter(
    "hallucination_webhook_calls_total",
    "Webhook notifications sent on resolution",
    ["status"],
)


@dataclass
class HallucinationSnapshot:
    """Serializable view of a review item for Redis dashboards."""

    review_id: str
    tenant_id: Optional[str]
    document_id: Optional[str]
    doc_hash: str
    extractor: Optional[str]
    confidence_score: float
    status: str
    created_at: str
    updated_at: Optional[str]
    extraction: dict
    provenance: Optional[dict]


class HallucinationTracker:
    """Tracks hallucination review lifecycle across storage and metrics."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        redis_client: Optional[RedisType] = None,
        recent_cache_size: int = 100,
        redis_ttl_seconds: int = 3600,
        webhook_url: Optional[str] = None,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis_client
        self._recent_key = "hallucination:recent"
        self._recent_cache_size = recent_cache_size
        self._redis_ttl = redis_ttl_seconds
        self._webhook_url = webhook_url or os.getenv("HALLUCINATION_WEBHOOK_URL")

    @contextmanager
    def _session_scope(self, tenant_id: Optional[str] = None) -> Iterable[Session]:
        session = self._session_factory()
        try:
            if tenant_id:
                session.execute(
                    text("SET LOCAL app.tenant_id = :tid"),
                    {"tid": str(tenant_id)},
                )
            yield session
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _tenant_label(tenant_id: Optional[UUID]) -> str:
        return str(tenant_id) if tenant_id is not None else "global"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _bump_metrics(self, tenant_id: Optional[UUID], extractor: Optional[str]) -> None:
        label_tenant = self._tenant_label(tenant_id)
        label_extractor = extractor or "unknown"
        hallucination_events_total.labels(tenant_id=label_tenant, extractor=label_extractor).inc()
        hallucination_active_reviews.labels(tenant_id=label_tenant).inc()

    def _decrement_active_metric(self, tenant_id: Optional[UUID]) -> None:
        label_tenant = self._tenant_label(tenant_id)
        gauge = hallucination_active_reviews.labels(tenant_id=label_tenant)
        # Gauge.dec() doesn't raise on negative; clamp manually
        current = gauge._value.get()
        if current > 0:
            gauge.dec()

    def _mutable_extraction(self, extraction: dict | None) -> dict:
        base = dict(extraction or {})
        attributes = dict(base.get("attributes") or {})
        base["attributes"] = attributes
        return base

    def _snapshot(self, item: ReviewItemModel) -> HallucinationSnapshot:
        extraction = item.extraction or {}
        attributes = extraction.get("attributes") or {}
        document_id = attributes.get("document_id")
        extractor = attributes.get("extractor")
        return HallucinationSnapshot(
            review_id=str(item.id),
            tenant_id=str(item.tenant_id) if item.tenant_id else None,
            document_id=document_id,
            doc_hash=item.doc_hash,
            extractor=extractor,
            confidence_score=item.confidence_score,
            status=item.status,
            created_at=item.created_at.isoformat() if item.created_at else self._now().isoformat(),
            updated_at=item.updated_at.isoformat() if item.updated_at else None,
            extraction=extraction,
            provenance=item.provenance or None,
        )

    def _cache_snapshot(self, snapshot: HallucinationSnapshot) -> None:
        if not self._redis:
            return
        try:
            payload = json.dumps(asdict(snapshot), default=str)
            self._redis.set(f"hallucination:{snapshot.review_id}", payload, ex=self._redis_ttl)
            self._redis.lpush(self._recent_key, payload)
            self._redis.ltrim(self._recent_key, 0, self._recent_cache_size - 1)
        except Exception as exc:  # pragma: no cover - depends on Redis availability
            logger.warning("redis_cache_failed", error=str(exc))

    def _serialize(self, item: ReviewItemModel) -> Dict[str, Any]:
        snapshot = self._snapshot(item)
        result = asdict(snapshot)
        result.update(
            {
                "reviewer_id": item.reviewer_id,
                "text_raw": item.text_raw,
            }
        )
        return result

    def record_hallucination(
        self,
        *,
        tenant_id: Optional[str],
        document_id: str,
        doc_hash: str,
        extractor: str,
        confidence_score: float,
        extraction: dict,
        provenance: Optional[dict] = None,
        text_raw: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Default to System Tenant if None
        tenant_uuid = UUID(tenant_id) if tenant_id else UUID("00000000-0000-0000-0000-000000000001")
        extraction_payload = self._mutable_extraction(extraction)
        attributes = extraction_payload.setdefault("attributes", {})
        attributes.setdefault("document_id", document_id)
        attributes["extractor"] = extractor
        resolved_text = text_raw or extraction_payload.get("source_text") or ""

        try:
            with self._session_scope(tenant_id=tenant_id) as session:
                item = ReviewItemModel(
                    tenant_id=tenant_uuid,
                    doc_hash=doc_hash,
                    text_raw=resolved_text,
                    extraction=extraction_payload,
                    provenance=provenance or {},
                    embedding=None,
                    confidence_score=confidence_score,
                    status="PENDING",
                    updated_at=self._now(),
                )
                session.add(item)
                session.flush()
                session.refresh(item)
                serialized = self._serialize(item)
                snapshot = self._snapshot(item)
        except IntegrityError as exc:
            # Duplicate detected - return existing record
            label_tenant = self._tenant_label(tenant_uuid)
            hallucination_duplicates_total.labels(tenant_id=label_tenant).inc()
            logger.info(
                "hallucination_duplicate_detected",
                tenant_id=label_tenant,
                doc_hash=doc_hash,
                error=str(exc),  # Log actual exception for debugging
            )
            return self._find_existing(tenant_uuid, doc_hash, resolved_text)
        except Exception as exc:
            # Log unexpected exceptions for debugging
            logger.error(
                "hallucination_insert_failed",
                tenant_id=tenant_id,
                doc_hash=doc_hash,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise

        self._bump_metrics(tenant_uuid, extractor)
        self._cache_snapshot(snapshot)
        logger.info(
            "hallucination_recorded",
            review_id=serialized["review_id"],
            tenant_id=serialized["tenant_id"],
            extractor=extractor,
            confidence=confidence_score,
        )
        return serialized

    def _find_existing(
        self, tenant_uuid: Optional[UUID], doc_hash: str, text_raw: str
    ) -> Dict[str, Any]:
        """Find existing review item for duplicate detection."""
        with self._session_scope() as session:
            query = session.query(ReviewItemModel).filter(
                ReviewItemModel.doc_hash == doc_hash,
                ReviewItemModel.text_raw == text_raw,
            )
            if tenant_uuid:
                query = query.filter(ReviewItemModel.tenant_id == tenant_uuid)
            else:
                # Default tenant ID (System Tenant)
                default_id = UUID("00000000-0000-0000-0000-000000000001")
                query = query.filter(ReviewItemModel.tenant_id == default_id)
            item = query.first()
            if item is None:
                raise LookupError("duplicate_record_not_found")
            return self._serialize(item)

    def record_hallucinations_batch(
        self,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Record multiple hallucinations in a single transaction for efficiency.
        
        Returns:
            Dict with 'successful', 'failed', and 'results' keys.
        """
        results = []
        successful = 0
        failed = 0
        
        with self._session_scope() as session:
            for item_data in items:
                try:
                    tenant_id = item_data.get("tenant_id")
                    tenant_uuid = UUID(tenant_id) if tenant_id else None
                    extraction_payload = self._mutable_extraction(item_data.get("extraction", {}))
                    attributes = extraction_payload.setdefault("attributes", {})
                    attributes.setdefault("document_id", item_data.get("document_id", "unknown"))
                    attributes["extractor"] = item_data.get("extractor", "unknown")
                    resolved_text = item_data.get("text_raw") or extraction_payload.get("source_text") or ""
                    
                    db_item = ReviewItemModel(
                        tenant_id=tenant_uuid,
                        doc_hash=item_data.get("doc_hash", "unknown"),
                        text_raw=resolved_text,
                        extraction=extraction_payload,
                        provenance=item_data.get("provenance") or {},
                        embedding=None,
                        confidence_score=item_data.get("confidence_score", 0.0),
                        status="PENDING",
                    )
                    session.add(db_item)
                    results.append({"status": "pending", "doc_hash": db_item.doc_hash})
                except Exception as exc:
                    logger.warning(f"Metric insert failed: {exc}", exc_info=True)
                    results.append({"status": "error", "error": str(exc), "input": item_data})
                    failed += 1
            
            # Flush all at once
            try:
                session.flush()
                # Update results with IDs after flush
                for i, res in enumerate(results):
                    if res["status"] == "pending":
                        res["status"] = "success"
                        successful += 1
            except IntegrityError as exc:
                # Some duplicates in batch - fall back to individual inserts
                session.rollback()
                return self._record_batch_fallback(items)
        
        return {"successful": successful, "failed": failed, "results": results}
    
    def _record_batch_fallback(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fallback to individual inserts when batch has duplicates."""
        results = []
        successful = 0
        failed = 0
        for item_data in items:
            try:
                result = self.record_hallucination(**item_data)
                results.append({"status": "success", "data": result})
                successful += 1
            except Exception as exc:
                logger.warning(f"Metric insert failed: {exc}", exc_info=True)
                results.append({"status": "error", "error": str(exc)})
                failed += 1
        return {"successful": successful, "failed": failed, "results": results}

    def list_hallucinations(
        self,
        *,
        status: Optional[str] = "PENDING",
        tenant_id: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List hallucinations with cursor-based pagination.
        
        Returns:
            Dict with 'items', 'next_cursor', and 'has_more' keys.
        """
        with self._session_scope() as session:
            query = session.query(ReviewItemModel)
            if status:
                query = query.filter(ReviewItemModel.status == status.upper())
            if tenant_id:
                query = query.filter(ReviewItemModel.tenant_id == UUID(tenant_id))
            
            # Cursor-based pagination using created_at + id
            if cursor:
                try:
                    cursor_time, cursor_id = cursor.split("_", 1)
                    cursor_dt = datetime.fromisoformat(cursor_time)
                    cursor_uuid = UUID(cursor_id)
                    # Items older than cursor OR same time but smaller ID
                    query = query.filter(
                        (ReviewItemModel.created_at < cursor_dt)
                        | (
                            (ReviewItemModel.created_at == cursor_dt)
                            & (ReviewItemModel.id < cursor_uuid)
                        )
                    )
                except (ValueError, TypeError) as exc:
                    logger.warning("invalid_pagination_cursor", cursor=cursor, error=str(exc))
            
            clamped_limit = max(1, min(limit, 500))
            items = (
                query.order_by(
                    ReviewItemModel.created_at.desc(),
                    ReviewItemModel.id.desc(),
                )
                .limit(clamped_limit + 1)  # fetch one extra to check for more
                .all()
            )
            
            has_more = len(items) > clamped_limit
            if has_more:
                items = items[:clamped_limit]
            
            next_cursor = None
            if has_more and items:
                last_item = items[-1]
                next_cursor = f"{last_item.created_at.isoformat()}_{last_item.id}"
            
            return {
                "items": [self._serialize(item) for item in items],
                "next_cursor": next_cursor,
                "has_more": has_more,
            }

    def get_hallucination(self, review_id: str) -> Dict[str, Any]:
        with self._session_scope() as session:
            item = session.get(ReviewItemModel, UUID(review_id))
            if item is None:
                raise LookupError("review_item_not_found")
            return self._serialize(item)

    def resolve_hallucination(
        self,
        review_id: str,
        *,
        new_status: str,
        reviewer_id: str,
        notes: Optional[str] = None,
        tenant_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
        actor_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve (approve/reject) a pending review item.

        Hardened against multiple tenant-isolation / review-correctness
        issues:

        - ``tenant_id`` (caller's authenticated tenant) MUST be passed
          by callers. If the looked-up ``item.tenant_id`` does not match,
          we raise ``LookupError`` (mapped to 404 upstream) to prevent
          cross-tenant approvals via guessed/leaked UUIDs.
          (Fixes #1360.)

        - Idempotency: the state machine rejects a second decision on an
          already-resolved item. Calling ``/approve`` or ``/reject`` on
          an APPROVED / REJECTED row raises ``ValueError`` which the
          route maps to 409 Conflict. The first reviewer's identity is
          preserved; we do NOT silently overwrite ``reviewer_id`` or
          ``review_notes``. (Fixes #1361.)

        - Audit chain: on a successful transition we append a
          ``review.decision`` entry to the tamper-evident ``audit_logs``
          SHA-256 hash chain via ``AuditLogger.log_event``. The actor is
          the human ``actor_user_id`` when available, falling back to
          the API key id. If the audit insert raises, the whole review
          update is rolled back -- the approval only becomes visible
          if and only if the audit chain entry is written. (Fixes #1369.)

        - Reviewer identity: callers SHOULD pass ``actor_user_id`` (the
          human user UUID from the authenticated session) so the audit
          row records the human rather than the bearer API key. If the
          caller only has a key_id we still record it, but we mark the
          provenance explicitly so auditors can see which decisions
          lack a human binding. (Partial fix for #1367; full
          per-human signature requires JWT + MFA step-up, tracked as
          follow-up.)
        """
        normalized_status = new_status.upper()
        if normalized_status not in {"APPROVED", "REJECTED"}:
            raise ValueError("Invalid status transition")

        with self._session_scope(tenant_id=tenant_id) as session:
            item = session.get(ReviewItemModel, UUID(review_id))
            if item is None:
                raise LookupError("review_item_not_found")

            # --- Tenant scoping (#1360) --------------------------------
            # If the caller passed a tenant_id, it MUST match the row.
            # We treat mismatch as "not found" to avoid leaking that a
            # review UUID exists in another tenant.
            if tenant_id is not None:
                try:
                    caller_tenant_uuid = UUID(str(tenant_id))
                except (ValueError, TypeError) as exc:
                    raise LookupError("review_item_not_found") from exc
                if item.tenant_id != caller_tenant_uuid:
                    logger.warning(
                        "review_cross_tenant_attempt_blocked",
                        review_id=review_id,
                        caller_tenant=str(caller_tenant_uuid),
                        item_tenant=str(item.tenant_id),
                        reviewer_id=reviewer_id,
                    )
                    # Raise 404 semantics -- do not acknowledge existence.
                    raise LookupError("review_item_not_found")

            # --- Idempotency (#1361) -----------------------------------
            prior_status = item.status
            if prior_status != "PENDING":
                # Already resolved: reject the second write. We explicitly
                # do not overwrite reviewer_id, review_notes, or
                # updated_at.
                logger.warning(
                    "review_idempotency_conflict",
                    review_id=review_id,
                    prior_status=prior_status,
                    attempted_status=normalized_status,
                    reviewer_id=reviewer_id,
                )
                raise ValueError(
                    f"Review item {review_id} is already {prior_status}; "
                    "a review decision cannot be changed once finalized"
                )

            was_pending = True  # guaranteed by the check above
            item.status = normalized_status
            item.reviewer_id = reviewer_id
            item.updated_at = self._now()
            if notes:
                provenance = dict(item.provenance or {})
                provenance["review_notes"] = notes
                # Record the identity binding so auditors can distinguish
                # human-bound decisions from key-only decisions. (#1367)
                provenance["reviewer_identity"] = {
                    "api_key_id": reviewer_id,
                    "user_id": actor_user_id,
                    "user_email": actor_email,
                    "human_bound": bool(actor_user_id),
                }
                item.provenance = provenance
            session.add(item)
            session.flush()

            # --- Audit chain write (#1369) -----------------------------
            # Emit to the tamper-evident audit_logs chain BEFORE commit.
            # If this fails, the SessionScope rolls back the transaction
            # so the review state change is atomic with the audit entry.
            try:
                from .audit import AuditLogger

                audit_actor_id = None
                if actor_user_id:
                    try:
                        audit_actor_id = UUID(str(actor_user_id))
                    except (ValueError, TypeError):
                        audit_actor_id = None

                audit_metadata = {
                    "status": normalized_status,
                    "prior_status": prior_status,
                    "api_key_id": reviewer_id,
                    "human_bound": bool(actor_user_id),
                }
                if notes:
                    import hashlib as _hashlib

                    audit_metadata["review_notes_sha256"] = _hashlib.sha256(
                        notes.encode("utf-8")
                    ).hexdigest()

                AuditLogger.log_event(
                    db=session,
                    tenant_id=item.tenant_id,
                    event_type="review.decision",
                    action=f"review.{normalized_status.lower()}",
                    event_category="data",
                    severity="info",
                    actor_id=audit_actor_id,
                    actor_email=actor_email,
                    resource_type="review_item",
                    resource_id=str(item.id),
                    metadata=audit_metadata,
                )
            except Exception as audit_err:  # noqa: BLE001
                # If audit-chain logging fails, fail the transition. The
                # approval must not commit without the tamper-evident
                # record being inserted.
                logger.error(
                    "review_audit_chain_write_failed",
                    review_id=review_id,
                    status=normalized_status,
                    error=str(audit_err),
                )
                raise

            session.refresh(item)
            serialized = self._serialize(item)
            snapshot = self._snapshot(item)
            resolved_tenant_id = item.tenant_id

        if was_pending:
            self._decrement_active_metric(resolved_tenant_id)
        self._cache_snapshot(snapshot)
        self._notify_webhook(serialized, normalized_status)
        logger.info(
            "hallucination_resolved",
            review_id=review_id,
            status=normalized_status,
            reviewer_id=reviewer_id,
            actor_user_id=actor_user_id,
            tenant_id=str(resolved_tenant_id) if resolved_tenant_id else None,
        )
        return serialized

    def _notify_webhook(self, serialized: Dict[str, Any], status: str) -> None:
        """Send webhook notification on resolution (fire-and-forget in background thread).
        
        Includes HMAC signature for webhook verification if signing secret is configured.
        """
        if not self._webhook_url:
            return
        
        def _send():
            try:
                payload = {
                    "event": "hallucination_resolved",
                    "status": status,
                    "data": serialized,
                    "timestamp": self._now().isoformat(),
                }
                payload_bytes = json.dumps(payload, default=str).encode("utf-8")
                
                # Build headers with optional HMAC signature
                headers = {"Content-Type": "application/json"}
                if WEBHOOK_SIGNING_AVAILABLE:
                    try:
                        signature = generate_signature(payload_bytes)
                        headers[get_signature_header_name("regengine")] = signature
                    except ValueError:
                        # No signing secret configured - send unsigned
                        logger.debug("webhook_signing_secret_not_configured")
                
                with httpx.Client(timeout=5.0) as client:
                    resp = client.post(
                        self._webhook_url,
                        content=payload_bytes,
                        headers=headers,
                    )
                    resp.raise_for_status()
                hallucination_webhook_calls_total.labels(status="success").inc()
                logger.info("webhook_notification_sent", review_id=serialized.get("review_id"))
            except Exception as exc:
                hallucination_webhook_calls_total.labels(status="error").inc()
                logger.warning(
                    "webhook_notification_failed",
                    error=str(exc),
                    review_id=serialized.get("review_id"),
                )
        
        # Fire-and-forget: don't block the API response
        thread = threading.Thread(target=_send, daemon=True)
        thread.start()


_tracker: Optional[HallucinationTracker] = None
_tracker_lock = threading.Lock()


def _build_redis_client() -> Optional[RedisType]:
    if redis is None:
        return None
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        logger.info("redis_cache_connected", url=url)
        return client
    except Exception as exc:  # pragma: no cover - depends on runtime env
        logger.warning("redis_cache_unavailable", error=str(exc))
        return None


def get_hallucination_tracker() -> HallucinationTracker:
    """Return a singleton tracker wired to SQLAlchemy + Redis."""

    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                redis_client = _build_redis_client()
                _tracker = HallucinationTracker(SessionLocal, redis_client)
    return _tracker
