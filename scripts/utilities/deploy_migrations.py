#!/usr/bin/env python3
"""Retired direct migration deploy helper.

The raw service migration files this script used to replay were removed in
#2004. Use Alembic for repository database migrations.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "Direct SQL migration deployment is retired. Run `alembic upgrade head` "
        "from the repository root with DATABASE_URL set."
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
