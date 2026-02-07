"""
Post-Commit Signature Verification

Background verifier that detects corruption as observable condition.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import ComplianceSnapshotModel
from app.crypto import (
    calculate_content_hash,
    calculate_signature_hash,
    verify_signature_hash,
    verify_chain_integrity
)
from app.metrics import (
    CHAIN_VERIFICATIONS_TOTAL,
    CHAIN_BREAKS_TOTAL,
    SNAPSHOT_INTEGRITY_REJECTIONS_TOTAL
)


logger = logging.getLogger(__name__)


class SnapshotVerifier:
    """
    Post-commit signature and chain verifier.
    
    Purpose: Turn corruption into detected condition, not latent risk.
    
    Runs as:
    - Background job (cron)
    - Health check component
    - On-demand via API
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def verify_latest_snapshot(
        self,
        substation_id: str
    ) -> Dict[str, Any]:
        """
        Verify latest snapshot for a substation.
        
        Checks:
        1. Content hash matches recalculated hash
        2. Signature hash is valid
        3. Chain linkage to previous snapshot
        4. Time monotonicity
        
        Returns verification report.
        """
        latest = (
            self.db.query(ComplianceSnapshotModel)
            .filter_by(substation_id=substation_id)
            .order_by(desc(ComplianceSnapshotModel.snapshot_time))
            .first()
        )
        
        if not latest:
            return {
                "status": "no_snapshots",
                "substation_id": substation_id
            }
        
        report = {
            "snapshot_id": str(latest.id),
            "snapshot_time": latest.snapshot_time.isoformat(),
            "checks": [],
            "status": "valid"
        }
        
        # Check 1: Content hash integrity
        content_hash_valid = self._verify_content_hash(latest)
        report["checks"].append({
            "name": "content_hash",
            "valid": content_hash_valid,
            "stored": latest.content_hash
        })
        
        if not content_hash_valid:
            report["status"] = "corrupted"
            SNAPSHOT_INTEGRITY_REJECTIONS_TOTAL.labels(
                reason="content_mismatch"
            ).inc()
        
        # Check 2: Signature hash validity
        signature_valid = verify_signature_hash(
            latest.id,
            latest.content_hash,
            latest.signature_hash
        )
        report["checks"].append({
            "name": "signature_hash",
            "valid": signature_valid,
            "stored": latest.signature_hash
        })
        
        if not signature_valid:
            report["status"] = "corrupted"
            SNAPSHOT_INTEGRITY_REJECTIONS_TOTAL.labels(
                reason="invalid_signature"
            ).inc()
        
        # Check 3: Chain integrity (if previous exists)
        if latest.previous_snapshot_id:
            chain_valid = self._verify_chain_linkage(latest)
            report["checks"].append({
                "name": "chain_integrity",
                "valid": chain_valid,
                "previous_snapshot_id": str(latest.previous_snapshot_id)
            })
            
            if not chain_valid:
                report["status"] = "corrupted"
                CHAIN_BREAKS_TOTAL.labels(
                    substation_id=substation_id,
                    violation_type="chain_break"
                ).inc()
        
        # Update metrics
        CHAIN_VERIFICATIONS_TOTAL.labels(
            result="success" if report["status"] == "valid" else "failure"
        ).inc()
        
        if report["status"] == "corrupted":
            logger.error(
                "snapshot_verification_failed",
                snapshot_id=str(latest.id),
                substation_id=substation_id,
                checks=report["checks"]
            )
        
        return report
    
    def verify_snapshot_by_id(
        self,
        snapshot_id: UUID
    ) -> Dict[str, Any]:
        """Verify specific snapshot by ID."""
        snapshot = (
            self.db.query(ComplianceSnapshotModel)
            .filter_by(id=snapshot_id)
            .first()
        )
        
        if not snapshot:
            return {
                "status": "not_found",
                "snapshot_id": str(snapshot_id)
            }
        
        report = {
            "snapshot_id": str(snapshot.id),
            "snapshot_time": snapshot.snapshot_time.isoformat(),
            "checks": [],
            "status": "valid"
        }
        
        # Content hash
        content_valid = self._verify_content_hash(snapshot)
        report["checks"].append({
            "name": "content_hash",
            "valid": content_valid
        })
        
        # Signature
        signature_valid = verify_signature_hash(
            snapshot.id,
            snapshot.content_hash,
            snapshot.signature_hash
        )
        report["checks"].append({
            "name": "signature_hash",
            "valid": signature_valid
        })
        
        if not content_valid or not signature_valid:
            report["status"] = "corrupted"
        
        return report
    
    def _verify_content_hash(
        self,
        snapshot: ComplianceSnapshotModel
    ) -> bool:
        """
        Recalculate content hash and compare to stored value.
        
        This detects corruption of snapshot data.
        """
        # Reconstruct snapshot data as it was hashed
        snapshot_data = {
            "id": str(snapshot.id),
            "snapshot_time": snapshot.snapshot_time.isoformat(),
            "substation_id": snapshot.substation_id,
            "facility_name": snapshot.facility_name,
            "system_status": snapshot.system_status.value,
            "asset_states": snapshot.asset_states,
            "esp_config": snapshot.esp_config,
            "patch_metrics": snapshot.patch_metrics,
            "active_mismatches": snapshot.active_mismatches,
            "generated_by": snapshot.generated_by.value,
            "trigger_event": snapshot.trigger_event.value if snapshot.trigger_event else None,
            "previous_snapshot_id": str(snapshot.previous_snapshot_id) if snapshot.previous_snapshot_id else None
        }
        
        recalculated_hash = calculate_content_hash(snapshot_data)
        
        is_valid = recalculated_hash == snapshot.content_hash
        
        if not is_valid:
            logger.error(
                "content_hash_mismatch",
                snapshot_id=str(snapshot.id),
                stored_hash=snapshot.content_hash,
                recalculated_hash=recalculated_hash
            )
        
        return is_valid
    
    def _verify_chain_linkage(
        self,
        current: ComplianceSnapshotModel
    ) -> bool:
        """
        Verify chain integrity between current and previous snapshot.
        
        Checks:
        - Previous snapshot exists
        - Time monotonicity
        - Previous signature valid
        """
        if not current.previous_snapshot_id:
            return True  # No previous - valid
        
        previous = (
            self.db.query(ComplianceSnapshotModel)
            .filter_by(id=current.previous_snapshot_id)
            .first()
        )
        
        if not previous:
            logger.error(
                "chain_broken_missing_previous",
                current_id=str(current.id),
                previous_id=str(current.previous_snapshot_id)
            )
            return False
        
        # Build verification objects
        current_data = {
            "id": str(current.id),
            "snapshot_time": current.snapshot_time.isoformat(),
            "previous_snapshot_id": str(current.previous_snapshot_id),
            "content_hash": current.content_hash,
            "signature_hash": current.signature_hash
        }
        
        previous_data = {
            "id": str(previous.id),
            "snapshot_time": previous.snapshot_time.isoformat(),
            "content_hash": previous.content_hash,
            "signature_hash": previous.signature_hash
        }
        
        try:
            verify_chain_integrity(current_data, previous_data)
            return True
        except Exception as e:
            logger.error(
                "chain_verification_failed",
                current_id=str(current.id),
                previous_id=str(previous.id),
                error=str(e)
            )
            return False
    
    def verify_all_recent(
        self,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Verify N most recent snapshots across all substations.
        
        Returns summary report.
        """
        recent = (
            self.db.query(ComplianceSnapshotModel)
            .order_by(desc(ComplianceSnapshotModel.created_at))
            .limit(limit)
            .all()
        )
        
        results = {
            "total_checked": len(recent),
            "valid": 0,
            "corrupted": 0,
            "corrupted_snapshots": []
        }
        
        for snapshot in recent:
            report = self.verify_snapshot_by_id(snapshot.id)
            
            if report["status"] == "valid":
                results["valid"] += 1
            else:
                results["corrupted"] += 1
                results["corrupted_snapshots"].append({
                    "snapshot_id": str(snapshot.id),
                    "substation_id": snapshot.substation_id,
                    "checks": report["checks"]
                })
        
        return results
