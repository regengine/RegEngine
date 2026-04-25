#!/usr/bin/env python3
"""CI guard — reject new migrations that declare ``tenant_id`` as TEXT or VARCHAR.

Every tenant-scoped table in RegEngine MUST use ``tenant_id UUID``. The
canonical RLS helper ``get_tenant_context()`` returns ``UUID`` and the
FastAPI ``set_tenant_context`` GUC is set from a UUID, so a TEXT or
VARCHAR column silently breaks every RLS policy comparing them — Postgres
emits ``operator does not exist: text = uuid`` and the policy returns
no rows.

Five tables historically drifted to TEXT / VARCHAR(36) and were
standardized to UUID by v067 (alembic/versions/20260424_e9f0a1b2c3d4).
This guard makes sure new migrations don't reintroduce the drift.

Allowed patterns (NOT flagged):
  * ``tenant_id UUID``                  — the canonical type
  * ``tenant_id UUID NOT NULL``         — same with constraint
  * ``ALTER COLUMN tenant_id TYPE text`` — explicitly reverting (downgrade
    paths or quarantine work). Caller takes responsibility.

Flagged patterns (will fail CI):
  * ``tenant_id TEXT``
  * ``tenant_id VARCHAR``
  * ``tenant_id VARCHAR(<n>)``
  * ``tenant_id character varying``

Grandfathered files (allowed to keep the legacy pattern):
  Historical creation migrations whose columns v067 fixes in-place.
  v067 itself contains the type names in its docstring — also grandfathered.

Exit code 0 = clean. Non-zero = drift detected in a non-grandfathered file.

Usage:
    python scripts/check_tenant_id_uuid_only.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = [
    REPO_ROOT / "alembic" / "versions",
    REPO_ROOT / "alembic" / "sql",
    REPO_ROOT / "services" / "admin" / "migrations",
]

# Files allowed to retain the legacy ``tenant_id TEXT/VARCHAR`` pattern.
# Either they ARE the historical drift (v049, v050, v057, v060, v063) and v067
# fixes the column in-place at upgrade time, or they reference the type
# string for a legitimate reason (function-local variable in V29 jwt_rls;
# v067's own docstring documents what it converts).
GRANDFATHERED = {
    "alembic/versions/20260327_v049_fsma_audit_trail.py",
    "alembic/versions/20260329_task_queue_v050.py",
    "alembic/versions/20260415_v057_schema_additions.py",
    "alembic/versions/20260420_eaba6af7ae2c_v060_dlq_replay_columns.py",
    "alembic/versions/20260422_85cebda8e7f7_v063_task_queue.py",
    "alembic/versions/20260424_e9f0a1b2c3d4_v067_tenant_id_uuid_standardization.py",
    # V29 declares ``jwt_tenant_id TEXT`` as a function-local variable
    # (not a column) before casting to UUID. Pattern in the file matches
    # our regex but is structurally fine.
    "services/admin/migrations/V29__jwt_rls_integration.sql",
    # Quarantined incident files — kept under abandoned_migrations_*
    # directories with their original content. Not active in any
    # deploy path.
}

# Patterns: ``tenant_id TEXT`` (case-insensitive), ``tenant_id VARCHAR(36)``,
# ``tenant_id character varying``. We don't flag ``tenant_id`` followed by
# UUID, the dominant correct shape.
_PAT_TENANT_TEXT = re.compile(
    r"\btenant_id\s+(?:TEXT|VARCHAR(?:\s*\(\s*\d+\s*\))?|character\s+varying)\b",
    re.IGNORECASE,
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
            # Skip any file under abandoned_migrations_* — those are
            # quarantined and not run anywhere.
            if any(part.startswith("abandoned_migrations_") for part in path.parts):
                continue
            yield path


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def check_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"could not read: {exc}"]

    violations: list[str] = []
    for match in _PAT_TENANT_TEXT.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        snippet = match.group(0)
        violations.append(f"L{line}: {snippet}")
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
            "\ntenant_id TEXT/VARCHAR pattern detected in a non-grandfathered file.\n"
            "Every tenant-scoped table MUST declare ``tenant_id UUID`` so RLS\n"
            "policies referencing ``get_tenant_context()`` (which returns UUID)\n"
            "compare cleanly. See v067 for the historical fix and the canonical\n"
            "shape used in v002, v042–v047, v052, etc."
        )
        return 1

    print("\nOK — no tenant_id TEXT/VARCHAR drift in non-grandfathered migrations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
