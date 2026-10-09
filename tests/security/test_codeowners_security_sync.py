"""CODEOWNERS security coverage for security-critical shared modules.

Guards the audit finding that services/shared/webhook_security.py and
services/shared/api_key_store.py were missing from the security owners
list in .github/CODEOWNERS, so changes could skip security review.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"
COPILOT_REVIEW = REPO_ROOT / ".github" / "copilot-review.yml"

# Files the security automation treats as security-critical shared modules.
SECURITY_CRITICAL_SHARED_MODULES = (
    "services/shared/webhook_security.py",
    "services/shared/api_key_store.py",
)


def _security_section_lines() -> list[str]:
    lines = CODEOWNERS.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "# Security-sensitive files")
    return [line.strip() for line in lines[start:] if line.strip() and not line.startswith("#")]


def test_security_critical_modules_have_security_owner() -> None:
    section = _security_section_lines()
    for module in SECURITY_CRITICAL_SHARED_MODULES:
        assert any(entry.split()[0] == module for entry in section), (
            f"{module} missing from CODEOWNERS security section"
        )


def test_codeowners_security_globs_match_copilot_review() -> None:
    section_paths = {entry.split()[0] for entry in _security_section_lines()}
    review = yaml.safe_load(COPILOT_REVIEW.read_text())
    review_paths = {
        item["path"]
        for item in review["reviews"]["path_instructions"]
        if item["path"].startswith("services/shared/") and not item["path"].endswith("/**")
    }
    missing = review_paths - section_paths
    assert not missing, f"CODEOWNERS security section missing: {sorted(missing)}"


@pytest.mark.parametrize("module", SECURITY_CRITICAL_SHARED_MODULES)
def test_security_critical_module_exists(module: str) -> None:
    assert (REPO_ROOT / module).is_file(), f"{module} does not exist"
