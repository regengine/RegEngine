#!/usr/bin/env python3
"""Guard against api.regengine.co (no DNS) in user-visible code samples.

Scans frontend/src/ and the Python SDK in regengine/ for any string containing
the bad host. The SDK is scanned because its default base URL is what a
developer's first call uses. Allowlists files that are known to contain the host
today; the parallel cleanup PR `marketing/fix-api-host` is removing them, after
which entries should be pruned.

Exit 1 (with file:line) on any non-allowlisted match. Stdlib only.
"""

from __future__ import annotations

import sys
from pathlib import Path

BAD_HOST = "api.regengine.co"

# TODO: remove allowlist entries after marketing/fix-api-host PR merges
ALLOWLIST = {
    "frontend/src/app/docs/page.tsx",
    "frontend/src/app/docs/connectors/inflow-lab/page.tsx",
    "frontend/src/app/developer/portal/codegen/page.tsx",
}

# Directory (relative to the repo root) -> file extensions scanned inside it.
SCAN_ROOTS = {
    "frontend/src": {".ts", ".tsx", ".js", ".jsx", ".mdx", ".md"},
    "regengine": {".py", ".md"},
}


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    violations: list[str] = []
    for root_rel, exts in SCAN_ROOTS.items():
        root = repo_root / root_rel
        if not root.is_dir():
            print(f"error: {root} not found", file=sys.stderr)
            return 1

        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in exts:
                continue
            rel = path.relative_to(repo_root).as_posix()
            if rel in ALLOWLIST:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if BAD_HOST in line:
                    violations.append(f"{rel}:{lineno}: contains '{BAD_HOST}'")

    if violations:
        print("Found references to non-resolving host 'api.regengine.co':", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nUse the canonical host (https://regengine.co) or add an allowlist "
            "entry in scripts/check_api_host_strings.py if intentional.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
