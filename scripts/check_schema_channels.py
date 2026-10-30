#!/usr/bin/env python3
"""CI guard — every SQL file in the two non-Alembic schema channels names the
Alembic revision it renders.

Decision record: docs/decisions/2026-10-30-schema-change-channel.md. The
Alembic chain under ``alembic/versions/`` is the only schema authority.
``supabase/migrations/`` and ``sql/prod-apply/`` may hold rendered copies of
Alembic revisions, and nothing else. A rendered copy starts with:

    -- alembic-revision: <12-hex revision id>
    -- rendered-from: alembic/versions/<file>.py (upgrade|downgrade|precheck)

Checks, per file under the two directories:

1. The ``alembic-revision`` header is present (within the first 20 lines)
   and names a revision id that exists in ``alembic/versions/``.
2. The ``rendered-from`` header is present and names a file that exists in
   ``alembic/versions/`` and whose ``revision`` matches the id in line 1.

Files that predate the decision carry no header and are grandfathered by
name below; the list only shrinks. ``PRECHECK_alembic_version_reconcile.sql``
is exempt because it checks every revision rather than rendering one.

Exit code 0 = clean. 1 = violation. 2 = repository layout not found.

Usage:
    python scripts/check_schema_channels.py
    python scripts/check_schema_channels.py --repo-root /path/to/checkout
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CHANNEL_DIRS = ("supabase/migrations", "sql/prod-apply")
HEADER_WINDOW_LINES = 20

_REVISION_HEADER = re.compile(r"^--\s*alembic-revision:\s*([0-9a-fA-F]{12})\s*$")
_RENDERED_FROM_HEADER = re.compile(
    r"^--\s*rendered-from:\s*(alembic/versions/[\w.\-]+\.py)\s*\((upgrade|downgrade|precheck)\)\s*$"
)
_REVISION_ASSIGNMENT = re.compile(r"""^revision(?::\s*str)?\s*=\s*['"]([0-9a-fA-F]+)['"]""", re.M)

# Files that existed before the 2026-10-30 decision without a header. Each is
# inventoried in the decision record's Appendix A. Remove an entry when the
# file gains its header or is moved out of the channel directory. Never add
# to this list: a new file must carry the header.
GRANDFATHERED: frozenset[str] = frozenset(
    {
        "supabase/migrations/20260314053557_create_waitlist_leads.sql",
        "supabase/migrations/20260314073855_create_developer_portal_tables.sql",
        "supabase/migrations/20260314074042_create_increment_invite_usage_rpc.sql",
        "supabase/migrations/20260314093510_create_assessment_submissions.sql",
        "supabase/migrations/20260317074952_create_fsma_organizations.sql",
        "supabase/migrations/20260319014551_create_search_queries_table.sql",
        "supabase/migrations/20260320220954_extend_organizations_schema.sql",
        "supabase/migrations/20260321014327_seed_fsma_204_obligations.sql",
        "supabase/migrations/20260321014418_seed_obligation_cte_rules.sql",
        "supabase/migrations/20260330002451_enable_rls_missing_tables.sql",
        "supabase/migrations/20260330031620_developer_portal_schema_doc.sql",
        "supabase/migrations/20260403234813_create_traceability_events_and_ingestion_runs.sql",
        "supabase/migrations/20260403235145_drop_hash_chain_fk_to_cte_events.sql",
        "supabase/migrations/20260403235708_create_rules_engine_tables.sql",
        "supabase/migrations/20260404000051_fix_cte_events_idempotency_constraint.sql",
        "supabase/migrations/20260404011602_create_transformation_links_adjacency.sql",
        "supabase/migrations/20260413044744_add_last_login_at_to_users.sql",
        "supabase/migrations/20260730025741_lockdown_anon_lead_capture_and_definer_rpcs.sql",
        "supabase/migrations/20260730025751_revoke_pgaudit_event_trigger_fn_execute.sql",
        "supabase/migrations/20260730033519_drop_transitional_anon_insert_on_assessment_submissions.sql",
        "supabase/migrations/20261001054030_security_fsma_rls_and_function_search_path_20260930.sql",
        "supabase/migrations/20261016072839_search_path_extensions.sql",
        "supabase/migrations/20261016073047_a_move_extensions_to_extensions_schema.sql",
        "supabase/migrations/20261016073057_b_drop_duplicate_indexes.sql",
        "supabase/migrations/20261016073107_c_rls_initplan_select_wrap.sql",
        "supabase/migrations/20261016073122_d_index_unindexed_foreign_keys.sql",
        "supabase/migrations/20261017021229_e_wrap_get_tenant_context.sql",
        "supabase/migrations/20261017021244_f_tenant_id_indexes.sql",
        "supabase/migrations/20261020072328_assessment_lead_abuse_guard.sql",
        "supabase/migrations/20261022101703_lock_down_submit_assessment_lead.sql",
        "supabase/migrations/20261022103548_enable_rls_internal_tables.sql",
        "supabase/migrations/20261023050348_sel401_notify_new_lead_secret.sql",
        "supabase/migrations/20261025100000_fix_obligation_1455_regulation_refs.sql",
        "supabase/migrations/20261025100100_waitlist_leads_drop_authenticated_read.sql",
        "supabase/migrations/20261025100200_task_queue_fail_closed_tenant_policy.sql",
        "supabase/migrations/20261025100300_data_gap_close_receipt_not_null.sql",
        "supabase/migrations/20261026132000_sel399_rls_split_api_keys_sessions_users.sql",
        "sql/prod-apply/rollback_sel399_rls_split_api_keys_sessions_users.sql",
    }
)

