"""#2824 — a CI step must not claim to verify what it does not test.

`qa-pipeline.yml` ran a step called "Tenant isolation checks" over a static
text scan of frontend `.tsx` files. Tenant isolation here is enforced by
PostgreSQL RLS policies, which such a scan cannot see, so the step could not
have failed on an isolation defect — and #2935 later found a live fail-open
RLS policy while that step was green.

These tests pin the naming, because the defect was never in the scanner's
logic. The scanner does what its own docstring said; the step name, the
banner and the filename claimed something else.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO / ".github" / "workflows" / "qa-pipeline.yml"
_SCANNER = _REPO / "qa" / "frontend-security-scan.js"

# A step or banner may not assert isolation/tenancy verification unless the
# thing it runs actually exercises a database.
_VERIFICATION_CLAIM = re.compile(r"tenant\s*[-_ ]?\s*isolation", re.IGNORECASE)


def _steps():
    data = yaml.safe_load(_WORKFLOW.read_text())
    for job in data["jobs"].values():
        for step in job.get("steps", []) or []:
            yield step


def test_no_qa_step_claims_tenant_isolation_over_a_static_scan():
    offenders = [
        (step.get("name"), step.get("run", ""))
        for step in _steps()
        if step.get("name")
        and _VERIFICATION_CLAIM.search(step["name"])
        and "node " in (step.get("run") or "")
    ]
    assert offenders == [], (
        "a qa-pipeline step claims tenant-isolation verification while running a "
        f"node static scan: {offenders}"
    )


def test_the_scanner_is_not_named_as_a_tenant_test():
    assert _SCANNER.exists(), "expected qa/frontend-security-scan.js"
    assert not (_REPO / "qa" / "tenant-test.js").exists(), (
        "qa/tenant-test.js is back — the filename itself was the false "
        "assurance: someone asking 'is tenant isolation tested?' finds it."
    )


def test_scanner_banner_does_not_claim_isolation_verification():
    body = _SCANNER.read_text()
    banner = [
        line
        for line in body.splitlines()
        if "console.log" in line and _VERIFICATION_CLAIM.search(line)
    ]
    # A banner may MENTION tenant isolation only to disclaim it.
    for line in banner:
        assert "NOT" in line or "not " in line, (
            f"scanner banner asserts tenant-isolation verification: {line.strip()}"
        )


def test_scanner_documents_where_real_isolation_coverage_lives():
    body = _SCANNER.read_text()
    for pointer in (
        "test_rls_enforcement_live.py",
        "test_rls_coverage.py",
    ):
        assert pointer in body, (
            f"scanner header should point at real isolation coverage ({pointer}) "
            "so the next reader is not left thinking nothing tests it"
        )


def test_the_referenced_isolation_suites_actually_exist():
    """Guard against the header becoming its own dangling pointer."""
    for rel in (
        "services/shared/tests/test_rls_enforcement_live.py",
        "tests/migrations/test_rls_coverage.py",
    ):
        assert (_REPO / rel).exists(), f"{rel} referenced by the scanner header is missing"


@pytest.mark.parametrize("sibling", ["qa/summary.js", "qa/decision.js"])
def test_sibling_qa_scripts_reference_the_real_filename(sibling):
    body = (_REPO / sibling).read_text()
    assert "tenant-test.js" not in body, f"{sibling} still invokes the old filename"
    assert "frontend-security-scan" in body, f"{sibling} does not reference the scanner"
