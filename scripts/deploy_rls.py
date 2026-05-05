#!/usr/bin/env python3
"""Retired direct RLS SQL deploy helper.

Service-level Flyway SQL migrations were removed in #2004 because Railway
deploys the repository-level Alembic chain. Keep this wrapper so older runbook
commands fail with a clear path instead of looking for deleted files.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "Direct RLS SQL deployment is retired. Run `alembic upgrade head` "
        "from the repository root with DATABASE_URL set."
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
