"""Assembly, signoff, and enforcement checks for the FDA request workflow."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from .constants import REQUIRED_SIGNOFF_TYPES, VALID_SIGNOFF_TYPES
from .utils import format_countdown, row_to_serializable

logger = logging.getLogger("request-workflow")


class AssemblyMixin:
    """Methods for package assembly, signoff, and blocking defect checks."""

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
                row_to_serializable(r) for r in ev_result.mappings().fetchall()
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
                row_to_serializable(r) for r in re_result.mappings().fetchall()
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
            row_to_serializable(r) for r in exc_result.mappings().fetchall()
        ]

        # Run gap analysis snapshot
        gap_analysis = self._compute_gap_snapshot(
            tenant_id, request_case_id, event_ids
        )

        # Snapshot rule versions at assembly time
        rule_versions = {}
        try:
            rv_result = self.db.execute(
                text("SELECT rule_id, rule_version, title, severity, category FROM fsma.rule_definitions"),
            )
            for rv in rv_result.mappings().fetchall():
                rule_versions[str(rv["rule_id"])] = {
                    "version": rv.get("rule_version"),
                    "title": rv.get("title"),
                    "severity": rv.get("severity"),
                    "category": rv.get("category"),
                }
        except Exception:
            logger.debug("rule_versions_snapshot_skipped", exc_info=True)

        # Snapshot identity state at assembly time
        identity_state = {}
        try:
            ent_result = self.db.execute(
                text("""
                    SELECT entity_id, canonical_name, entity_type, confidence_score
                    FROM fsma.canonical_entities
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id},
            )
            for ent in ent_result.mappings().fetchall():
                eid = str(ent["entity_id"])
                aliases = []
                try:
                    al_result = self.db.execute(
                        text("SELECT alias_value, alias_type FROM fsma.entity_aliases WHERE entity_id = :eid"),
                        {"eid": eid},
                    )
                    aliases = [{"value": a["alias_value"], "type": a["alias_type"]} for a in al_result.mappings().fetchall()]
                except Exception:
                    logger.debug("entity_aliases_snapshot_skipped", exc_info=True)
                identity_state[eid] = {
                    "name": ent.get("canonical_name"),
                    "type": ent.get("entity_type"),
                    "confidence": float(ent["confidence_score"]) if ent.get("confidence_score") else None,
                    "aliases": aliases,
                }
        except Exception:
            logger.debug("identity_state_snapshot_skipped", exc_info=True)

        # Snapshot signoff state
        signoff_state = []
        try:
            sig_result = self.db.execute(
                text("""
                    SELECT signoff_type, signed_by, signed_at, notes
                    FROM fsma.request_signoffs
                    WHERE request_case_id = :case_id
                    ORDER BY signed_at
                """),
                {"case_id": request_case_id},
            )
            signoff_state = [row_to_serializable(s) for s in sig_result.mappings().fetchall()]
        except Exception:
            logger.debug("signoff_state_snapshot_skipped", exc_info=True)

        # Waiver state — waived exception IDs
        waiver_state = [
            str(e.get("exception_id"))
            for e in exception_cases
            if e.get("status") == "waived"
        ]

        # Build package contents with full manifest
        sorted_event_ids = sorted([str(e.get("event_id", e) if isinstance(e, dict) else e) for e in event_ids]) if event_ids else []
        eval_ids = sorted([str(r.get("evaluation_id", "")) for r in rule_evaluations if r.get("evaluation_id")])

        package_contents = {
            "manifest_version": "1.0",
            "request_case_id": request_case_id,
            "tenant_id": tenant_id,
            "version_number": version_number,
            "assembled_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": generated_by,
            "scoped_event_ids": sorted_event_ids,
            "rule_evaluation_ids": eval_ids,
            "rule_versions": rule_versions,
            "identity_state": identity_state,
            "exception_state": {
                str(e.get("exception_id", "")): {
                    "status": e.get("status"),
                    "resolution": e.get("resolution_summary"),
                }
                for e in exception_cases
                if e.get("exception_id")
            },
            "signoff_state": signoff_state,
            "waiver_state": waiver_state,
            "scope": {
                "scope_type": case.get("scope_type"),
                "scope_description": case.get("scope_description"),
                "affected_products": case.get("affected_products") or [],
                "affected_lots": case.get("affected_lots") or [],
                "affected_facilities": case.get("affected_facilities") or [],
            },
            "event_ids": sorted_event_ids,
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

        # Compute manifest hash (exclude package_hash itself for self-verification)
        contents_for_hash = {k: v for k, v in package_contents.items() if k != "package_hash"}
        manifest_json = json.dumps(contents_for_hash, sort_keys=True, default=str)
        package_contents["package_hash"] = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()

        # Use the manifest hash computed above
        contents_json = json.dumps(package_contents, sort_keys=True, default=str)
        package_hash = package_contents["package_hash"]

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
        self._safe_commit()

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
                ON CONFLICT (tenant_id, request_case_id, signoff_type) DO NOTHING
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
        self._safe_commit()

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
    # 6b. Blocking Defect Check (ENFORCEMENT)
    # ------------------------------------------------------------------

    def check_blocking_defects(
        self,
        tenant_id: str,
        request_case_id: str,
    ) -> Dict[str, Any]:
        """Check for defects that BLOCK package submission.

        A blocking defect is any of:
        - Critical rule failure with no corresponding waiver/resolution
        - Unresolved critical exception cases
        - Events in scope with zero rule evaluations
        - Missing required signoff types

        Returns:
            Dict with 'can_submit' (bool), 'blockers' (list of blocking
            issues), and 'warnings' (list of non-blocking issues).
        """
        case = self._get_case(tenant_id, request_case_id)
        event_ids = self._get_scope_event_ids(tenant_id, case)
        blockers: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        # 1. Critical rule failures not covered by exception waiver/resolution
        if event_ids:
            critical_fails = self.db.execute(
                text("""
                    SELECT re.evaluation_id, re.event_id, re.rule_id,
                           re.why_failed, rd.title AS rule_title,
                           rd.citation_reference
                    FROM fsma.rule_evaluations re
                    JOIN fsma.rule_definitions rd
                      ON re.rule_id = rd.rule_id AND re.rule_version = rd.rule_version
                    WHERE re.tenant_id = :tenant_id
                      AND re.event_id = ANY(:event_ids)
                      AND re.result = 'fail'
                      AND rd.severity = 'critical'
                      AND NOT EXISTS (
                          SELECT 1 FROM fsma.exception_cases ec
                          WHERE ec.tenant_id = re.tenant_id
                            AND ec.linked_event_ids @> ARRAY[re.event_id]::text[]
                            AND ec.status IN ('resolved', 'waived')
                      )
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            for row in critical_fails.mappings().fetchall():
                blockers.append({
                    "type": "critical_rule_failure",
                    "event_id": str(row["event_id"]),
                    "rule_id": row["rule_id"],
                    "rule_title": row["rule_title"],
                    "citation": row["citation_reference"],
                    "why_failed": row["why_failed"],
                    "message": (
                        f"Critical rule '{row['rule_title']}' failed on event "
                        f"{str(row['event_id'])[:8]}... with no waiver or resolution."
                    ),
                })

        # 2. Unresolved critical exceptions
        critical_exceptions = self.db.execute(
            text("""
                SELECT case_id, severity, source_supplier,
                       rule_category, recommended_remediation
                FROM fsma.exception_cases
                WHERE tenant_id = :tenant_id
                  AND (request_case_id = :case_id
                       OR linked_event_ids && :event_ids)
                  AND status NOT IN ('resolved', 'waived')
                  AND severity = 'critical'
            """),
            {
                "tenant_id": tenant_id,
                "case_id": request_case_id,
                "event_ids": event_ids or [],
            },
        )
        for row in critical_exceptions.mappings().fetchall():
            blockers.append({
                "type": "unresolved_critical_exception",
                "exception_id": str(row["case_id"]),
                "supplier": row["source_supplier"],
                "rule_category": row["rule_category"],
                "message": (
                    f"Critical exception from {row['source_supplier'] or 'unknown'} "
                    f"in '{row['rule_category'] or 'unknown'}' is unresolved."
                ),
            })

        # 3. Events with zero rule evaluations (unevaluated data)
        if event_ids:
            unevaluated = self.db.execute(
                text("""
                    SELECT te.event_id, te.event_type, te.traceability_lot_code
                    FROM fsma.traceability_events te
                    WHERE te.tenant_id = :tenant_id
                      AND te.event_id = ANY(:event_ids)
                      AND te.status = 'active'
                      AND NOT EXISTS (
                          SELECT 1 FROM fsma.rule_evaluations re
                          WHERE re.tenant_id = te.tenant_id
                            AND re.event_id = te.event_id
                      )
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            for row in unevaluated.mappings().fetchall():
                blockers.append({
                    "type": "unevaluated_event",
                    "event_id": str(row["event_id"]),
                    "event_type": row["event_type"],
                    "tlc": row["traceability_lot_code"],
                    "message": (
                        f"Event {str(row['event_id'])[:8]}... ({row['event_type']}) "
                        f"has no rule evaluations — cannot verify compliance."
                    ),
                })

        # 4. Missing required signoff types
        signoff_result = self.db.execute(
            text("""
                SELECT DISTINCT signoff_type
                FROM fsma.request_signoffs
                WHERE request_case_id = :case_id
                  AND tenant_id = :tenant_id
            """),
            {"case_id": request_case_id, "tenant_id": tenant_id},
        )
        existing_signoffs = {r[0] for r in signoff_result.fetchall()}
        missing_signoffs = REQUIRED_SIGNOFF_TYPES - existing_signoffs
        for missing in sorted(missing_signoffs):
            blockers.append({
                "type": "missing_signoff",
                "signoff_type": missing,
                "message": f"Required signoff '{missing}' has not been provided.",
            })

        # 5. Pending identity reviews for entities in scope
        #    High-confidence matches (>=0.85) that haven't been resolved
        #    could mean duplicate entities are splitting traceability chains.
        try:
            identity_issues = self.db.execute(
                text("""
                    SELECT irq.review_id, irq.match_confidence,
                           ea.canonical_name AS entity_a_name,
                           eb.canonical_name AS entity_b_name
                    FROM fsma.identity_review_queue irq
                    JOIN fsma.canonical_entities ea
                      ON irq.entity_a_id = ea.entity_id
                    JOIN fsma.canonical_entities eb
                      ON irq.entity_b_id = eb.entity_id
                    WHERE irq.tenant_id = :tenant_id
                      AND irq.status = 'pending'
                      AND irq.match_confidence >= 0.85
                    LIMIT 20
                """),
                {"tenant_id": tenant_id},
            )
            for row in identity_issues.mappings().fetchall():
                blockers.append({
                    "type": "identity_ambiguity",
                    "review_id": str(row["review_id"]),
                    "entity_a": row["entity_a_name"],
                    "entity_b": row["entity_b_name"],
                    "similarity": float(row["match_confidence"]),
                    "message": (
                        f"Identity ambiguity: '{row['entity_a_name']}' and "
                        f"'{row['entity_b_name']}' are {int(row['match_confidence'] * 100)}% "
                        f"similar but unresolved. This may split traceability chains."
                    ),
                })
        except Exception:
            # identity_review_queue table may not exist yet — non-fatal
            logger.debug("identity_review_check_skipped", reason="table_not_available")

        # 6. Stale evaluations — events modified or rules changed after evaluation
        if event_ids:
            try:
                stale_result = self.db.execute(
                    text("""
                        SELECT re.event_id, re.rule_id,
                               COALESCE(e.amended_at, e.created_at) AS event_modified,
                               re.evaluated_at,
                               rd.rule_version AS current_version,
                               re.rule_version AS eval_version
                        FROM fsma.rule_evaluations re
                        JOIN fsma.traceability_events e
                          ON re.event_id = e.event_id AND re.tenant_id = e.tenant_id
                        JOIN fsma.rule_definitions rd
                          ON re.rule_id = rd.rule_id
                        WHERE re.tenant_id = :tenant_id
                          AND re.event_id = ANY(:event_ids)
                          AND (
                            COALESCE(e.amended_at, e.created_at) > re.evaluated_at
                            OR rd.rule_version != re.rule_version
                          )
                    """),
                    {"tenant_id": tenant_id, "event_ids": event_ids},
                )
                stale_rows = stale_result.mappings().fetchall()
                if stale_rows:
                    stale_details = []
                    for sr in stale_rows:
                        event_mod = sr.get("event_modified")
                        eval_at = sr.get("evaluated_at")
                        cur_ver = sr.get("current_version")
                        eval_ver = sr.get("eval_version")
                        if event_mod and eval_at and event_mod > eval_at:
                            reason = "event_modified"
                        else:
                            reason = "rule_version_changed"
                        stale_details.append({
                            "event_id": str(sr["event_id"]),
                            "rule_id": str(sr["rule_id"]),
                            "reason": reason,
                        })
                    blockers.append({
                        "type": "stale_evaluations",
                        "count": len(stale_details),
                        "details": stale_details,
                        "message": f"{len(stale_details)} evaluation(s) are stale — re-evaluate before submission.",
                    })
            except Exception:
                logger.debug("stale_evaluation_check_skipped", reason="query_failed")

        # 7. Non-critical warnings (don't block but should be noted)
        if event_ids:
            non_critical_fails = self.db.execute(
                text("""
                    SELECT COUNT(*) AS cnt
                    FROM fsma.rule_evaluations re
                    JOIN fsma.rule_definitions rd
                      ON re.rule_id = rd.rule_id AND re.rule_version = rd.rule_version
                    WHERE re.tenant_id = :tenant_id
                      AND re.event_id = ANY(:event_ids)
                      AND re.result = 'fail'
                      AND rd.severity = 'warning'
                """),
                {"tenant_id": tenant_id, "event_ids": event_ids},
            )
            warn_count = non_critical_fails.scalar() or 0
            if warn_count > 0:
                warnings.append({
                    "type": "non_critical_failures",
                    "count": warn_count,
                    "message": f"{warn_count} non-critical rule warning(s) present.",
                })

        can_submit = len(blockers) == 0

        logger.info(
            "blocking_defect_check",
            case_id=request_case_id,
            can_submit=can_submit,
            blocker_count=len(blockers),
            warning_count=len(warnings),
        )

        return {
            "can_submit": can_submit,
            "blockers": blockers,
            "warnings": warnings,
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
        }

    # ------------------------------------------------------------------
    # 6c. Deadline Status Check (ENFORCEMENT)
    # ------------------------------------------------------------------

    def check_deadline_status(
        self,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """Check all active cases for deadline urgency.

        Returns list of cases with urgency classification:
        - 'overdue': past deadline
        - 'critical': <2 hours remaining
        - 'urgent': <6 hours remaining
        - 'normal': >6 hours remaining

        Use this in a background job or health check to drive alerts.
        """
        result = self.db.execute(
            text("""
                SELECT request_case_id, package_status,
                       requesting_party, scope_description,
                       response_due_at,
                       EXTRACT(EPOCH FROM (response_due_at - NOW())) / 3600.0
                           AS hours_remaining,
                       response_due_at < NOW() AS is_overdue,
                       gap_count, active_exception_count
                FROM fsma.request_cases
                WHERE tenant_id = :tenant_id
                  AND package_status NOT IN ('submitted', 'amended')
                ORDER BY response_due_at ASC
            """),
            {"tenant_id": tenant_id},
        )

        cases = []
        for row in result.mappings().fetchall():
            hours = float(row["hours_remaining"] or 0)
            if row["is_overdue"]:
                urgency = "overdue"
            elif hours < 2:
                urgency = "critical"
            elif hours < 6:
                urgency = "urgent"
            else:
                urgency = "normal"

            cases.append({
                "request_case_id": str(row["request_case_id"]),
                "package_status": row["package_status"],
                "requesting_party": row["requesting_party"],
                "scope_description": row["scope_description"],
                "response_due_at": row["response_due_at"].isoformat() if row["response_due_at"] else None,
                "hours_remaining": round(hours, 2),
                "countdown_display": format_countdown(hours),
                "urgency": urgency,
                "gap_count": row["gap_count"],
                "active_exception_count": row["active_exception_count"],
            })

        overdue_count = sum(1 for c in cases if c["urgency"] == "overdue")
        critical_count = sum(1 for c in cases if c["urgency"] == "critical")

        if overdue_count > 0:
            logger.warning(
                "deadline_overdue",
                tenant_id=tenant_id,
                overdue_count=overdue_count,
            )
        if critical_count > 0:
            logger.warning(
                "deadline_critical",
                tenant_id=tenant_id,
                critical_count=critical_count,
            )

        return cases