EXEMPT: frozenset[str] = frozenset({"sql/prod-apply/PRECHECK_alembic_version_reconcile.sql"})


def collect_revisions(versions_dir: Path) -> dict[str, str]:
    """Map revision id -> file name (relative to the repo root) for every
    migration under ``versions_dir``."""
    found: dict[str, str] = {}
    for path in sorted(versions_dir.glob("*.py")):
        match = _REVISION_ASSIGNMENT.search(path.read_text(encoding="utf-8", errors="replace"))
        if match:
            found[match.group(1).lower()] = f"alembic/versions/{path.name}"
    return found


def read_headers(path: Path) -> tuple[str | None, str | None, str | None]:
    """Return (revision_id, rendered_from_file, rendered_from_kind) from the
    first ``HEADER_WINDOW_LINES`` lines, or ``None`` for each missing part."""
    revision = rendered_file = rendered_kind = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            if index >= HEADER_WINDOW_LINES:
                break
            stripped = line.rstrip("\n")
            if revision is None:
                match = _REVISION_HEADER.match(stripped)
                if match:
                    revision = match.group(1).lower()
                    continue
            if rendered_file is None:
                match = _RENDERED_FROM_HEADER.match(stripped)
                if match:
                    rendered_file, rendered_kind = match.group(1), match.group(2)
    return revision, rendered_file, rendered_kind


def check_file(rel: str, path: Path, revisions: dict[str, str]) -> list[str]:
    """Return the list of violations for one channel file (empty when clean)."""
    if rel in EXEMPT or rel in GRANDFATHERED:
        return []
    problems: list[str] = []
    revision, rendered_file, _kind = read_headers(path)
    if revision is None:
        problems.append(f"{rel}: missing '-- alembic-revision: <id>' header in the first {HEADER_WINDOW_LINES} lines")
    elif revision not in revisions:
        problems.append(f"{rel}: alembic-revision {revision} does not exist in alembic/versions/")
    if rendered_file is None:
        problems.append(
            f"{rel}: missing '-- rendered-from: alembic/versions/<file>.py (upgrade|downgrade|precheck)' header"
        )
    elif revision is not None and revision in revisions and revisions[revision] != rendered_file:
        problems.append(
            f"{rel}: rendered-from names {rendered_file} but revision {revision} lives in {revisions[revision]}"
        )
    return problems


def scan(repo_root: Path) -> tuple[list[str], int]:
    versions_dir = repo_root / "alembic" / "versions"
    if not versions_dir.is_dir():
        print(f"!! alembic/versions not found under {repo_root}", file=sys.stderr)
        sys.exit(2)
    revisions = collect_revisions(versions_dir)
    problems: list[str] = []
    scanned = 0
    for channel in CHANNEL_DIRS:
        channel_dir = repo_root / channel
        if not channel_dir.is_dir():
            continue
        for path in sorted(channel_dir.rglob("*.sql")):
            rel = path.relative_to(repo_root).as_posix()
            scanned += 1
            problems.extend(check_file(rel, path, revisions))
    return problems, scanned


def stale_grandfathered(repo_root: Path) -> list[str]:
    """Grandfathered names that no longer exist on disk; each must be removed
    from ``GRANDFATHERED`` so the list only shrinks."""
    return sorted(name for name in GRANDFATHERED if not (repo_root / name).exists())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="repository root (default: parent of scripts/)",
    )
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    problems, scanned = scan(repo_root)
    for name in stale_grandfathered(repo_root):
        problems.append(f"GRANDFATHERED lists {name}, which no longer exists; remove the entry")
    print(f"Scanned {scanned} file(s) under {', '.join(CHANNEL_DIRS)}")
    if problems:
        print("\nSchema channel guard FAILED:")
        for problem in problems:
            print(f"  {problem}")
        print(
            "\nA file in these directories must be a render of an Alembic revision and "
            "start with the two header lines described in "
            "docs/decisions/2026-10-30-schema-change-channel.md."
        )
        return 1
    print("OK — every non-grandfathered channel file names an existing Alembic revision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
