from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
import sys
from pathlib import Path
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

# Standardized path discovery
_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

# Ensure shared utilities are importable
from shared.paths import ensure_shared_importable
ensure_shared_importable()

# Production Hardening (Phase 18)
from shared.logging import setup_logging
from shared.middleware.security import add_security
from shared.rate_limit import add_rate_limiting
from shared.observability import add_observability

# Initialize standardized logging
logger = setup_logging()

# Local imports
from .db_session import get_db
from .snapshot_engine import SnapshotEngine
from .verifier import SnapshotVerifier
from .models import (
    SnapshotCreationRequest,
    ComplianceSnapshot,
    SnapshotGenerator,
    SnapshotTriggerEvent
)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("energy_service_startup")
    yield
    # Shutdown
    logger.info("energy_service_shutdown")

app = FastAPI(
    title="Energy Compliance Service",
    description="FERC and NERC regulatory compliance engine",
    version="1.0.0",
    lifespan=lifespan,
)

# Production Hardening Middleware (Phase 18)
add_security(app)
add_rate_limiting(app)
add_observability(app)

from shared.middleware import TenantContextMiddleware, RequestIDMiddleware
from shared.tenant_rate_limiting import TenantRateLimitMiddleware

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(TenantRateLimitMiddleware, default_rpm=100)

# Global exception handlers (Sprint 18)
from shared.error_handling import install_exception_handlers
install_exception_handlers(app)

# --- Original Energy Service Routes ---

@app.post("/api/v1/energy/snapshots", response_model=ComplianceSnapshot)
async def create_snapshot(
    request: SnapshotCreationRequest,
    db: Session = Depends(get_db)
):
    """Create a geotagged, cryptographically sealed snapshot."""
    engine = SnapshotEngine(db)
    try:
        snapshot = engine.create_snapshot_idempotent(request)
        return snapshot
    except Exception as e:
        logger.error("snapshot_creation_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Snapshot creation failed")

@app.get("/api/v1/energy/snapshots", response_model=List[ComplianceSnapshot])
async def list_snapshots(
    substation_id: Optional[str] = None,
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db)
):
    """List snapshots with pagination."""
    from .database import ComplianceSnapshotModel
    query = db.query(ComplianceSnapshotModel)
    if substation_id:
        query = query.filter(ComplianceSnapshotModel.substation_id == substation_id)
    results = query.order_by(ComplianceSnapshotModel.snapshot_time.desc()).limit(limit).all()
    return results

@app.get("/api/v1/energy/verify/latest/{substation_id}")
async def verify_latest(
    substation_id: str,
    db: Session = Depends(get_db)
):
    """Real-time head-of-chain integrity check."""
    verifier = SnapshotVerifier(db)
    return verifier.verify_latest_snapshot(substation_id)

@app.get("/api/v1/energy/verify/recent")
async def verify_recent(
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    """High-intensity bulk audit of the compliance chain."""
    verifier = SnapshotVerifier(db)
    return verifier.verify_all_recent(limit=limit)

# --- Standardized Health & Readiness (Phase 17) ---
from shared.health import HealthCheck, install_health_router
from sqlalchemy import text

health = HealthCheck(service_name="energy-service")

async def check_database():
    try:
        db = next(get_db())
        try:
            db.execute(text("SELECT 1"))
            return True
        finally:
            db.close()
    except Exception:
        return False

health.add_dependency("postgres", check_database)
install_health_router(app, service_name="energy-service", health_check=health)
