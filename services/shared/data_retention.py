"""
SEC-018: Data Retention and GDPR Right-to-Erasure Enforcement.

This module provides data retention management for PII (personally identifiable
information) handling, including soft-delete, hard-delete, and audit log
anonymization to comply with GDPR and data retention policies.

GitHub Issue #870: Data Retention Enforcement for PII
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.audit_logging import (
    AuditLogger,
    AuditActor,
    AuditResource,
    AuditEventType,
    AuditEventCategory,
    AuditSeverity,
)
from shared.database import get_db, engine


logger = logging.getLogger(__name__)


# =============================================================================
# Data Retention Configuration
# =============================================================================


class RetentionPolicy(str, Enum):
    """Standard retention policies for different data types."""

    USER_ACCOUNT = "user_account"  # Soft-delete after 0 days, hard-delete after 30 days
    SUPPLIER_CONTACT = "supplier_contact"  # Soft-delete after 0 days, hard-delete after 30 days
    AUDIT_LOG = "audit_log"  # Keep for 24 months, then anonymize
    TRANSACTION_LOG = "transaction_log"  # Keep for 7 years per FDA requirements
    TEMPORARY_PII = "temporary_pii"  # Soft-delete after 0 days, hard-delete after 14 days


@dataclass
class RetentionConfig:
    """Configuration for data retention policies."""

    policy: RetentionPolicy
    soft_delete_days: int = 0  # Days before soft-delete (0 = immediate)
    hard_delete_days: int = 30  # Days after soft-delete before hard-delete
    audit_retention_months: int = 24  # Months to retain full audit logs
    anonymization_enabled: bool = True  # Whether to anonymize instead of delete
    pii_fields: List[str] = field(default_factory=list)  # Fields containing PII

    def hard_delete_threshold(self) -> datetime:
        """Calculate when soft-deleted records become eligible for hard-delete."""
        days = self.soft_delete_days + self.hard_delete_days
        return datetime.now(timezone.utc) - timedelta(days=days)

    def anonymization_threshold(self) -> datetime:
        """Calculate when audit logs become eligible for anonymization."""
        return datetime.now(timezone.utc) - timedelta(days=self.audit_retention_months * 30)


# Default retention configs
RETENTION_CONFIGS: Dict[RetentionPolicy, RetentionConfig] = {
    RetentionPolicy.USER_ACCOUNT: RetentionConfig(
        policy=RetentionPolicy.USER_ACCOUNT,
        soft_delete_days=0,
        hard_delete_days=30,
        audit_retention_months=24,
        pii_fields=["email", "phone", "name", "address"],
    ),
    RetentionPolicy.SUPPLIER_CONTACT: RetentionConfig(
        policy=RetentionPolicy.SUPPLIER_CONTACT,
        soft_delete_days=0,
        hard_delete_days=30,
        audit_retention_months=24,
        pii_fields=["email", "phone", "contact_name", "address"],
    ),
    RetentionPolicy.AUDIT_LOG: RetentionConfig(
        policy=RetentionPolicy.AUDIT_LOG,
        soft_delete_days=0,
        hard_delete_days=0,
        audit_retention_months=24,
        pii_fields=[],
    ),
    RetentionPolicy.TRANSACTION_LOG: RetentionConfig(
        policy=RetentionPolicy.TRANSACTION_LOG,
        soft_delete_days=0,
        hard_delete_days=0,
        audit_retention_months=84,  # 7 years
        pii_fields=[],
    ),
    RetentionPolicy.TEMPORARY_PII: RetentionConfig(
        policy=RetentionPolicy.TEMPORARY_PII,
        soft_delete_days=0,
        hard_delete_days=14,
        audit_retention_months=12,
        pii_fields=["email", "phone", "name"],
    ),
}


# =============================================================================
# Data Retention Events
# =============================================================================


class DeletionRequest(str, Enum):
    """Types of deletion requests."""

    USER_INITIATED = "user_initiated"  # User requested erasure
    GDPR_SAR = "gdpr_sar"  # GDPR Subject Access Request
    COMPLIANCE_CLEANUP = "compliance_cleanup"  # Automated compliance cleanup
    RETENTION_POLICY = "retention_policy"  # Automatic retention policy enforcement


@dataclass
class DeletedRecord:
    """Metadata about a deleted record for audit trail."""

    record_id: str
    resource_type: str
    deletion_request_type: DeletionRequest
    deleted_at: datetime
    soft_deleted_at: Optional[datetime] = None
    hard_deleted_at: Optional[datetime] = None
    reason: Optional[str] = None
    requested_by: Optional[str] = None
    hash_before_deletion: Optional[str] = None
    pii_fields_deleted: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {k: v for k, v in asdict(self).items() if v is not None}


# =============================================================================
# PII Anonymization
# =============================================================================


class PIIAnonymizer:
    """Anonymize PII in audit logs and other records."""

    # Mapping of field patterns to anonymization functions
    FIELD_ANONYMIZERS: Dict[str, Callable[[str], str]] = {
        "email": lambda x: f"anon_{hashlib.sha256(x.encode()).hexdigest()[:8]}@example.com",
        "phone": lambda x: "***-***-****",
        "name": lambda x: "REDACTED_NAME",
        "address": lambda x: "REDACTED_ADDRESS",
        "contact_name": lambda x: "REDACTED_NAME",
    }

    @classmethod
    def anonymize_value(cls, field_name: str, value: Any) -> Any:
        """Anonymize a single value based on field name.

        Args:
            field_name: Name of the field (e.g., 'email', 'phone')
            value: Value to anonymize

        Returns:
            Anonymized value or original if no anonymizer found
        """
        if value is None:
            return None

        # Check for exact match
        if field_name in cls.FIELD_ANONYMIZERS:
            try:
                return cls.FIELD_ANONYMIZERS[field_name](str(value))
            except Exception as e:
                logger.warning(
                    "pii_anonymization_error",
                    field=field_name,
                    error=str(e),
                )
                return "[ANONYMIZATION_ERROR]"

        # Check for pattern match (e.g., 'email_address' matches 'email')
        for pattern, anonymizer in cls.FIELD_ANONYMIZERS.items():
            if pattern in field_name.lower():
                try:
                    return anonymizer(str(value))
                except Exception as e:
                    logger.warning(
                        "pii_anonymization_error",
                        field=field_name,
                        error=str(e),
                    )
                    return "[ANONYMIZATION_ERROR]"

        return value

    @classmethod
    def anonymize_dict(
        cls,
        data: Dict[str, Any],
        pii_fields: List[str],
    ) -> Dict[str, Any]:
        """Anonymize multiple PII fields in a dictionary.

        Args:
            data: Dictionary with data to anonymize
            pii_fields: List of field names to anonymize

        Returns:
            Dictionary with PII anonymized
        """
        result = data.copy()

        for field in pii_fields:
            if field in result:
                result[field] = cls.anonymize_value(field, result[field])

        return result


# =============================================================================
# Data Retention Manager
# =============================================================================


class DataRetentionManager:
    """Manage data retention, soft-delete, hard-delete, and GDPR compliance."""

    def __init__(
        self,
        audit_logger: Optional[AuditLogger] = None,
        custom_configs: Optional[Dict[RetentionPolicy, RetentionConfig]] = None,
    ):
        """Initialize data retention manager.

        Args:
            audit_logger: Audit logger instance
            custom_configs: Custom retention configurations
        """
        self.audit_logger = audit_logger or AuditLogger.get_instance()
        self.configs = {**RETENTION_CONFIGS, **(custom_configs or {})}

    async def soft_delete_record(
        self,
        db: Session,
        resource_type: str,
        record_id: str,
        policy: RetentionPolicy,
        deletion_request: DeletionRequest,
        actor: AuditActor,
        reason: Optional[str] = None,
    ) -> bool:
        """Soft-delete a record by setting deleted_at timestamp.

        This marks the record as deleted without removing it, allowing
        for recovery and compliance auditing.

        Args:
            db: Database session
            resource_type: Type of resource (e.g., 'user', 'supplier_contact')
            record_id: ID of the record to delete
            policy: Retention policy to apply
            deletion_request: Type of deletion request
            actor: Who requested the deletion
            reason: Reason for deletion

        Returns:
            True if soft-delete succeeded
        """
        try:
            # Update record to mark as deleted
            deleted_at = datetime.now(timezone.utc)

            update_query = text(f"""
                UPDATE {resource_type}
                SET deleted_at = :deleted_at
                WHERE id = :record_id AND deleted_at IS NULL
            """)

            result = db.execute(
                update_query,
                {"deleted_at": deleted_at, "record_id": record_id},
            )
            db.commit()

            if result.rowcount == 0:
                logger.warning(
                    "soft_delete_record_not_found",
                    resource_type=resource_type,
                    record_id=record_id,
                )
                return False

            # Log the soft-delete
            await self.audit_logger.log_data_modification(
                actor=actor,
                resource=AuditResource(
                    resource_type=resource_type,
                    resource_id=record_id,
                ),
                operation="soft_delete",
                changes={
                    "deleted_at": deleted_at.isoformat(),
                    "deletion_request_type": deletion_request.value,
                    "reason": reason,
                },
                context=None,
            )

            logger.info(
                "soft_delete_record_success",
                resource_type=resource_type,
                record_id=record_id,
                deletion_request=deletion_request.value,
            )

            return True

        except Exception as e:
            logger.error(
                "soft_delete_record_failed",
                resource_type=resource_type,
                record_id=record_id,
                error=str(e),
            )
            return False

    async def hard_delete_record(
        self,
        db: Session,
        resource_type: str,
        record_id: str,
        actor: AuditActor,
    ) -> bool:
        """Permanently delete a soft-deleted record.

        This removes the record completely from the database. Should only
        be called after the retention period has passed.

        Args:
            db: Database session
            resource_type: Type of resource
            record_id: ID of the record to permanently delete
            actor: Who performed the deletion

        Returns:
            True if hard-delete succeeded
        """
        try:
            # Verify record was soft-deleted
            check_query = text(f"""
                SELECT deleted_at FROM {resource_type}
                WHERE id = :record_id AND deleted_at IS NOT NULL
            """)

            result = db.execute(check_query, {"record_id": record_id}).fetchone()

            if not result:
                logger.warning(
                    "hard_delete_record_not_soft_deleted",
                    resource_type=resource_type,
                    record_id=record_id,
                )
                return False

            soft_deleted_at = result[0]

            # Delete the record
            delete_query = text(f"""
                DELETE FROM {resource_type}
                WHERE id = :record_id
            """)

            db.execute(delete_query, {"record_id": record_id})
            db.commit()

            # Log the hard-delete
            await self.audit_logger.log_data_modification(
                actor=actor,
                resource=AuditResource(
                    resource_type=resource_type,
                    resource_id=record_id,
                ),
                operation="hard_delete",
                changes={
                    "hard_deleted_at": datetime.now(timezone.utc).isoformat(),
                    "soft_deleted_at": soft_deleted_at.isoformat() if soft_deleted_at else None,
                },
                context=None,
            )

            logger.info(
                "hard_delete_record_success",
                resource_type=resource_type,
                record_id=record_id,
            )

            return True

        except Exception as e:
            logger.error(
                "hard_delete_record_failed",
                resource_type=resource_type,
                record_id=record_id,
                error=str(e),
            )
            return False

    async def anonymize_audit_logs(
        self,
        db: Session,
        retention_policy: RetentionPolicy,
        actor: AuditActor,
    ) -> Tuple[int, int]:
        """Anonymize old audit logs according to retention policy.

        Replaces PII in audit logs that exceed the retention period.

        Args:
            db: Database session
            retention_policy: Which retention policy to apply
            actor: Who performed the anonymization

        Returns:
            Tuple of (records_anonymized, errors)
        """
        config = self.configs.get(retention_policy)
        if not config:
            logger.error(
                "anonymize_audit_logs_unknown_policy",
                policy=retention_policy.value,
            )
            return 0, 0

        threshold = config.anonymization_threshold()
        anonymized = 0
        errors = 0

        try:
            # Find audit logs older than threshold
            query = text("""
                SELECT id, details, tags FROM audit_logs
                WHERE timestamp < :threshold
                AND (details LIKE '%email%' OR details LIKE '%phone%')
                AND anonymized_at IS NULL
                LIMIT 1000
            """)

            results = db.execute(query, {"threshold": threshold}).fetchall()

            for log_id, details_json, tags in results:
                try:
                    details = json.loads(details_json) if details_json else {}

                    # Anonymize PII fields
                    anonymized_details = PIIAnonymizer.anonymize_dict(
                        details,
                        config.pii_fields,
                    )

                    # Update the log
                    update_query = text("""
                        UPDATE audit_logs
                        SET details = :details, anonymized_at = :anonymized_at
                        WHERE id = :log_id
                    """)

                    db.execute(
                        update_query,
                        {
                            "log_id": log_id,
                            "details": json.dumps(anonymized_details),
                            "anonymized_at": datetime.now(timezone.utc),
                        },
                    )

                    anonymized += 1

                except Exception as e:
                    logger.warning(
                        "anonymize_audit_logs_record_error",
                        log_id=log_id,
                        error=str(e),
                    )
                    errors += 1

            db.commit()

            # Log the anonymization batch
            await self.audit_logger.log_data_modification(
                actor=actor,
                resource=AuditResource(
                    resource_type="audit_logs",
                    resource_id="batch",
                ),
                operation="anonymize",
                changes={
                    "records_anonymized": anonymized,
                    "threshold": threshold.isoformat(),
                    "policy": retention_policy.value,
                },
                context=None,
            )

            logger.info(
                "anonymize_audit_logs_complete",
                policy=retention_policy.value,
                anonymized=anonymized,
                errors=errors,
            )

            return anonymized, errors

        except Exception as e:
            logger.error(
                "anonymize_audit_logs_failed",
                policy=retention_policy.value,
                error=str(e),
            )
            return anonymized, errors + 1

    async def process_deletion_request(
        self,
        db: Session,
        resource_type: str,
        record_id: str,
        policy: RetentionPolicy,
        deletion_request: DeletionRequest,
        actor: AuditActor,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a complete GDPR deletion request.

        Soft-deletes the record and schedules hard-delete after retention period.

        Args:
            db: Database session
            resource_type: Type of resource
            record_id: ID of the record
            policy: Retention policy to apply
            deletion_request: Type of deletion request
            actor: Who requested the deletion
            reason: Reason for deletion

        Returns:
            Dictionary with deletion status
        """
        result = {
            "resource_type": resource_type,
            "record_id": record_id,
            "soft_deleted": False,
            "hard_delete_scheduled": False,
            "error": None,
        }

        try:
            # Soft-delete the record
            soft_delete_ok = await self.soft_delete_record(
                db=db,
                resource_type=resource_type,
                record_id=record_id,
                policy=policy,
                deletion_request=deletion_request,
                actor=actor,
                reason=reason,
            )

            result["soft_deleted"] = soft_delete_ok

            if soft_delete_ok:
                config = self.configs[policy]

                # Log that hard-delete is scheduled
                hard_delete_date = (
                    datetime.now(timezone.utc) +
                    timedelta(days=config.hard_delete_days)
                )

                await self.audit_logger.log(
                    event_type=AuditEventType.DATA_DELETE,
                    category=AuditEventCategory.DATA_MODIFICATION,
                    severity=AuditSeverity.INFO,
                    actor=actor,
                    action="schedule_hard_delete",
                    outcome="success",
                    resource=AuditResource(
                        resource_type=resource_type,
                        resource_id=record_id,
                    ),
                    message=f"Hard-delete scheduled for {resource_type}/{record_id}",
                    details={
                        "scheduled_for": hard_delete_date.isoformat(),
                        "retention_days": config.hard_delete_days,
                        "deletion_request": deletion_request.value,
                    },
                    tags=["gdpr", "data_retention", "scheduled_deletion"],
                )

                result["hard_delete_scheduled"] = True
                result["hard_delete_date"] = hard_delete_date.isoformat()

        except Exception as e:
            logger.error(
                "process_deletion_request_failed",
                resource_type=resource_type,
                record_id=record_id,
                error=str(e),
            )
            result["error"] = str(e)

        return result


