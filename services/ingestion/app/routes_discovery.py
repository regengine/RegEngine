"""Discovery queue routes: approve, reject, bulk operations."""

from __future__ import annotations

from typing import List

import redis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from shared.auth import APIKey, require_api_key
from shared.database import SessionLocal
from shared.task_queue import enqueue_task

from .config import get_settings
from .models import (
    DiscoveryQueueItem, BulkDiscoveryRequest, ManualQueueResponse,
    DiscoveryApprovalResponse, DiscoveryRejectionResponse,
    BulkDiscoveryApprovalResponse, BulkDiscoveryRejectionResponse
)

logger = structlog.get_logger("ingestion.discovery")
router = APIRouter(include_in_schema=False)


@router.get("/v1/ingest/discovery/queue", response_model=List[DiscoveryQueueItem])
async def get_discovery_queue(api_key: APIKey = Depends(require_api_key)):
    """Retrieve all items in the manual discovery queue."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)

    items = r.lrange("manual_upload_queue", 0, -1)
    results = []
    for i, item in enumerate(items):
        try:
            val = item.decode("utf-8")
            if ":" in val:
                body, url = val.split(":", 1)
                results.append(DiscoveryQueueItem(body=body, url=url, index=i))
        except Exception as e:
            logger.debug("discovery_queue_parse_skip", index=i, error=str(e))
            continue
    return results


@router.get("/v1/ingest/manual-queue", response_model=ManualQueueResponse)
async def get_manual_queue(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    api_key: APIKey = Depends(require_api_key),
):
    """Retrieve items from the tenant-scoped manual upload queue."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    tenant_id = api_key.tenant_id

    queue_key = f"manual_upload_queue:{tenant_id}"
    total = r.llen(queue_key)
    raw_items = r.lrange(queue_key, skip, skip + limit - 1)

    items = []
    for i, raw in enumerate(raw_items):
        try:
            val = raw.decode("utf-8")
            if ":" in val:
                body, url = val.split(":", 1)
                items.append({"index": skip + i, "body": body, "url": url})
            else:
                items.append({"index": skip + i, "body": val, "url": None})
        except Exception as e:
            logger.debug("manual_queue_parse_skip", index=skip + i, error=str(e))
            continue

    logger.info(
        "manual_queue_fetched",
        tenant_id=tenant_id,
        total=total,
        returned=len(items),
    )
    return {
        "tenant_id": tenant_id,
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": items,
    }


@router.post("/v1/ingest/discovery/approve", response_model=DiscoveryApprovalResponse)
async def approve_discovery(
    index: int,
    api_key: APIKey = Depends(require_api_key),
):
    """Approve a discovery item and trigger a scrape."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)

    item = r.lindex("manual_upload_queue", index)
    if not item:
        raise HTTPException(status_code=404, detail="Discovery item not found at index")

    val = item.decode("utf-8")
    body, url = val.split(":", 1)
    r.lrem("manual_upload_queue", 1, item)

    db = SessionLocal()
    try:
        enqueue_task(
            db,
            task_type="discovery_scrape",
            payload={"body": body, "url": url},
            tenant_id=api_key.tenant_id,
        )
        db.commit()
    finally:
        db.close()

    logger.info("discovery_approved", body=body, url=url, tenant_id=api_key.tenant_id)
    return {"status": "approved", "body": body, "url": url}


@router.post("/v1/ingest/discovery/reject", response_model=DiscoveryRejectionResponse)
async def reject_discovery(
    index: int,
    api_key: APIKey = Depends(require_api_key),
):
    """Reject and remove a discovery item from the queue."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)

    item = r.lindex("manual_upload_queue", index)
    if not item:
        raise HTTPException(status_code=404, detail="Discovery item not found at index")

    r.lrem("manual_upload_queue", 1, item)
    logger.info("discovery_rejected", index=index, tenant_id=api_key.tenant_id)
    return {"status": "rejected", "index": index}


@router.post("/v1/ingest/discovery/bulk-approve", response_model=BulkDiscoveryApprovalResponse)
async def bulk_approve_discovery(
    payload: BulkDiscoveryRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Approve multiple discovery items and trigger scrapes."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)

    approved = []
    items_to_process = []
    for index in payload.indices:
        item = r.lindex("manual_upload_queue", index)
        if item:
            items_to_process.append(item)

    db = SessionLocal()
    try:
        for item in items_to_process:
            val = item.decode("utf-8")
            body, url = val.split(":", 1)
            r.lrem("manual_upload_queue", 1, item)
            enqueue_task(
                db,
                task_type="discovery_scrape",
                payload={"body": body, "url": url},
                tenant_id=api_key.tenant_id,
            )
            approved.append({"body": body, "url": url})
        db.commit()
    finally:
        db.close()

    logger.info("bulk_discovery_approved", count=len(approved), tenant_id=api_key.tenant_id)
    return {"status": "approved", "count": len(approved), "items": approved}


@router.post("/v1/ingest/discovery/bulk-reject", response_model=BulkDiscoveryRejectionResponse)
async def bulk_reject_discovery(
    payload: BulkDiscoveryRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Reject and remove multiple discovery items from the queue."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)

    items_to_remove = []
    for index in payload.indices:
        item = r.lindex("manual_upload_queue", index)
        if item:
            items_to_remove.append(item)

    rejected_count = 0
    for item in items_to_remove:
        r.lrem("manual_upload_queue", 1, item)
        rejected_count += 1

    logger.info("bulk_discovery_rejected", count=rejected_count, tenant_id=api_key.tenant_id)
    return {"status": "rejected", "count": rejected_count}
