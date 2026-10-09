"""Package versions advance by relative increment, never a fixed number.

Regression coverage for the audit finding that
``tests/test_e2e_package_manifest.py::TestPackageManifest::test_09_amendment_preserves_original``
asserted ``version_number == 3``. That hard-coded value only holds when two
earlier assembly tests both ran first, so any reorder or skip broke it. The
production rule (``services/shared/request_workflow/assembly.py``) assigns
``version_number = MAX(version_number) + 1``. These tests pin that rule by
driving the real assembler against a scripted stand-in database, with
histories of several lengths and no live Postgres required.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

from services.shared.request_workflow import RequestWorkflow

TENANT = "tenant-version-test"
CASE_ID = "case-version-test"


class _FakeResult:
    """Minimal stand-in for a SQLAlchemy result."""

    def __init__(self, scalar_value: Any = None, rows: List[Any] | None = None):
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self) -> Any:
        return self._scalar_value

    def mappings(self) -> "_FakeResult":
        return self

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> List[Any]:
        return list(self._rows)


class _FakeDb(MagicMock):
    """Scripted session: tracks inserted package versions per case."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.versions: List[int] = []

    def execute(self, statement: Any, params: Dict[str, Any] | None = None) -> _FakeResult:
        sql = str(statement)
        if "MAX(version_number)" in sql:
            prior_max = max(self.versions, default=0)
            return _FakeResult(scalar_value=prior_max)
        if "INSERT INTO fsma.response_packages" in sql:
            assert params is not None
            self.versions.append(params["version"])
            return _FakeResult(
                rows=[
                    {
                        "package_id": params["pkg_id"],
                        "tenant_id": params["tenant_id"],
                        "request_case_id": params["case_id"],
                        "version_number": params["version"],
                        "package_hash": params["hash"],
                    }
                ]
            )
        return _FakeResult()


def _workflow_with_history(prior_versions: List[int]) -> tuple[RequestWorkflow, _FakeDb]:
    """Build a workflow whose case already has the given package versions."""
    db = _FakeDb()
    db.versions = list(prior_versions)
    workflow = RequestWorkflow(db)
    workflow._get_case = MagicMock(
        return_value={
            "request_case_id": CASE_ID,
            "tenant_id": TENANT,
            "package_status": "internal_review",
            "scope_type": "product_recall",
            "scope_description": "version test",
            "affected_products": [],
            "affected_lots": [],
            "affected_facilities": [],
        }
    )
    workflow._get_scope_event_ids = MagicMock(return_value=[])
    workflow._compute_gap_snapshot = MagicMock(return_value={})
    workflow._compute_diff = MagicMock(return_value={})
    return workflow, db


def test_consecutive_assemblies_increment_by_one():
    """Each assembly lands exactly one above the previous maximum."""
    workflow, db = _workflow_with_history([])
    seen = []
    for _ in range(3):
        prior_max = max(db.versions, default=0)
        package = workflow.assemble_response_package(TENANT, CASE_ID)
        assert package["version_number"] == prior_max + 1
        seen.append(package["version_number"])
    assert seen == [1, 2, 3]


def test_single_prior_assembly_yields_version_two():
    """With one earlier package (reordered or skipped history), the next is 2.

    This is the case the old hard-coded ``== 3`` assertion got wrong: it
    failed here even though the increment itself was correct.
    """
    workflow, db = _workflow_with_history([1])
    prior_max = max(db.versions)
    package = workflow.assemble_response_package(TENANT, CASE_ID)
    assert package["version_number"] == prior_max + 1
    assert package["version_number"] == 2
    assert package["version_number"] != 3


def test_longer_history_still_increments_by_one():
    """A five-version history amends to version 6, not to any fixed number."""
    workflow, db = _workflow_with_history([1, 2, 3, 4, 5])
    prior_max = max(db.versions)
    package = workflow.assemble_response_package(TENANT, CASE_ID)
    assert package["version_number"] == prior_max + 1
    assert package["version_number"] == 6
