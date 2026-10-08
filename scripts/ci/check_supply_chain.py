#!/usr/bin/env python3
"""Supply-chain gate for RegEngine (Pattern 6: unpinned supply chain).

One shared mechanism that scans every place a third-party artifact can
enter the build: GitHub Actions refs, shell installs, downloads, and
container images. Anything not pinned to an exact version or digest,
or downloaded without checksum verification, fails the run unless it
is recorded in scripts/ci/supply_chain_baseline.json with a reason.

Rules:
  action-pin            every `uses:` ref pins a full 40-char commit SHA
  pipe-shell            no curl/wget piped into sh or bash
  latest-url            no floating `latest` URLs or @latest installs
  image-digest          every container image pins a sha256 digest
  download-checksum     archive downloads need checksum evidence in file
  pip-pin               pip installs pin == versions or use locked files
  pip-break-system      no --break-system-packages bypass
  npm-unlocked          no bare `npm install` (use `npm ci` or pinned -g)
  lockfile-present      requirements.lock and package-lock.json exist

Usage:
  python3 scripts/ci/check_supply_chain.py [--root DIR] [--baseline FILE]

Exit codes: 0 clean, 1 violations or stale baseline, 2 usage error.
Only the standard library is used so the gate runs on a bare runner.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SHA40 = re.compile(r"^[0-9a-f]{40}$")
USES_RE = re.compile(r"uses:\s*[\"']?([A-Za-z0-9_.\-/]+)(?:@([^\"'#\s]+))?[\"']?")
PIPE_SHELL_RE = re.compile(r"\|\s*(sudo\s+)?(sh|bash)\b")
LATEST_URL_RE = re.compile(r"https?://\S*latest\S*|@latest\b", re.IGNORECASE)
FROM_RE = re.compile(r"^\s*FROM\s+(\S+)")
IMAGE_RE = re.compile(r"^\s*(?:-\s*)?image:\s*[\"']?(\S+?)[\"']?\s*$")
ARCHIVE_FETCH_RE = re.compile(r"\b(curl|wget)\b.*https?://\S+\.(tar\.gz|tgz|tar\.bz2|zip|whl)\b")
CHECKSUM_EVIDENCE_RE = re.compile(r"sha256sum|shasum\s+-c|_SHA256|cosign\s+verify")
PIP_INSTALL_RE = re.compile(r"(?:^|[\s;|&])(?:python3?\s+-m\s+)?pip3?\s+install\b(.*)$")
BREAK_SYSTEM_RE = re.compile(r"--break-system-packages")
NPM_INSTALL_RE = re.compile(r"\bnpm\s+(install|i)\b(?!\s+ci\b)(.*)$")
NPM_EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

WORKFLOW_GLOBS = ("*.yml", "*.yaml")
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".metacode-fleet",
    "output",
    "artifacts",
}


@dataclass
class Violation:
    rule: str
    file: str
    line: int
    text: str


def repo_files(root: Path, *globs: str) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if globs and not any(path.match(g) for g in globs):
            continue
        found.append(path)
    return found


def workflow_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for base in (root / ".github" / "workflows", root / ".github" / "actions"):
        if not base.is_dir():
            continue
        for ext in WORKFLOW_GLOBS:
            files.extend(sorted(base.rglob(ext)))
    return files


def dockerfiles(root: Path) -> list[Path]:
    return [p for p in repo_files(root, "Dockerfile", "Dockerfile.*", "*.Dockerfile") if p.name != ".metacode_pr.md"]


def compose_files(root: Path) -> list[Path]:
    return repo_files(root, "docker-compose*.y*ml", "compose*.y*ml")


def shell_files(root: Path) -> list[Path]:
    scripts = root / "scripts"
    if not scripts.is_dir():
        return []
    return [p for p in repo_files(scripts, "*.sh") if p.is_file()]


def infra_manifests(root: Path) -> list[Path]:
    infra = root / "infra"
    if not infra.is_dir():
        return []
    return [p for p in repo_files(infra, "*.y*ml") if p.is_file()]


def strip_comment(line: str) -> str:
    """Split off a trailing `#` comment. Good enough for scan purposes."""
    for i, ch in enumerate(line):
        if ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def check_action_pin(path: Path, rel: str) -> list[Violation]:
    out: list[Violation] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        match = USES_RE.search(line)
        if not match:
            continue
        target, ref = match.group(1), match.group(2)
        if ref is None:
            # Local reusable workflow or action, versioned with the repo.
            if target.startswith(("./", "/")) or target.endswith((".yml", ".yaml")):
                continue
            out.append(Violation("action-pin", rel, lineno, line.strip()))
        elif not SHA40.match(ref):
            out.append(Violation("action-pin", rel, lineno, line.strip()))
    return out


def check_pipe_shell(path: Path, rel: str) -> list[Violation]:
    out: list[Violation] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        code = strip_comment(line)
        if PIPE_SHELL_RE.search(code):
            out.append(Violation("pipe-shell", rel, lineno, line.strip()))
    return out


def check_latest_url(path: Path, rel: str) -> list[Violation]:
    out: list[Violation] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        code = strip_comment(line)
        match = LATEST_URL_RE.search(code)
        if match:
            out.append(Violation("latest-url", rel, lineno, line.strip()))
    return out


def check_image_digest_dockerfile(path: Path, rel: str) -> list[Violation]:
    out: list[Violation] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        match = FROM_RE.match(strip_comment(line))
        if match and "@sha256:" not in match.group(1):
            out.append(Violation("image-digest", rel, lineno, line.strip()))
    return out


def check_image_digest_yaml(path: Path, rel: str) -> list[Violation]:
    out: list[Violation] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        match = IMAGE_RE.match(strip_comment(line))
        if match and "@sha256:" not in match.group(1):
            out.append(Violation("image-digest", rel, lineno, line.strip()))
    return out


def check_download_checksum(path: Path, rel: str) -> list[Violation]:
    text = path.read_text()
    if not CHECKSUM_EVIDENCE_RE.search(text):
        out: list[Violation] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ARCHIVE_FETCH_RE.search(strip_comment(line)):
                out.append(Violation("download-checksum", rel, lineno, line.strip()))
        return out
    return []


def check_pip(path: Path, rel: str) -> list[Violation]:
    out: list[Violation] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        code = strip_comment(line).strip()
        if not code or code.startswith(("echo ", "printf ", "#")):
            continue
        if BREAK_SYSTEM_RE.search(code):
            out.append(Violation("pip-break-system", rel, lineno, line.strip()))
        match = PIP_INSTALL_RE.search(code)
        if not match:
            continue
        rest = match.group(1)
        tokens = rest.split()
        if "-r" in tokens or "--requirement" in tokens:
            if "--require-hashes" not in tokens:
                out.append(Violation("pip-pin", rel, lineno, line.strip()))
            continue
        pkgs = [
            t.strip("\"'") for t in tokens if not t.startswith("-") and not t.startswith(("./", "../", "/", "http"))
        ]
        pkgs = [t for t in pkgs if t not in ("pip",)]
        if pkgs and any("==" not in p for p in pkgs):
            out.append(Violation("pip-pin", rel, lineno, line.strip()))
    return out


def _is_pinned_npm_package(token: str) -> bool:
    """Is this `npm install -g` token pinned to an exact version?

    A scoped name (`@scope/name`) carries a leading `@` that is part of
    the name, not a version pin, so the version is whatever follows the
    LAST `@` — and the name before it must be non-empty.
    """
    name, sep, version = token.rpartition("@")
    if not sep or not name:
        return False
    return bool(NPM_EXACT_VERSION_RE.match(version))


def check_npm(path: Path, rel: str) -> list[Violation]:
    out: list[Violation] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        code = strip_comment(line).strip()
        if not code or code.startswith(("echo ", "printf ", "#")):
            continue
        match = NPM_INSTALL_RE.search(code)
        if not match:
            continue
        rest = match.group(2).strip()
        if rest.startswith("-g"):
            # Global tool install: every package must pin an exact version.
            pkgs = [t.strip("\"'") for t in rest.split() if not t.startswith("-")]
            if not pkgs or any(not _is_pinned_npm_package(p) for p in pkgs):
                out.append(Violation("npm-unlocked", rel, lineno, line.strip()))
            continue
        out.append(Violation("npm-unlocked", rel, lineno, line.strip()))
    return out


def check_lockfiles(root: Path) -> list[Violation]:
    out: list[Violation] = []
    for lock in ("requirements.lock", "frontend/package-lock.json"):
        if not (root / lock).is_file():
            out.append(Violation("lockfile-present", lock, 0, f"missing {lock}"))
    return out


def find_violations(root: Path) -> list[Violation]:
    found: list[Violation] = []
    found.extend(check_lockfiles(root))
    for path in workflow_files(root):
        rel = path.relative_to(root).as_posix()
        found.extend(check_action_pin(path, rel))
        found.extend(check_pipe_shell(path, rel))
        found.extend(check_latest_url(path, rel))
        found.extend(check_download_checksum(path, rel))
        found.extend(check_pip(path, rel))
        found.extend(check_npm(path, rel))
    for path in dockerfiles(root):
        rel = path.relative_to(root).as_posix()
        found.extend(check_image_digest_dockerfile(path, rel))
        found.extend(check_pipe_shell(path, rel))
    for path in compose_files(root) + infra_manifests(root):
        rel = path.relative_to(root).as_posix()
        found.extend(check_image_digest_yaml(path, rel))
    for path in shell_files(root):
        rel = path.relative_to(root).as_posix()
        found.extend(check_pipe_shell(path, rel))
        found.extend(check_latest_url(path, rel))
        found.extend(check_download_checksum(path, rel))
        found.extend(check_pip(path, rel))
        found.extend(check_npm(path, rel))
    return sorted(found, key=lambda v: (v.file, v.line, v.rule))


@dataclass
class BaselineEntry:
    rule: str
    file: str
    match: str
    reason: str


def load_baseline(path: Path) -> list[BaselineEntry]:
    data = json.loads(path.read_text())
    return [BaselineEntry(**e) for e in data.get("entries", [])]


def apply_baseline(
    violations: list[Violation], baseline: list[BaselineEntry]
) -> tuple[list[Violation], list[BaselineEntry]]:
    """Split violations into unbaselined failures and stale baseline entries."""
    remaining = list(violations)
    stale = list(baseline)
    for entry in baseline:
        matched = False
        for violation in violations:
            if violation.rule == entry.rule and violation.file == entry.file and entry.match in violation.text:
                matched = True
                if violation in remaining:
                    remaining.remove(violation)
        if matched and entry in stale:
            stale.remove(entry)
    return remaining, stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Supply-chain pinning gate.")
    parser.add_argument("--root", default=".", help="repo root to scan")
    parser.add_argument(
        "--baseline",
        default="scripts/ci/supply_chain_baseline.json",
        help="baseline file with accepted violations",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path
    if not root.is_dir():
        print(f"error: root not found: {root}", file=sys.stderr)
        return 2
    if not baseline_path.is_file():
        print(f"error: baseline not found: {baseline_path}", file=sys.stderr)
        return 2

    violations = find_violations(root)
    baseline = load_baseline(baseline_path)
    failures, stale = apply_baseline(violations, baseline)

    for entry in stale:
        print(f"::error::stale baseline entry (no longer found): {entry.rule} {entry.file} [{entry.match}]")
    for violation in failures:
        loc = f"{violation.file}:{violation.line}" if violation.line else violation.file
        print(f"::error::{loc} [{violation.rule}] {violation.text}")

    if stale or failures:
        print(
            f"supply-chain gate failed: {len(failures)} unpinned, "
            f"{len(stale)} stale baseline entries "
            f"({len(violations)} total findings, {len(baseline)} baselined)"
        )
        return 1
    print(f"supply-chain gate passed: {len(violations)} findings, all covered by baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
