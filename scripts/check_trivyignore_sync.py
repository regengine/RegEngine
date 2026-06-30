#!/usr/bin/env python3
"""CI guard — keep .trivyignore in lockstep with the pip-audit ignore set.

The pip-audit dependency gate (.github/workflows/security.yml and
.github/workflows/backend-ci.yml) accepts a documented set of CVEs via
``--ignore-vuln <ID>``. The Trivy container scan runs with
``ignore-unfixed: true`` and ``exit-code: 1``, so any *fixed-upstream*
advisory in that accepted set will hard-fail the container scan unless it is
also suppressed in ``.trivyignore``. PR #2492 mirrored only 2 of the accepted
IDs, leaving Trivy free to flap red on risk the team already accepted (#2528).

This guard fails if the two gates diverge:

  * Every CVE-keyed ID in the pip-audit ``--ignore-vuln`` set must appear in
    ``.trivyignore`` (Trivy keys Python advisories by CVE/GHSA).
  * ``.trivyignore`` must not list a CVE the pip-audit set no longer accepts.

PYSEC-only IDs (e.g. PYSEC-2025-183) are excluded from the comparison: Trivy
cannot match them and ``ignore-unfixed: true`` already filters the unfixed
ones. If such an advisory ever needs Trivy suppression, add its CVE/GHSA
equivalent to both gates and to TRIVY_ONLY_EXEMPT below.

Exit code 0 = in sync. Non-zero = drift detected.

Usage:
    python scripts/check_trivyignore_sync.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TRIVYIGNORE = REPO_ROOT / ".trivyignore"
PIP_AUDIT_WORKFLOWS = (
    REPO_ROOT / ".github" / "workflows" / "security.yml",
    REPO_ROOT / ".github" / "workflows" / "backend-ci.yml",
)

# CVE/GHSA-keyed advisory IDs that Trivy can match. PYSEC-* and other
# non-CVE/GHSA IDs are deliberately ignored because Trivy keys Python
# advisories by CVE/GHSA only.
_CVE_RE = re.compile(r"\b((?:CVE|GHSA)-[A-Za-z0-9-]+)\b")

# --ignore-vuln <ID> as it appears in the pip-audit step.
_IGNORE_VULN_RE = re.compile(r"--ignore-vuln\s+([A-Za-z0-9-]+)")

# .trivyignore entries: "<ID> exp:YYYY-MM-DD" or bare "<ID>" (comments skipped).
_TRIVY_ENTRY_RE = re.compile(r"^\s*([A-Za-z0-9-]+)")

# CVE/GHSA IDs that may legitimately appear in .trivyignore without a matching
# pip-audit --ignore-vuln entry (e.g. an OS-package CVE Trivy raises that
# pip-audit never sees). Keep this list small and justified.
TRIVY_ONLY_EXEMPT: set[str] = set()


def _pip_audit_cve_ids() -> set[str]:
    """Collect CVE/GHSA-keyed IDs from every pip-audit --ignore-vuln flag."""
    ids: set[str] = set()
    for wf in PIP_AUDIT_WORKFLOWS:
        if not wf.exists():
            continue
        for raw in _IGNORE_VULN_RE.findall(wf.read_text()):
            if _CVE_RE.fullmatch(raw):
                ids.add(raw)
    return ids


def _trivyignore_cve_ids() -> set[str]:
    """Collect CVE/GHSA-keyed IDs listed in .trivyignore."""
    ids: set[str] = set()
    if not TRIVYIGNORE.exists():
        return ids
    for line in TRIVYIGNORE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _TRIVY_ENTRY_RE.match(stripped)
        if m and _CVE_RE.fullmatch(m.group(1)):
            ids.add(m.group(1))
    return ids


def main() -> int:
    pip_audit = _pip_audit_cve_ids()
    trivy = _trivyignore_cve_ids()

    missing_from_trivy = sorted(pip_audit - trivy)
    extra_in_trivy = sorted(trivy - pip_audit - TRIVY_ONLY_EXEMPT)

    if not missing_from_trivy and not extra_in_trivy:
        print(
            f"OK: .trivyignore and pip-audit agree on {len(pip_audit)} CVE/GHSA ID(s): "
            f"{', '.join(sorted(pip_audit)) or '(none)'}"
        )
        return 0

    if missing_from_trivy:
        print(
            "::error::These pip-audit-accepted CVEs are missing from .trivyignore. "
            "Trivy (ignore-unfixed:true, exit-code:1) will hard-fail on them: "
            f"{', '.join(missing_from_trivy)}"
        )
    if extra_in_trivy:
        print(
            "::error::These CVEs are in .trivyignore but no longer accepted by the "
            "pip-audit gate. Remove them or add a justified TRIVY_ONLY_EXEMPT entry: "
            f"{', '.join(extra_in_trivy)}"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
