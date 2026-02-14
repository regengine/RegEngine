"""
Energy Service - FastAPI Application

Compliance snapshot and mismatch management API.
"""
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from prometheus_client import make_asgi_app
import structlog
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.database import Base, ComplianceSnapshotModel
from app.db_session import get_db
from app.snapshot_engine import SnapshotEngine
from app.models import (
    SnapshotCreationRequest,
    SnapshotGenerator,
    SnapshotTriggerEvent
)
from app.crypto import verify_signature_hash

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="RegEngine Energy - Compliance API",
    description="Immutable compliance snapshot and mismatch management",
    version="1.0.0"
)

# Register rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add shared utilities to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware

# Tenant isolation middleware - extracts tenant_id from JWT or headers
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)

# Per-tenant rate limiting (Sprint 16)
from shared.tenant_rate_limiting import TenantRateLimitMiddleware
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

# CORS - configurable for production
import os
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

_energy_logger = structlog.get_logger("energy-api")

@app.on_event("startup")
async def startup():
    _energy_logger.info("energy_service_started", version="1.0.0")

@app.on_event("shutdown")
async def shutdown():
    _energy_logger.info("energy_service_stopped")


# Request/Response Models

class SnapshotCreateRequest(BaseModel):
    """API request to create snapshot with full state data."""
    substation_id: str = Field(..., min_length=1)
    facility_name: str = Field(..., min_length=1)
    system_status: str = Field(default="NOMINAL")
    assets: List[dict] = Field(default_factory=list)
    esp_config: dict = Field(default_factory=dict)
    patch_metrics: dict = Field(default_factory=dict)
    trigger_reason: str = Field(default="Manual API request")


class SnapshotResponse(BaseModel):
    """API response for snapshot."""
    snapshot_id: str
    snapshot_time: str
    system_status: str
    asset_summary: dict
    content_hash: str
    signature_hash: Optional[str] = None


class ErrorResponse(BaseModel):
    """Structured error response."""
    error: str
    detail: str
    error_id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# Endpoints

from app.auth import get_current_user, get_optional_user, AuthenticatedUser

@limiter.limit("10/minute")  # H-1: Rate limiting - max 10 snapshots/min per IP
@app.post("/energy/snapshots", status_code=201, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def create_snapshot(
    request: SnapshotCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)  # Require authentication
):
    """
    Create manual compliance snapshot.
    
    Requires authentication - user ID extracted from JWT token.
    Production endpoint with proper user attribution.
    """
    from sqlalchemy.exc import IntegrityError, SQLAlchemyError
    from pydantic import ValidationError
    
    try:
        engine = SnapshotEngine(db)
        
        # Convert SDK request to internal snapshot request
        # Use data from request body instead of mock helper
        snapshot_request = SnapshotCreationRequest(
            substation_id=request.substation_id,
            facility_name=request.facility_name,
            asset_states={
                "assets": [asset.model_dump() for asset in request.assets] if hasattr(request.assets[0], 'model_dump') else request.assets,
                "summary": {
                    "total_assets": len(request.assets),
                    "verified_count": sum(1 for a in request.assets if getattr(a, 'last_verified', None)),
                    "mismatch_count": 0,
                    "unknown_count": 0
                }
            },
            esp_config=request.esp_config.model_dump() if hasattr(request.esp_config, 'model_dump') else request.esp_config,
            patch_metrics=request.patch_metrics or {},
            active_mismatch_ids=[],
            generated_by=SnapshotGenerator.USER_MANUAL,
            trigger_event=SnapshotTriggerEvent.USER_MANUAL_REQUEST,
            generator_user_id=UUID(current_user.user_id),  # Extract from JWT token
            tenant_id=UUID(current_user.tenant_id) if current_user.tenant_id else None
        )
        
        snapshot = engine.create_snapshot(snapshot_request)
        
        return SnapshotResponse(
            snapshot_id=str(snapshot.id),
            snapshot_time=snapshot.snapshot_time.isoformat(),
            system_status=snapshot.system_status.value,
            asset_summary=snapshot.asset_states.get("summary", {}),
            content_hash=snapshot.content_hash,
            signature_hash=snapshot.signature_hash
        )
    
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Validation error: {str(e)}"
        )
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Database integrity error: duplicate or constraint violation"
        )
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )




