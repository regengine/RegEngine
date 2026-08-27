#!/usr/bin/env python3
"""CI guard — reject RLS policies that fall back to a constant tenant.

Scans active Alembic migration files (both the Python revisions and the
raw ``alembic/sql/`` files those revisions ``op.execute``) plus any
remaining service migration helpers, for the fail-open pattern:

    USING (tenant_id = COALESCE(
        NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
        '00000000-0000-0000-0000-000000000001'::UUID
    ))

for the same shape in the write arm:

    WITH CHECK (tenant_id = COALESCE(
        NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
        '00000000-0000-0000-0000-000000000001'::UUID
    ))

and for the silently-fail-open variant:

    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id))

A fallback to *any* constant tenant is fail-open, not just the sandbox
UUID: a connection that never set ``app.tenant_id`` silently reads (or
writes) as that tenant instead of raising. Every new RLS policy MUST use
``get_tenant_context()``, which raises when the GUC is unset.

Legacy service-level Flyway migrations were removed in #2004. The guard's
purpose is to prevent the pattern from reappearing in active migrations.

Exit code 0 = clean. Non-zero = fail-open pattern detected in a
non-grandfathered file, or the guard found no inputs to scan (a guard
that reads zero files is not a guard — see #2936 for the same class of
structural rot).

Usage:
    python scripts/check_rls_fallback.py            # scan SCAN_DIRS
    python scripts/check_rls_fallback.py PATH ...   # scan explicit paths
                                                    # (files or directories)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories to scan.
#
# ``alembic/sql`` is NOT dead history: live Alembic revisions read these
# files and ``op.execute`` them, so a fresh-DB ``alembic upgrade head``
# depends on them (see scripts/check_orphan_migrations.py) and 23 live
# ``CREATE POLICY`` statements live there. It was omitted here until
# #2935; the sibling guard check_tenant_id_uuid_only.py always scanned it.
SCAN_DIRS = [
    REPO_ROOT / "services" / "admin" / "migrations",
    REPO_ROOT / "alembic" / "versions",
    REPO_ROOT / "alembic" / "sql",
]

# No active migration file is allowed to keep the fail-open pattern.
# Grandfathering must be explicit here, never by omitting a directory
# from SCAN_DIRS.
GRANDFATHERED: set[str] = set()

FALLBACK_UUID = "00000000-0000-0000-0000-000000000001"

# A quoted UUID literal in any casing, e.g. '0000...0001' or 'DEADBEEF-...'.
_UUID_LITERAL = r"'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'"

# Opening of an RLS policy predicate. Both arms matter: USING governs which
# rows are *readable*, WITH CHECK governs which rows can be *written* into
# another tenant. Anchoring on USING alone (the pre-#2935 behaviour) left
# every ``FOR INSERT ... WITH CHECK (...)`` policy unexamined.
_POLICY_PREDICATE = r"(?:USING|WITH\s+CHECK)\s*\("

# ``[\s\S]{0,N}?`` rather than ``[^)]*``: the canonical form nests
# ``NULLIF(current_setting(...), '')::UUID`` inside the COALESCE, so a
# character class that stops at the first ``)`` can never reach the
# default argument. That is why the pre-#2935 _PAT_FALLBACK_UUID could
# not match the snippet in this module's own docstring.
_COALESCE_OVER_TENANT_GUC = (
    r"COALESCE\s*\([\s\S]{0,300}?current_setting\s*\(\s*'app\.tenant_id'[\s\S]{0,300}?"
)

# 1. COALESCE over app.tenant_id defaulting to ANY constant UUID.
#    Not just the sandbox constant — a fallback to any fixed tenant is
#    fail-open.
_PAT_FALLBACK_UUID = re.compile(
    _COALESCE_OVER_TENANT_GUC + _UUID_LITERAL,
    re.IGNORECASE,
)

# 2. COALESCE over app.tenant_id defaulting to the row's own tenant_id,
#    which lets a context-less connection see every row.
_PAT_SELF_TENANT = re.compile(
    _COALESCE_OVER_TENANT_GUC + r",\s*tenant_id\s*\)",
    re.IGNORECASE,
)

# 3. The literal sandbox UUID anywhere inside a policy predicate
#    (heuristic — catches hand-rolled shapes that skip COALESCE).
_PAT_LITERAL_IN_POLICY = re.compile(
    _POLICY_PREDICATE + r"[^;]*" + re.escape(FALLBACK_UUID),
    re.IGNORECASE | re.DOTALL,
)

# 4. Inside a policy predicate, a COALESCE over app.tenant_id defaulting to
#    any quoted literal at all — covers constants that are not written in
#    canonical UUID form.
_PAT_LITERAL_DEFAULT_IN_POLICY = re.compile(
    _POLICY_PREDICATE + r"[^;]{0,2000}?" + _COALESCE_OVER_TENANT_GUC + r",\s*'[^']*'",
    re.IGNORECASE,
)

_PATTERNS = (
    (_PAT_FALLBACK_UUID, "COALESCE(app.tenant_id) -> constant-UUID fallback"),
    (_PAT_SELF_TENANT, "COALESCE(app.tenant_id) -> self-tenant (visible-to-all)"),
    (_PAT_LITERAL_IN_POLICY, f"literal {FALLBACK_UUID} inside USING/WITH CHECK(...)"),
    (_PAT_LITERAL_DEFAULT_IN_POLICY, "COALESCE(app.tenant_id) -> literal default inside USING/WITH CHECK(...)"),
)


def iter_migration_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file():
            yield root
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in (".sql", ".py"):
                continue
            yield path


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def check_text(text: str) -> list[str]:
    """Return a list of violation descriptions for *text*, empty if clean."""
    violations: list[str] = []
    seen: set[tuple[int, str]] = set()
    for pat, label in _PATTERNS:
        for match in pat.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            key = (line, label)
            if key in seen:
                continue
            seen.add(key)
            snippet = " ".join(match.group(0).split())[:140]
            violations.append(f"L{line}: {label}: {snippet}")
    return violations


def check_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"could not read: {exc}"]
    return check_text(text)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        roots = [Path(a).resolve() for a in argv]
        missing = [r for r in roots if not r.exists()]
        if missing:
            for r in missing:
                print(f"ERROR: path does not exist: {r}")
            return 1
    else:
        roots = list(SCAN_DIRS)
        # A configured scan directory that has vanished means the guard is
        # silently covering less than it claims. Fail instead of shrinking.
        absent = [d for d in roots if not d.is_dir()]
        if absent:
            for d in absent:
                print(f"ERROR: configured scan directory is missing: {rel(d)}")
            print(
                "\nThe guard's scan surface shrank. Either restore the directory or\n"
                "remove it from SCAN_DIRS deliberately — never let it disappear silently."
            )
            return 1

    grandfathered_paths = {REPO_ROOT / g for g in GRANDFATHERED}
    any_violations = False
    scanned = 0
    for path in iter_migration_files(roots):
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
    for d in roots:
        print(f"  - {rel(d)}")

    if scanned == 0:
        print(
            "\nERROR: the guard read ZERO files — it is not checking anything.\n"
            "A hard gate that cannot fail is worse than no gate. Fix SCAN_DIRS."
        )
        return 1

    if any_violations:
        print(
            "\nFail-open RLS predicate detected in a non-grandfathered file.\n"
            "Every new RLS policy MUST use `get_tenant_context()` — which raises\n"
            "when app.tenant_id is unset — instead of COALESCE-to-a-constant.\n"
            "This applies to the WITH CHECK arm as well as USING. See #1091,\n"
            "#2935 and the active Alembic RLS hardening migrations."
        )
        return 1
    print("\nOK — no fail-open RLS patterns in non-grandfathered migrations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
