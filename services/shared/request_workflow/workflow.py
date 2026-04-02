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

from sqlalchemy.orm import Session

from .assembly import AssemblyMixin
from .collection import CollectionMixin
from .intake import IntakeMixin
from .queries import QueryMixin
from .submission import SubmissionMixin
from .utils import WorkflowBase


class RequestWorkflow(
    IntakeMixin,
    CollectionMixin,
    AssemblyMixin,
    SubmissionMixin,
    QueryMixin,
    WorkflowBase,
):
    """24-hour FDA request-response workflow manager.

    All methods enforce tenant_id scoping on every query. Mutations
    advance the case through the workflow stages and maintain the
    immutable package/submission audit trail.
    """

    def __init__(self, db: Session):
        self.db = db
