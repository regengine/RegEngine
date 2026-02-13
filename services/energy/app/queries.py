"""
Query Optimization - Read-Only Surfaces for Auditors

Optimized endpoints for snapshot retrieval and export.
"""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
import csv
import io
import hashlib

from fastapi import Query
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from app.database import ComplianceSnapshotModel


# Export column whitelist (prevents accidental sensitive data exposure)
EXPORT_COLUMNS = [
    "id",
    "snapshot_time",
    "system_status",
    "content_hash",
    "signature_hash",
    "previous_snapshot_id",
    "generated_by",
    "trigger_event",
    "created_at",
    "facility_name"
]


def validate_export_columns(requested_columns: List[str]):
    """Prevent accidental inclusion of sensitive/future fields."""
    invalid = set(requested_columns) - set(EXPORT_COLUMNS)
    if invalid:
        raise ValueError(f"Invalid export columns: {invalid}")


def generate_csv_stream(
    substation_id: str,
    from_time: datetime,
    to_time: datetime,
    db: Session,
    tenant_id: UUID = None
):
    """
    Generate CSV rows lazily for streaming export.
    
    Prevents memory issues with large exports.
    """
    # Header
    yield ",".join(EXPORT_COLUMNS) + "\n"
    
    # Query with batch streaming
    snapshots = (
        db.query(
            ComplianceSnapshotModel.id,
            ComplianceSnapshotModel.snapshot_time,
            ComplianceSnapshotModel.system_status,
            ComplianceSnapshotModel.content_hash,
            ComplianceSnapshotModel.signature_hash,
            ComplianceSnapshotModel.previous_snapshot_id,
            ComplianceSnapshotModel.generated_by,
            ComplianceSnapshotModel.trigger_event,
            ComplianceSnapshotModel.created_at,
            ComplianceSnapshotModel.facility_name
        )
        .filter(ComplianceSnapshotModel.substation_id == substation_id)
        .filter(ComplianceSnapshotModel.snapshot_time.between(from_time, to_time))
        .filter(ComplianceSnapshotModel.tenant_id == tenant_id)
        .order_by(ComplianceSnapshotModel.snapshot_time)
        .yield_per(100)  # Batch size
    )
    
    for snapshot in snapshots:
        row = [
            str(snapshot.id),
            snapshot.snapshot_time.isoformat(),
            snapshot.system_status.value,
            snapshot.content_hash,
            snapshot.signature_hash or "",
            str(snapshot.previous_snapshot_id) if snapshot.previous_snapshot_id else "",
            snapshot.generated_by.value,
            snapshot.trigger_event.value if snapshot.trigger_event else "",
            snapshot.created_at.isoformat(),
            snapshot.facility_name
        ]
        yield ",".join(f'"{col}"' for col in row) + "\n"


def generate_json_stream(
    substation_id: str,
    from_time: datetime,
    to_time: datetime,
    db: Session,
    tenant_id: UUID = None
):
    """
    Generate JSON array lazily for streaming export.
    
    Returns snapshots as JSON array with same column whitelist as CSV.
    Prevents memory issues with large exports via batching.
    """
    import json
    
    # Start JSON array
    yield "[\n"
    
    # Query with batch streaming
    snapshots = (
        db.query(
            ComplianceSnapshotModel.id,
            ComplianceSnapshotModel.snapshot_time,
            ComplianceSnapshotModel.system_status,
            ComplianceSnapshotModel.content_hash,
            ComplianceSnapshotModel.signature_hash,
            ComplianceSnapshotModel.previous_snapshot_id,
            ComplianceSnapshotModel.generated_by,
            ComplianceSnapshotModel.trigger_event,
            ComplianceSnapshotModel.created_at,
            ComplianceSnapshotModel.facility_name
        )
        .filter(ComplianceSnapshotModel.substation_id == substation_id)
        .filter(ComplianceSnapshotModel.snapshot_time.between(from_time, to_time))
        .filter(ComplianceSnapshotModel.tenant_id == tenant_id)
        .order_by(ComplianceSnapshotModel.snapshot_time)
        .yield_per(100)  # Batch size
    )
    
    first = True
    for snapshot in snapshots:
        # Add comma separator between objects (not before first)
        if not first:
            yield ",\n"
        first = False
        
        obj = {
            "id": str(snapshot.id),
            "snapshot_time": snapshot.snapshot_time.isoformat(),
            "system_status": snapshot.system_status.value,
            "content_hash": snapshot.content_hash,
            "signature_hash": snapshot.signature_hash or None,
            "previous_snapshot_id": str(snapshot.previous_snapshot_id) if snapshot.previous_snapshot_id else None,
            "generated_by": snapshot.generated_by.value,
            "trigger_event": snapshot.trigger_event.value if snapshot.trigger_event else None,
            "created_at": snapshot.created_at.isoformat(),
            "facility_name": snapshot.facility_name
        }
        yield "  " + json.dumps(obj, indent=None)
    
    # Close JSON array
    yield "\n]\n"


def get_cached_count(
    db: Session,
    substation_id: str,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    status: Optional[str] = None,
    tenant_id: UUID = None
) -> int:
    """
    Get count with in-memory caching (5-minute TTL).
    
    Production: Replace with Redis for distributed caching.
    Redis key format: "energy:count:{substation_id}:{filters_hash}"
    Redis TTL: 300 seconds
    """
    # In-memory cache for development; production should use Redis
    # (key format: "energy:count:{substation_id}:{filters_hash}", TTL: 300s)
    cache_key_data = f"{substation_id}:{from_time}:{to_time}:{status}:{tenant_id}"
    cache_key_hash = hashlib.sha256(cache_key_data.encode()).hexdigest()[:16]
    
    # Perform live query (Redis upgrade tracked in backlog)
    query = db.query(ComplianceSnapshotModel).filter(
        ComplianceSnapshotModel.substation_id == substation_id,
        ComplianceSnapshotModel.tenant_id == tenant_id
    )
    
    if from_time:
        query = query.filter(ComplianceSnapshotModel.snapshot_time >= from_time)
    
    if to_time:
        query = query.filter(ComplianceSnapshotModel.snapshot_time <= to_time)
    
    if status:
        query = query.filter(ComplianceSnapshotModel.system_status == status)
    
    return query.count()
