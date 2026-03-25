"""
Request-Response Workflow Service for FDA 24-Hour Response Readiness.

Implements the full 10-stage workflow:
    intake -> scope -> collect -> gap_analysis -> exception_triage ->
    assembling -> internal_review -> ready -> submitted -> amended

Each stage is an explicit operation — the workflow never auto-advances.
Package snapshots are immutable and SHA-256 sealed. Amendments create
new versions with diffs against prior snapshots.

Usage:
    from shared.request_workflow import RequestWorkflow

    workflow = RequestWorkflow(db_session)

    # Create and advance a case
    case = workflow.create_request_case(tenant_id, ...)
    workflow.update_scope(tenant_id, case_id, products=[...], lots=[...])
    records = workflow.collect_records(tenant_id, case_id)
    gaps = workflow.run_gap_analysis(tenant_id, case_id)
    package = workflow.assemble_response_package(tenant_id, case_id, generated_by="user@co.com")
    workflow.add_signoff(tenant_id, case_id, "scope_approval", signed_by="qa_lead")
    workflow.submit_package(tenant_id, case_id, package_id, submitted_by="qa_director")
    amendment = workflow.create_amendment(tenant_id, case_id, generated_by="user@co.com")
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("request-workflow")

# ---------------------------------------------------------------------------
# Valid workflow stages (ordered)
# ---------------------------------------------------------------------------

WORKFLOW_STAGES = [
    "intake",
    "scoping",
    "collecting",
    "gap_analysis",
    "exception_triage",
    "assembling",
    "internal_review",
    "ready",
    "submitted",
    "amended",
]

VALID_SIGNOFF_TYPES = [
    "scope_approval",
    "package_review",
    "final_approval",
    "submission_authorization",
]

VALID_SCOPE_TYPES = [
    "tlc_trace",
    "product_recall",
    "facility_audit",
    "date_range",
    "custom",
]

VALID_SUBMISSION_TYPES = ["initial", "amendment", "supplement", "correction"]
VALID_SUBMISSION_METHODS = ["export", "email", "portal", "mail", "other"]
VALID_REQUEST_CHANNELS = ["email", "phone", "portal", "letter", "drill", "other"]

DEFAULT_RESPONSE_HOURS = 24


# ---------------------------------------------------------------------------
# Workflow Service
# ---------------------------------------------------------------------------

class RequestWorkflow:
    """24-hour FDA request-response workflow manager.

    All methods enforce tenant_id scoping on every query. Mutations
    advance the case through the workflow stages and maintain the
    immutable package/submission audit trail.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 1. Create Request Case
    # ------------------------------------------------------------------

    def create_request_case(
        self,
        tenant_id: str,
        *,
        requesting_party: str = "FDA",
        request_channel: str = "email",
        scope_type: str = "tlc_trace",
        scope_description: Optional[str] = None,
        response_hours: int = DEFAULT_RESPONSE_HOURS,
        response_due_at: Optional[datetime] = None,
        affected_products: Optional[List[str]] = None,
        affected_lots: Optional[List[str]] = None,
        affected_facilities: Optional[List[str]] = None,
        reviewer: Optional[str] = None,
        final_approver: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new request case in 'intake' status.

        Args:
            tenant_id: Tenant UUID.
            requesting_party: Who is requesting (e.g. 'FDA', 'State DOH').
            request_channel: How the request arrived.
            scope_type: Type of scope for the request.
            scope_description: Free-text description of scope.
            response_hours: Hours until response is due (default 24).
            response_due_at: Explicit deadline (overrides response_hours).
            affected_products: Product references in scope.
            affected_lots: Lot/batch codes in scope.
            affected_facilities: Facility references in scope.
            reviewer: Assigned reviewer.
            final_approver: Final approver identity.

        Returns:
            Dict with the created request case fields.
        """
        if request_channel not in VALID_REQUEST_CHANNELS:
            raise ValueError(f"Invalid request_channel: {request_channel}")
        if scope_type not in VALID_SCOPE_TYPES:
            raise ValueError(f"Invalid scope_type: {scope_type}")

        now = datetime.now(timezone.utc)
        case_id = str(uuid4())
        due_at = response_due_at or (now + timedelta(hours=response_hours))

        result = self.db.execute(
            text("""
                INSERT INTO fsma.request_cases (
                    request_case_id, tenant_id,
                    request_received_at, response_due_at,
                    requesting_party, request_channel,
                    scope_type, scope_description,
                    affected_products, affected_lots, affected_facilities,
                    package_status,
                    reviewer, final_approver,
                    created_at, updated_at
                ) VALUES (
                    :case_id, :tenant_id,
                    :received_at, :due_at,
                    :requesting_party, :request_channel,
                    :scope_type, :scope_description,
                    :affected_products, :affected_lots, :affected_facilities,
                    'intake',
                    :reviewer, :final_approver,
                    :now, :now
                )
                RETURNING *
            """),
            {
                "case_id": case_id,
                "tenant_id": tenant_id,
                "received_at": now,
                "due_at": due_at,
                "requesting_party": requesting_party,
                "request_channel": request_channel,
                "scope_type": scope_type,
                "scope_description": scope_description,
                "affected_products": affected_products or [],
                "affected_lots": affected_lots or [],
                "affected_facilities": affected_facilities or [],
                "reviewer": reviewer,
                "final_approver": final_approver,
                "now": now,
            },
        )
        self.db.commit()
        row = result.mappings().fetchone()
        logger.info(
            "request_case_created",
            case_id=case_id,
            tenant_id=tenant_id,
            due_at=str(due_at),
        )
        return dict(row)

    # ------------------------------------------------------------------
    # 2. Update Scope
    # ------------------------------------------------------------------

    def update_scope(
        self,
        tenant_id: str,
        request_case_id: str,
        *,
        affected_products: Optional[List[str]] = None,
        affected_lots: Optional[List[str]] = None,
        affected_facilities: Optional[List[str]] = None,
        scope_type: Optional[str] = None,
        scope_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update the scope of a request case and advance to 'scoping'.

        Only allowed when case is in 'intake' or 'scoping' status.
        """
        if scope_type and scope_type not in VALID_SCOPE_TYPES:
            raise ValueError(f"Invalid scope_type: {scope_type}")

        case = self._get_case(tenant_id, request_case_id)
        if case["package_status"] not in ("intake", "scoping"):
            raise ValueError(
                f"Cannot update scope in status '{case['package_status']}'. "
                "Case must be in 'intake' or 'scoping'."
            )

        sets = ["package_status = 'scoping'", "updated_at = :now"]
        params: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "case_id": request_case_id,
            "now": datetime.now(timezone.utc),
        }

        if affected_products is not None:
            sets.append("affected_products = :products")
            params["products"] = affected_products
        if affected_lots is not None:
            sets.append("affected_lots = :lots")
            params["lots"] = affected_lots
        if affected_facilities is not None:
            sets.append("affected_facilities = :facilities")
            params["facilities"] = affected_facilities
        if scope_type is not None:
            sets.append("scope_type = :scope_type")
            params["scope_type"] = scope_type
        if scope_description is not None:
            sets.append("scope_description = :scope_description")
            params["scope_description"] = scope_description

        result = self.db.execute(
            text(f"""
                UPDATE fsma.request_cases
                SET {', '.join(sets)}
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
                RETURNING *
            """),
            params,
        )
        self.db.commit()
        row = result.mappings().fetchone()
        logger.info("scope_updated", case_id=request_case_id, tenant_id=tenant_id)
        return dict(row)

    # ------------------------------------------------------------------
    # 3. Collect Records for Scope
    # ------------------------------------------------------------------

    def collect_records(
        self,
        tenant_id: str,
        request_case_id: str,
    ) -> Dict[str, Any]:
        """Query canonical events matching the case scope.

        Advances the case to 'collecting' status and returns the matched
        events along with a record count update on the case.
        """
        case = self._get_case(tenant_id, request_case_id)
        if case["package_status"] not in ("scoping", "collecting"):
            raise ValueError(
                f"Cannot collect in status '{case['package_status']}'. "
                "Case must be in 'scoping' or 'collecting'."
            )

        # Build dynamic scope filter
        conditions = ["te.tenant_id = :tenant_id", "te.status = 'active'"]
        params: Dict[str, Any] = {"tenant_id": tenant_id, "case_id": request_case_id}

        products = case.get("affected_products") or []
        lots = case.get("affected_lots") or []
        facilities = case.get("affected_facilities") or []

        if products:
            conditions.append("te.product_reference = ANY(:products)")
            params["products"] = products
        if lots:
            conditions.append(
                "(te.lot_reference = ANY(:lots) OR te.traceability_lot_code = ANY(:lots))"
            )
            params["lots"] = lots
        if facilities:
            conditions.append(
                "(te.from_facility_reference = ANY(:facilities) "
                "OR te.to_facility_reference = ANY(:facilities))"
            )
            params["facilities"] = facilities

        where_clause = " AND ".join(conditions)

        events_result = self.db.execute(
            text(f"""
                SELECT event_id, event_type, event_timestamp,
                       product_reference, lot_reference, traceability_lot_code,
                       quantity, unit_of_measure,
                       from_entity_reference, to_entity_reference,
                       from_facility_reference, to_facility_reference,
                       transport_reference, kdes, confidence_score
                FROM fsma.traceability_events te
                WHERE {where_clause}
                ORDER BY te.event_timestamp
            """),
            params,
        )
        events = [dict(r) for r in events_result.mappings().fetchall()]
        total_records = len(events)

        # Update case status and record count
        now = datetime.now(timezone.utc)
        self.db.execute(
            text("""
                UPDATE fsma.request_cases
                SET package_status = 'collecting',
                    total_records = :total,
                    updated_at = :now
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
            """),
            {
                "total": total_records,
                "now": now,
                "case_id": request_case_id,
                "tenant_id": tenant_id,
            },
        )
        self.db.commit()

        logger.info(
            "records_collected",
            case_id=request_case_id,
            total_records=total_records,
        )
        return {"events": events, "total_records": total_records}

    # ------------------------------------------------------------------
    # 4. Run Gap Analysis
    # ------------------------------------------------------------------

    def run_gap_analysis(
        self,
        tenant_id: str,
        request_case_id: str,
    ) -> Dict[str, Any]:
        """Identify missing data and unresolved exceptions for the scope.

        Advances to 'gap_analysis'. Returns structured gap report including
        failed rule evaluations and open exception cases.
        """
        case = self._get_case(tenant_id, request_case_id)
        if case["package_status"] not in ("collecting", "gap_analysis"):
            raise ValueError(
                f"Cannot run gap analysis in status '{case['package_status']}'. "
                "Case must be in 'collecting' or 'gap_analysis'."
            )

        # Collect event IDs in scope
        event_ids = self._get_scope_event_ids(tenant_id, case)

        # Find failed rule evaluations for in-scope events
        failed_rules: List[Dict[str, Any]] = []
        if event_ids:
            rules_result = self.db.execute(
                text("""
                    SELECT re.evaluation_id, re.event_id, re.rule_id,
                           re.rule_version, re.result, re.why_failed,
                           re.evidence_fields_inspected, re.confidence,
                           rd.title AS rule_title, rd.severity, rd.category,
                           rd.citation_reference
                    FROM fsma.rule_evaluations re
                    JOIN fsma.rule_definitions rd
                      ON re.rule_id = rd.rule_id AND re.rule_version = rd.rule_version
                    WHERE re.tenant_id = :tenant_id
                      AND re.event_id = ANY(:event_ids)
                      AND re.result IN ('fail', 'warn')
                    ORDER BY rd.severity, re.evaluated_at
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            failed_rules = [dict(r) for r in rules_result.mappings().fetchall()]

        # Find unresolved exception cases linked to this request
        exceptions_result = self.db.execute(
            text("""
                SELECT case_id, severity, status, source_supplier,
                       source_facility_reference, rule_category,
                       recommended_remediation, owner_user_id, due_date,
                       created_at
                FROM fsma.exception_cases
                WHERE tenant_id = :tenant_id
                  AND (request_case_id = :case_id
                       OR linked_event_ids && :event_ids)
                  AND status NOT IN ('resolved', 'waived')
                ORDER BY severity, created_at
            """),
            {
                "tenant_id": tenant_id,
                "case_id": request_case_id,
                "event_ids": event_ids or [],
            },
        )
        unresolved_exceptions = [
            dict(r) for r in exceptions_result.mappings().fetchall()
        ]

        # Build gap owners map: group gaps by supplier/facility
        gap_owners: Dict[str, List[str]] = {}
        for exc in unresolved_exceptions:
            owner = exc.get("source_supplier") or exc.get("source_facility_reference") or "unknown"
            gap_owners.setdefault(owner, []).append(str(exc["case_id"]))

        # Identify events with no rule evaluations at all (missing evaluations)
        missing_evaluations: List[str] = []
        if event_ids:
            evaluated_result = self.db.execute(
                text("""
                    SELECT DISTINCT event_id
                    FROM fsma.rule_evaluations
                    WHERE tenant_id = :tenant_id
                      AND event_id = ANY(:event_ids)
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            evaluated_ids = {str(r[0]) for r in evaluated_result.fetchall()}
            missing_evaluations = [
                eid for eid in [str(e) for e in event_ids]
                if eid not in evaluated_ids
            ]

        gap_analysis = {
            "missing_events": missing_evaluations,
            "failed_rules": failed_rules,
            "unresolved_exceptions": unresolved_exceptions,
            "gap_owners": gap_owners,
        }

        gap_count = (
            len(missing_evaluations)
            + len(failed_rules)
            + len(unresolved_exceptions)
        )

        # Update case
        now = datetime.now(timezone.utc)
        self.db.execute(
            text("""
                UPDATE fsma.request_cases
                SET package_status = 'gap_analysis',
                    gap_count = :gap_count,
                    active_exception_count = :exc_count,
                    updated_at = :now
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
            """),
            {
                "gap_count": gap_count,
                "exc_count": len(unresolved_exceptions),
                "now": now,
                "case_id": request_case_id,
                "tenant_id": tenant_id,
            },
        )
        self.db.commit()

        logger.info(
            "gap_analysis_complete",
            case_id=request_case_id,
            gap_count=gap_count,
            exception_count=len(unresolved_exceptions),
        )
        return gap_analysis

    # ------------------------------------------------------------------
    # 5. Assemble Response Package
    # ------------------------------------------------------------------

    def assemble_response_package(
        self,
        tenant_id: str,
        request_case_id: str,
        *,
        generated_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an immutable response package snapshot.

        Collects all in-scope events, rule evaluations, and exception
        status into a single JSONB document. Computes SHA-256 hash of
        the full contents. Advances case to 'assembling'.

        This can be called multiple times to regenerate the package
        (each call creates a new version).
        """
        case = self._get_case(tenant_id, request_case_id)
        allowed = ("gap_analysis", "exception_triage", "assembling", "internal_review")
        if case["package_status"] not in allowed:
            raise ValueError(
                f"Cannot assemble in status '{case['package_status']}'. "
                f"Case must be in one of {allowed}."
            )

        # Determine version number
        ver_result = self.db.execute(
            text("""
                SELECT COALESCE(MAX(version_number), 0) AS max_ver
                FROM fsma.response_packages
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
            """),
            {"case_id": request_case_id, "tenant_id": tenant_id},
        )
        max_ver = ver_result.scalar()
        version_number = max_ver + 1

        # Gather event IDs
        event_ids = self._get_scope_event_ids(tenant_id, case)

        # Gather full event data
        events_data: List[Dict[str, Any]] = []
        if event_ids:
            ev_result = self.db.execute(
                text("""
                    SELECT event_id, event_type, event_timestamp,
                           product_reference, lot_reference, traceability_lot_code,
                           quantity, unit_of_measure,
                           from_entity_reference, to_entity_reference,
                           from_facility_reference, to_facility_reference,
                           transport_reference, kdes, confidence_score,
                           normalized_payload
                    FROM fsma.traceability_events
                    WHERE tenant_id = :tenant_id
                      AND event_id = ANY(:event_ids)
                      AND status = 'active'
                    ORDER BY event_timestamp
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            events_data = [
                _row_to_serializable(r) for r in ev_result.mappings().fetchall()
            ]

        # Gather rule evaluations
        rule_evaluations: List[Dict[str, Any]] = []
        if event_ids:
            re_result = self.db.execute(
                text("""
                    SELECT re.evaluation_id, re.event_id, re.rule_id,
                           re.rule_version, re.result, re.why_failed,
                           re.evidence_fields_inspected, re.confidence,
                           re.evaluated_at,
                           rd.title AS rule_title, rd.severity, rd.category,
                           rd.citation_reference
                    FROM fsma.rule_evaluations re
                    JOIN fsma.rule_definitions rd
                      ON re.rule_id = rd.rule_id AND re.rule_version = rd.rule_version
                    WHERE re.tenant_id = :tenant_id
                      AND re.event_id = ANY(:event_ids)
                    ORDER BY re.evaluated_at
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            rule_evaluations = [
                _row_to_serializable(r) for r in re_result.mappings().fetchall()
            ]

        # Gather exception case status
        exception_cases: List[Dict[str, Any]] = []
        exc_result = self.db.execute(
            text("""
                SELECT case_id, severity, status, source_supplier,
                       source_facility_reference, rule_category,
                       recommended_remediation, resolution_summary,
                       waiver_reason, waiver_approved_by, waiver_approved_at,
                       owner_user_id, due_date, created_at, updated_at, resolved_at
                FROM fsma.exception_cases
                WHERE tenant_id = :tenant_id
                  AND (request_case_id = :case_id
                       OR linked_event_ids && :event_ids)
                ORDER BY created_at
            """),
            {
                "tenant_id": tenant_id,
                "case_id": request_case_id,
                "event_ids": event_ids or [],
            },
        )
        exception_cases = [
            _row_to_serializable(r) for r in exc_result.mappings().fetchall()
        ]

        # Run gap analysis snapshot
        gap_analysis = self._compute_gap_snapshot(
            tenant_id, request_case_id, event_ids
        )

        # Build package contents
        package_contents = {
            "request_case_id": request_case_id,
            "tenant_id": tenant_id,
            "version_number": version_number,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": generated_by,
            "scope": {
                "scope_type": case.get("scope_type"),
                "scope_description": case.get("scope_description"),
                "affected_products": case.get("affected_products") or [],
                "affected_lots": case.get("affected_lots") or [],
                "affected_facilities": case.get("affected_facilities") or [],
            },
            "event_ids": [str(e.get("event_id", e) if isinstance(e, dict) else e) for e in event_ids] if event_ids else [],
            "trace_data": events_data,
            "rule_evaluations": rule_evaluations,
            "exception_cases": exception_cases,
            "gap_analysis": gap_analysis,
            "summary": {
                "total_events": len(events_data),
                "total_rule_evaluations": len(rule_evaluations),
                "failed_evaluations": sum(
                    1 for r in rule_evaluations if r.get("result") == "fail"
                ),
                "warned_evaluations": sum(
                    1 for r in rule_evaluations if r.get("result") == "warn"
                ),
                "total_exceptions": len(exception_cases),
                "open_exceptions": sum(
                    1 for e in exception_cases
                    if e.get("status") not in ("resolved", "waived")
                ),
            },
        }

        # Compute SHA-256 hash
        contents_json = json.dumps(package_contents, sort_keys=True, default=str)
        package_hash = hashlib.sha256(contents_json.encode("utf-8")).hexdigest()

        # Compute diff from previous version
        diff_from_previous = None
        if version_number > 1:
            diff_from_previous = self._compute_diff(
                tenant_id, request_case_id, version_number - 1, package_contents
            )

        # Insert package
        package_id = str(uuid4())
        now = datetime.now(timezone.utc)
        pkg_result = self.db.execute(
            text("""
                INSERT INTO fsma.response_packages (
                    package_id, tenant_id, request_case_id,
                    version_number, package_contents, package_hash,
                    gap_analysis, diff_from_previous,
                    generated_at, generated_by
                ) VALUES (
                    :pkg_id, :tenant_id, :case_id,
                    :version, :contents::jsonb, :hash,
                    :gap::jsonb, :diff::jsonb,
                    :now, :generated_by
                )
                RETURNING *
            """),
            {
                "pkg_id": package_id,
                "tenant_id": tenant_id,
                "case_id": request_case_id,
                "version": version_number,
                "contents": contents_json,
                "hash": package_hash,
                "gap": json.dumps(gap_analysis, default=str),
                "diff": json.dumps(diff_from_previous, default=str) if diff_from_previous else None,
                "now": now,
                "generated_by": generated_by,
            },
        )

        # Update case status
        self.db.execute(
            text("""
                UPDATE fsma.request_cases
                SET package_status = 'assembling',
                    total_records = :total,
                    updated_at = :now
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
            """),
            {
                "total": len(events_data),
                "now": now,
                "case_id": request_case_id,
                "tenant_id": tenant_id,
            },
        )
        self.db.commit()

        row = pkg_result.mappings().fetchone()
        logger.info(
            "package_assembled",
            case_id=request_case_id,
            package_id=package_id,
            version=version_number,
            hash=package_hash,
            record_count=len(events_data),
        )
        return dict(row)

    # ------------------------------------------------------------------
    # 6. Add Signoff
    # ------------------------------------------------------------------

    def add_signoff(
        self,
        tenant_id: str,
        request_case_id: str,
        signoff_type: str,
        *,
        signed_by: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a review signoff to the request case.

        Valid signoff types: scope_approval, package_review,
        final_approval, submission_authorization.

        Advances case status based on signoff type:
            - scope_approval -> exception_triage
            - package_review -> internal_review
            - final_approval -> ready
            - submission_authorization -> ready (no further advance)
        """
        if signoff_type not in VALID_SIGNOFF_TYPES:
            raise ValueError(
                f"Invalid signoff_type: {signoff_type}. "
                f"Must be one of {VALID_SIGNOFF_TYPES}."
            )

        case = self._get_case(tenant_id, request_case_id)

        signoff_id = str(uuid4())
        now = datetime.now(timezone.utc)

        self.db.execute(
            text("""
                INSERT INTO fsma.request_signoffs (
                    id, tenant_id, request_case_id,
                    signoff_type, signed_by, signed_at, notes
                ) VALUES (
                    :id, :tenant_id, :case_id,
                    :signoff_type, :signed_by, :now, :notes
                )
            """),
            {
                "id": signoff_id,
                "tenant_id": tenant_id,
                "case_id": request_case_id,
                "signoff_type": signoff_type,
                "signed_by": signed_by,
                "now": now,
                "notes": notes,
            },
        )

        # Advance status based on signoff type
        status_transitions = {
            "scope_approval": "exception_triage",
            "package_review": "internal_review",
            "final_approval": "ready",
            "submission_authorization": "ready",
        }
        new_status = status_transitions.get(signoff_type)

        update_fields = ["updated_at = :now"]
        update_params: Dict[str, Any] = {
            "now": now,
            "case_id": request_case_id,
            "tenant_id": tenant_id,
        }

        if new_status:
            update_fields.append("package_status = :new_status")
            update_params["new_status"] = new_status

        if signoff_type == "package_review":
            update_fields.append("reviewer = :reviewer")
            update_params["reviewer"] = signed_by
        elif signoff_type == "final_approval":
            update_fields.append("final_approver = :approver")
            update_params["approver"] = signed_by

        self.db.execute(
            text(f"""
                UPDATE fsma.request_cases
                SET {', '.join(update_fields)}
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
            """),
            update_params,
        )
        self.db.commit()

        logger.info(
            "signoff_added",
            case_id=request_case_id,
            signoff_type=signoff_type,
            signed_by=signed_by,
            new_status=new_status,
        )
        return {
            "signoff_id": signoff_id,
            "request_case_id": request_case_id,
            "signoff_type": signoff_type,
            "signed_by": signed_by,
            "signed_at": now.isoformat(),
            "notes": notes,
            "case_status": new_status or case["package_status"],
        }

    # ------------------------------------------------------------------
    # 7. Submit Package
    # ------------------------------------------------------------------

    def submit_package(
        self,
        tenant_id: str,
        request_case_id: str,
        package_id: str,
        *,
        submitted_by: str,
        submitted_to: Optional[str] = None,
        submission_method: str = "export",
        submission_notes: Optional[str] = None,
        submission_type: str = "initial",
    ) -> Dict[str, Any]:
        """Submit a package and mark the case as submitted.

        Creates a submission log entry with the immutable package hash
        and record count. Advances case to 'submitted'.
        """
        if submission_type not in VALID_SUBMISSION_TYPES:
            raise ValueError(f"Invalid submission_type: {submission_type}")
        if submission_method not in VALID_SUBMISSION_METHODS:
            raise ValueError(f"Invalid submission_method: {submission_method}")

        case = self._get_case(tenant_id, request_case_id)
        if case["package_status"] not in ("ready", "submitted", "amended"):
            raise ValueError(
                f"Cannot submit in status '{case['package_status']}'. "
                "Case must be in 'ready', 'submitted', or 'amended'."
            )

        # Fetch the package to get its hash and record count
        pkg_result = self.db.execute(
            text("""
                SELECT package_id, package_hash, package_contents
                FROM fsma.response_packages
                WHERE package_id = :pkg_id
                  AND tenant_id = :tenant_id
                  AND request_case_id = :case_id
            """),
            {
                "pkg_id": package_id,
                "tenant_id": tenant_id,
                "case_id": request_case_id,
            },
        )
        pkg = pkg_result.mappings().fetchone()
        if not pkg:
            raise ValueError(
                f"Package {package_id} not found for case {request_case_id}."
            )

        package_hash = pkg["package_hash"]
        contents = pkg["package_contents"]
        record_count = 0
        if isinstance(contents, str):
            contents = json.loads(contents)
        if isinstance(contents, dict):
            record_count = contents.get("summary", {}).get("total_events", 0)

        # Determine who the submission goes to
        if not submitted_to:
            submitted_to = case.get("requesting_party") or "FDA"

        # Create submission log entry
        submission_id = str(uuid4())
        now = datetime.now(timezone.utc)

        self.db.execute(
            text("""
                INSERT INTO fsma.submission_log (
                    id, tenant_id, request_case_id, package_id,
                    submission_type, submitted_to, submitted_by,
                    submission_method, submission_notes,
                    package_hash, record_count, submitted_at
                ) VALUES (
                    :id, :tenant_id, :case_id, :pkg_id,
                    :sub_type, :sub_to, :sub_by,
                    :sub_method, :sub_notes,
                    :hash, :record_count, :now
                )
            """),
            {
                "id": submission_id,
                "tenant_id": tenant_id,
                "case_id": request_case_id,
                "pkg_id": package_id,
                "sub_type": submission_type,
                "sub_to": submitted_to,
                "sub_by": submitted_by,
                "sub_method": submission_method,
                "sub_notes": submission_notes,
                "hash": package_hash,
                "record_count": record_count,
                "now": now,
            },
        )

        # Update case to submitted
        self.db.execute(
            text("""
                UPDATE fsma.request_cases
                SET package_status = 'submitted',
                    submission_timestamp = :now,
                    submission_notes = :notes,
                    updated_at = :now
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
            """),
            {
                "now": now,
                "notes": submission_notes,
                "case_id": request_case_id,
                "tenant_id": tenant_id,
            },
        )
        self.db.commit()

        logger.info(
            "package_submitted",
            case_id=request_case_id,
            package_id=package_id,
            submission_id=submission_id,
            submitted_by=submitted_by,
            record_count=record_count,
        )
        return {
            "submission_id": submission_id,
            "request_case_id": request_case_id,
            "package_id": package_id,
            "submission_type": submission_type,
            "submitted_to": submitted_to,
            "submitted_by": submitted_by,
            "submission_method": submission_method,
            "package_hash": package_hash,
            "record_count": record_count,
            "submitted_at": now.isoformat(),
        }

    # ------------------------------------------------------------------
    # 8. Create Amendment
    # ------------------------------------------------------------------

    def create_amendment(
        self,
        tenant_id: str,
        request_case_id: str,
        *,
        generated_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new package version (amendment) with diff against prior.

        Only allowed after initial submission. Advances case to 'amended'.
        Returns the new package record including diff_from_previous.
        """
        case = self._get_case(tenant_id, request_case_id)
        if case["package_status"] not in ("submitted", "amended"):
            raise ValueError(
                f"Cannot amend in status '{case['package_status']}'. "
                "Case must be in 'submitted' or 'amended'."
            )

        # Assemble a new package version (reuses assemble logic)
        # Temporarily set status to allow assembly
        self.db.execute(
            text("""
                UPDATE fsma.request_cases
                SET package_status = 'assembling',
                    updated_at = :now
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
            """),
            {
                "now": datetime.now(timezone.utc),
                "case_id": request_case_id,
                "tenant_id": tenant_id,
            },
        )
        self.db.commit()

        package = self.assemble_response_package(
            tenant_id, request_case_id, generated_by=generated_by
        )

        # Set status to amended
        now = datetime.now(timezone.utc)
        self.db.execute(
            text("""
                UPDATE fsma.request_cases
                SET package_status = 'amended',
                    updated_at = :now
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
            """),
            {
                "now": now,
                "case_id": request_case_id,
                "tenant_id": tenant_id,
            },
        )
        self.db.commit()

        logger.info(
            "amendment_created",
            case_id=request_case_id,
            package_id=package.get("package_id"),
            version=package.get("version_number"),
        )
        return package

    # ------------------------------------------------------------------
    # 9. Get Active Request Cases with Countdown
    # ------------------------------------------------------------------

    def get_active_cases(
        self,
        tenant_id: str,
        *,
        include_submitted: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get active request cases with countdown timer information.

        Returns cases ordered by urgency (closest deadline first).
        Each case includes hours_remaining and is_overdue fields.
        """
        status_filter = (
            "1=1"
            if include_submitted
            else "package_status NOT IN ('submitted', 'amended')"
        )

        result = self.db.execute(
            text(f"""
                SELECT rc.*,
                       EXTRACT(EPOCH FROM (rc.response_due_at - NOW())) / 3600.0
                           AS hours_remaining,
                       rc.response_due_at < NOW() AS is_overdue,
                       (SELECT COUNT(*) FROM fsma.request_signoffs rs
                        WHERE rs.request_case_id = rc.request_case_id
                          AND rs.tenant_id = rc.tenant_id) AS signoff_count,
                       (SELECT COUNT(*) FROM fsma.response_packages rp
                        WHERE rp.request_case_id = rc.request_case_id
                          AND rp.tenant_id = rc.tenant_id) AS package_count
                FROM fsma.request_cases rc
                WHERE rc.tenant_id = :tenant_id
                  AND {status_filter}
                ORDER BY rc.response_due_at ASC
            """),
            {"tenant_id": tenant_id},
        )
        rows = result.mappings().fetchall()
        cases = []
        for row in rows:
            case = dict(row)
            hours = case.get("hours_remaining")
            if hours is not None:
                case["hours_remaining"] = round(float(hours), 2)
                case["countdown_display"] = _format_countdown(float(hours))
            cases.append(case)
        return cases

    # ------------------------------------------------------------------
    # 10. Get Package Version History
    # ------------------------------------------------------------------

    def get_package_history(
        self,
        tenant_id: str,
        request_case_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all package versions for a request case, ordered by version.

        Returns package metadata (without full contents) including hash,
        gap analysis summary, and diff information.
        """
        self._get_case(tenant_id, request_case_id)  # validate access

        result = self.db.execute(
            text("""
                SELECT rp.package_id, rp.version_number,
                       rp.package_hash, rp.gap_analysis,
                       rp.diff_from_previous,
                       rp.generated_at, rp.generated_by,
                       sl.submitted_at, sl.submitted_by,
                       sl.submission_type, sl.submission_method
                FROM fsma.response_packages rp
                LEFT JOIN fsma.submission_log sl
                  ON sl.package_id = rp.package_id
                 AND sl.tenant_id = rp.tenant_id
                WHERE rp.request_case_id = :case_id
                  AND rp.tenant_id = :tenant_id
                ORDER BY rp.version_number ASC
            """),
            {"case_id": request_case_id, "tenant_id": tenant_id},
        )
        return [dict(r) for r in result.mappings().fetchall()]

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _get_case(self, tenant_id: str, request_case_id: str) -> Dict[str, Any]:
        """Fetch a request case, raising if not found."""
        result = self.db.execute(
            text("""
                SELECT * FROM fsma.request_cases
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
            """),
            {"case_id": request_case_id, "tenant_id": tenant_id},
        )
        row = result.mappings().fetchone()
        if not row:
            raise ValueError(
                f"Request case {request_case_id} not found for tenant {tenant_id}."
            )
        return dict(row)

    def _get_scope_event_ids(
        self, tenant_id: str, case: Dict[str, Any]
    ) -> List[str]:
        """Get event IDs matching the case scope criteria."""
        conditions = ["te.tenant_id = :tenant_id", "te.status = 'active'"]
        params: Dict[str, Any] = {"tenant_id": tenant_id}

        products = case.get("affected_products") or []
        lots = case.get("affected_lots") or []
        facilities = case.get("affected_facilities") or []

        if products:
            conditions.append("te.product_reference = ANY(:products)")
            params["products"] = products
        if lots:
            conditions.append(
                "(te.lot_reference = ANY(:lots) OR te.traceability_lot_code = ANY(:lots))"
            )
            params["lots"] = lots
        if facilities:
            conditions.append(
                "(te.from_facility_reference = ANY(:facilities) "
                "OR te.to_facility_reference = ANY(:facilities))"
            )
            params["facilities"] = facilities

        where_clause = " AND ".join(conditions)
        result = self.db.execute(
            text(f"""
                SELECT event_id FROM fsma.traceability_events te
                WHERE {where_clause}
            """),
            params,
        )
        return [str(r[0]) for r in result.fetchall()]

    def _compute_gap_snapshot(
        self,
        tenant_id: str,
        request_case_id: str,
        event_ids: List[str],
    ) -> Dict[str, Any]:
        """Compute a gap analysis snapshot for package assembly."""
        failed_rules: List[Dict[str, Any]] = []
        missing_evaluations: List[str] = []

        if event_ids:
            # Failed/warned rules
            fr_result = self.db.execute(
                text("""
                    SELECT re.evaluation_id, re.event_id, re.rule_id,
                           re.result, re.why_failed,
                           rd.title AS rule_title, rd.severity
                    FROM fsma.rule_evaluations re
                    JOIN fsma.rule_definitions rd
                      ON re.rule_id = rd.rule_id AND re.rule_version = rd.rule_version
                    WHERE re.tenant_id = :tenant_id
                      AND re.event_id = ANY(:event_ids)
                      AND re.result IN ('fail', 'warn')
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            failed_rules = [
                _row_to_serializable(r) for r in fr_result.mappings().fetchall()
            ]

            # Events without any evaluations
            ev_result = self.db.execute(
                text("""
                    SELECT DISTINCT event_id
                    FROM fsma.rule_evaluations
                    WHERE tenant_id = :tenant_id
                      AND event_id = ANY(:event_ids)
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            evaluated = {str(r[0]) for r in ev_result.fetchall()}
            missing_evaluations = [eid for eid in event_ids if eid not in evaluated]

        # Unresolved exceptions
        exc_result = self.db.execute(
            text("""
                SELECT case_id, severity, status, source_supplier
                FROM fsma.exception_cases
                WHERE tenant_id = :tenant_id
                  AND (request_case_id = :case_id
                       OR linked_event_ids && :event_ids)
                  AND status NOT IN ('resolved', 'waived')
            """),
            {
                "tenant_id": tenant_id,
                "case_id": request_case_id,
                "event_ids": event_ids or [],
            },
        )
        unresolved = [
            _row_to_serializable(r) for r in exc_result.mappings().fetchall()
        ]

        gap_owners: Dict[str, List[str]] = {}
        for exc in unresolved:
            owner = exc.get("source_supplier") or "unknown"
            gap_owners.setdefault(owner, []).append(str(exc["case_id"]))

        return {
            "missing_events": missing_evaluations,
            "failed_rules": failed_rules,
            "unresolved_exceptions": unresolved,
            "gap_owners": gap_owners,
        }

    def _compute_diff(
        self,
        tenant_id: str,
        request_case_id: str,
        prior_version: int,
        new_contents: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compute a diff between the new package and the prior version."""
        result = self.db.execute(
            text("""
                SELECT package_contents, package_hash
                FROM fsma.response_packages
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
                  AND version_number = :version
            """),
            {
                "case_id": request_case_id,
                "tenant_id": tenant_id,
                "version": prior_version,
            },
        )
        row = result.mappings().fetchone()
        if not row:
            return {"error": f"Prior version {prior_version} not found"}

        prior_contents = row["package_contents"]
        if isinstance(prior_contents, str):
            prior_contents = json.loads(prior_contents)

        prior_event_ids = set(prior_contents.get("event_ids", []))
        new_event_ids = set(new_contents.get("event_ids", []))

        prior_exc_ids = {
            str(e.get("case_id", ""))
            for e in prior_contents.get("exception_cases", [])
        }
        new_exc_ids = {
            str(e.get("case_id", ""))
            for e in new_contents.get("exception_cases", [])
        }

        prior_summary = prior_contents.get("summary", {})
        new_summary = new_contents.get("summary", {})

        return {
            "prior_version": prior_version,
            "prior_hash": row["package_hash"],
            "events_added": sorted(new_event_ids - prior_event_ids),
            "events_removed": sorted(prior_event_ids - new_event_ids),
            "exceptions_added": sorted(new_exc_ids - prior_exc_ids),
            "exceptions_resolved": sorted(prior_exc_ids - new_exc_ids),
            "summary_changes": {
                key: {
                    "prior": prior_summary.get(key),
                    "new": new_summary.get(key),
                }
                for key in set(list(prior_summary.keys()) + list(new_summary.keys()))
                if prior_summary.get(key) != new_summary.get(key)
            },
        }


# ---------------------------------------------------------------------------
# Module-level Helpers
# ---------------------------------------------------------------------------

def _row_to_serializable(row) -> Dict[str, Any]:
    """Convert a SQLAlchemy row mapping to a JSON-serializable dict."""
    d = dict(row)
    for key, val in d.items():
        if isinstance(val, UUID):
            d[key] = str(val)
        elif isinstance(val, datetime):
            d[key] = val.isoformat()
    return d


def _format_countdown(hours: float) -> str:
    """Format hours remaining into a human-readable countdown string."""
    if hours <= 0:
        abs_hours = abs(hours)
        h = int(abs_hours)
        m = int((abs_hours - h) * 60)
        return f"OVERDUE by {h}h {m}m"
    h = int(hours)
    m = int((hours - h) * 60)
    if h >= 24:
        days = h // 24
        remaining_h = h % 24
        return f"{days}d {remaining_h}h {m}m remaining"
    return f"{h}h {m}m remaining"
