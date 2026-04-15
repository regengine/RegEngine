"""Shared utilities for request workflow modules."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("request-workflow")


def row_to_serializable(row) -> Dict[str, Any]:
    """Convert a SQLAlchemy row mapping to a JSON-serializable dict."""
    d = dict(row)
    for key, val in d.items():
        if isinstance(val, UUID):
            d[key] = str(val)
        elif isinstance(val, datetime):
            d[key] = val.isoformat()
    return d


def format_countdown(hours: float) -> str:
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


class WorkflowBase:
    """Base providing shared helpers for all workflow mixins.

    Subclasses must set ``self.db`` (a SQLAlchemy Session).
    """

    db: Session

    def _safe_commit(self) -> None:
        """Commit the current transaction, rolling back on failure."""
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

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
            fr_result = self.db.execute(
                text("""
                    SELECT re.evaluation_id, re.event_id, re.rule_id,
                           re.result, re.why_failed,
                           rd.title AS rule_title, rd.severity
                    FROM fsma.rule_evaluations re
                    JOIN fsma.rule_definitions rd
                      ON re.rule_id = rd.rule_id AND re.rule_version = rd.rule_version
                    WHERE re.tenant_id = :tenant_id
                      AND re.event_id = ANY(CAST(:event_ids AS uuid[]))
                      AND re.result IN ('fail', 'warn')
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            failed_rules = [
                row_to_serializable(r) for r in fr_result.mappings().fetchall()
            ]

            ev_result = self.db.execute(
                text("""
                    SELECT DISTINCT event_id
                    FROM fsma.rule_evaluations
                    WHERE tenant_id = :tenant_id
                      AND event_id = ANY(CAST(:event_ids AS uuid[]))
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            evaluated = {str(r[0]) for r in ev_result.fetchall()}
            missing_evaluations = [eid for eid in event_ids if eid not in evaluated]

        exc_result = self.db.execute(
            text("""
                SELECT case_id, severity, status, source_supplier
                FROM fsma.exception_cases
                WHERE tenant_id = :tenant_id
                  AND (request_case_id = :case_id
                       OR linked_event_ids && CAST(:event_ids AS uuid[]))
                  AND status NOT IN ('resolved', 'waived')
            """),
            {
                "tenant_id": tenant_id,
                "case_id": request_case_id,
                "event_ids": event_ids or [],
            },
        )
        unresolved = [
            row_to_serializable(r) for r in exc_result.mappings().fetchall()
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
