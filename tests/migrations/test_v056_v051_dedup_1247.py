"""Static regression guard — v051/v056 duplication cleanup (#1247).

v051 and v056 both consolidate SQL_V048/V049/V050 work. #1247 flagged
that the duplication created policy drift whenever v056 re-ran v051's
statements without guards. Every v056 statement in Part 1 is already
idempotent (``IF NOT EXISTS`` / ``CREATE OR REPLACE`` / ``DO $$`` with
existence checks) EXCEPT the ``DROP FUNCTION get_tenant_context() CASCADE``
which was unconditional and silently dropped dependent policies.

This test asserts two invariants via file inspection:

  1. v056's docstring mentions #1247 and the known overlap with v051 —
     so a future reader doesn't rediscover the problem.
  2. v056's ``DROP FUNCTION ... CASCADE`` is wrapped in a guard (a
     ``DO $`` block that checks the function's existing return type
     before dropping) — so a re-run against a DB that already has the
     UUID-returning version does not destroy dependent policies.

This is a static check — it doesn't require PostgreSQL or Docker and
runs in CI as a fast regression gate. The behavioral contract is
verified by ``test_rls_hardening.py`` and ``test_rls_coverage.py``
(both require testcontainers and skip without Docker).

Run via:
    pytest tests/migrations/test_v056_v051_dedup_1247.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
V056_PATH = REPO_ROOT / "alembic" / "versions" / "20260415_v056_rls_hardening.py"
V051_PATH = (
    REPO_ROOT / "alembic" / "versions"
    / "20260331_rls_tenant_feature_tables_v051.py"
)


@pytest.fixture(scope="module")
def v056_source() -> str:
    assert V056_PATH.exists(), f"v056 migration not found at {V056_PATH}"
    return V056_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def v051_source() -> str:
    assert V051_PATH.exists(), f"v051 migration not found at {V051_PATH}"
    return V051_PATH.read_text(encoding="utf-8")


def test_v056_docstring_references_1247_and_overlap(v056_source: str) -> None:
    """The first docstring must flag the known v051 overlap and #1247 so
    a future dev reading the file can't accidentally re-introduce the
    drift by "fixing" what they think is a duplicate."""
    # Grab the module docstring — everything between the first pair of
    # triple-quotes.
    first = v056_source.index('"""')
    second = v056_source.index('"""', first + 3)
    docstring = v056_source[first:second + 3]
    assert "#1247" in docstring, (
        "v056 docstring must reference issue #1247 — the known duplication "
        "with v051. Without this pointer, a future reader may delete what "
        "they think is a duplicate Part 1 and break the fresh-DB path."
    )
    assert "v051" in docstring, (
        "v056 docstring must name v051 as the source of the overlap."
    )


def test_v056_drop_function_cascade_is_guarded(v056_source: str) -> None:
    """The DROP FUNCTION ... CASCADE must sit inside a conditional block
    so it only fires when the function actually needs a signature
    change. An unconditional DROP+CASCADE wipes dependent policies
    (see #1227) — the guard is what prevents that on any re-run path."""
    # Find every DROP FUNCTION ... get_tenant_context ... CASCADE occurrence.
    # Each one must be preceded (within the same string) by a DO $ block
    # and an IF condition that references the function's return type.
    import re

    # Extract all op.execute triple-quoted SQL blocks.
    execute_blocks = re.findall(
        r'op\.execute\(\s*"""(.*?)"""\s*\)',
        v056_source,
        re.DOTALL,
    )
    cascade_blocks = [
        blk for blk in execute_blocks
        if "DROP FUNCTION" in blk and "get_tenant_context" in blk
        and "CASCADE" in blk
    ]
    assert cascade_blocks, (
        "Expected at least one block mentioning "
        "DROP FUNCTION ... get_tenant_context ... CASCADE in v056."
    )
    for blk in cascade_blocks:
        # The guard must include a DO $...$ block wrapping the DROP+CREATE.
        assert "DO $" in blk, (
            "DROP FUNCTION ... CASCADE in v056 is not wrapped in a "
            "PL/pgSQL DO block. Without the guard it drops dependent "
            "policies on every run — see #1247 / #1227.\n"
            f"Block was:\n{blk[:400]}..."
        )
        # The guard must check the function's return type before dropping.
        assert (
            "typname" in blk.lower() or "pg_type" in blk.lower()
        ), (
            "DROP FUNCTION ... CASCADE guard must check the existing "
            "function's return type via pg_type / typname so it only "
            "fires when the signature truly differs. #1247 guard.\n"
            f"Block was:\n{blk[:400]}..."
        )


def test_v051_part2_comment_cross_references_v056(v051_source: str) -> None:
    """v051's Part 2 comment should point out the overlap with v056 so a
    reader landing in v051 first sees the same dedup context. Both
    migrations need the pointer because they're often read independently."""
    assert "#1247" in v051_source, (
        "v051 should reference #1247 in comments to flag the known "
        "overlap with v056 for anyone reading v051 in isolation."
    )
    assert "v056" in v051_source, (
        "v051 should mention v056 so a reader lands on the full picture."
    )


def test_v056_part1_creates_use_idempotency_guards(v056_source: str) -> None:
    """Every CREATE in v056 Part 1 (role, schema, table, index, function,
    grant) must carry an idempotency guard. This is what lets v051 +
    v056 converge on the same end state regardless of which ran first
    or whether both ran on the same DB."""
    # Slice out Part 1 (from function start through the Part 2 marker).
    import re
    part1_match = re.search(
        r"# Part 1:.*?(?=# ={5,}|# Part 2)",
        v056_source,
        re.DOTALL,
    )
    assert part1_match, "Could not locate Part 1 boundaries in v056."
    part1 = part1_match.group(0)

    # Every CREATE TABLE / SCHEMA / INDEX must use IF NOT EXISTS.
    for creation_kind in ("CREATE TABLE", "CREATE SCHEMA", "CREATE INDEX"):
        # Permissive: "CREATE TABLE ... IF NOT EXISTS" on same SQL line
        # or continuation — so just check that every CREATE <kind> is
        # paired with an IF NOT EXISTS somewhere on the same logical
        # statement (within 80 chars).
        for match in re.finditer(creation_kind, part1):
            snippet = part1[match.start():match.start() + 160]
            assert "IF NOT EXISTS" in snippet, (
                f"{creation_kind} in v056 Part 1 is missing IF NOT EXISTS. "
                f"Context:\n{snippet}"
            )

    # Every CREATE FUNCTION / CREATE ROLE in Part 1 must be inside a
    # DO block (guarded) or use CREATE OR REPLACE.
    # Walk statement by statement.
    for statement_kind in ("CREATE FUNCTION", "CREATE ROLE"):
        for match in re.finditer(statement_kind, part1):
            # Look backwards up to ~300 chars for either OR REPLACE on the
            # same statement OR a DO $$ wrapper.
            window = part1[max(0, match.start() - 300):match.start() + 80]
            has_or_replace = "OR REPLACE" in window
            has_do_block = "DO $" in window
            assert has_or_replace or has_do_block, (
                f"{statement_kind} in v056 Part 1 is missing an "
                "idempotency guard (neither CREATE OR REPLACE nor a "
                "DO $$ wrapper). Without a guard, re-running the chain "
                "on a DB where v051 already ran will fail or drift.\n"
                f"Window:\n{window}"
            )
