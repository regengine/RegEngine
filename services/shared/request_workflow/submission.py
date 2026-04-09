"""Submission and amendment stage of the FDA request workflow."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import text

from .constants import VALID_SUBMISSION_METHODS, VALID_SUBMISSION_TYPES

logger = logging.getLogger("request-workflow")


class SubmissionMixin:
    """Methods for submitting packages and creating amendments."""

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
        force: bool = False,
    ) -> Dict[str, Any]:
        """Submit a package and mark the case as submitted.

        Creates a submission log entry with the immutable package hash
        and record count. Advances case to 'submitted'.

        ENFORCEMENT: Checks for blocking defects before allowing submission.
        Set force=True to override blockers (logged as an audit event).
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

        # ── ENFORCEMENT: Blocking defect gate ──
        defect_check = self.check_blocking_defects(tenant_id, request_case_id)
        if not defect_check["can_submit"]:
            if not force:
                blocker_summary = "; ".join(
                    b["message"] for b in defect_check["blockers"][:5]
                )
                raise ValueError(
                    f"Cannot submit: {defect_check['blocker_count']} blocking "
                    f"defect(s). {blocker_summary}"
                )
            else:
                logger.warning(
                    "submission_forced_with_blockers",
                    case_id=request_case_id,
                    submitted_by=submitted_by,
                    blocker_count=defect_check["blocker_count"],
                    blockers=[b["message"] for b in defect_check["blockers"]],
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
        self._safe_commit()

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
        # Allow 'assembling' as a recovery path: if a prior attempt crashed
        # mid-assembly, the case is stuck in 'assembling' with no other way
        # to retry. Accepting it here lets the caller retry the amendment.
        if case["package_status"] not in ("submitted", "amended", "assembling"):
            raise ValueError(
                f"Cannot amend in status '{case['package_status']}'. "
                "Case must be in 'submitted', 'amended', or 'assembling'."
            )

        prior_status = case["package_status"]

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
        self._safe_commit()

        try:
            package = self.assemble_response_package(
                tenant_id, request_case_id, generated_by=generated_by
            )
        except Exception:
            # Revert to prior status so the case isn't stuck in 'assembling'
            self.db.execute(
                text("""
                    UPDATE fsma.request_cases
                    SET package_status = :prior_status,
                        updated_at = :now
                    WHERE request_case_id = :case_id
                      AND tenant_id = :tenant_id
                """),
                {
                    "prior_status": prior_status if prior_status != "assembling" else "amended",
                    "now": datetime.now(timezone.utc),
                    "case_id": request_case_id,
                    "tenant_id": tenant_id,
                },
            )
            self._safe_commit()
            raise

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
        self._safe_commit()

        logger.info(
            "amendment_created",
            case_id=request_case_id,
            package_id=package.get("package_id"),
            version=package.get("version_number"),
        )
        return package
