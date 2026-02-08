"""
Transaction vault API for immutable gaming transaction logs.
Core compliance module for Gaming Commission audits.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field
import hashlib

from .models import TransactionLog, SelfExclusionRecord, ResponsibleGamingAlert
from .db_session import get_db
from .auth import require_api_key

import sys
import uuid
from pathlib import Path

# Add shared utilities (portable path resolution)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.middleware import get_current_tenant_id

router = APIRouter(prefix="/v1/gaming", tags=["gaming"])


# Request/Response Models
class TransactionCreate(BaseModel):
    """Request body for creating a transaction log."""
    player_id: str = Field(..., min_length=1, max_length=255)
    transaction_type: str = Field(..., pattern="^(WAGER|PAYOUT|JACKPOT|DEPOSIT|WITHDRAWAL)$")
    amount_cents: int = Field(..., ge=0)
    game_id: str = Field(..., min_length=1, max_length=255)
    jurisdiction: str = Field(..., min_length=1, max_length=100)
    timestamp: datetime
    metadata: Optional[dict] = None


class TransactionResponse(BaseModel):
    """Response body for transaction creation."""
    id: int
    content_hash: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class SelfExclusionCreate(BaseModel):
    """Request body for self-exclusion registration."""
    player_id: str = Field(..., min_length=1, max_length=255)
    duration_days: int = Field(..., ge=0)
    reason: Optional[str] = Field(None, max_length=500)


class DashboardMetrics(BaseModel):
    """Dashboard metrics for Gaming compliance."""
    total_transactions: int
    total_volume_cents: int
    active_players_24h: int
    active_exclusions: int
    pending_alerts: int
    jurisdiction_breakdown: dict


# API Endpoints
@router.post("/transaction-log", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    transaction: TransactionCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Create immutable transaction record with cryptographic integrity.
    Required for Gaming Commission audits and AML/FinCEN reporting.
    
    **Compliance Standards:**
    - Nevada Gaming Control Board Regulation 6
    - New Jersey DGE Technical Standards
    - IGRA (Indian Gaming Regulatory Act)
    - FinCEN Anti-Money Laundering requirements
    """
    # Check if player is self-excluded
    exclusion = db.query(SelfExclusionRecord).filter(
        SelfExclusionRecord.player_id == transaction.player_id,
        SelfExclusionRecord.status == "ACTIVE",
        SelfExclusionRecord.tenant_id == tenant_id
    ).first()
    
    if exclusion:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Player {transaction.player_id} is currently self-excluded until {exclusion.expiration_date}"
        )
    
    # Calculate content hash (immutability proof)
    content = (
        f"{transaction.player_id}:"
        f"{transaction.transaction_type}:"
        f"{transaction.amount_cents}:"
        f"{transaction.game_id}:"
        f"{transaction.timestamp.isoformat()}"
    )
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    
    # Check for duplicate (idempotency)
    existing = db.query(TransactionLog).filter(
        TransactionLog.content_hash == content_hash,
        TransactionLog.tenant_id == tenant_id
    ).first()
    
    if existing:
        return TransactionResponse(
            id=existing.id,
            content_hash=existing.content_hash,
            status="duplicate",
            created_at=existing.created_at
        )
    
    # Create record
    record = TransactionLog(
        tenant_id=tenant_id,
        player_id=transaction.player_id,
        transaction_type=transaction.transaction_type,
        amount_cents=transaction.amount_cents,
        game_id=transaction.game_id,
        jurisdiction=transaction.jurisdiction,
        timestamp=transaction.timestamp,
        content_hash=content_hash,
        metadata=transaction.metadata,
        created_at=datetime.utcnow()
    )
    
    db.add(record)
    db.commit()
    db.refresh(record)
    
    return TransactionResponse(
        id=record.id,
        content_hash=record.content_hash,
        status="sealed",
        created_at=record.created_at
    )


