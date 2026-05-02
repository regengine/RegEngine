"""
Exception Queue Service Layer.

Manages remediation work items created from failed rule evaluations.
Exception cases track the lifecycle of compliance failures from detection
through resolution or waiver, including comments, assignments, and signoffs.

Usage:
    from services.shared.exception_queue import ExceptionQueueService

    svc = ExceptionQueueService(db_session)
    svc.set_tenant_context(tenant_id)
    case = svc.create_exception(tenant_id, severity="critical", ...)
    svc.assign_owner(tenant_id, case_id, owner_user_id)
    svc.resolve_exception(tenant_id, case_id, resolution_summary)
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

# Imported only for type-checking — avoids pulling in the rules engine
# at runtime since this service doesn't need to evaluate, only to
# consume an already-produced summary.
if TYPE_CHECKING:
    from shared.rules.types import EvaluationSummary

logger = logging.getLogger("exception-queue")


# ---------------------------------------------------------------------------
# Data Transfer Objects
# ---------------------------------------------------------------------------

class ExceptionCase:
    """A persisted exception case."""

    __slots__ = (
        "case_id", "tenant_id", "severity", "status",
        "linked_event_ids", "linked_rule_evaluation_ids",
        "owner_user_id", "due_date", "source_supplier",
        "source_facility_reference", "rule_category",
        "recommended_remediation", "resolution_summary",
        "waiver_reason", "waiver_approved_by", "waiver_approved_at",
        "request_case_id", "created_at", "updated_at", "resolved_at",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self) -> Dict[str, Any]:
        return {slot: getattr(self, slot) for slot in self.__slots__}


class ExceptionComment:
    """A comment on an exception case."""

    __slots__ = (
        "id", "tenant_id", "case_id", "author_user_id",
        "comment_text", "comment_type", "created_at",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self) -> Dict[str, Any]:
        return {slot: getattr(self, slot) for slot in self.__slots__}


class ExceptionSignoff:
    """A signoff record on an exception case."""

    __slots__ = (
        "id", "tenant_id", "case_id", "signoff_type",
        "signed_by", "signed_at", "reason",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self) -> Dict[str, Any]:
        return {slot: getattr(self, slot) for slot in self.__slots__}


# ---------------------------------------------------------------------------
# Severity → Due-date defaults (business days from creation)
# ---------------------------------------------------------------------------

SEVERITY_DUE_DAYS = {
    "critical": 3,
    "warning": 14,
    "info": 30,
}


# ---------------------------------------------------------------------------
# Service Layer
# ---------------------------------------------------------------------------

class ExceptionQueueService:
    """
    Database-backed service for managing exception cases.

    All methods expect a SQLAlchemy session. Tenant isolation is enforced
    via explicit tenant_id filters on every query. The caller is responsible
    for committing the session.
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Tenant Context
    # ------------------------------------------------------------------

    def set_tenant_context(self, tenant_id: str) -> None:
        """Set the RLS tenant context for this session.

        Delegates to ``services.shared.tenant_context.set_tenant_guc`` —
        the canonical Phase B primitive (#1934). Behavior-preserving for
        valid UUIDs (same ``SET LOCAL app.tenant_id = :tid`` SQL with
        the same parameterized binding); the helper additionally
        validates ``tenant_id`` is a UUID up front and raises
        ``ValueError`` on bad input rather than silently setting a
        non-UUID GUC that would break every
        ``get_tenant_context()::UUID`` comparison in RLS.
        """
        from services.shared.tenant_context import set_tenant_guc  # noqa: PLC0415
        set_tenant_guc(self.session, tenant_id)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_exception(
        self,
        tenant_id: str,
        severity: str,
        rule_category: str,
        recommended_remediation: Optional[str] = None,
        linked_event_ids: Optional[List[str]] = None,
        linked_rule_evaluation_ids: Optional[List[str]] = None,
        source_supplier: Optional[str] = None,
        source_facility_reference: Optional[str] = None,
        due_date: Optional[datetime] = None,
        request_case_id: Optional[str] = None,
    ) -> ExceptionCase:
        """
        Create a new exception case.

        If no due_date is provided, one is computed from severity defaults.
        """
        self.set_tenant_context(tenant_id)
        case_id = str(uuid4())
        now = datetime.now(timezone.utc)

        if due_date is None:
            due_days = SEVERITY_DUE_DAYS.get(severity, 14)
            due_date = now + timedelta(days=due_days)

        linked_events = linked_event_ids or []
        linked_evals = linked_rule_evaluation_ids or []

        self.session.execute(
            text("""
                INSERT INTO fsma.exception_cases (
                    case_id, tenant_id, severity, status,
                    linked_event_ids, linked_rule_evaluation_ids,
                    due_date, source_supplier, source_facility_reference,
                    rule_category, recommended_remediation,
                    request_case_id, created_at, updated_at
                ) VALUES (
                    :case_id, :tenant_id, :severity, 'open',
                    :linked_event_ids, :linked_rule_evaluation_ids,
                    :due_date, :source_supplier, :source_facility_reference,
                    :rule_category, :recommended_remediation,
                    :request_case_id, :now, :now
                )
            """),
            {
                "case_id": case_id,
                "tenant_id": tenant_id,
                "severity": severity,
                "linked_event_ids": linked_events,
                "linked_rule_evaluation_ids": linked_evals,
                "due_date": due_date,
                "source_supplier": source_supplier,
                "source_facility_reference": source_facility_reference,
                "rule_category": rule_category,
                "recommended_remediation": recommended_remediation,
                "request_case_id": request_case_id,
                "now": now,
            },
        )

        logger.info(
            "exception_case_created",
            extra={
                "case_id": case_id,
                "tenant_id": tenant_id,
                "severity": severity,
                "rule_category": rule_category,
            },
        )

        # Add system comment for case creation
        self._add_comment(
            tenant_id=tenant_id,
            case_id=case_id,
            author_user_id="system",
            comment_text=f"Exception case created. Severity: {severity}, Category: {rule_category}.",
            comment_type="system",
        )

        return self.get_exception(tenant_id, case_id)

    # ------------------------------------------------------------------
    # Read / List
    # ------------------------------------------------------------------

    def get_exception(self, tenant_id: str, case_id: str) -> Optional[ExceptionCase]:
        """Fetch a single exception case by ID."""
        self.set_tenant_context(tenant_id)
        row = self.session.execute(
            text("""
                SELECT case_id, tenant_id, severity, status,
                       linked_event_ids, linked_rule_evaluation_ids,
                       owner_user_id, due_date, source_supplier,
                       source_facility_reference, rule_category,
                       recommended_remediation, resolution_summary,
                       waiver_reason, waiver_approved_by, waiver_approved_at,
                       request_case_id, created_at, updated_at, resolved_at
                FROM fsma.exception_cases
                WHERE case_id = :case_id AND tenant_id = :tenant_id
            """),
            {"case_id": case_id, "tenant_id": tenant_id},
        ).fetchone()

        if not row:
            return None
        return self._row_to_case(row)

    def list_exceptions(
        self,
        tenant_id: str,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        source_supplier: Optional[str] = None,
        due_before: Optional[datetime] = None,
        source_facility_reference: Optional[str] = None,
        rule_category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ExceptionCase]:
        """
        List exception cases for a tenant with optional filters.

        Filters:
            severity - critical, warning, info
            status - open, in_review, awaiting_supplier, resolved, waived
            source_supplier - supplier name substring match (ILIKE)
            due_before - cases due on or before this datetime
            source_facility_reference - facility reference substring match
            rule_category - exact category match
        """
        self.set_tenant_context(tenant_id)
        clauses = ["tenant_id = :tenant_id"]
        params: Dict[str, Any] = {"tenant_id": tenant_id, "limit": limit, "offset": offset}

        if severity is not None:
            clauses.append("severity = :severity")
            params["severity"] = severity

        if status is not None:
            clauses.append("status = :status")
            params["status"] = status

        if source_supplier is not None:
            clauses.append("source_supplier ILIKE :source_supplier")
            params["source_supplier"] = f"%{source_supplier}%"

        if due_before is not None:
            clauses.append("due_date <= :due_before")
            params["due_before"] = due_before

        if source_facility_reference is not None:
            clauses.append("source_facility_reference ILIKE :facility_ref")
            params["facility_ref"] = f"%{source_facility_reference}%"

        if rule_category is not None:
            clauses.append("rule_category = :rule_category")
            params["rule_category"] = rule_category

        where = " AND ".join(clauses)

        rows = self.session.execute(
            text(f"""
                SELECT case_id, tenant_id, severity, status,
                       linked_event_ids, linked_rule_evaluation_ids,
                       owner_user_id, due_date, source_supplier,
                       source_facility_reference, rule_category,
                       recommended_remediation, resolution_summary,
                       waiver_reason, waiver_approved_by, waiver_approved_at,
                       request_case_id, created_at, updated_at, resolved_at
                FROM fsma.exception_cases
                WHERE {where}
                ORDER BY
                    CASE severity
                        WHEN 'critical' THEN 1
                        WHEN 'warning'  THEN 2
                        WHEN 'info'     THEN 3
                        ELSE 4
                    END,
                    due_date ASC NULLS LAST,
                    created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).fetchall()

        return [self._row_to_case(row) for row in rows]

    def get_unresolved_blocking_count(self, tenant_id: str) -> int:
        """
        Count unresolved exceptions with critical severity.

        These are cases that block compliance sign-off.
        """
        self.set_tenant_context(tenant_id)
        row = self.session.execute(
            text("""
                SELECT COUNT(*)
                FROM fsma.exception_cases
                WHERE tenant_id = :tenant_id
                  AND severity = 'critical'
                  AND status NOT IN ('resolved', 'waived')
            """),
            {"tenant_id": tenant_id},
        ).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Assign Owner
    # ------------------------------------------------------------------

    def assign_owner(
        self,
        tenant_id: str,
        case_id: str,
        owner_user_id: str,
        assigned_by: str = "system",
    ) -> Optional[ExceptionCase]:
        """
        Assign an owner to an exception case and move to in_review status.
        """
        self.set_tenant_context(tenant_id)
        now = datetime.now(timezone.utc)

        result = self.session.execute(
            text("""
                UPDATE fsma.exception_cases
                SET owner_user_id = :owner_user_id,
                    status = CASE
                        WHEN status = 'open' THEN 'in_review'
                        ELSE status
                    END,
                    updated_at = :now
                WHERE case_id = :case_id AND tenant_id = :tenant_id
            """),
            {
                "owner_user_id": owner_user_id,
                "case_id": case_id,
                "tenant_id": tenant_id,
                "now": now,
            },
        )

        if result.rowcount == 0:
            logger.warning(
                "assign_owner_not_found",
                extra={"case_id": case_id, "tenant_id": tenant_id},
            )
            return None

        self._add_comment(
            tenant_id=tenant_id,
            case_id=case_id,
            author_user_id=assigned_by,
            comment_text=f"Case assigned to {owner_user_id}.",
            comment_type="assignment",
        )

        logger.info(
            "exception_owner_assigned",
            extra={
                "case_id": case_id,
                "owner_user_id": owner_user_id,
            },
        )

        return self.get_exception(tenant_id, case_id)

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------

    def resolve_exception(
        self,
        tenant_id: str,
        case_id: str,
        resolution_summary: str,
        resolved_by: str = "system",
    ) -> Optional[ExceptionCase]:
        """
        Resolve an exception case with a resolution summary.
        """
        self.set_tenant_context(tenant_id)
        now = datetime.now(timezone.utc)

        result = self.session.execute(
            text("""
                UPDATE fsma.exception_cases
                SET status = 'resolved',
                    resolution_summary = :resolution_summary,
                    resolved_at = :now,
                    updated_at = :now
                WHERE case_id = :case_id
                  AND tenant_id = :tenant_id
                  AND status NOT IN ('resolved', 'waived')
            """),
            {
                "resolution_summary": resolution_summary,
                "case_id": case_id,
                "tenant_id": tenant_id,
                "now": now,
            },
        )

        if result.rowcount == 0:
            logger.warning(
                "resolve_exception_failed",
                extra={"case_id": case_id, "tenant_id": tenant_id},
            )
            return None

        # Record signoff
        self._add_signoff(
            tenant_id=tenant_id,
            case_id=case_id,
            signoff_type="approve",
            signed_by=resolved_by,
            reason=resolution_summary,
        )

        self._add_comment(
            tenant_id=tenant_id,
            case_id=case_id,
            author_user_id=resolved_by,
            comment_text=f"Case resolved: {resolution_summary}",
            comment_type="status_change",
        )

        logger.info(
            "exception_resolved",
            extra={"case_id": case_id, "resolved_by": resolved_by},
        )

        return self.get_exception(tenant_id, case_id)

    # ------------------------------------------------------------------
    # Waive
    # ------------------------------------------------------------------

    def waive_exception(
        self,
        tenant_id: str,
        case_id: str,
        waiver_reason: str,
        waiver_approved_by: str,
    ) -> Optional[ExceptionCase]:
        """
        Waive an exception case. Requires a reason and approver identity.

        Waivers are tracked with a signoff record for audit purposes.
        """
        self.set_tenant_context(tenant_id)
        now = datetime.now(timezone.utc)

        result = self.session.execute(
            text("""
                UPDATE fsma.exception_cases
                SET status = 'waived',
                    waiver_reason = :waiver_reason,
                    waiver_approved_by = :waiver_approved_by,
                    waiver_approved_at = :now,
                    resolved_at = :now,
                    updated_at = :now
                WHERE case_id = :case_id
                  AND tenant_id = :tenant_id
                  AND status NOT IN ('resolved', 'waived')
            """),
            {
                "waiver_reason": waiver_reason,
                "waiver_approved_by": waiver_approved_by,
                "case_id": case_id,
                "tenant_id": tenant_id,
                "now": now,
            },
        )

        if result.rowcount == 0:
            logger.warning(
                "waive_exception_failed",
                extra={"case_id": case_id, "tenant_id": tenant_id},
            )
            return None

        # Record waiver signoff
        self._add_signoff(
            tenant_id=tenant_id,
            case_id=case_id,
            signoff_type="waive",
            signed_by=waiver_approved_by,
            reason=waiver_reason,
        )

        self._add_comment(
            tenant_id=tenant_id,
            case_id=case_id,
            author_user_id=waiver_approved_by,
            comment_text=f"Case waived: {waiver_reason}",
            comment_type="status_change",
        )

        logger.info(
            "exception_waived",
            extra={
                "case_id": case_id,
                "waiver_approved_by": waiver_approved_by,
            },
        )

        return self.get_exception(tenant_id, case_id)

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def add_comment(
        self,
        tenant_id: str,
        case_id: str,
        author_user_id: str,
        comment_text: str,
        comment_type: str = "note",
    ) -> ExceptionComment:
        """
        Add a comment to an exception case.

        comment_type: note, status_change, assignment, supplier_response, system
        """
        self.set_tenant_context(tenant_id)
        # Verify case exists for this tenant
        case = self.get_exception(tenant_id, case_id)
        if case is None:
            raise ValueError(f"Exception case {case_id} not found for tenant {tenant_id}")

        return self._add_comment(
            tenant_id=tenant_id,
            case_id=case_id,
            author_user_id=author_user_id,
            comment_text=comment_text,
            comment_type=comment_type,
        )

    def list_comments(
        self,
        tenant_id: str,
        case_id: str,
    ) -> List[ExceptionComment]:
        """List all comments for an exception case, ordered by creation time."""
        self.set_tenant_context(tenant_id)
        rows = self.session.execute(
            text("""
                SELECT id, tenant_id, case_id, author_user_id,
                       comment_text, comment_type, created_at
                FROM fsma.exception_comments
                WHERE case_id = :case_id AND tenant_id = :tenant_id
                ORDER BY created_at ASC
            """),
            {"case_id": case_id, "tenant_id": tenant_id},
        ).fetchall()

        return [
            ExceptionComment(
                id=str(row[0]),
                tenant_id=str(row[1]),
                case_id=str(row[2]),
                author_user_id=row[3],
                comment_text=row[4],
                comment_type=row[5],
                created_at=row[6],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Auto-create from EvaluationSummary
    # ------------------------------------------------------------------

    def create_exceptions_from_evaluation(
        self,
        tenant_id: str,
        summary: "EvaluationSummary",
        source_supplier: Optional[str] = None,
        source_facility_reference: Optional[str] = None,
    ) -> List[ExceptionCase]:
        """
        Create exception cases from a RulesEngine EvaluationSummary.

        Failures are grouped by rule_category so that related failures
        produce a single exception case rather than one per rule.

        Only failures (result == 'fail') generate exception cases.
        Warnings are not promoted to exceptions.

        Args:
            tenant_id: The tenant owning these exceptions.
            summary: EvaluationSummary from shared.rules_engine.
            source_supplier: Optional supplier name to attach.
            source_facility_reference: Optional facility reference.

        Returns:
            List of created ExceptionCase objects.
        """
        from services.shared.rules_engine import RuleEvaluationResult

        failures = [r for r in summary.results if r.result == "fail"]
        if not failures:
            return []

        # Group failures by category
        by_category: Dict[str, List[RuleEvaluationResult]] = defaultdict(list)
        for failure in failures:
            by_category[failure.category].append(failure)

        created_cases: List[ExceptionCase] = []

        for category, category_failures in by_category.items():
            # Use the highest severity in the group
            severity = self._highest_severity(
                [f.severity for f in category_failures]
            )

            # Build a combined remediation suggestion
            remediation_parts = []
            evaluation_ids = []
            for f in category_failures:
                evaluation_ids.append(f.evaluation_id)
                if f.remediation_suggestion:
                    remediation_parts.append(
                        f"[{f.rule_title}] {f.remediation_suggestion}"
                    )
                elif f.why_failed:
                    remediation_parts.append(
                        f"[{f.rule_title}] {f.why_failed}"
                    )

            recommended_remediation = "\n".join(remediation_parts) if remediation_parts else None

            case = self.create_exception(
                tenant_id=tenant_id,
                severity=severity,
                rule_category=category,
                recommended_remediation=recommended_remediation,
                linked_event_ids=[summary.event_id] if summary.event_id else [],
                linked_rule_evaluation_ids=evaluation_ids,
                source_supplier=source_supplier,
                source_facility_reference=source_facility_reference,
            )
            created_cases.append(case)

        logger.info(
            "exceptions_created_from_evaluation",
            extra={
                "tenant_id": tenant_id,
                "event_id": summary.event_id,
                "total_failures": len(failures),
                "cases_created": len(created_cases),
            },
        )

        return created_cases

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _add_comment(
        self,
        tenant_id: str,
        case_id: str,
        author_user_id: str,
        comment_text: str,
        comment_type: str,
    ) -> ExceptionComment:
        """Insert a comment row (internal, no case-existence check)."""
        comment_id = str(uuid4())
        now = datetime.now(timezone.utc)

        self.session.execute(
            text("""
                INSERT INTO fsma.exception_comments (
                    id, tenant_id, case_id, author_user_id,
                    comment_text, comment_type, created_at
                ) VALUES (
                    :id, :tenant_id, :case_id, :author_user_id,
                    :comment_text, :comment_type, :now
                )
            """),
            {
                "id": comment_id,
                "tenant_id": tenant_id,
                "case_id": case_id,
                "author_user_id": author_user_id,
                "comment_text": comment_text,
                "comment_type": comment_type,
                "now": now,
            },
        )

        return ExceptionComment(
            id=comment_id,
            tenant_id=tenant_id,
            case_id=case_id,
            author_user_id=author_user_id,
            comment_text=comment_text,
            comment_type=comment_type,
            created_at=now,
        )

    def _add_signoff(
        self,
        tenant_id: str,
        case_id: str,
        signoff_type: str,
        signed_by: str,
        reason: Optional[str] = None,
    ) -> ExceptionSignoff:
        """Insert a signoff row."""
        signoff_id = str(uuid4())
        now = datetime.now(timezone.utc)

        self.session.execute(
            text("""
                INSERT INTO fsma.exception_signoffs (
                    id, tenant_id, case_id, signoff_type,
                    signed_by, signed_at, reason
                ) VALUES (
                    :id, :tenant_id, :case_id, :signoff_type,
                    :signed_by, :now, :reason
                )
            """),
            {
                "id": signoff_id,
                "tenant_id": tenant_id,
                "case_id": case_id,
                "signoff_type": signoff_type,
                "signed_by": signed_by,
                "now": now,
                "reason": reason,
            },
        )

        return ExceptionSignoff(
            id=signoff_id,
            tenant_id=tenant_id,
            case_id=case_id,
            signoff_type=signoff_type,
            signed_by=signed_by,
            signed_at=now,
            reason=reason,
        )

    @staticmethod
    def _row_to_case(row) -> ExceptionCase:
        """Convert a database row to an ExceptionCase DTO."""
        return ExceptionCase(
            case_id=str(row[0]),
            tenant_id=str(row[1]),
            severity=row[2],
            status=row[3],
            linked_event_ids=[str(e) for e in row[4]] if row[4] else [],
            linked_rule_evaluation_ids=[str(e) for e in row[5]] if row[5] else [],
            owner_user_id=row[6],
            due_date=row[7],
            source_supplier=row[8],
            source_facility_reference=row[9],
            rule_category=row[10],
            recommended_remediation=row[11],
            resolution_summary=row[12],
            waiver_reason=row[13],
            waiver_approved_by=row[14],
            waiver_approved_at=row[15],
            request_case_id=str(row[16]) if row[16] else None,
            created_at=row[17],
            updated_at=row[18],
            resolved_at=row[19],
        )

    @staticmethod
    def _highest_severity(severities: List[str]) -> str:
        """Return the highest severity from a list."""
        rank = {"critical": 0, "warning": 1, "info": 2}
        return min(severities, key=lambda s: rank.get(s, 99))