# =============================================================================
# Scheduled Cleanup Job (for APScheduler)
# =============================================================================


async def cleanup_deleted_records_job():
    """
    Scheduled job to hard-delete soft-deleted records that exceed retention period.

    Call this from APScheduler at regular intervals (e.g., daily).

    This job:
    1. Finds all soft-deleted records older than their hard-delete threshold
    2. Permanently removes them from the database
    3. Logs all deletions for compliance audit trail
    4. Anonymizes audit logs that exceed retention
    """
    logger.info("cleanup_deleted_records_job_started")

    system_actor = AuditActor(
        actor_id="system:retention_cleanup",
        actor_type="system",
        username="system",
    )

    stats = {
        "hard_deleted_total": 0,
        "anonymized_logs_total": 0,
        "errors": 0,
    }

    try:
        with get_db() as db:
            manager = DataRetentionManager()

            # Process hard-deletes for each retention policy
            for policy, config in RETENTION_CONFIGS.items():
                if policy == RetentionPolicy.AUDIT_LOG:
                    # Skip — handled separately
                    continue

                threshold = config.hard_delete_threshold()

                # Find soft-deleted records eligible for hard-delete
                query = text(f"""
                    SELECT id FROM {policy.value.replace('-', '_')}
                    WHERE deleted_at IS NOT NULL AND deleted_at < :threshold
                    LIMIT 100
                """)

                try:
                    results = db.execute(query, {"threshold": threshold}).fetchall()

                    for (record_id,) in results:
                        deleted_ok = await manager.hard_delete_record(
                            db=db,
                            resource_type=policy.value.replace('-', '_'),
                            record_id=record_id,
                            actor=system_actor,
                        )

                        if deleted_ok:
                            stats["hard_deleted_total"] += 1
                        else:
                            stats["errors"] += 1

                except Exception as e:
                    logger.error(
                        "cleanup_policy_error",
                        policy=policy.value,
                        error=str(e),
                    )
                    stats["errors"] += 1

            # Anonymize old audit logs
            try:
                anon_count, anon_errors = await manager.anonymize_audit_logs(
                    db=db,
                    retention_policy=RetentionPolicy.AUDIT_LOG,
                    actor=system_actor,
                )
                stats["anonymized_logs_total"] = anon_count
                stats["errors"] += anon_errors

            except Exception as e:
                logger.error(
                    "cleanup_anonymization_error",
                    error=str(e),
                )
                stats["errors"] += 1

    except Exception as e:
        logger.error(
            "cleanup_deleted_records_job_failed",
            error=str(e),
        )
        stats["errors"] += 1

    logger.info(
        "cleanup_deleted_records_job_complete",
        hard_deleted_total=stats["hard_deleted_total"],
        anonymized_logs_total=stats["anonymized_logs_total"],
        errors=stats["errors"],
    )

    return stats


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "DataRetentionManager",
    "RetentionPolicy",
    "RetentionConfig",
    "DeletionRequest",
    "DeletedRecord",
    "PIIAnonymizer",
    "cleanup_deleted_records_job",
    "RETENTION_CONFIGS",
]
