import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Constitution 1.1: Zero PHI Keywords
FORBIDDEN_KEYWORDS = [
    "patient_name",
    "ssn",
    "social_security",
    "diagnosis",
    "medical_record_number",
    "mrn",
    "clinical_notes",
    "treatment_plan",
    "prescription_details",
    "dob",
    "date_of_birth",
]

# Whole-word matching: short terms such as "dob" must not fire inside ordinary
# words such as "adobe", and "diagnosis" must not fire inside "diagnoses".
KEYWORD_PATTERNS = {
    keyword: re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE) for keyword in FORBIDDEN_KEYWORDS
}

# Directories covered by the zero-PHI banner, relative to the repo root.
# These must be real product-code trees, never a list of files that no longer
# exist: a missing target is reported as a finding so coverage can never
# silently shrink to a vacuous pass.
SCAN_TARGETS = [
    "services",
    "scripts",
]

SCAN_EXTENSIONS = {".sql", ".py", ".json"}

SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
}

# Central exclusion registry: the ONLY way to take a whole file out of scope.
# Inline markers are not honored anywhere; every exclusion lives here with
# its reason so reviewers can audit this one list.
EXCLUDED_FILES = [
    "scripts/security/scan_phi.py",  # The scanner names its own keywords.
]

# Central suppression registry: relative path -> {keyword: reason}.
# For code that must name a keyword without holding PHI (redaction patterns,
# PII allowlists, English prose such as "diagnosis" of a bug). A suppression
# silences one keyword in one file only; anything else in that file still
# fails the scan. Every applied suppression is printed by run_scan so the
# review trail appears in CI logs.
SUPPRESSED_KEYWORDS: Dict[str, Dict[str, str]] = {
    "services/graph/app/config.py": {
        "ssn": "Redaction regex list; matches SSN text only to redact it from logs.",
    },
    "services/admin/app/audit_routes.py": {
        "ssn": "PII field allowlist for audit hashing; values are never stored in the clear.",
    },
    "services/shared/pii.py": {
        "ssn": "Canonical PII module; names SSN as a sensitive alias type so it gets masked.",
    },
    "services/ingestion/app/inflow_workbench.py": {
        "diagnosis": "English prose ('sandbox diagnosis'); no clinical data field.",
    },
    "services/shared/rules/uom.py": {
        "diagnosis": "Comment prose ('diagnosis path' for unit mismatch); no clinical data.",
    },
    "scripts/backfill_canonical_from_legacy.py": {
        "diagnosis": "Comment prose ('actionable diagnosis'); no clinical data.",
    },
}


def scan_file(file_path: Path, repo_root: Path) -> Tuple[List[str], List[str]]:
    """Scan one file. Return (violations, applied suppressions).

    Files that cannot be read are reported as violations (fail closed):
    an unreadable file must never pass the gate with just a warning.
    """
    try:
        rel_path = str(file_path.relative_to(repo_root))
    except ValueError:
        rel_path = file_path.name
    suppressed_here = SUPPRESSED_KEYWORDS.get(rel_path, {})
    violations: List[str] = []
    applied: List[str] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                for keyword, pattern in KEYWORD_PATTERNS.items():
                    if pattern.search(line):
                        reason = suppressed_here.get(keyword)
                        if reason is not None:
                            applied.append(f"{rel_path}:{line_no}: '{keyword}' suppressed: {reason}")
                        else:
                            violations.append(f"Line {line_no}: Found forbidden keyword '{keyword}'")
    except (OSError, UnicodeDecodeError) as e:
        violations.append(
            f"Could not read {rel_path}: {e} (treated as a finding; fix readability or add a central suppression)"
        )
    return violations, applied


def _iter_target_files(root_dir: Path) -> Tuple[List[Path], List[str]]:
    """Return (files to scan, coverage problems). Missing scan targets are
    coverage problems: the gate must fail rather than pass vacuously."""
    files: List[Path] = []
    problems: List[str] = []
    for target in SCAN_TARGETS:
        target_path = root_dir / target
        if not target_path.exists():
            problems.append(f"Scan target missing: {target} (coverage shrank; fix SCAN_TARGETS)")
            continue
        for file_path in target_path.rglob("*"):
            if not file_path.is_file():
                continue
            if SKIP_DIR_NAMES.intersection(file_path.parts):
                continue
            if file_path.suffix not in SCAN_EXTENSIONS:
                continue
            files.append(file_path)
    return files, problems


def run_scan(root_dir: Path = None) -> int:
    print("🛡️  Starting Zero-PHI Constitution Scan...")
    print("-----------------------------------------")

    root = Path(root_dir).resolve() if root_dir is not None else Path(".").resolve()

    files, problems = _iter_target_files(root)

    total_violations = 0
    suppressed_trail: List[str] = []
    scanned = 0

    for file_path in sorted(files):
        # Check exclusions
        rel_path = str(file_path.relative_to(root))
        if rel_path in EXCLUDED_FILES:
            suppressed_trail.append(f"{rel_path}: excluded file (see EXCLUDED_FILES)")
            continue

        scanned += 1
        violations, applied = scan_file(file_path, root)
        suppressed_trail.extend(applied)
        if violations:
            print(f"❌ VIOLATION in {rel_path}:")
            for v in violations:
                print(f"   {v}")
            total_violations += 1

    for problem in problems:
        print(f"❌ COVERAGE: {problem}")
        total_violations += 1

    print("-----------------------------------------")
    if suppressed_trail:
        print("Suppressed (central registry review trail):")
        for entry in suppressed_trail:
            print(f"   {entry}")
    print(f"Scanned {scanned} files.")
    if total_violations > 0:
        print(f"🚨 SCAN FAILED: Found {total_violations} files with potential PHI keywords.")
        return 1
    else:
        print("✅ SCAN PASSED: No PHI keywords detected in covered paths.")
        return 0


if __name__ == "__main__":
    sys.exit(run_scan())
