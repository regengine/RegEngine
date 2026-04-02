"""Collection and gap analysis stage of the FDA request workflow."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import text

logger = logging.getLogger("request-workflow")


class CollectionMixin:
    """Methods for collecting records and running gap analysis."""

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
        self._safe_commit()

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
        self._safe_commit()

        logger.info(
            "gap_analysis_complete",
            case_id=request_case_id,
            gap_count=gap_count,
            exception_count=len(unresolved_exceptions),
        )
        return gap_analysis
