#!/usr/bin/env python3
"""Guard: forbid imports of ``kernel.control`` from production code.

``kernel/control/`` (the codegen + RCE-prone vertical compiler stack) was
retired by the ``epic-g-retire-kernel`` epic — see
``project_kernel_audit_2026_04_17`` and PR #2205. The directory no longer
exists; this script prevents accidental re-introduction.

Scope: ``services/`` and ``server/`` only. Tests and other historical
references are not blocked. Failure exits non-zero and prints offending
lines.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("services", "server")
PATTERN = re.compile(
    r"^[ \t]*(from|import)[ \t]+kernel\.control(\.|[ \t]|$)",
)


def main() -> int:
    offenders: list[str] = []
    for sub in SCAN_DIRS:
        root = REPO_ROOT / sub
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if PATTERN.match(line):
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")

    if offenders:
        print(
            "ERROR: kernel.control was retired (epic-g-retire-kernel). Found forbidden imports:",
            file=sys.stderr,
        )
        for line in offenders:
            print(f"  {line}", file=sys.stderr)
        return 1

    print("OK: no kernel.control imports in services/ or server/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
