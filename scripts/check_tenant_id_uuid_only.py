#!/usr/bin/env python3
"""CI guard — reject new migrations that drift tenant isolation.

Two independent checks live here:

A. ``tenant_id`` column type must be ``UUID``.
   Every tenant-scoped table in RegEngine MUST use ``tenant_id UUID``. The
   canonical RLS helper ``get_tenant_context()`` returns ``UUID`` and the
   FastAPI ``set_tenant_context`` GUC is set from a UUID, so a TEXT or
   VARCHAR column silently breaks every RLS policy comparing them —
   Postgres emits ``operator does not exist: text = uuid`` and the policy
   returns no rows.

B. RLS policies must use the fail-hard ``get_tenant_context()`` predicate,
   not a ``current_setting('app.tenant_id', ...)`` text-compare (#2526).
   ``get_tenant_context()`` RAISES when the ``app.tenant_id`` GUC is unset
   (fail-hard, debuggable). A bare ``current_setting('app.tenant_id', true)``
   text-compare fails OPEN: an unset GUC silently returns the wrong rows
   (zero rows, or — with an explicit ``OR ... = ''`` clause — every
   tenant's rows). v090 converged the last live text-compare policies onto
   the fail-hard predicate; this check stops new migrations from
   reintroducing the divergence.

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
    # Quarantined incident files, if present in historical checkouts, are
    # skipped by path below. They are not active in any deploy path.
}

# Patterns: ``tenant_id TEXT`` (case-insensitive), ``tenant_id VARCHAR(36)``,
# ``tenant_id character varying``. We don't flag ``tenant_id`` followed by
# UUID, the dominant correct shape.
_PAT_TENANT_TEXT = re.compile(
    r"\btenant_id\s+(?:TEXT|VARCHAR(?:\s*\(\s*\d+\s*\))?|character\s+varying)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Check B — fail-hard RLS predicate (#2526)
# ---------------------------------------------------------------------------

# Files allowed to keep ``current_setting('app.tenant_id', ...)`` inside a
# CREATE POLICY. These are historical migrations already merged. v048–v051
# and v063 are the fail-open / text-compare originals that v090 (and v067
# for task_queue) supersede in the live chain; v078/v080 use the
# NULLIF-guarded fail-closed form. New migrations get no such pass.
POLICY_PREDICATE_GRANDFATHERED = {
    "alembic/sql/V052__ensure_tenant_tables.sql",
    "alembic/versions/20260327_v048_operational_hardening.py",
    "alembic/versions/20260327_v049_fsma_audit_trail.py",
    "alembic/versions/20260329_task_queue_v050.py",
    "alembic/versions/20260331_rls_tenant_feature_tables_v051.py",
    "alembic/versions/20260422_85cebda8e7f7_v063_task_queue.py",
    "alembic/versions/20260505_5ac9e7b1d402_v078_orphan_migration_forward_ports.py",
    "alembic/versions/20260512_8a9b0c1d2e3f_v080_rule_rejections_audit.py",
}

_PAT_CREATE_POLICY = re.compile(r"CREATE\s+POLICY", re.IGNORECASE)
_PAT_TENANT_GUC = re.compile(r"current_setting\(\s*'app\.tenant_id'", re.IGNORECASE)

# Cap how far past a ``CREATE POLICY`` we look for the text-compare, so the
# window can't bleed into an unrelated later statement.
_POLICY_WINDOW_CHARS = 1200


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


def check_policy_predicates(path: Path) -> list[str]:
    """Flag ``current_setting('app.tenant_id', ...)`` used inside a
    ``CREATE POLICY``. Each ``CREATE POLICY`` starts a window that ends at
    the next ``CREATE POLICY`` (or ``_POLICY_WINDOW_CHARS`` past the start,
    whichever comes first); a text-compare reference inside that window is
    a violation. Looking only inside policy windows avoids flagging the
    legitimate ``current_setting('app.tenant_id', ...)`` uses elsewhere —
    e.g. the body of ``get_tenant_context()`` itself, or index/comment
    text."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"could not read: {exc}"]

    starts = [m.start() for m in _PAT_CREATE_POLICY.finditer(text)]
    violations: list[str] = []
    for i, start in enumerate(starts):
        next_start = starts[i + 1] if i + 1 < len(starts) else len(text)
        window_end = min(next_start, start + _POLICY_WINDOW_CHARS)
        window = text[start:window_end]
        guc = _PAT_TENANT_GUC.search(window)
        if guc:
            line = text.count("\n", 0, start + guc.start()) + 1
            violations.append(f"L{line}: current_setting('app.tenant_id', ...) inside CREATE POLICY")
    return violations


def main() -> int:
    grandfathered_paths = {REPO_ROOT / g for g in GRANDFATHERED}
    policy_grandfathered_paths = {REPO_ROOT / g for g in POLICY_PREDICATE_GRANDFATHERED}
    type_violations = False
    policy_violations = False
    scanned = 0
    for path in iter_migration_files():
        scanned += 1

        # Check A — tenant_id column type.
        violations = check_file(path)
        if violations:
            if path in grandfathered_paths:
                print(f"  [grandfathered:type] {rel(path)}: {len(violations)} pre-existing pattern(s)")
            else:
                type_violations = True
                print(f"\nFAIL (tenant_id type) {rel(path)}")
                for v in violations:
                    print(f"    {v}")

        # Check B — fail-hard RLS predicate.
        pol = check_policy_predicates(path)
        if pol:
            if path in policy_grandfathered_paths:
                print(f"  [grandfathered:policy] {rel(path)}: {len(pol)} pre-existing predicate(s)")
            else:
                policy_violations = True
                print(f"\nFAIL (RLS predicate) {rel(path)}")
                for v in pol:
                    print(f"    {v}")

    print(f"\nScanned {scanned} migration file(s) in:")
    for d in SCAN_DIRS:
        print(f"  - {rel(d)}")

    if type_violations:
        print(
            "\ntenant_id TEXT/VARCHAR pattern detected in a non-grandfathered file.\n"
            "Every tenant-scoped table MUST declare ``tenant_id UUID`` so RLS\n"
            "policies referencing ``get_tenant_context()`` (which returns UUID)\n"
            "compare cleanly. See v067 for the historical fix and the canonical\n"
            "shape used in v002, v042–v047, v052, etc."
        )

    if policy_violations:
        print(
            "\ncurrent_setting('app.tenant_id', ...) text-compare detected inside\n"
            "a CREATE POLICY in a non-grandfathered file. Tenant-isolation policies\n"
            "MUST use the fail-hard predicate ``tenant_id = get_tenant_context()``\n"
            "(which RAISES on an unset GUC) rather than a current_setting()\n"
            "text-compare (which fails OPEN). See v090 for the convergence and the\n"
            "canonical _TENANT_POLICY shape in v074."
        )

    if type_violations or policy_violations:
        return 1

    print("\nOK — no tenant_id type drift and no fail-open RLS predicates in non-grandfathered migrations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