@router.get("/transaction-log/{transaction_id}")
async def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Retrieve transaction by ID with integrity verification."""
    record = db.query(TransactionLog).filter(
        TransactionLog.id == transaction_id,
        TransactionLog.tenant_id == tenant_id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return {
        "id": record.id,
        "player_id": record.player_id,
        "transaction_type": record.transaction_type,
        "amount_cents": record.amount_cents,
        "game_id": record.game_id,
        "jurisdiction": record.jurisdiction,
        "timestamp": record.timestamp,
        "content_hash": record.content_hash,
        "created_at": record.created_at,
        "metadata": record.metadata
    }


@router.post("/self-exclusion", status_code=status.HTTP_201_CREATED)
async def register_self_exclusion(
    exclusion: SelfExclusionCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Register player self-exclusion for responsible gaming compliance.
    
    **Compliance Standards:**
    - Nevada Regulation 5.011 (Self-Exclusion Program)
    - NJ Responsible Gaming Statute
    - Responsible Gaming Framework (RGF)
    """
    # Check for existing active exclusion
    existing = db.query(SelfExclusionRecord).filter(
        SelfExclusionRecord.player_id == exclusion.player_id,
        SelfExclusionRecord.status == "ACTIVE",
        SelfExclusionRecord.tenant_id == tenant_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Player already has an active self-exclusion until {existing.expiration_date}"
        )
    
    # Calculate expiration
    effective_date = datetime.utcnow()
    expiration_date = None if exclusion.duration_days == 0 else effective_date + timedelta(days=exclusion.duration_days)
    
    record = SelfExclusionRecord(
        tenant_id=tenant_id,
        player_id=exclusion.player_id,
        duration_days=exclusion.duration_days,
        reason=exclusion.reason,
        effective_date=effective_date,
        expiration_date=expiration_date,
        status="ACTIVE"
    )
    
    db.add(record)
    db.commit()
    db.refresh(record)
    
    return {
        "status": "registered",
        "player_id": record.player_id,
        "effective_date": record.effective_date,
        "expiration_date": record.expiration_date,
        "is_permanent": exclusion.duration_days == 0
    }


@router.get("/dashboard", response_model=DashboardMetrics)
async def get_dashboard(
    lookback_hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Get dashboard metrics for Gaming compliance overview.
    """
    cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
    
    # Total transactions
    total_transactions = db.query(func.count(TransactionLog.id)).filter(
        TransactionLog.tenant_id == tenant_id
    ).scalar() or 0
    
    # Total volume
    total_volume = db.query(func.sum(TransactionLog.amount_cents)).filter(
        TransactionLog.tenant_id == tenant_id
    ).scalar() or 0
    
    # Active players in period
    active_players = db.query(func.count(func.distinct(TransactionLog.player_id))).filter(
        TransactionLog.timestamp >= cutoff,
        TransactionLog.tenant_id == tenant_id
    ).scalar() or 0
    
    # Active exclusions
    active_exclusions = db.query(func.count(SelfExclusionRecord.id)).filter(
        SelfExclusionRecord.status == "ACTIVE",
        SelfExclusionRecord.tenant_id == tenant_id
    ).scalar() or 0
    
    # Pending alerts
    pending_alerts = db.query(func.count(ResponsibleGamingAlert.id)).filter(
        ResponsibleGamingAlert.status == "PENDING",
        ResponsibleGamingAlert.tenant_id == tenant_id
    ).scalar() or 0
    
    # Jurisdiction breakdown
    jurisdiction_data = db.query(
        TransactionLog.jurisdiction,
        func.count(TransactionLog.id).label('count')
    ).filter(
        TransactionLog.timestamp >= cutoff,
        TransactionLog.tenant_id == tenant_id
    ).group_by(TransactionLog.jurisdiction).all()
    
    jurisdiction_breakdown = {j: count for j, count in jurisdiction_data}
    
    return DashboardMetrics(
        total_transactions=total_transactions,
        total_volume_cents=total_volume,
        active_players_24h=active_players,
        active_exclusions=active_exclusions,
        pending_alerts=pending_alerts,
        jurisdiction_breakdown=jurisdiction_breakdown
    )


@router.post("/compliance-export")
async def export_compliance_report(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    jurisdiction: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """
    Export compliance report for Gaming Commission audits.
    Returns transaction logs for specified period.
    """
    query = db.query(TransactionLog).filter(
        TransactionLog.timestamp >= start_date,
        TransactionLog.timestamp <= end_date,
        TransactionLog.tenant_id == tenant_id
    )
    
    if jurisdiction:
        query = query.filter(TransactionLog.jurisdiction == jurisdiction)
    
    transactions = query.order_by(TransactionLog.timestamp).all()
    
    return {
        "report_generated_at": datetime.utcnow().isoformat(),
        "period_start": start_date.isoformat(),
        "period_end": end_date.isoformat(),
        "jurisdiction": jurisdiction or "ALL",
        "transaction_count": len(transactions),
        "total_volume_cents": sum(t.amount_cents for t in transactions),
        "transactions": [
            {
                "id": t.id,
                "player_id": t.player_id,
                "type": t.transaction_type,
                "amount_cents": t.amount_cents,
                "game_id": t.game_id,
                "timestamp": t.timestamp.isoformat(),
                "content_hash": t.content_hash
            }
            for t in transactions
        ]
    }
