"""
Snapshot Creation Engine - Pure Service

Deterministic snapshot creation with cryptographic integrity.
No side effects beyond persistence and event emission.
"""
import uuid
from uuid import UUID
from uuid_extensions import uuid7  # Time-ordered UUIDs (uuid7 v0.1.0 installs as uuid_extensions)
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
import logging

logger = logging.getLogger(__name__)

from app.models import (
    SnapshotCreationRequest,
    ComplianceSnapshot,
    SystemStatus,
    MismatchSeverity
)
from app.crypto import (
    calculate_content_hash,
    calculate_signature_hash,
    verify_chain_integrity,
    ImmutabilityError
)
from app.database import ComplianceSnapshotModel, MismatchModel
from app.idempotency import SnapshotIdempotencyModel


class SnapshotEngine:
    """
    Pure, deterministic snapshot creation engine.
    
    Principles:
    1. No side effects except persistence + events
    2. Same input → same output (deterministic)
    3. Cryptographic integrity guaranteed
    4. Append-only - never modifies existing snapshots
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize engine with database session.
        
        Args:
            db_session: SQLAlchemy session for persistence
        """
        self.db = db_session
    
    def create_snapshot_idempotent(
        self,
        request: SnapshotCreationRequest,
        idempotency_key: Optional[str] = None
    ) -> ComplianceSnapshot:
        """
        Create snapshot with exactly-once guarantee.
        
        CRITICAL: Snapshot creation and idempotency record MUST be in same transaction.
        
        Transaction sequence:
        1. Try INSERT idempotency record with event_fingerprint
        2. If conflict (duplicate) → fetch existing snapshot and return it
        3. If success → create snapshot in SAME transaction
        4. Update idempotency record with snapshot_id
        5. Commit atomically (both or neither)
        
        Idempotency window: 5 minutes
        """
        
        if not idempotency_key:
            idempotency_mgr = IdempotencyManager(self.db)
            idempotency_key = idempotency_mgr.generate_key(
                request.substation_id,
                request.trigger_event.value,
                tenant_id=request.tenant_id
            )
        
        
        # Calculate expiration (5-minute window)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        # Check if idempotency record already exists (within expiration window)
        existing_record = (
            self.db.query(SnapshotIdempotencyModel)
            .filter(SnapshotIdempotencyModel.idempotency_key == idempotency_key)
            .filter(SnapshotIdempotencyModel.expires_at > datetime.now(timezone.utc))
            .first()
        )
        
        if existing_record and existing_record.snapshot_id:
            # Record exists and snapshot already created - return existing snapshot
            existing_snapshot = (
                self.db.query(ComplianceSnapshotModel)
                .filter(ComplianceSnapshotModel.id == existing_record.snapshot_id)
                .first()
            )
            
            if existing_snapshot:
                logger.info(
                    f"snapshot_deduplicated idempotency_key={idempotency_key} "
                    f"snapshot_id={existing_snapshot.id} trigger_event={request.trigger_event.value}"
                )
                
                return ComplianceSnapshot(
                    id=existing_snapshot.id,
                    created_at=existing_snapshot.created_at,
                    snapshot_time=existing_snapshot.snapshot_time,
                    substation_id=existing_snapshot.substation_id,
                    facility_name=existing_snapshot.facility_name,
                    system_status=existing_snapshot.system_status,
                    asset_states=existing_snapshot.asset_states,
                    esp_config=existing_snapshot.esp_config,
                    patch_metrics=existing_snapshot.patch_metrics,
                    active_mismatches=existing_snapshot.active_mismatches,
                    generated_by=existing_snapshot.generated_by,
                    trigger_event=existing_snapshot.trigger_event,
                    content_hash=existing_snapshot.content_hash,
                    signature_hash=existing_snapshot.signature_hash,
                    previous_snapshot_id=existing_snapshot.previous_snapshot_id,
                    generator_user_id=existing_snapshot.generator_user_id
                )
        
        # No existing record found - proceed with creation
        try:
            # Step 1: Insert idempotency record FIRST (establishes claim)
            idem_record = SnapshotIdempotencyModel(
                idempotency_key=idempotency_key,
                snapshot_id=None,  # Will be updated after snapshot creation
                expires_at=expires_at
            )
            
            self.db.add(idem_record)
            self.db.flush()  # Force write to detect duplicate constraint violation
            
        except IntegrityError as e:
            # Race condition: Another transaction inserted the record between our check and insert
            # Rollback and retry fetching
            self.db.rollback()
            
            # Fetch the record that was just inserted by the other transaction
            existing_record = (
                self.db.query(SnapshotIdempotencyModel)
                .filter(SnapshotIdempotencyModel.idempotency_key == idempotency_key)
                .first()
            )
            
            if not existing_record or not existing_record.snapshot_id:
                # Race condition: record exists but snapshot not yet created
                # Wait briefly and retry
                import time
                time.sleep(0.1)
                
                existing_record = (
                    self.db.query(SnapshotIdempotencyModel)
                    .filter(SnapshotIdempotencyModel.idempotency_key == idempotency_key)
                    .first()
                )
            
            if existing_record and existing_record.snapshot_id:
                # Fetch existing snapshot
                existing_snapshot = (
                    self.db.query(ComplianceSnapshotModel)
                    .filter(ComplianceSnapshotModel.id == existing_record.snapshot_id)
                    .first()
                )
                
                logger.info(
                    f"snapshot_deduplicated idempotency_key={idempotency_key} "
                    f"snapshot_id={existing_snapshot.id} trigger_event={request.trigger_event.value}"
                )
                
                return ComplianceSnapshot(
                    id=existing_snapshot.id,
                    created_at=existing_snapshot.created_at,
                    snapshot_time=existing_snapshot.snapshot_time,
                    substation_id=existing_snapshot.substation_id,
                    facility_name=existing_snapshot.facility_name,
                    system_status=existing_snapshot.system_status,
                    asset_states=existing_snapshot.asset_states,
                    esp_config=existing_snapshot.esp_config,
                    patch_metrics=existing_snapshot.patch_metrics,
                    active_mismatches=existing_snapshot.active_mismatches,
                    generated_by=existing_snapshot.generated_by,
                    trigger_event=existing_snapshot.trigger_event,
                    content_hash=existing_snapshot.content_hash,
                    signature_hash=existing_snapshot.signature_hash,
                    previous_snapshot_id=existing_snapshot.previous_snapshot_id,
                    generator_user_id=existing_snapshot.generator_user_id
                )
            else:
                # Should never happen - idempotency record with no snapshot
                raise ImmutabilityError(
                    f"Idempotency record exists but no snapshot: {idempotency_key}"
                )
        
        # Step 2: Create snapshot (SAME transaction as idempotency record)
        try:
            snapshot = self._create_snapshot_impl(request)
            
            # Step 3: Update idempotency record with snapshot_id (atomic with snapshot creation)
            idem_record.snapshot_id = snapshot.id
            
            # Step 4: Commit BOTH atomically
            self.db.commit()
            
            logger.info(
                f"snapshot_created_idempotent snapshot_id={snapshot.id} "
                f"idempotency_key={idempotency_key} trigger_event={request.trigger_event.value}"
            )
            
            return snapshot
            
        except Exception as e:
            # Rollback BOTH snapshot and idempotency record
            self.db.rollback()
            logger.error(
                f"snapshot_creation_failed idempotency_key={idempotency_key} error={str(e)}"
            )
            raise
    
    def _create_snapshot_impl(
        self, 
        request: SnapshotCreationRequest
    ) -> ComplianceSnapshot:
        """
        Internal: Create snapshot WITHOUT managing transaction.
        
        Transaction management is caller's responsibility.
        This allows atomic composition with idempotency record.
        
        Process:
        1. Get previous snapshot (for chaining)
        2. Calculate system status from current state
        3. Generate snapshot data with UUIDv7 ID
        4. Calculate content hash
        5. Persist to database (INSERT only)
        6. Calculate signature hash (binds ID to content)
        7. Update signature field (only post-creation update allowed)
        8. Verify chain integrity
        9. Emit event (non-blocking)
        10. Return immutable snapshot
        
        Args:
            request: Snapshot creation request with all data
            
        Returns:
            ComplianceSnapshot: Immutable snapshot with hashes
            
        Raises:
            ImmutabilityError: If chain integrity violated
        """
        # Step 1: Get previous snapshot for chaining
        previous = self._get_latest_snapshot(request.substation_id)
        
        # Step 2: Calculate system status deterministically
        system_status = self._calculate_system_status(
            request.asset_states,
            request.active_mismatch_ids
        )
        
        # Step 3: Prepare snapshot data
        snapshot_time = datetime.now(timezone.utc)
        snapshot_id = uuid7()  # Time-ordered UUID
        
        snapshot_data = {
            "id": str(snapshot_id),
            "snapshot_time": snapshot_time.isoformat(),
            "substation_id": request.substation_id,
            "facility_name": request.facility_name,
            "system_status": system_status.value,
            "asset_states": request.asset_states,
            "esp_config": request.esp_config,
            "patch_metrics": request.patch_metrics,
            "active_mismatches": [str(m) for m in request.active_mismatch_ids],
            "generated_by": request.generated_by.value,
            "trigger_event": request.trigger_event.value,
            "generator_user_id": str(request.generator_user_id) if request.generator_user_id else None,
            "previous_snapshot_id": str(previous.id) if previous else None,
            "regulatory_version": "CIP-013-1",
        }
        
        # Step 4: Calculate content hash BEFORE persistence
        content_hash = calculate_content_hash(snapshot_data)
        
        # Step 5: Persist snapshot (INSERT only)
        db_snapshot = ComplianceSnapshotModel(
            id=snapshot_id,
            tenant_id=request.tenant_id,  # Set tenant context
            created_at=snapshot_time,
            snapshot_time=snapshot_time,
            substation_id=request.substation_id,
            facility_name=request.facility_name,
            system_status=system_status,
            asset_states=request.asset_states,
            esp_config=request.esp_config,
            patch_metrics=request.patch_metrics,
            active_mismatches=[str(m) for m in request.active_mismatch_ids],
            generated_by=request.generated_by,
            trigger_event=request.trigger_event,
            content_hash=content_hash,
            previous_snapshot_id=previous.id if previous else None,
            generator_user_id=request.generator_user_id,
            regulatory_version="CIP-013-1"
        )
        
        self.db.add(db_snapshot)
        self.db.flush()  # Get DB-assigned values WITHOUT commit
        
        # Step 6: Calculate signature hash (binds ID to content)
        signature_hash = calculate_signature_hash(snapshot_id, content_hash)
        
        # Step 7: Update signature (ONLY allowed post-creation update)
        self.db.execute(
            update(ComplianceSnapshotModel)
            .where(ComplianceSnapshotModel.id == snapshot_id)
            .where(ComplianceSnapshotModel.signature_hash.is_(None))  # Safety
            .values(signature_hash=signature_hash)
        )
        
        self.db.flush()  # Ensure signature written (commit is caller's responsibility)
        
        # Step 8: Verify chain integrity
        if previous:
            previous_data = {
                "id": str(previous.id),
                "snapshot_time": previous.snapshot_time.isoformat(),
                "content_hash": previous.content_hash,
                "signature_hash": previous.signature_hash
            }
            current_data = {
                "id": str(snapshot_id),
                "snapshot_time": snapshot_time.isoformat(),
                "previous_snapshot_id": str(previous.id),
                "content_hash": content_hash,
                "signature_hash": signature_hash
            }
            verify_chain_integrity(current_data, previous_data)
        
        # Step 9: Return immutable snapshot (NO COMMIT - caller manages transaction)
        return ComplianceSnapshot(
            id=snapshot_id,
            tenant_id=request.tenant_id,
            created_at=snapshot_time,
            snapshot_time=snapshot_time,
            substation_id=request.substation_id,
            facility_name=request.facility_name,
            system_status=system_status,
            asset_states=request.asset_states,
            esp_config=request.esp_config,
            patch_metrics=request.patch_metrics,
            active_mismatches=[str(m) for m in request.active_mismatch_ids],
            generated_by=request.generated_by,
            trigger_event=request.trigger_event,
            content_hash=content_hash,
            signature_hash=signature_hash,
            previous_snapshot_id=previous.id if previous else None,
            generator_user_id=request.generator_user_id
        )
    
    def _get_latest_snapshot(
        self, 
        substation_id: str
    ) -> Optional[ComplianceSnapshotModel]:
        """
        Get most recent snapshot for substation.
        
        Uses UUIDv7 ordering for time-based sort.
        """
        return (
            self.db.query(ComplianceSnapshotModel)
            .filter(ComplianceSnapshotModel.substation_id == substation_id)
            .order_by(ComplianceSnapshotModel.id.desc())  # UUIDv7 time-ordered
            .first()
        )
    
    def _calculate_system_status(
        self,
        asset_states: Dict[str, Any],
        active_mismatch_ids: List[uuid.UUID]
    ) -> SystemStatus:
        """
        Deterministic system status calculation.
        
        Rules:
        1. Any CRITICAL/HIGH mismatches → NON_COMPLIANT
        2. MEDIUM mismatches OR <90% verified → DEGRADED
        3. Otherwise → NOMINAL
        
        Args:
            asset_states: Current asset state dictionary
            active_mismatch_ids: List of open mismatch UUIDs
            
        Returns:
            SystemStatus enum value
        """
        # Rule 1: Check for high-severity mismatches
        if active_mismatch_ids:
            high_severity_count = self._count_high_severity_mismatches(
                active_mismatch_ids
            )
            if high_severity_count > 0:
                return SystemStatus.NON_COMPLIANT
            
            # If any mismatches exist (even if low severity), degraded
            return SystemStatus.DEGRADED
        
        # Rule 2: Check asset verification percentage
        summary = asset_states.get("summary", {})
        total = summary.get("total_assets", 0)
        verified = summary.get("verified_count", 0)
        
        if total > 0:
            verification_pct = verified / total
            if verification_pct < 0.9:
                return SystemStatus.DEGRADED
        
        # Rule 3: All good
        return SystemStatus.NOMINAL
    
    def _count_high_severity_mismatches(
        self, 
        mismatch_ids: List[uuid.UUID]
    ) -> int:
        """Count mismatches with HIGH or CRITICAL severity."""
        return (
            self.db.query(MismatchModel)
            .filter(MismatchModel.id.in_(mismatch_ids))
            .filter(MismatchModel.severity.in_([
                MismatchSeverity.HIGH,
                MismatchSeverity.CRITICAL
            ]))
            .count()
        )
