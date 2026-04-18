#!/usr/bin/env python3
"""CI guard — reject new RLS policies that fall back to the sandbox tenant UUID.

Scans migration files (both the raw-SQL `services/*/migrations/` and the
alembic `alembic/versions/` directories) for the fail-open pattern:

    USING (tenant_id = COALESCE(
        NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
        '00000000-0000-0000-0000-000000000001'::UUID
    ))

and for the silently-fail-open variant:

    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id))

Legacy migrations (V12–V28) are grandfathered — they are superseded by the
v059 migration which rewrites every policy via ``get_tenant_context()``.
The guard's purpose is to prevent the pattern from reappearing in NEW
migrations.

Exit code 0 = clean. Non-zero = fail-open pattern detected in a
non-grandfathered file (or an unexpected file).

Usage:
    python scripts/check_rls_fallback.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories to scan.
SCAN_DIRS = [
    REPO_ROOT / "services" / "admin" / "migrations",
    REPO_ROOT / "alembic" / "versions",
]

# Files that are allowed to keep the pattern (historical migrations already
# superseded by v059). These are the origin of the bug — rewriting them in
# place would break idempotency for environments that have already run
# them. The fix migration (v059) rebuilds the policies.
GRANDFATHERED = {
    # Admin raw-SQL migrations that defined the fail-open policies.
    # Superseded by alembic/versions/20260417_rls_fail_closed_hardening_v059.py.
    "services/admin/migrations/V3__tenant_isolation.sql",
    "services/admin/migrations/V12__production_compliance_init.sql",
    "services/admin/migrations/V14__tax_credit_tables.sql",
    "services/admin/migrations/V15__form_autofill_tables.sql",
    "services/admin/migrations/V16__classification_tables.sql",
    "services/admin/migrations/V17__paperwork_visa_tables.sql",
    "services/admin/migrations/V18__audit_provenance_tables.sql",
    "services/admin/migrations/V27__rls_core_security_tables.sql",
    "services/admin/migrations/V28__rls_pcos_vertical_tables.sql",
    "services/admin/migrations/V28_5__fix_rls_fail_closed.sql",  # references UUID in comment
    "services/admin/migrations/V29__jwt_rls_integration.sql",    # get_user_tenant_id fallback
    # The fix migration itself references the pattern in its downgrade() —
    # that's the whole point.
    "alembic/versions/20260417_rls_fail_closed_hardening_v059.py",
}

FALLBACK_UUID = "00000000-0000-0000-0000-000000000001"

# Patterns that indicate fail-open RLS.
#   - COALESCE(..., '00000000-...-000000000001') — the canonical form
#   - COALESCE(current_setting(...), tenant_id) — self-tenant fallback
#     which lets a context-less connection see every row
_PAT_FALLBACK_UUID = re.compile(
    r"COALESCE\s*\([^)]*current_setting\s*\(\s*'app\.tenant_id'[^)]*\)[^)]*"
    + re.escape(FALLBACK_UUID),
    re.IGNORECASE | re.DOTALL,
)
_PAT_SELF_TENANT = re.compile(
    r"COALESCE\s*\(\s*current_setting\s*\(\s*'app\.tenant_id'[^)]*\)\s*::\s*UUID\s*,\s*tenant_id\s*\)",
    re.IGNORECASE,
)

# Also flag any use of the literal sandbox UUID inside an RLS policy
# expression (heuristic — looks for 'USING' within 1500 chars before).
_PAT_LITERAL_IN_POLICY = re.compile(
    r"USING\s*\([^;]*" + re.escape(FALLBACK_UUID),
    re.IGNORECASE | re.DOTALL,
)


def iter_migration_files() -> Iterable[Path]:
    for root in SCAN_DIRS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in (".sql", ".py"):
                continue
            yield path


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def check_file(path: Path) -> list[str]:
    """Return a list of violation descriptions, empty if clean."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"could not read: {exc}"]

    violations: list[str] = []
    for pat, label in (
        (_PAT_FALLBACK_UUID, "COALESCE->fallback-UUID"),
        (_PAT_SELF_TENANT, "COALESCE->self-tenant (visible-to-all)"),
        (_PAT_LITERAL_IN_POLICY, f"literal {FALLBACK_UUID} inside USING(...)"),
    ):
        for match in pat.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            snippet = match.group(0).replace("\n", " ")[:140]
            violations.append(f"L{line}: {label}: {snippet}")
    return violations


def main() -> int:
    grandfathered_paths = {REPO_ROOT / g for g in GRANDFATHERED}
    any_violations = False
    scanned = 0
    for path in iter_migration_files():
        scanned += 1
        violations = check_file(path)
        if not violations:
            continue
        if path in grandfathered_paths:
            # Historical file — expected to still contain the pattern.
            print(f"  [grandfathered] {rel(path)}: {len(violations)} pre-existing pattern(s)")
            continue
        any_violations = True
        print(f"\nFAIL {rel(path)}")
        for v in violations:
            print(f"    {v}")

    print(f"\nScanned {scanned} migration file(s) in:")
    for d in SCAN_DIRS:
        print(f"  - {rel(d)}")

    if any_violations:
        print(
            "\nRLS fallback-UUID pattern detected in a non-grandfathered file.\n"
            "Every new RLS policy MUST use `get_tenant_context()` instead of\n"
            "COALESCE-to-fallback. See #1091 and\n"
            "alembic/versions/20260417_rls_fail_closed_hardening_v059.py\n"
            "for the approved pattern."
        )
        return 1
    print("\nOK — no fail-open RLS patterns in non-grandfathered migrations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
