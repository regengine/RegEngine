#!/usr/bin/env python3
"""Schema parity audit (WS-2c) — fresh-DB `alembic upgrade head` ≡ expected schema.

The migration-consolidation acceptance criterion is that one executable
migration system produces the whole schema. This tool makes that testable:

* ``snapshot`` dumps the schema (every user table's columns with their
  data types and nullability) of a database to a canonical JSON file —
  the checked-in contract lives at ``docs/schema/expected_schema.json``.
* ``check`` compares a live database against that file and exits non-zero
  on any missing table, missing/extra column, or type/nullability change.

Unlike the ORM drift gate (``alembic check``), this covers EVERY table —
including the raw-SQL-managed canonical FSMA tables that have no ORM
model — which is how ``verify_orm_db_type_alignment``'s type guarantees
extend to the whole schema without inventing ORM overlays for raw tables.

Workflow when a migration intentionally changes the schema: run

    DATABASE_URL=... python scripts/schema_parity_audit.py snapshot

against a freshly migrated database and commit the regenerated JSON in
the same PR as the migration. The CI step in backend-ci.yml
(repo-root-suite) fails if the migrated schema and the checked-in
contract disagree — so schema changes are always deliberate, reviewable
diffs rather than silent drift.

Usage:
    python scripts/schema_parity_audit.py snapshot [--out PATH]
    python scripts/schema_parity_audit.py check [--expected PATH]

DATABASE_URL must point at the database to audit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SNAPSHOT = REPO_ROOT / "docs" / "schema" / "expected_schema.json"

# Alembic's own bookkeeping table — version stamps differ per environment.
IGNORED_TABLES = {"alembic_version"}
# System / extension schemas are not part of the migration contract.
IGNORED_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast"}


def _connect(database_url: str):
    from sqlalchemy import create_engine

    return create_engine(database_url)


def dump_schema(database_url: str) -> dict:
    """Reflect every user table into a canonical, diff-stable dict."""
    from sqlalchemy import inspect

    engine = _connect(database_url)
    inspector = inspect(engine)
    result: dict[str, dict] = {}

    for schema in sorted(inspector.get_schema_names()):
        if schema in IGNORED_SCHEMAS:
            continue
        for table in sorted(inspector.get_table_names(schema=schema)):
            if table in IGNORED_TABLES:
                continue
            columns = {}
            for column in inspector.get_columns(table, schema=schema):
                columns[column["name"]] = {
                    "type": str(column["type"]).lower(),
                    "nullable": bool(column["nullable"]),
                }
            result[f"{schema}.{table}"] = {
                "columns": dict(sorted(columns.items())),
            }

    engine.dispose()
    return result


def cmd_snapshot(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL must be set", file=sys.stderr)
        return 2
    snapshot = dump_schema(database_url)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(snapshot)} tables to {out}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL must be set", file=sys.stderr)
        return 2
    expected_path = Path(args.expected)
    if not expected_path.exists():
        print(
            f"ERROR: expected-schema file not found: {expected_path}. "
            "Generate it with the `snapshot` subcommand.",
            file=sys.stderr,
        )
        return 2

    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    actual = dump_schema(database_url)

    problems: list[str] = []

    for table, spec in sorted(expected.items()):
        if table not in actual:
            problems.append(f"MISSING TABLE: {table} (in contract, not produced by migrations)")
            continue
        actual_columns = actual[table]["columns"]
        for name, col in sorted(spec["columns"].items()):
            live = actual_columns.get(name)
            if live is None:
                problems.append(f"MISSING COLUMN: {table}.{name}")
            elif live != col:
                problems.append(
                    f"COLUMN DRIFT: {table}.{name} expected {col}, got {live}"
                )
        for name in sorted(set(actual_columns) - set(spec["columns"])):
            problems.append(
                f"EXTRA COLUMN: {table}.{name} (migrations added it; regenerate the snapshot "
                "in this PR if intentional)"
            )

    for table in sorted(set(actual) - set(expected)):
        problems.append(
            f"EXTRA TABLE: {table} (migrations created it; regenerate the snapshot in this "
            "PR if intentional)"
        )

    if problems:
        print("Schema parity audit FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nIf these changes are intentional (a new migration), regenerate the "
            "contract in the same PR:\n"
            "  DATABASE_URL=<freshly migrated db> python scripts/schema_parity_audit.py snapshot",
            file=sys.stderr,
        )
        return 1

    print(f"Schema parity audit OK — {len(expected)} tables match the contract.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="write the expected-schema contract from a live DB")
    snap.add_argument("--out", default=str(DEFAULT_SNAPSHOT))
    snap.set_defaults(func=cmd_snapshot)

    check = sub.add_parser("check", help="compare a live DB against the contract")
    check.add_argument("--expected", default=str(DEFAULT_SNAPSHOT))
    check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
