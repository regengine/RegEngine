#!/usr/bin/env python3
"""
Script to remove duplicate MarketingHeader and MarketingFooter from page.tsx files.
The root layout already provides these components, so individual pages should not include them.
"""

import argparse
import difflib
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FRONTEND_DIR = REPO_ROOT / "frontend" / "src" / "app"


def resolve_frontend_dir(root=None):
    """Derive the frontend app directory from the repo root."""
    base = Path(root) if root else REPO_ROOT
    return base / "frontend" / "src" / "app"


def find_page_files(frontend_dir):
    """Find all page.tsx files, excluding layouts which should keep the headers."""
    page_files = list(Path(frontend_dir).rglob("page.tsx"))
    return [f for f in page_files if "layout.tsx" not in str(f)]


def fixed_content(content):
    """Return content with duplicate headers removed, without touching disk."""
    # Remove the import for MarketingHeader (with or without MarketingFooter)
    content = re.sub(
        r"import \{ MarketingHeader(, MarketingFooter)? \} from '@/components/layout/(marketing-header|marketing-footer)';\n?",
        "",
        content,
    )

    # Remove standalone MarketingFooter import if it exists
    content = re.sub(r"import \{ MarketingFooter \} from '@/components/layout/marketing-footer';\n?", "", content)

    # Remove <MarketingHeader /> with optional whitespace
    content = re.sub(r"\s*<MarketingHeader />\n?", "", content)

    # Remove <MarketingFooter /> with optional whitespace
    content = re.sub(r"\s*<MarketingFooter />\n?", "", content)

    return content


def preview_diff(file_path, original, updated):
    """Return a unified diff preview of a pending change."""
    return "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
    )


def remove_duplicate_headers(file_path, dry_run=False):
    """Remove MarketingHeader and MarketingFooter imports and JSX from a page.tsx file.

    With dry_run=True, report whether the file would change without writing.
    Returns True when the file changed (or would change in dry-run mode).
    """
    with open(file_path, "r") as f:
        content = f.read()

    updated = fixed_content(content)

    # Check if content changed
    if updated != content:
        if dry_run:
            return True
        with open(file_path, "w") as f:
            f.write(updated)
        return True
    return False


def run(frontend_dir, dry_run=False, assume_yes=False):
    """Plan and optionally apply header fixes. Returns the number of files changed."""
    frontend_dir = Path(frontend_dir)
    page_files = find_page_files(frontend_dir)

    planned = []
    for page_file in page_files:
        with open(page_file, "r") as f:
            content = f.read()
        updated = fixed_content(content)
        if updated != content:
            planned.append((page_file, content, updated))

    if dry_run:
        print(f"Dry run: {len(planned)} file(s) would be modified, {len(page_files)} checked.")
        for page_file, original, updated in planned:
            print(f"Would fix: {page_file}")
            print(preview_diff(page_file, original, updated))
        return len(planned)

    if not planned:
        print(f"\nModified 0 files\nTotal files checked: {len(page_files)}")
        return 0

    print(f"{len(planned)} file(s) would be modified:")
    for page_file, _original, _updated in planned:
        print(f"  {page_file}")

    if not assume_yes:
        answer = input("Apply these changes? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted: no files were modified.")
            return 0

    modified_count = 0
    for page_file, _original, updated in planned:
        with open(page_file, "w") as f:
            f.write(updated)
        try:
            label = page_file.relative_to(frontend_dir)
        except ValueError:
            label = page_file
        print(f"Fixed: {label}")
        modified_count += 1

    print(f"\nModified {modified_count} files")
    print(f"Total files checked: {len(page_files)}")
    return modified_count


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Remove duplicate MarketingHeader/MarketingFooter from page.tsx files."
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repo root to resolve frontend paths from (defaults to the git checkout root).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which files would change, with a diff, without writing anything.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Apply changes without asking for confirmation.",
    )
    args = parser.parse_args(argv)

    frontend_dir = resolve_frontend_dir(args.root)
    if not frontend_dir.is_dir():
        print(f"Frontend app directory not found: {frontend_dir}", file=sys.stderr)
        return 1

    run(frontend_dir, dry_run=args.dry_run, assume_yes=args.yes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
