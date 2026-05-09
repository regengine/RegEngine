#!/usr/bin/env python3
"""Guard against api.regengine.co (no DNS) in user-visible frontend code samples.

Scans frontend/src/ for any string literal containing the bad host. Allowlists
files that are known to contain the host today; the parallel cleanup PR
`marketing/fix-api-host` is removing them, after which entries should be pruned.

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

SCAN_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mdx", ".md"}


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    src_root = repo_root / "frontend" / "src"
    if not src_root.is_dir():
        print(f"error: {src_root} not found", file=sys.stderr)
        return 1

    violations: list[str] = []
    for path in src_root.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_EXTS:
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
