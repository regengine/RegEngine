"""QA gate invariants for the suites wired into blocking CI by #3248.

The Backend CI Status Gate only proves what its pytest argv actually runs. A
strict xfail exits 0, an importorskip exits 0, and a directory with no
test_*.py files collects nothing, so each of those silently passes the gate
while proving nothing. These tests pin the argv shape so a future edit cannot
reintroduce that coverage theater without turning the gate red.

Pure stdlib and offline: safe for the repo-root offline step.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "backend-ci.yml"

DISCLOSURE_TEST = "tests/qa_sweep_20261002/test_portal_export_disclosure.py"

# Modules in the blocking contract step that must fail collection, never
# skip, when fastapi or httpx is missing (SSRF and compliance coverage).
NO_SKIP_MODULES = [
    "tests/ingestion/test_ingest_url.py",
    "tests/compliance/test_api_endpoints.py",
    "tests/compliance/test_validate_rules_engine_golden.py",
]


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _argv_lines(text: str) -> list[str]:
    """Lines that are pytest argv entries (not comments or shell)."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("tests/") and not line.strip().startswith("#")
    ]


def test_be011_disclosure_stays_out_of_blocking_argv_while_xfailed():
    """BE-011 is a strict xfail, so the gate must not claim to run it.

    While the test carries an xfail marker (the redacted FDA CSV still
    embeds the portal link token), the blocking argv must ignore the file:
    an expected failure exits 0 and proves nothing. Once the export is
    fixed and the marker is removed, this test requires the --ignore to go
    away too, so the live assertion rejoins the gate.
    """
    tree = ast.parse(
        (REPO_ROOT / DISCLOSURE_TEST).read_text(encoding="utf-8"),
        filename=DISCLOSURE_TEST,
    )
    has_xfail = any(isinstance(node, ast.Attribute) and node.attr == "xfail" for node in ast.walk(tree))
    ignored = f"--ignore={DISCLOSURE_TEST}" in _workflow_text()
    if has_xfail:
        assert ignored, (
            f"{DISCLOSURE_TEST} is still xfail-marked but is no longer "
            "excluded from the blocking argv: the gate would exit 0 over "
            "an expected failure"
        )
    else:
        assert not ignored, (
            f"{DISCLOSURE_TEST} no longer xfails, so the blocking argv must "
            "run it: drop the --ignore from backend-ci.yml"
        )


def test_audit_dir_matches_argv_membership():
    """tests/audit must be gated if and only if it holds real tests."""
    has_tests = any((REPO_ROOT / "tests" / "audit").glob("test_*.py"))
    argv_hit = any(line in {"tests/audit", "tests/audit \\"} for line in _argv_lines(_workflow_text()))
    if has_tests:
        assert argv_hit, "tests/audit now holds test_*.py files but is missing from the blocking argv"
    else:
        assert not argv_hit, (
            "tests/audit holds no test_*.py files, so pytest collects "
            "nothing there: remove it from the blocking argv instead of "
            "letting the gate comment claim it is asserted"
        )


def test_gated_modules_cannot_silently_skip_imports():
    """No importorskip in modules the blocking gate relies on."""
    offenders = []
    for relative in NO_SKIP_MODULES:
        tree = ast.parse(
            (REPO_ROOT / relative).read_text(encoding="utf-8"),
            filename=relative,
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "importorskip":
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "importorskip in blocking-gate modules exits 0 without running the "
        "SSRF/compliance assertions; fail collection instead:\n" + "\n".join(offenders)
    )


def test_backend_ci_triggers_on_published_spec_changes():
    """The OpenAPI contract gate must run when the spec it reads changes."""
    text = _workflow_text()
    assert text.count("frontend/src/lib/public-openapi.ts") >= 2, (
        "backend-ci.yml must list frontend/src/lib/public-openapi.ts in "
        "both push and pull_request paths, or a spec-only change never runs "
        "the contract test that compares it"
    )