@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Enhanced health check with dependency validation.
    
    Validates:
    - Database connectivity
    - Latest snapshot signature integrity
    """
    health = {
        "status": "healthy",
        "service": "energy-api",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "dependencies": []
    }
    
    # Check database
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        health["dependencies"].append({
            "name": "postgresql",
            "status": "healthy"
        })
    except Exception as e:
        health["status"] = "unhealthy"
        health["dependencies"].append({
            "name": "postgresql",
            "status": "unhealthy",
            "error": str(e)
        })
        return JSONResponse(content=health, status_code=503)
    
    # Check chain integrity of latest snapshot
    try:
        latest = (
            db.query(ComplianceSnapshotModel)
            .order_by(ComplianceSnapshotModel.id.desc())
            .first()
        )
        
        if latest:
            # Verify signature
            is_valid = verify_signature_hash(
                latest.id,
                latest.content_hash,
                latest.signature_hash
            )
            
            health["dependencies"].append({
                "name": "snapshot_integrity",
                "status": "healthy" if is_valid else "corrupted",
                "latest_snapshot_id": str(latest.id)
            })
            
            if not is_valid:
                health["status"] = "corrupted"
                return JSONResponse(content=health, status_code=503)
        else:
            health["dependencies"].append({
                "name": "snapshot_integrity",
                "status": "no_snapshots"
            })
    
    except Exception as e:
        health["dependencies"].append({
            "name": "snapshot_integrity",
            "status": "error",
            "error": str(e)
        })
    
    status_code = 200 if health["status"] == "healthy" else 503
    return JSONResponse(content=health, status_code=status_code)


@app.get("/ready")
async def readiness():
    """Readiness probe for k8s orchestration."""
    return {"status": "ready", "service": "energy-api", "version": "1.0.0"}


@app.get("/energy/verify/latest/{substation_id}")
def verify_latest_snapshot(
    substation_id: str,
    db: Session = Depends(get_db)
):
    """
    H-2: Post-commit signature verification.
    
    Verifies latest snapshot integrity:
    - Content hash recalculation
    - Signature validity
    - Chain integrity
    
    Makes corruption an observable condition.
    """
    from app.verifier import SnapshotVerifier
    
    verifier = SnapshotVerifier(db)
    report = verifier.verify_latest_snapshot(substation_id)
    
    if report.get("status") == "corrupted":
        return JSONResponse(
            content=report,
            status_code=500  # Internal error - corruption detected
        )
    
    return report


@app.get("/energy/verify/recent")
def verify_recent_snapshots(
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    """
    Verify N most recent snapshots.
    
    Background verification endpoint for monitoring.
    """
    from app.verifier import SnapshotVerifier
    
    verifier = SnapshotVerifier(db)
    results = verifier.verify_all_recent(limit)
    
    if results["corrupted"] > 0:
        return JSONResponse(
            content=results,
            status_code=500
        )
    
    return results


# Query endpoints

@app.get("/energy/snapshots", responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def list_snapshots(
    substation_id: str = Query(..., description="Substation ID"),
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=200, description="Max results"),
    offset: int = Query(0, description="Pagination offset"),
    db: Session = Depends(get_db)
):
    """
    List snapshots with pagination and filtering.
    
    Optimized with:
    - Covering index on (substation_id, snapshot_time, system_status)
    - Deferred JSONB columns (only fetched if needed)
    - Efficient pagination
    """
    from app.queries import get_cached_count
    from sqlalchemy.exc import SQLAlchemyError
    
    # Validate date range
    if from_time and to_time and from_time >= to_time:
        raise HTTPException(
            status_code=400,
            detail="Invalid date range: from_time must be before to_time"
        )
    
    try:
        query = (
            db.query(
                ComplianceSnapshotModel.id,
                ComplianceSnapshotModel.snapshot_time,
                ComplianceSnapshotModel.system_status,
                ComplianceSnapshotModel.content_hash,
                ComplianceSnapshotModel.signature_hash,
                ComplianceSnapshotModel.generated_by,
                ComplianceSnapshotModel.trigger_event
            )
            .filter(ComplianceSnapshotModel.substation_id == substation_id)
        )
        
        if from_time:
            query = query.filter(ComplianceSnapshotModel.snapshot_time >= from_time)
        
        if to_time:
            query = query.filter(ComplianceSnapshotModel.snapshot_time <= to_time)
        
        if status:
            query = query.filter(ComplianceSnapshotModel.system_status == status)
        
        # Count query with caching strategy documented
        total = get_cached_count(db, substation_id, from_time, to_time, status)
        
        # Fetch page
        snapshots = (
            query
            .order_by(ComplianceSnapshotModel.snapshot_time.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        
        return {
            "snapshots": [
                {
                    "id": str(s.id),
                    "snapshot_time": s.snapshot_time.isoformat(),
                    "system_status": s.system_status.value,
                    "content_hash": s.content_hash,
                    "signature_hash": s.signature_hash,
                    "generated_by": s.generated_by.value,
                    "trigger_event": s.trigger_event.value if s.trigger_event else None
                }
                for s in snapshots
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total
        }
    
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database query error: {str(e)}"
        )


@app.get("/energy/snapshots/{snapshot_id}", responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def get_snapshot_detail(
    snapshot_id: UUID,
    include_asset_details: bool = Query(False),
    include_esp_config: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    Get detailed snapshot with selective JSONB loading.
    
    Reduces bandwidth for auditors who only need metadata.
    """
    from sqlalchemy.orm import defer
    from sqlalchemy.exc import SQLAlchemyError
    
    try:
        query = db.query(ComplianceSnapshotModel).filter_by(id=snapshot_id)
        
        # Defer expensive JSONB columns by default
        if not include_asset_details:
            query = query.options(defer(ComplianceSnapshotModel.asset_states))
        
        if not include_esp_config:
            query = query.options(defer(ComplianceSnapshotModel.esp_config))
        
        snapshot = query.first()
        
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"Snapshot {snapshot_id} not found"
            )
        
        result = {
            "id": str(snapshot.id),
            "created_at": snapshot.created_at.isoformat(),
            "snapshot_time": snapshot.snapshot_time.isoformat(),
            "substation_id": snapshot.substation_id,
            "facility_name": snapshot.facility_name,
            "system_status": snapshot.system_status.value,
            "content_hash": snapshot.content_hash,
            "signature_hash": snapshot.signature_hash,
            "previous_snapshot_id": str(snapshot.previous_snapshot_id) if snapshot.previous_snapshot_id else None,
            "generated_by": snapshot.generated_by.value,
            "trigger_event": snapshot.trigger_event.value if snapshot.trigger_event else None,
            "regulatory_version": snapshot.regulatory_version
        }
        
        # Conditionally include heavy fields
        if include_asset_details:
            result["asset_states"] = snapshot.asset_states
        
        if include_esp_config:
            result["esp_config"] = snapshot.esp_config
        
        return result
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error retrieving snapshot: {str(e)}"
        )


