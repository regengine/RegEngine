#!/usr/bin/env python3
"""CI guard: keep orphan migrations at zero.

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
- Fails CI if any file appears in either orphan-prone location.
- Fails CI if ``scripts/orphan_migrations_allowlist.txt`` contains any
  non-comment entry. The file is retained only as documentation of the
  zero-state contract after #2004.

Usage (local): ``python3 scripts/check_orphan_migrations.py``
Usage (CI):    same. Non-zero exit fails the step.

Forward-port any required DDL through ``alembic/versions/``. Do not add
new grandfathered entries to ``scripts/orphan_migrations_allowlist.txt``.
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
    # WS-2: the top-level Flyway tree was deleted long ago — reject any
    # attempt to reintroduce it. Railway runs alembic only.
    "migrations/V*.sql",
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


def _alembic_sql_reference_errors() -> list[str]:
    """Cross-check ``alembic/sql/`` against the revisions that execute it (WS-2).

    ``alembic/sql/`` is NOT dead history: live Alembic revisions (the
    V002–V042 baseline ``97588ba8edf3``, the control-plane revisions, …)
    read these files and ``op.execute`` them, so a fresh-DB
    ``alembic upgrade head`` depends on them. Enforce the contract in both
    directions:

    * every ``alembic/sql/*.sql`` file must be referenced by at least one
      revision — an unreferenced file is dead weight masquerading as an
      executable migration (archive it under ``docs/archive/migrations/``
      instead);
    * every ``V*.sql`` filename mentioned in a revision must exist in
      ``alembic/sql/`` — a missing file breaks fresh-DB bootstrap (#1187).
    """
    sql_dir = ROOT / "alembic" / "sql"
    versions_dir = ROOT / "alembic" / "versions"
    if not versions_dir.is_dir():
        return []

    revision_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(versions_dir.glob("*.py"))
    )
    sql_files = {path.name for path in sql_dir.glob("*.sql")} if sql_dir.is_dir() else set()

    errors: list[str] = []
    for name in sorted(sql_files):
        if name not in revision_text:
            errors.append(
                f"alembic/sql/{name} is referenced by NO alembic revision — "
                "dead weight in the executable tree. Archive it under "
                "docs/archive/migrations/ (see the README there) or wire it "
                "into a revision."
            )

    import re

    for name in sorted(set(re.findall(r'"(V\d+__[A-Za-z0-9_]+\.sql)"', revision_text))):
        if name not in sql_files:
            errors.append(
                f"alembic revision references {name} but alembic/sql/{name} "
                "does not exist — fresh-DB `alembic upgrade head` will crash "
                "(#1187). Restore the file; do not delete referenced SQL."
            )
    return errors


def main() -> int:
    allowlist = _load_allowlist()
    orphans = _find_orphans()

    forbidden_allowlist = sorted(allowlist)

    if forbidden_allowlist:
        print("ERROR: orphan migration allowlist entries are no longer permitted.", file=sys.stderr)
        print(
            f"{ALLOWLIST_FILE.relative_to(ROOT)} must contain comments only. "
            "Forward-port required DDL through alembic/versions/ and delete "
            "the orphan source file.",
            file=sys.stderr,
        )
        for p in forbidden_allowlist:
            print(f"  forbidden allowlist entry: {p}", file=sys.stderr)
        return 1

    if orphans:
        print("ERROR: orphan migration file(s) introduced.", file=sys.stderr)
        print(
            "These are not executed by the Railway alembic runner — every "
            "column/table added here is a latent 500 in prod (#1864, #1872).",
            file=sys.stderr,
        )
        for p in sorted(orphans):
            print(f"  orphan: {p}", file=sys.stderr)
        print(
            "\nFix options:\n"
            "  (a) Forward-port the DDL to a new alembic migration in "
            "alembic/versions/ (idempotent IF NOT EXISTS pattern) and "
            "delete this file.\n"
            "  (b) If the DDL is dead code, delete the file outright.",
            file=sys.stderr,
        )
        return 1

    reference_errors = _alembic_sql_reference_errors()
    if reference_errors:
        print("ERROR: alembic/sql <-> revision reference contract violated.", file=sys.stderr)
        for message in reference_errors:
            print(f"  {message}", file=sys.stderr)
        return 1

    print(
        "OK — 0 orphan migration file(s); allowlist is comments-only; "
        "alembic/sql references are consistent."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
