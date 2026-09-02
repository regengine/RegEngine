#!/usr/bin/env python3
"""Fail CI when documentation references a repo path that does not exist.

Filed as #2915 and #2926: root docs pointed readers at ``docs/CODEBASE_MAP.md``,
``services/graph/app/consumers/fsma_consumer.py`` and other paths that had been
deleted. Both issues asked for the same guard, so it is built once here.

The check is deliberately conservative. It only resolves a reference when the
text is unambiguously naming a repo path -- a backticked span or a markdown
link target that contains a ``/`` and ends in a known source extension (or a
trailing ``/`` for a directory). Prose, URLs, and shell snippets are ignored.

Some references name a path *in order to say it was removed*, which is correct
documentation rather than a dangling pointer. Those are declared in the
allowlist file with a reason, so the exemption is auditable rather than magic.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Extensions that make a slash-bearing token unambiguously a repo path.
_SOURCE_SUFFIXES = {
    ".py",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".sh",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".sql",
    ".txt",
    ".cfg",
    ".ini",
    ".env",
    ".lock",
    ".tf",
}

_BACKTICK = re.compile(r"`([^`\n]+)`")
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# ``server/main.py:1116-1140`` and ``file.py:22`` -> strip the line reference.
_LINE_REF = re.compile(r":\d+(?:-\d+)?$")

ALLOWLIST_NAME = ".docs-link-allowlist"

# The live documentation set this gate guards. Deliberately NOT all of ``docs/``:
# that tree carries a large backlog of stale references concentrated in
# ``docs/archive/``, where staleness is correct by design (an archived report
# describes the tree as it was on its date). Turning the gate on over that
# backlog would make it noise, and a noisy gate gets ignored. Widening the
# scope means triaging the backlog first -- see docs/CODEBASE_MAP.md section 8.
# ``docs/compliance`` joined the scope with #3007: the RTM is audit evidence,
# so a dangling artifact citation there is a compliance defect, not staleness.
DEFAULT_SCOPE = ("runbooks", "docs/CODEBASE_MAP.md", "docs/compliance")


def _candidate_paths(text: str) -> set[str]:
    """Extract tokens from one markdown file that name a repo path."""
    found: set[str] = set()
    for raw in [m.group(1) for m in _BACKTICK.finditer(text)] + [m.group(1) for m in _MD_LINK.finditer(text)]:
        token = raw.strip()
        # Drop anchors and line references before any other judgement.
        token = token.split("#", 1)[0]
        token = _LINE_REF.sub("", token)
        token = token.rstrip(".,;:)")
        if not token or " " in token:
            continue
        if token.startswith(("http://", "https://", "mailto:", "#", "<", "$")):
            continue
        # Absolute and home-relative paths name the filesystem, not the repo
        # (``/tmp/scratch.json``, ``~/.claude/CLAUDE.md``). URL schemes and API
        # route templates (``/api/v1/``, ``postgresql+psycopg://``) are not
        # files either, and globs/placeholders cannot be resolved at all.
        if token.startswith(("/", "~")):
            continue
        if "://" in token or "*" in token or "{" in token or "}" in token:
            continue
        # A repo path reference always carries a directory separator; this is
        # what keeps bare prose words and ``pip install foo`` out of the check.
        if "/" not in token:
            continue
        if token.startswith(("./", "../")):
            token = token.lstrip("./")
        suffix = Path(token).suffix
        if not token.endswith("/") and suffix not in _SOURCE_SUFFIXES:
            continue
        # Require a non-empty segment on both sides of a separator. A bare
        # ``chore/`` or ``feat/`` is a git branch prefix, and ``app/`` is a
        # generic directory word -- neither is a resolvable repo reference,
        # while ``kernel/control/`` and ``services/shared/auth.py`` are.
        segments = [seg for seg in token.split("/") if seg]
        if len(segments) < 2:
            continue
        found.add(token)
    return found


def _load_allowlist(repo_root: Path) -> set[tuple[str, str]]:
    """Return {(doc, path)} pairs exempted, e.g. paths named as removed."""
    allowed: set[tuple[str, str]] = set()
    for location in (repo_root / ALLOWLIST_NAME, repo_root / "docs" / ALLOWLIST_NAME):
        if not location.is_file():
            continue
        for line in location.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            doc, _, path = line.partition("::")
            if not path:
                continue
            allowed.add((doc.strip(), path.strip()))
    return allowed


def check(repo_root: Path, doc_paths: list[Path]) -> list[str]:
    allowed = _load_allowlist(repo_root)
    failures: list[str] = []
    for doc in sorted(doc_paths):
        rel_doc = doc.relative_to(repo_root).as_posix()
        try:
            text = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for token in sorted(_candidate_paths(text)):
            if (rel_doc, token) in allowed or ("*", token) in allowed:
                continue
            # Resolve against the repo root first, then against the doc's own
            # directory -- both are ordinary markdown conventions.
            if (repo_root / token).exists():
                continue
            if (doc.parent / token).exists():
                continue
            failures.append(f"{rel_doc}: references missing path `{token}`")
    return failures


def _discover(repo_root: Path, roots: list[str]) -> list[Path]:
    docs: list[Path] = []
    for entry in roots:
        target = repo_root / entry
        if target.is_file() and target.suffix == ".md":
            docs.append(target)
        elif target.is_dir():
            docs.extend(p for p in target.rglob("*.md") if "node_modules" not in p.parts)
    return docs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to scan (default: root *.md plus DEFAULT_SCOPE)",
    )
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    if args.paths:
        docs = _discover(repo_root, args.paths)
    else:
        docs = sorted(repo_root.glob("*.md"))
        docs += _discover(repo_root, list(DEFAULT_SCOPE))

    failures = check(repo_root, docs)
    if failures:
        print(f"Documentation link check FAILED ({len(failures)} dangling reference(s)):")
        for failure in failures:
            print(f"  {failure}")
        print(
            f"\nIf a path is named deliberately because it was removed, add it to "
            f"{ALLOWLIST_NAME} as `<doc>::<path>` with a comment saying why."
        )
        return 1
    print(f"Documentation link check passed ({len(docs)} file(s) scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
