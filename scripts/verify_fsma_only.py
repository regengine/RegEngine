#!/usr/bin/env python3
"""Verification script: confirms non-FSMA vertical stubs have been deleted.

Run from repo root:
    python scripts/verify_fsma_only.py

Exit code 0 = clean.  Non-zero = stubs found.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ── 1. Directories that must NOT exist ─────────────────────────────────────
BANNED_DIRS = [
    "services/admin/app/verticals/energy",
    "services/admin/app/verticals/finance",
    "services/admin/app/verticals/gaming",
    "services/admin/app/verticals/healthcare",
    "services/admin/app/verticals/healthcare_enterprise",
    "services/admin/app/verticals/nuclear",
    "services/admin/app/verticals/technology",
    "sdks/nuclear",
]

# ── 2. Files that must NOT exist ───────────────────────────────────────────
BANNED_FILES = [
    "services/admin/app/verticals/models.py",
    "services/admin/app/verticals/router.py",
    "services/admin/seeds/energy_demo.py",
    "services/admin/seeds/finance_demo.py",
    "services/admin/seeds/gaming_demo.py",
    "services/admin/seeds/healthcare_demo.py",
    "services/admin/seeds/technology_demo.py",
    "services/admin/seeds/compliance_frameworks/energy_nerc_cip_v1.json",
    "services/admin/seeds/compliance_frameworks/finance_pci_sox_v1.json",
    "services/admin/seeds/compliance_frameworks/gaming_aml_gli_v1.json",
    "services/admin/seeds/compliance_frameworks/healthcare_hipaa_v1.json",
    "services/admin/seeds/compliance_frameworks/technology_soc2_iso_gdpr_v1.json",
    "services/admin/tests/verticals/test_energy_supply_chain.py",
    "services/admin/tests/verticals/test_finance_reconciliation.py",
    "services/admin/tests/verticals/test_gaming_risk.py",
    "services/admin/tests/verticals/test_healthcare_enterprise_breach.py",
    "services/admin/tests/verticals/test_healthcare_logic.py",
    "services/admin/tests/verticals/test_tech_evidence.py",
    "services/nlp/app/extractors/dora_extractor.py",
    "services/nlp/app/extractors/nydfs_extractor.py",
    "services/nlp/app/extractors/sec_sci_extractor.py",
    "services/ingestion/app/scrapers/state_adaptors/nj_gaming.py",
    "services/ingestion/app/scrapers/state_adaptors/nv_gaming.py",
    "services/ingestion/app/scrapers/state_adaptors/nydfs.py",
    "services/graph/app/queries/arbitrage_queries.py",
    "services/graph/app/routers/arbitrage.py",
]

# ── 3. Strings that must NOT appear in key shared modules ──────────────────
FORBIDDEN_IMPORTS = {
    "services/shared/schemas.py": ["HIPAA", "Fair Lending", "Aerospace", "NERC_CIP", "PCI_DSS"],
    "services/shared/fsma_rules.py": ["HIPAA", "Fair Lending", "Aerospace"],
    "services/shared/fsma_validation.py": ["HIPAA", "Fair Lending", "Aerospace"],
}


def main() -> int:
    failures: list[str] = []

    # Check banned directories
    for d in BANNED_DIRS:
        full = REPO_ROOT / d
        if full.exists():
            failures.append(f"BANNED DIR still exists: {d}")

    # Check banned files
    for f in BANNED_FILES:
        full = REPO_ROOT / f
        if full.exists():
            failures.append(f"BANNED FILE still exists: {f}")

    # Check forbidden strings in shared modules
    for filepath, keywords in FORBIDDEN_IMPORTS.items():
        full = REPO_ROOT / filepath
        if not full.exists():
            continue
        content = full.read_text()
        for kw in keywords:
            if kw in content:
                failures.append(f"FORBIDDEN STRING '{kw}' found in {filepath}")

    # Report
    if failures:
        print(f"\n{'='*60}")
        print(f"  VERIFICATION FAILED — {len(failures)} issue(s)")
        print(f"{'='*60}\n")
        for f in failures:
            print(f"  ✗ {f}")
        print()
        return 1

    print(f"\n{'='*60}")
    print("  VERIFICATION PASSED — FSMA 204 only, all stubs removed")
    print(f"{'='*60}\n")
    checks = len(BANNED_DIRS) + len(BANNED_FILES) + sum(len(v) for v in FORBIDDEN_IMPORTS.values())
    print(f"  {checks} checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
