#!/usr/bin/env python3
"""CI guard — enforce the alembic revision-ID generation policy (#1296).

Background
----------
Alembic revision IDs MUST be random 12-char hex hashes — either generated
by ``alembic revision -m "<message>"`` (which emits ``rev_id`` from
``uuid.uuid4().hex[-12:]``) or by any equivalent cryptographic source.

This repo historically handcrafted IDs as a cosmetic pattern — the
previous revision's characters shifted one position (e.g. ``a1b2c3d4e5f6``,
``b2c3d4e5f6a7``, ``c3d4e5f6a7b8`` …).  The scheme LOOKS like a 12-char
hex hash so tooling does not complain, but it has two fatal properties:

1. The keyspace is tiny — two developers producing parallel migrations
   will independently arrive at the same "next" ID.  This has already
   happened here: five v059 migrations collided on
   ``f5a6b7c8d9e0``, v060/v061 collided on ``a7b8c9d0e1f2``, and two
   v068 migrations collided on ``b4c5d6e7f8a9``.  Alembic treats each
   revision ID as the primary key of the migration graph; duplicates
   mean the graph can only resolve one of the colliders.
2. ``alembic revision --autogenerate`` produces a random ID, so every
   handcrafted ID requires a manual rename step that is trivially
   forgotten.

What this guard enforces (for NEW migrations only)
--------------------------------------------------
- Every migration file under ``alembic/versions/`` must declare a
  ``revision`` line whose value is a 12-char lowercase hex string.
- No two migrations may share the same ``revision`` ID.
- Every ``down_revision`` must either be ``None`` / unset (single root)
  or point to a revision that actually exists in-tree.

Existing collisions (the ones the issue documented) are grandfathered —
rewriting them would require re-stamping every deployed environment.
The set is enumerated in ``KNOWN_COLLISIONS`` below.  Any NEW duplicate
triggers a hard fail, so the problem stops growing.

Usage
-----
    python scripts/check_alembic_revisions.py

Exits 0 clean, non-zero on violation.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"

# Random-hash shape: 12 lowercase hex chars.  This is what both
# ``alembic revision`` (uuid4 tail) and hand-written random IDs end up
# looking like, so the shape check alone does not ban the handcrafted
# scheme — the uniqueness check below is what does the work.
_HEX12 = re.compile(r"^[0-9a-f]{12}$")

# ``revision = "…"`` / ``revision: str = "…"`` / single- or double-quoted.
_REVISION_RE = re.compile(
    r"""^\s*revision\s*(?::\s*[A-Za-z_.\[\], |]+)?\s*=\s*['\"]([^'\"]+)['\"]""",
    re.MULTILINE,
)

# ``down_revision`` can be a single string, ``None``, a tuple, or a
# sequence — we only need the string values to validate existence.
_DOWN_REVISION_RE = re.compile(
    r"""^\s*down_revision\s*(?::\s*[A-Za-z_.\[\], |]+)?\s*=\s*(.+?)\s*$""",
    re.MULTILINE,
)
_QUOTED_STR = re.compile(r"""['\"]([^'\"]+)['\"]""")

