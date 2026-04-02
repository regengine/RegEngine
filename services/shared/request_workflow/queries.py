"""Query methods for the FDA request workflow."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import text

from .utils import format_countdown

logger = logging.getLogger("request-workflow")


class QueryMixin:
    """Methods for querying request cases and package history."""

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
                case["countdown_display"] = format_countdown(float(hours))
            cases.append(case)
        return cases

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
