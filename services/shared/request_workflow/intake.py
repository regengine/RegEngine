"""Intake and scoping stage of the FDA request workflow."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from .constants import DEFAULT_RESPONSE_HOURS, VALID_REQUEST_CHANNELS, VALID_SCOPE_TYPES

logger = logging.getLogger("request-workflow")


class IntakeMixin:
    """Methods for creating request cases and updating scope."""

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
        """Create a new request case in 'intake' status."""
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
        self._safe_commit()
        row = result.mappings().fetchone()
        logger.info(
            "request_case_created",
            case_id=case_id,
            tenant_id=tenant_id,
            due_at=str(due_at),
        )
        return dict(row)

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
        self._safe_commit()
        row = result.mappings().fetchone()
        logger.info("scope_updated", case_id=request_case_id, tenant_id=tenant_id)
        return dict(row)