# Pre-existing collisions documented in #1296.  Each inner tuple is the
# set of files that share a single (bad) revision ID.  Do NOT edit these
# to "clean up history" — the databases running in staging/production
# have those IDs stamped in ``alembic_version`` and renaming them would
# force a painful manual re-stamp across every environment.  A follow-up
# ticket should decide whether to deprecate the losers-of-the-race or
# merge them into a single superseding revision.
KNOWN_COLLISIONS: dict[str, frozenset[str]] = {
    # v059 — five migrations that all claim "f5a6b7c8d9e0".  Alembic will
    # pick ONE of them as the canonical v059; the others are effectively
    # no-ops unless manually stamped.  See #1296.
    "f5a6b7c8d9e0": frozenset({
        "alembic/versions/20260417_cte_kdes_jsonb_v059.py",
        "alembic/versions/20260417_identity_alias_unique_constraint_v059.py",
        "alembic/versions/20260417_review_items_tenant_not_null_v059.py",
        "alembic/versions/20260417_rls_fail_closed_hardening_v059.py",
        "alembic/versions/20260417_task_queue_hardening_v059.py",
    }),
    # v060 (graph_outbox) and v061 (task_queue_rls_fail_closed) both
    # claim "a7b8c9d0e1f2".  v061 also lists v059's
    # "f5a6b7c8d9e0" as its down_revision, so in practice the graph_outbox
    # change silently chained behind the task-queue change.
    "a7b8c9d0e1f2": frozenset({
        "alembic/versions/20260417_graph_outbox_v060.py",
        "alembic/versions/20260417_v061_task_queue_rls_fail_closed.py",
    }),
    # v068 — identity-review-reopen and transformation-links-trace-indexes
    # both claim "b4c5d6e7f8a9".
    "b4c5d6e7f8a9": frozenset({
        "alembic/versions/20260418_v068_identity_review_reopen_1211.py",
        "alembic/versions/20260418_v068_transformation_links_trace_indexes.py",
    }),
}


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def parse_migration(path: Path) -> tuple[str | None, list[str]]:
    """Return (revision_id, [down_revision_ids]).  None/[] on parse failure."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None, []

    rev_match = _REVISION_RE.search(text)
    revision = rev_match.group(1) if rev_match else None

    down_ids: list[str] = []
    down_match = _DOWN_REVISION_RE.search(text)
    if down_match:
        rhs = down_match.group(1)
        # Either a single quoted hex, a tuple of them, or ``None``.
        if rhs.strip() not in ("None", "none"):
            down_ids = _QUOTED_STR.findall(rhs)
    return revision, down_ids


def main() -> int:
    if not VERSIONS_DIR.is_dir():
        print(f"no such directory: {rel(VERSIONS_DIR)}", file=sys.stderr)
        return 2

    migrations: list[tuple[Path, str, list[str]]] = []
    violations: list[str] = []

    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        revision, down_ids = parse_migration(path)
        if revision is None:
            violations.append(
                f"{rel(path)}: could not find a ``revision = '<hex12>'`` line"
            )
            continue
        if not _HEX12.match(revision):
            violations.append(
                f"{rel(path)}: revision '{revision}' is not 12 lowercase hex "
                f"chars — use ``alembic revision -m '<message>'`` to generate one"
            )
        migrations.append((path, revision, down_ids))

    # Uniqueness check — the core of #1296.
    by_revision: dict[str, list[Path]] = defaultdict(list)
    for path, revision, _ in migrations:
        by_revision[revision].append(path)

    for revision, paths in by_revision.items():
        if len(paths) < 2:
            continue
        paths_rel = frozenset(rel(p) for p in paths)
        grandfathered = KNOWN_COLLISIONS.get(revision)
        if grandfathered is not None and paths_rel <= grandfathered:
            # Exactly the known-bad set, nothing new.
            print(
                f"  [known-collision #1296] {revision}: {len(paths)} files "
                f"(grandfathered; see KNOWN_COLLISIONS in this script)"
            )
            continue
        violations.append(
            f"duplicate revision '{revision}' declared in {len(paths)} files:"
        )
        for p in sorted(paths):
            marker = (
                "  (grandfathered)"
                if grandfathered and rel(p) in grandfathered
                else "  (NEW — fix by regenerating this file's revision ID)"
            )
            violations.append(f"    - {rel(p)}{marker}")

    # Dangling-down_revision check.
    known_revisions = {revision for _, revision, _ in migrations}
    for path, revision, down_ids in migrations:
        for down in down_ids:
            if down not in known_revisions:
                violations.append(
                    f"{rel(path)}: down_revision '{down}' does not exist "
                    f"in alembic/versions/ — migration graph is broken"
                )

    # Report.
    print(f"\nScanned {len(migrations)} migration file(s) in {rel(VERSIONS_DIR)}")
    if violations:
        print("\nFAIL — alembic revision-ID policy violations:")
        for v in violations:
            print(f"  {v}")
        print(
            "\nPolicy (see CONTRIBUTING.md and issue #1296):\n"
            "  - Revision IDs must be random 12-char lowercase hex.\n"
            "  - Generate them via ``alembic revision -m '<message>'`` — do\n"
            "    NOT handcraft the IDs, even if the pattern 'looks like' hex.\n"
            "  - Two migrations sharing a revision ID is a hard-fail: only\n"
            "    one of them will execute at ``alembic upgrade head``."
        )
        return 1

    print("OK — every revision is 12-char hex, unique, and reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