@app.get("/energy/snapshots/export")
def export_snapshots(
    substation_id: str = Query(...),
    from_time: datetime = Query(...),
    to_time: datetime = Query(...),
    format: str = Query("csv", regex="^(csv|json)$"),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)  # Require auth for exports
):
    """
    Export snapshots for audit trail.
    
    Requires authentication - prevents unauthorized data access.
    Supports CSV and JSON formats.
    Streams response to avoid memory issues with large exports.
    Column whitelist prevents accidental sensitive data exposure.
    """
    from fastapi.responses import StreamingResponse
    from app.queries import generate_csv_stream, generate_json_stream
    
    # Validate date range
    if from_time >= to_time:
        raise HTTPException(
            status_code=400,
            detail="Invalid date range: from_time must be before to_time"
        )
    
    if format == "csv":
        return StreamingResponse(
            generate_csv_stream(substation_id, from_time, to_time, db),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=snapshots_{substation_id}_{from_time.date()}_to_{to_time.date()}.csv"
            }
        )
    else:  # format == "json"
        return StreamingResponse(
            generate_json_stream(substation_id, from_time, to_time, db),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=snapshots_{substation_id}_{from_time.date()}_to_{to_time.date()}.json"
            }
        )


@app.get("/energy/substations/{substation_id}/snapshots/export/verify")
def export_for_verification(
    substation_id: str,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Export snapshot chain for customer verification SDK.
    
    P0-1 Implementation: External Verification SDK Export
    
    Returns complete snapshot chain with all cryptographic fields needed
    for independent customer-side verification of chain integrity.
    
    This endpoint is the bridge between RegEngine's backend and customer
    verification SDK, enabling "don't trust us, verify the math" capability.
    
    Export Format:
    {
        "metadata": {
            "substation_id": "ALPHA-001",
            "export_time": "2026-01-30T08:00:00Z",
            "total_snapshots": 47,
            "verification_sdk_version": "1.0.0"
        },
        "snapshots": [
            {
                "id": "uuid-here",
                "snapshot_time": "2026-01-30T00:00:00Z",
                "substation_id": "ALPHA-001",
                "system_status": "NOMINAL",
                "asset_states": {...},
                "esp_config": {...},
                "patch_metrics": {...},
                "active_mismatches": [],
                "content_hash": "sha256-hexdigest",
                "signature_hash": "sha256-hexdigest",
                "previous_snapshot_id": "uuid-of-previous" | null
            },
            ...
        ]
    }
    
    Security:
    - Requires authentication (prevents anonymous data access)
    - Returns only customer's own substation data
    - No sensitive credentials included
    """
    from sqlalchemy.exc import SQLAlchemyError
    
    try:
        # Build query
        query = (
            db.query(ComplianceSnapshotModel)
            .filter(ComplianceSnapshotModel.substation_id == substation_id)
        )
        
        if from_time:
            query = query.filter(ComplianceSnapshotModel.snapshot_time >= from_time)
        
        if to_time:
            query = query.filter(ComplianceSnapshotModel.snapshot_time <= to_time)
        
        # Order by snapshot_time (chronological chain)
        snapshots = query.order_by(ComplianceSnapshotModel.snapshot_time.asc()).all()
        
        if not snapshots:
            raise HTTPException(
                status_code=404,
                detail=f"No snapshots found for substation {substation_id}"
            )
        
        # Build export
        export_data = {
            "metadata": {
                "substation_id": substation_id,
                "export_time": datetime.now(timezone.utc).isoformat(),
                "total_snapshots": len(snapshots),
                "verification_sdk_version": "1.0.0",
                "from_time": snapshots[0].snapshot_time.isoformat() if snapshots else None,
                "to_time": snapshots[-1].snapshot_time.isoformat() if snapshots else None
            },
            "snapshots": [
                {
                    "id": str(snapshot.id),
                    "snapshot_time": snapshot.snapshot_time.isoformat(),
                    "substation_id": snapshot.substation_id,
                    "facility_name": snapshot.facility_name,
                    "system_status": snapshot.system_status.value,
                    "asset_states": snapshot.asset_states,
                    "esp_config": snapshot.esp_config,
                    "patch_metrics": snapshot.patch_metrics,
                    "active_mismatches": snapshot.active_mismatch_ids or [],
                    "content_hash": snapshot.content_hash,
                    "signature_hash": snapshot.signature_hash,
                    "previous_snapshot_id": str(snapshot.previous_snapshot_id) if snapshot.previous_snapshot_id else None
                }
                for snapshot in snapshots
            ]
        }
        
        return JSONResponse(
            content=export_data,
            headers={
                "Content-Disposition": f"attachment; filename=verification_export_{substation_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            }
        )
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error during export: {str(e)}"
        )



