#!/usr/bin/env python3
"""CI guard: prevent new orphan migrations from being introduced.

RegEngine had two categories of "ghost" migrations that drifted prod DB
state away from the code's expectations:

1. ``services/*/migrations/V*.sql`` — Flyway files. Railway runs alembic
   only, so these NEVER apply in prod. Every column added here since the
   Railway consolidation is a latent 500 waiting for its first SELECT
   (see #1864 `users.token_version`, #1872 `fsma.task_queue`).

2. ``docs/abandoned_migrations_*`` — alembic migrations quarantined
   during the 2026-04-20 consolidation incident. They contained real
   DDL that was supposed to be folded into the v059 consolidated head
   but was missed. Source of #1871 (`fsma.task_queue`) and likely
   others not yet surfaced.

This guard:
- Lists every currently-tracked orphan file as a grandfathered allowlist
  (``scripts/orphan_migrations_allowlist.txt``).
- Fails CI if any file outside that allowlist appears in either
  orphan-prone location.
- Succeeds when an allowlist entry is *removed from the allowlist AND
  deleted from disk* — that's the incremental cleanup path.

Usage (local): ``python3 scripts/check_orphan_migrations.py``
Usage (CI):    same. Non-zero exit fails the step.

Add/remove entries in ``scripts/orphan_migrations_allowlist.txt`` as
you forward-port or delete files. Keep the allowlist monotonically
shrinking.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_FILE = Path(__file__).with_name("orphan_migrations_allowlist.txt")

# Globs that should contain ZERO files long-term. Each hit must either
# appear in the allowlist (grandfathered) or be deleted/forward-ported
# before this check passes.
FORBIDDEN_GLOBS: list[str] = [
    "services/*/migrations/V*.sql",
    "docs/abandoned_migrations_*/**/*.py",
]


def _load_allowlist() -> set[str]:
    if not ALLOWLIST_FILE.exists():
        return set()
    entries: set[str] = set()
    for line in ALLOWLIST_FILE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.add(stripped)
    return entries


def _find_orphans() -> set[str]:
    found: set[str] = set()
    for pattern in FORBIDDEN_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_file():
                found.add(str(path.relative_to(ROOT)))
    return found


def main() -> int:
    allowlist = _load_allowlist()
    orphans = _find_orphans()

    new_orphans = sorted(orphans - allowlist)
    stale_allowlist = sorted(allowlist - orphans)

    if new_orphans:
        print("ERROR: new orphan migration file(s) introduced.", file=sys.stderr)
        print(
            "These are not executed by the Railway alembic runner — every "
            "column/table added here is a latent 500 in prod (#1864, #1872).",
            file=sys.stderr,
        )
        for p in new_orphans:
            print(f"  new orphan: {p}", file=sys.stderr)
        print(
            "\nFix options:\n"
            "  (a) Forward-port the DDL to a new alembic migration in "
            "alembic/versions/ (idempotent IF NOT EXISTS pattern) and "
            "delete this file.\n"
            "  (b) If the DDL is dead code, delete the file outright.\n"
            "  (c) Grandfather it by adding the path to "
            f"{ALLOWLIST_FILE.relative_to(ROOT)} — only if forward-port "
            "is tracked in a linked issue.",
            file=sys.stderr,
        )
        return 1

    if stale_allowlist:
        print("ERROR: allowlist contains entries for files that no longer exist.", file=sys.stderr)
        print(
            "The allowlist must shrink as files are forward-ported or "
            "deleted. Remove these stale entries so the guard tightens.",
            file=sys.stderr,
        )
        for p in stale_allowlist:
            print(f"  stale allowlist entry: {p}", file=sys.stderr)
        return 1

    print(
        f"OK — {len(orphans)} orphan file(s), all grandfathered. "
        f"Allowlist is clean. Target: 0."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
